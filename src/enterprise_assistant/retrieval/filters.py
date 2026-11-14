"""Resolve safe, deterministic retrieval filters from a user question.

Relative dates use a rolling one-year window ending on the injected current
date. Filter parsing cannot widen authorization; role-derived access labels
remain supplied separately by the authenticated backend.
"""

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DocumentType = Literal[
    "access_policy",
    "architecture_note",
    "incident_report",
    "product_specification",
    "runbook",
]
_DEPARTMENT_TERMS = (
    ("payments-operations", r"payments?[ -]+operations"),
    ("platform-engineering", r"platform[ -]+engineering"),
    ("payments", r"payments?"),
    ("product", r"products?"),
    ("security", r"security"),
)


class SearchFilters(BaseModel):
    """Validate optional department, type, and inclusive date filters.

    Attributes:
        department: Optional exact department name.
        document_type: Optional supported source classification.
        date_from: Inclusive lower source-date boundary.
        date_to: Inclusive upper source-date boundary.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    department: str | None = Field(default=None, min_length=1, max_length=80)
    document_type: DocumentType | None = None
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> "SearchFilters":
        """Reject reversed inclusive date boundaries.

        Returns:
            The validated filter object.

        Raises:
            ValueError: The lower boundary occurs after the upper boundary.
        """
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from > self.date_to
        ):
            raise ValueError("date_from must not be after date_to")
        return self


def filters_for_question(
    question: str,
    *,
    today: date,
    department: str | None = None,
) -> SearchFilters:
    """Infer known department, source-type, and rolling-year constraints.

    Args:
        question: User question or original research objective.
        today: Injected current date for deterministic relative-date handling.
        department: Optional exact department supplied by trusted code. When
            absent, a known department named in the user request is used.

    Returns:
        Validated search filters. "Last year" means the rolling year from
        the same calendar date one year earlier through ``today`` inclusive.
    """
    normalized = question.casefold()
    resolved_department = department or _department_from_question(normalized)
    document_type = _document_type(normalized)
    if re.search(r"\b(?:last year|past year|last 12 months)\b", normalized):
        start = _previous_year(today)
        return SearchFilters(
            department=resolved_department,
            document_type=document_type,
            date_from=start,
            date_to=today,
        )
    return SearchFilters(
        department=resolved_department,
        document_type=document_type,
    )


def _previous_year(value: date) -> date:
    """Return the same date in the previous year, clamping leap day.

    Args:
        value: Current date supplied by the caller.

    Returns:
        Previous-year date, using February 28 for a non-leap year.
    """
    try:
        return value.replace(year=value.year - 1)
    except ValueError:
        return value.replace(year=value.year - 1, day=28)


def _document_type(question: str) -> DocumentType | None:
    """Map explicit source-type terms to the supported local vocabulary.

    Args:
        question: Lowercased user text.

    Returns:
        A known source type, or None when the question is not specific.
    """
    if re.search(r"\b(?:runbook|run books)\b", question):
        return "runbook"
    if re.search(r"\b(?:architecture|system design)\b", question):
        return "architecture_note"
    if re.search(r"\b(?:access policy|security policy)\b", question):
        return "access_policy"
    if re.search(r"\b(?:product specification|product spec)\b", question):
        return "product_specification"
    if re.search(r"\b(?:incident|incidents|outage|outages)\b", question):
        return "incident_report"
    return None


def _department_from_question(question: str) -> str | None:
    """Select a known exact department named in the question.

    Args:
        question: Lowercased untrusted request text.

    Returns:
        A matching supported department, or None for an unrestricted search.

    Security:
        Department selection can only narrow retrieval. The user text cannot
        alter the separately derived role access labels.
    """
    for department, pattern in _DEPARTMENT_TERMS:
        if re.search(rf"\b{pattern}\b", question):
            return department
    return None
