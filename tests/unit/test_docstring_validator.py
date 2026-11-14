"""Verify the AST validator accepts complete docs and finds coverage gaps.

Tests feed source snippets directly to the standard-library parser. This
isolates rule behavior from repository coverage and avoids filesystem fixtures
for the ordinary missing-docstring and single-line cases.
"""

import textwrap

from scripts.check_docstrings import validate_source


def test_validator_accepts_multiline_nested_docstrings() -> None:
    """Accept a module, class, method, and nested function with docs.

    The valid sample exercises recursive AST traversal across definitions.
    """
    source = textwrap.dedent(
        '''
        """Module contract.

        Additional module context.
        """
        class Example:
            """Describe the example type.

            Additional class context.
            """
            def method(self) -> None:
                """Describe the method.

                Additional method context.
                """
                def nested() -> None:
                    """Describe the nested function.

                    Additional nested context.
                    """
                    return None
        '''
    )

    assert validate_source(source, "sample.py") == []


def test_validator_reports_missing_and_one_line_docstrings() -> None:
    """Report module and function omissions plus one-line source literals.

    Diagnostics must include a stable rule code and the offending line.
    """
    source = (
        "def missing():\n"
        "    return None\n"
        "\n"
        "def one_line():\n"
        "    \"\"\"Short summary.\"\"\"\n"
        "    return None\n"
    )

    violations = validate_source(source, "sample.py")

    assert [violation.code for violation in violations] == [
        "DOC001",
        "DOC003",
        "DOC004",
    ]
    assert [violation.line for violation in violations] == [1, 1, 5]


def test_validator_reports_syntax_errors_with_source_location() -> None:
    """Turn parse failures into diagnostics rather than crashing.

    The checker should report the parser line and preserve the filename.
    """
    violations = validate_source("def broken(:\n    pass\n", "broken.py")

    assert len(violations) == 1
    assert violations[0].code == "DOC005"
    assert violations[0].path == "broken.py"
    assert violations[0].line == 1
