"""Run bounded recursive investigations over authorized retrieval results.

The executor lets the configured model decompose research questions into
search tasks. It recursively expands those tasks within validated budgets,
uses the trusted search callback for every leaf, and fuses findings by
complete document and chunk identity. Model-generated code is never run.
"""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from enterprise_assistant.domain.models import SearchResult
from enterprise_assistant.llm.contracts import ModelProvider
from enterprise_assistant.retrieval.hybrid import reciprocal_rank_fusion
from enterprise_assistant.rlm.contracts import (
    ExecutionBudget,
    SearchPlan,
    TaskDecomposition,
    interpret_search_plan,
)

type SearchFunction = Callable[
    [str, int], Awaitable[Sequence[SearchResult]]
]


@dataclass(frozen=True, slots=True)
class InvestigationFinding:
    """Associate one executed subtask with its retrieved source chunks.

    Attributes:
        task: Bounded task text proposed by the structured planner.
        results: Ranked evidence returned for this task.
    """

    task: str
    results: tuple[SearchResult, ...]


@dataclass(frozen=True, slots=True)
class InvestigationReport:
    """Summarize bounded searches and their attributed evidence.

    Attributes:
        results: Fused findings with stable source identities.
        findings: Per-subtask source attribution before cross-task fusion.
        search_calls: Retrieval calls started within the budget.
        decomposition_calls: Model decomposition calls attempted.
        max_depth_reached: Deepest recursive task level visited.
        failure_codes: Safe failure labels for incomplete investigations.
    """

    results: tuple[SearchResult, ...]
    findings: tuple[InvestigationFinding, ...]
    search_calls: int
    decomposition_calls: int
    max_depth_reached: int
    failure_codes: tuple[str, ...]


class BoundedResearchExecutor:
    """Interpret model-proposed search tasks under one shared budget.

    Attributes:
        model_provider: Provider that proposes structured subtasks.
        search: Trusted callback that enforces backend access policy.
        budget: Validated limits shared by all recursive branches.
    """

    def __init__(
        self,
        model_provider: ModelProvider,
        search: SearchFunction,
        budget: ExecutionBudget | None = None,
    ) -> None:
        """Store the model, authorized search callback, and execution bounds.

        Args:
            model_provider: Provider returning validated task decompositions.
            search: Callback receiving a query and maximum result count.
            budget: Optional validated limits for this investigation.
        """
        self.model_provider = model_provider
        self.search = search
        self.budget = budget or ExecutionBudget(
            max_depth=2,
            max_search_calls=4,
            max_documents=20,
            timeout_seconds=30,
        )
        self._deadline = 0.0
        self._search_calls = 0
        self._reserved_documents = 0
        self._decomposition_calls = 0
        self._max_depth_reached = 0
        self._failure_codes: list[str] = []

    async def execute(self, question: str) -> InvestigationReport:
        """Decompose, recursively search, and aggregate one investigation.

        Args:
            question: User question selected for the research workflow.

        Returns:
            Aggregated results and bounded-work status for the graph.

        Raises:
            ValueError: The question is empty after trimming.
            asyncio.CancelledError: The caller cancels the investigation.
        """
        objective = question.strip()
        if not objective:
            raise ValueError("research question must not be blank")
        loop = asyncio.get_running_loop()
        self._deadline = loop.time() + self.budget.timeout_seconds
        findings = await self._investigate(objective, depth=0)
        fused = reciprocal_rank_fusion(
            [finding.results for finding in findings]
        )
        results = tuple(fused[: self.budget.max_documents])
        return InvestigationReport(
            results=results,
            findings=tuple(findings),
            search_calls=self._search_calls,
            decomposition_calls=self._decomposition_calls,
            max_depth_reached=self._max_depth_reached,
            failure_codes=tuple(dict.fromkeys(self._failure_codes)),
        )

    async def _investigate(
        self,
        objective: str,
        *,
        depth: int,
    ) -> list[InvestigationFinding]:
        """Expand an objective or search it when it reaches a leaf.

        Args:
            objective: Current task proposed by the structured planner.
            depth: Current level, where the root is level zero.

        Returns:
            Subtask findings retaining their own source attribution.
        """
        self._max_depth_reached = max(self._max_depth_reached, depth)
        if depth >= self.budget.max_depth:
            return [
                InvestigationFinding(
                    task=objective,
                    results=tuple(await self._search_leaf(objective)),
                )
            ]

        try:
            remaining = self._remaining_seconds()
            if remaining <= 0:
                raise TimeoutError
            self._decomposition_calls += 1
            async with asyncio.timeout(remaining):
                decomposition = await self.model_provider.decompose_question(
                    objective
                )
            queries = self._validated_queries(decomposition)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            self._failure_codes.append("decomposition_timeout")
            return [
                InvestigationFinding(
                    task=objective,
                    results=tuple(await self._search_leaf(objective)),
                )
            ]
        except Exception:
            self._failure_codes.append("decomposition_failed")
            return [
                InvestigationFinding(
                    task=objective,
                    results=tuple(await self._search_leaf(objective)),
                )
            ]

        if len(queries) == 1:
            return [
                InvestigationFinding(
                    task=queries[0],
                    results=tuple(await self._search_leaf(queries[0])),
                )
            ]

        children = await asyncio.gather(
            *(
                self._investigate(query, depth=depth + 1)
                for query in queries
            ),
            return_exceptions=True,
        )
        findings: list[InvestigationFinding] = []
        for child in children:
            if isinstance(
                child,
                (asyncio.CancelledError, KeyboardInterrupt, SystemExit),
            ):
                raise child
            if isinstance(child, BaseException):
                self._failure_codes.append("subtask_failed")
                continue
            findings.extend(child)
        return findings

    def _validated_queries(
        self,
        decomposition: TaskDecomposition,
    ) -> tuple[str, ...]:
        """Convert a validated decomposition into bounded search strings.

        Args:
            decomposition: Structured output already validated by Pydantic.

        Returns:
            Search strings limited to the configured call budget.
        """
        plan = SearchPlan(
            queries=decomposition.subtasks,
            max_depth=self.budget.max_depth,
        )
        return interpret_search_plan(plan, self.budget)

    async def _search_leaf(self, query: str) -> list[SearchResult]:
        """Run one authorized retrieval call within count, size, and time caps.

        Args:
            query: Validated subtask text used by the trusted callback.

        Returns:
            Results from this query, or an empty list after a safe failure.
        """
        if self._remaining_seconds() <= 0:
            self._failure_codes.append("research_timeout")
            return []
        if self._search_calls >= self.budget.max_search_calls:
            self._failure_codes.append("search_call_budget_exhausted")
            return []
        remaining_documents = (
            self.budget.max_documents - self._reserved_documents
        )
        if remaining_documents <= 0:
            self._failure_codes.append("document_budget_exhausted")
            return []

        result_limit = min(5, remaining_documents)
        self._search_calls += 1
        self._reserved_documents += result_limit
        try:
            async with asyncio.timeout(self._remaining_seconds()):
                results = list(await self.search(query, result_limit))
        except asyncio.CancelledError:
            self._reserved_documents -= result_limit
            raise
        except TimeoutError:
            self._reserved_documents -= result_limit
            self._failure_codes.append("search_timeout")
            return []
        except Exception:
            self._reserved_documents -= result_limit
            self._failure_codes.append("search_failed")
            return []

        bounded_results = results[:result_limit]
        self._reserved_documents -= result_limit - len(bounded_results)
        return bounded_results

    def _remaining_seconds(self) -> float:
        """Return positive time remaining before the shared deadline.

        Returns:
            Remaining wall-clock seconds, clamped to zero.
        """
        return max(0.0, self._deadline - asyncio.get_running_loop().time())
