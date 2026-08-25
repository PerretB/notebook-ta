"""Deterministic expansion of reusable prompt fragments."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping

_FRAGMENT_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_RESERVED_FRAGMENT_NAMES = frozenset(
    {
        "fragments",
        "hint_history_length",
        "on_failure",
        "on_free_text",
        "on_no_llm",
        "on_success",
        "student_code_safety_instruction",
        "student_text_safety_instruction",
    }
)


class PromptTemplateError(ValueError):
    """Raised when a prompt fragment or reference cannot be resolved."""


def resolve_prompt_fragments(fragments: Mapping[str, str]) -> dict[str, str]:
    """Validate and recursively resolve every configured prompt fragment."""
    for name in fragments:
        if not _FRAGMENT_NAME_PATTERN.fullmatch(name):
            raise PromptTemplateError(
                f"Invalid prompt fragment name {name!r}; expected a name matching "
                "[A-Za-z_][A-Za-z0-9_]*."
            )
        if name in _RESERVED_FRAGMENT_NAMES:
            raise PromptTemplateError(f"Prompt fragment name {name!r} is reserved.")

    resolved: dict[str, str] = {}

    def resolve_fragment(name: str, stack: tuple[str, ...]) -> str:
        if name in resolved:
            return resolved[name]
        if name not in fragments:
            raise PromptTemplateError(f"references unknown prompt fragment {name!r}.")
        if name in stack:
            cycle_start = stack.index(name)
            cycle = (*stack[cycle_start:], name)
            raise PromptTemplateError(f"Cyclic prompt fragment reference: {' -> '.join(cycle)}.")

        value = _expand_template(
            fragments[name],
            lambda reference: resolve_fragment(reference, (*stack, name)),
            location=f"prompts.fragments.{name}",
        )
        resolved[name] = value
        return value

    for fragment_name in fragments:
        resolve_fragment(fragment_name, ())
    return resolved


def expand_prompt_template(
    template: str,
    fragments: Mapping[str, str],
    *,
    location: str,
) -> str:
    """Expand one template using an already resolved prompt-fragment mapping."""

    def resolve_reference(name: str) -> str:
        try:
            return fragments[name]
        except KeyError:
            raise PromptTemplateError(
                f"{location} references unknown prompt fragment {name!r}."
            ) from None

    return _expand_template(template, resolve_reference, location=location)


def _expand_template(
    template: str,
    resolve_reference: Callable[[str], str],
    *,
    location: str,
) -> str:
    """Scan and expand a template without evaluating inserted fragment contents twice."""
    parts: list[str] = []
    index = 0
    while index < len(template):
        if template.startswith("{{{{", index):
            parts.append("{{")
            index += 4
            continue
        if template.startswith("}}}}", index):
            parts.append("}}")
            index += 4
            continue
        if template.startswith("{{", index):
            closing = template.find("}}", index + 2)
            if closing < 0:
                raise PromptTemplateError(
                    f"{location} contains an unterminated prompt fragment reference."
                )
            reference = template[index + 2 : closing].strip()
            if not _FRAGMENT_NAME_PATTERN.fullmatch(reference):
                raise PromptTemplateError(
                    f"{location} contains malformed prompt fragment reference "
                    f"{template[index : closing + 2]!r}."
                )
            parts.append(resolve_reference(reference))
            index = closing + 2
            continue
        if template.startswith("}}", index):
            raise PromptTemplateError(
                f"{location} contains an unmatched prompt fragment closing delimiter."
            )
        parts.append(template[index])
        index += 1
    return "".join(parts)
