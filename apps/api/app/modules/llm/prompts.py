"""Versioned prompts (spec 005 AC13, AGENTS rule 8).

Prompts live in code, each with a name and version (`summarize@1`). Using a prompt puts its
version in the call context, so every attempt records it in `llm_usage` and cost or quality can
be compared across prompt changes. A prompt editor in the admin panel comes later (D26).

Untrusted text (paper content, user questions, template instructions) is never part of the
system prompt: it is passed as data, wrapped in tags, with any tag-like sequence inside it
neutralised so it cannot close the wrapper and pose as instructions.
"""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from app.modules.llm.gateway import reset_context, set_context
from app.ports.llm import ChatMessage

_LABEL = re.compile(r"^[a-z_]{2,32}$")
_TAG = re.compile(r"</?\s*([a-z_]{2,32})\s*>", re.IGNORECASE)


def wrap_untrusted(label: str, value: str) -> str:
    """`<label>value</label>`, with tags inside the value defused (e.g. `</paper>`)."""
    if not _LABEL.match(label):
        raise ValueError(f"invalid label {label!r}")
    # Angle quotation marks look alike to a reader but are not tag delimiters for the model.
    defused = _TAG.sub(lambda m: m.group(0).replace("<", "\u2039").replace(">", "\u203a"), value)
    return f"<{label}>\n{defused}\n</{label}>"


@dataclass(frozen=True)
class Prompt:
    name: str
    version: int
    system: str  # instructions only: never contains untrusted text
    user: str  # may reference {placeholders}; filled only with wrapped data

    @property
    def key(self) -> str:
        return f"{self.name}@{self.version}"

    def messages(self, **data: str) -> list[ChatMessage]:
        filled = self.user.format(**{k: wrap_untrusted(k, v) for k, v in data.items()})
        return [
            ChatMessage(role="system", content=self.system),
            ChatMessage(role="user", content=filled),
        ]


@contextmanager
def using(prompt: Prompt) -> Iterator[Prompt]:
    """Record `prompt.key` on every model attempt made inside the block."""
    token = set_context(prompt_version=prompt.key)
    try:
        yield prompt
    finally:
        reset_context(token)


REGISTRY: dict[str, Prompt] = {}


def register(prompt: Prompt) -> Prompt:
    existing = REGISTRY.get(prompt.name)
    if existing is not None and existing.version >= prompt.version and existing != prompt:
        raise ValueError(f"{prompt.name}: changed prompts need a higher version")
    REGISTRY[prompt.name] = prompt
    return prompt
