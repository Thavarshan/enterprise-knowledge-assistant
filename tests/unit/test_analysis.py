"""Verify strict numeric parsing and the functional Python analysis tool.

The tests cover supported arithmetic and reject dynamic Python text,
unbounded values, non-finite numbers, and extra tool arguments.
"""

import pytest
from pydantic import ValidationError

from enterprise_assistant.tools.analysis import (
    AnalysisInputError,
    AnalysisRequest,
    PythonAnalysisTool,
    parse_analysis_question,
)


@pytest.mark.asyncio
async def test_analysis_tool_calculates_average_from_explicit_numbers() -> None:
    """Verify the tool computes a bounded average without code evaluation.

    The parser accepts only comma-separated decimal literals in its
    documented command format.
    """
    request = parse_analysis_question(
        "Please calculate average of 10, 20, 30."
    )
    result = await PythonAnalysisTool().run(request.model_dump())

    assert result.operation == "average"
    assert result.field == "values"
    assert result.input_count == 3
    assert result.value == pytest.approx(20)


@pytest.mark.asyncio
async def test_analysis_tool_supports_sum_and_count() -> None:
    """Verify the supported arithmetic operations return numeric results.

    Both operations use the exact values validated by the parser.
    """
    tool = PythonAnalysisTool()
    values = [2.5, 3.5, 4.0]
    summed = await tool.run(
        {"operation": "sum", "field": "values", "values": values}
    )
    counted = await tool.run(
        {"operation": "count", "field": "values", "values": values}
    )

    assert summed.value == pytest.approx(10)
    assert counted.value == 3


def test_analysis_parser_rejects_expressions_and_unsupported_numbers() -> None:
    """Verify inputs cannot contain executable or unsupported expressions.

    The accepted grammar contains literal decimal values only, with no
    Python operators, calls, exponents, or field lookup.
    """
    with pytest.raises(AnalysisInputError):
        parse_analysis_question(
            "calculate sum of __import__('os').system('whoami')"
        )
    with pytest.raises(AnalysisInputError):
        parse_analysis_question("calculate average of 1e9")
    with pytest.raises(AnalysisInputError):
        parse_analysis_question("calculate average of 1, 1e309")


def test_analysis_schema_rejects_nonfinite_values_and_extra_fields() -> None:
    """Verify Pydantic rejects values outside the strict tool schema.

    NaN, infinity, oversized magnitudes, and unknown properties are not
    accepted at the executable tool boundary.
    """
    base = {"operation": "sum", "field": "values", "values": [1]}
    for value in (float("nan"), float("inf"), 1_000_000_000_001):
        with pytest.raises(ValidationError):
            AnalysisRequest.model_validate(
                {**base, "values": [value]}
            )
    with pytest.raises(ValidationError):
        AnalysisRequest.model_validate({**base, "expression": "1 + 1"})
    for value in ("1", True):
        with pytest.raises(ValidationError):
            AnalysisRequest.model_validate({**base, "values": [value]})


@pytest.mark.asyncio
async def test_analysis_average_rejects_empty_values() -> None:
    """Verify average never divides an empty list.

    Direct tool callers receive a safe domain error even when they bypass
    the chat-question parser.
    """
    with pytest.raises(AnalysisInputError):
        await PythonAnalysisTool().run(
            {"operation": "average", "field": "values", "values": []}
        )
