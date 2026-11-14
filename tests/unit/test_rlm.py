"""Verify recursive investigation, attribution, and shared execution budgets.

Tests use synthetic documents and deterministic providers to exercise the
same recursive executor used by the graph without external services.
"""

import asyncio
from collections.abc import Sequence
from pathlib import Path

import pytest

from enterprise_assistant.domain.models import SearchResult
from enterprise_assistant.llm.providers import MockModelProvider
from enterprise_assistant.retrieval.in_memory import InMemoryRetriever
from enterprise_assistant.rlm.contracts import (
    ExecutionBudget,
    TaskDecomposition,
)
from enterprise_assistant.rlm.executor import BoundedResearchExecutor


@pytest.mark.asyncio
async def test_incident_investigation_executes_multiple_attributed_subtasks(
) -> None:
    """Verify incident research performs and fuses multiple searches.

    The deterministic provider decomposes the question into symptoms,
    causes, and mitigations. Every search uses viewer-authorized fixture
    retrieval, and findings retain task-to-source attribution.
    """
    retriever = InMemoryRetriever.from_json(
        Path("data/samples/incident_corpus.json")
    )
    queries: list[str] = []

    async def search(query: str, limit: int) -> Sequence[SearchResult]:
        """Search the synthetic corpus under the viewer's trusted scope.

        Args:
            query: One structured incident subtask.
            limit: Remaining result limit from the executor budget.

        Returns:
            Ranked synthetic chunks accessible to a viewer.
        """
        queries.append(query)
        return await retriever.search(
            query,
            allowed_access_levels=frozenset({"viewer"}),
            limit=limit,
        )

    report = await BoundedResearchExecutor(
        MockModelProvider(),
        search,
    ).execute(
        "Investigate payment incidents and compare symptoms, causes, "
        "and mitigations."
    )

    assert report.search_calls == 3
    assert report.decomposition_calls == 4
    assert report.max_depth_reached == 1
    assert len(queries) == 3
    assert len(report.findings) == 3
    assert report.results
    assert all(finding.results for finding in report.findings)
    assert all(
        result.chunk.metadata.access_level == "viewer"
        for result in report.results
    )
    assert all(
        result.chunk.metadata.document_id
        and result.chunk.metadata.chunk_id
        for finding in report.findings
        for result in finding.results
    )


class NestedProvider:
    """Return controlled nested tasks for executor tests.

    The provider creates one recursively nested branch.
    """

    async def decompose_question(
        self,
        question: str,
    ) -> TaskDecomposition:
        """Split one child again and leave other branches as single tasks.

        Args:
            question: Current task at this recursion level.

        Returns:
            A deterministic decomposition suitable for unit tests.
        """
        if question == "root":
            subtasks = ["branch-a", "branch-b"]
        elif question == "branch-a":
            subtasks = ["leaf-a1", "leaf-a2"]
        else:
            subtasks = [question]
        return TaskDecomposition(objective=question, subtasks=subtasks)


@pytest.mark.asyncio
async def test_executor_recurses_to_configured_depth() -> None:
    """Verify nested decomposition and search stop at the depth budget.

    The root creates two branches and one branch is decomposed again. The
    executor searches three leaves at depth two without executing code.
    """
    queries: list[str] = []

    async def search(query: str, limit: int) -> Sequence[SearchResult]:
        """Record leaf searches and return no fixture evidence.

        Args:
            query: Leaf task text.
            limit: Bounded maximum number of source chunks.

        Returns:
            An empty source list for this planning-only test.
        """
        del limit
        queries.append(query)
        return []

    report = await BoundedResearchExecutor(
        NestedProvider(),
        search,
        ExecutionBudget(
            max_depth=2,
            max_search_calls=4,
            max_documents=4,
            timeout_seconds=5,
        ),
    ).execute("root")

    assert report.max_depth_reached == 2
    assert report.decomposition_calls == 3
    assert report.search_calls == 3
    assert set(queries) == {"leaf-a1", "leaf-a2", "branch-b"}


@pytest.mark.asyncio
async def test_executor_retains_partial_results_when_a_branch_fails() -> None:
    """Verify one failed branch does not discard completed siblings.

    The executor caps search attempts at two while the model proposes three
    tasks, and records a safe failure code instead of exception details.
    """

    class FailingProvider:
        """Produce leaf tasks for budget and failure checks.

        One branch fails while a sibling completes safely.
        """

        async def decompose_question(
            self,
            question: str,
        ) -> TaskDecomposition:
            """Return three distinct search tasks.

            Args:
                question: Current investigation objective.

            Returns:
                Three bounded tasks that will exercise shared call limits.
            """
            if question == "root":
                subtasks = ["failed task", "completed task", "extra task"]
            else:
                subtasks = [question]
            return TaskDecomposition(objective=question, subtasks=subtasks)

    search_calls: list[str] = []
    retriever = InMemoryRetriever.from_json(
        Path("data/samples/incident_corpus.json")
    )

    async def search(query: str, limit: int) -> Sequence[SearchResult]:
        """Fail one branch and leave another available for aggregation.

        Args:
            query: Leaf query from the validated decomposition.
            limit: Remaining document allowance.

        Returns:
                Authorized synthetic incident results on success.

        Raises:
            RuntimeError: The synthetic failed task exercises partial errors.
        """
        search_calls.append(query)
        if query == "failed task":
            raise RuntimeError("synthetic failure detail")
        return await retriever.search(
            "INC-2026-057",
            allowed_access_levels=frozenset({"viewer"}),
            limit=limit,
        )

    report = await BoundedResearchExecutor(
        FailingProvider(),
        search,
        ExecutionBudget(
            max_depth=1,
            max_search_calls=2,
            max_documents=2,
            timeout_seconds=5,
        ),
    ).execute("root")

    assert len(search_calls) == 2
    assert report.search_calls == 2
    assert report.results
    assert len(report.findings) == 2
    assert sum(bool(finding.results) for finding in report.findings) == 1
    assert "search_failed" in report.failure_codes
    assert "synthetic failure detail" not in str(report.failure_codes)


@pytest.mark.asyncio
async def test_executor_times_out_a_slow_search_within_wall_clock_budget(
) -> None:
    """Verify the total investigation deadline cancels a slow leaf search.

    The executor records a safe timeout code and returns a partial report
    instead of waiting for the retrieval callback to finish.
    """
    search_started = False

    async def slow_search(query: str, limit: int) -> Sequence[SearchResult]:
        """Wait beyond the small wall-clock budget.

        Args:
            query: Leaf query text, unused by this timeout test.
            limit: Result allowance, unused by this timeout test.

        Returns:
            No evidence; the callback should be cancelled before returning.
        """
        nonlocal search_started
        del query, limit
        search_started = True
        await asyncio.sleep(1.1)
        return []

    report = await BoundedResearchExecutor(
        MockModelProvider(),
        slow_search,
        ExecutionBudget(
            max_depth=0,
            max_search_calls=1,
            max_documents=1,
            timeout_seconds=1,
        ),
    ).execute("leaf task")

    assert search_started
    assert report.search_calls == 1
    assert "search_timeout" in report.failure_codes
