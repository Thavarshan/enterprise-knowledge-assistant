"""Parse and execute bounded numeric analysis without dynamic code.

The tool accepts only count, sum, and average over a short explicit list of
finite numeric literals. It validates structured inputs and uses trusted
Python arithmetic; it never evaluates expressions or accesses external data.
"""

import math
import re
from collections.abc import Mapping
from typing import Annotated, Literal

from langsmith import traceable
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    ValidationError,
    field_validator,
)

AnalysisOperation = Literal["count", "sum", "average"]
BoundedNumber = Annotated[
    FiniteFloat,
    Field(ge=-1_000_000_000_000, le=1_000_000_000_000),
]
_NUMBER_PATTERN = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
_QUESTION_PATTERN = re.compile(
    rf"^\s*(?:please\s+)?(?:calculate|compute)\s+"
    rf"(?P<operation>count|sum|average)\s+of\s+"
    rf"(?P<values>{_NUMBER_PATTERN}"
    rf"(?:\s*,\s*{_NUMBER_PATTERN}){{0,999}})\s*[?.]?\s*$",
    re.IGNORECASE,
)


class AnalysisInputError(ValueError):
    """Report an invalid or unsupported numeric analysis request.

    Error messages are generic and do not contain user-supplied values.
    """


class AnalysisRequest(BaseModel):
    """Validate one arithmetic operation over bounded finite numbers.

    Attributes:
        operation: Supported count, sum, or average operation.
        field: Short display label associated with the supplied numbers.
        values: Up to one thousand finite values within the numeric bound.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: AnalysisOperation
    field: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z][A-Za-z0-9_. -]{0,79}$",
    )
    values: list[BoundedNumber] = Field(max_length=1000)

    @field_validator("values", mode="before")
    @classmethod
    def require_json_numbers(cls, values: object) -> object:
        """Reject strings, booleans, and non-list numeric inputs.

        Args:
            values: Raw value list supplied by a tool caller.

        Returns:
            Numeric list for finite and range validation by Pydantic.

        Raises:
            ValueError: Inputs are not a list of JSON numeric values.
        """
        if not isinstance(values, list) or any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            for value in values
        ):
            raise ValueError("values must be a list of JSON numbers")
        return values


class AnalysisResult(BaseModel):
    """Return a bounded arithmetic result and its input count.

    Attributes:
        operation: Operation applied to the input values.
        field: Display label copied from the validated request.
        value: Finite result of the arithmetic operation.
        input_count: Number of values consumed by the operation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: AnalysisOperation
    field: str
    value: FiniteFloat
    input_count: int = Field(ge=0, le=1000)


def parse_analysis_question(question: str) -> AnalysisRequest:
    """Parse only the documented calculate/compute numeric grammar.

    No Python expressions, operators beyond signed decimal literals, field
    references, or model-generated code are accepted.

    Args:
        question: User text selected for the analysis workflow.

    Returns:
        Validated operation and values for the Python analysis tool.

    Raises:
        AnalysisInputError: The text does not match the supported grammar.
    """
    match = _QUESTION_PATTERN.fullmatch(question)
    if match is None:
        raise AnalysisInputError("Unsupported analysis request.")
    try:
        values = [
            float(value.strip())
            for value in match.group("values").split(",")
        ]
        return AnalysisRequest(
            operation=match.group("operation").casefold(),
            field="values",
            values=values,
        )
    except (ValueError, OverflowError, ValidationError) as exc:
        raise AnalysisInputError(
            "Analysis values are outside the limit."
        ) from exc


class PythonAnalysisTool:
    """Execute bounded numeric operations after strict schema validation.

    The graph invokes this handler only after ToolRegistry checks the
    authenticated role. The implementation has no filesystem, network, or
    dynamic-code capabilities.
    """

    @traceable(
        name="python_analysis",
        run_type="tool",
        metadata={"tool_name": "python_analysis"},
    )
    async def run(self, arguments: Mapping[str, object]) -> AnalysisResult:
        """Calculate a count, sum, or average for validated numeric values.

        Args:
            arguments: Structured request fields checked by Pydantic.

        Returns:
            Result value and the count of input values.

        Raises:
            AnalysisInputError: Values cannot be parsed or averaged.
            ValidationError: The request has invalid or extra fields.
        """
        request = AnalysisRequest.model_validate(dict(arguments))
        if request.operation == "count":
            value = float(len(request.values))
        elif request.operation == "sum":
            value = math.fsum(request.values)
        else:
            if not request.values:
                raise AnalysisInputError(
                    "Average requires at least one numeric value."
                )
            value = math.fsum(request.values) / len(request.values)
        return AnalysisResult(
            operation=request.operation,
            field=request.field,
            value=value,
            input_count=len(request.values),
        )
