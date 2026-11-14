"""Validate first-party Python docstring coverage with the standard library.

The checker scans source, application, script, and test packages with AST
source locations. It reports missing module, class, and function docstrings
and rejects definitions whose docstring occupies only one source line. Ruff
handles Google-style layout and argument documentation separately.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

type DocumentableNode = (
    ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
)


@dataclass(frozen=True)
class Violation:
    """Describe one documentation rule violation.

    Attributes:
        path: Source path displayed to the developer.
        line: One-based source line associated with the violation.
        code: Stable validator rule identifier.
        message: Short action-oriented explanation.
    """

    path: str
    line: int
    code: str
    message: str


class DocstringValidator(ast.NodeVisitor):
    """Visit Python syntax and enforce required docstring coverage.

    The visitor checks every class and synchronous or asynchronous function,
    including private helpers and nested definitions. Module docstrings must
    be the first statement. Source positions distinguish a one-line literal
    from a multiline docstring without inspecting textual quote patterns.
    """

    def __init__(self, path: str) -> None:
        """Create a visitor that reports issues against one source path.

        Args:
            path: Relative or absolute filename used in diagnostics.
        """
        self.path = path
        self.violations: list[Violation] = []

    def visit_Module(self, node: ast.Module) -> None:
        """Check the module header, then visit nested definitions.

        Args:
            node: Parsed module syntax tree.
        """
        self._check_docstring(node, "DOC001", "module")
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Check a class docstring and recursively visit its members.

        Args:
            node: Class definition to inspect.
        """
        self._check_docstring(node, "DOC002", "class")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Check a function or method docstring and visit nested functions.

        Args:
            node: Synchronous function definition to inspect.
        """
        self._check_docstring(node, "DOC003", "function")
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Check a coroutine docstring and visit nested definitions.

        Args:
            node: Asynchronous function definition to inspect.
        """
        self._check_docstring(node, "DOC003", "function")
        self.generic_visit(node)

    def _check_docstring(
        self,
        node: DocumentableNode,
        missing_code: str,
        description: str,
    ) -> None:
        """Report a missing or single-source-line docstring.

        Args:
            node: Module, class, or function to inspect.
            missing_code: Rule identifier for a missing docstring.
            description: Human-readable node kind for diagnostics.
        """
        if not node.body:
            return
        first = node.body[0]
        is_docstring = (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        )
        if not is_docstring:
            line = 1 if isinstance(node, ast.Module) else node.lineno
            self.violations.append(
                Violation(
                    self.path,
                    line,
                    missing_code,
                    f"missing {description} docstring",
                )
            )
            return

        if first.lineno == first.end_lineno:
            self.violations.append(
                Violation(
                    self.path,
                    first.lineno,
                    "DOC004",
                    f"{description} docstring must span multiple source lines",
                )
            )


def validate_source(source: str, path: str) -> list[Violation]:
    """Validate one Python source string.

    Args:
        source: Complete Python source contents.
        path: Display path included in each returned violation.

    Returns:
        Violations in source traversal order.

    Notes:
        Syntax errors are returned as DOC005 instead of escaping the checker.
    """
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as error:
        return [
            Violation(
                path,
                error.lineno or 1,
                "DOC005",
                f"Python syntax error: {error.msg}",
            )
        ]
    validator = DocstringValidator(path)
    validator.visit(tree)
    return validator.violations


def python_files(repository_root: Path) -> list[Path]:
    """Return first-party Python files under configured project roots.

    Args:
        repository_root: Repository directory containing src, apps, scripts,
            and tests.

    Returns:
        Sorted Python files, excluding generated and environment directories.
    """
    ignored_parts = {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
    }
    files = [
        path
        for root_name in ("src", "apps", "scripts", "tests")
        for path in (repository_root / root_name).rglob("*.py")
        if not ignored_parts.intersection(path.parts)
    ]
    return sorted(files)


def validate_repository(repository_root: Path) -> list[Violation]:
    """Validate all first-party Python files in a repository.

    Args:
        repository_root: Repository directory to scan.

    Returns:
        All violations with repository-relative file paths.
    """
    violations = []
    for path in python_files(repository_root):
        relative_path = path.relative_to(repository_root).as_posix()
        violations.extend(
            validate_source(path.read_text(encoding="utf-8"), relative_path)
        )
    return violations


def main() -> int:
    """Print repository docstring violations and return a shell exit code.

    Returns:
        Zero when validation passes; one when any violation is found.
    """
    repository_root = Path(__file__).resolve().parents[1]
    violations = validate_repository(repository_root)
    for violation in violations:
        print(
            f"{violation.path}:{violation.line}: "
            f"{violation.code} {violation.message}"
        )
    if violations:
        print(f"Found {len(violations)} docstring violation(s).")
        return 1
    print("All first-party Python docstrings are multiline and present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
