# Python documentation standards

Python documentation is part of the public engineering contract. Module
headers explain the module's actual role and boundaries; class and function
docstrings describe behavior that cannot be inferred from names and types.
Keep explanations concrete, current, and proportional to complexity.

## Required coverage

The automated check scans first-party Python under `src/`, `apps/`,
`scripts/`, and `tests/`. Every module, class, synchronous function,
coroutine, method, protocol, and nested function needs a source-level
multiline docstring. Private helpers are included. Decorators and lambdas do
not have docstring syntax and are outside this rule.

Every module docstring identifies its purpose and layer, describes its
responsibilities and important dependencies, and states relevant security,
configuration, lifecycle, or concurrency implications. Interface modules
must distinguish a contract from an implemented integration.

Class and protocol docstrings explain purpose, observable behavior,
invariants, dependencies, lifecycle, concurrency, and trust boundaries as
relevant. Use an `Attributes` section for a meaningful public data contract.
Pydantic models and dataclasses should explain constraints or fields that
are not self-explanatory from their names and types.

Function and method docstrings state why a nontrivial operation exists and
describe inputs, output, errors, side effects, concurrency, and security
constraints where those details matter. Use Google-style sections only when
they add useful information:

- `Args`
- `Returns`
- `Yields`
- `Raises`
- `Attributes`
- `Notes`
- `Security`
- `Concurrency`
- `Side Effects`
- `Design Rationale`
- `Limitations`

Do not create empty sections. Do not document exceptions that are neither
raised nor allowed to propagate. A short method may use a concise multiline
description; complexity, not word count, determines depth.

## Layout and line length

Use triple-double-quoted strings and put the summary on the opening line.
Separate the summary from following detail with one blank line. Keep section
headings aligned with the summary and indent their entries by four spaces.
Wrap Python lines at 80 characters, including comments and docstrings.

```python
async def load_profile(user_id: str) -> Profile | None:
    """Load the profile visible to one authenticated user.

    Args:
        user_id: Server-resolved identity used for the ownership check.

    Returns:
        The matching profile, or None when it is absent or not visible.
    """
    ...
```

Module, class, and function docstrings must span multiple source lines,
including concise summaries. Ruff enforces Google pydocstyle rules; the AST
validator checks coverage and source-line count.

## Inline comments

Comment on why a non-obvious branch, invariant, boundary, or algorithm exists.
Keep comments next to the logic they explain. Do not narrate syntax or repeat
the code in prose. Update a comment when behavior changes; remove comments
that no longer match the implementation.

## Architecture and integration claims

Markdown explains behavior across modules and records decisions; it should
not repeat entire source docstrings. Label scaffolds and proposals clearly.
Do not describe a provider as available until the code performs the
integration. Do not claim a connection, trace, or security control was
verified without evidence from a test or live result.

ADRs use the template in `docs/decisions/README.md`. An alternative included
for analysis must not be presented as a historical team discussion.
Infrastructure and test documentation should explain operational boundaries,
important fixtures, and the behavior a test protects.

## Enforcement

- `uv run ruff check .` applies Ruff's Google pydocstyle convention and the
  configured 80-character Python limit.
- `make docs-check` runs `scripts/check_docstrings.py`, which parses source
  with `ast`, reports the path and line, and exits nonzero on a violation.
- The local pre-commit hook and the CI docblock job run the AST validator.
- `make check` includes lint, comment and line-length checks, formatting,
  package build, type checking, docstrings, syntax, and tests.

The validator skips generated or environment directories and only scans the
four first-party project roots above. It deliberately avoids arbitrary
minimum word counts; accuracy and clarity remain review responsibilities.
