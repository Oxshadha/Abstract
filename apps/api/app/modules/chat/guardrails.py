"""Input guardrails (spec 007 AC6, D74, OWASP LLM01). A cheap screen before any model call;
the scope classifier (rewrite task) and the answer prompt are the next layers."""

import re
import unicodedata
from dataclasses import dataclass

# Common prompt-injection and exfiltration phrasings. Matching is case- and spacing-insensitive.
_PATTERNS = [
    r"ignore (all |any )?(the )?(previous|prior|above|earlier) (instructions|prompts|rules)",
    r"disregard (all |any )?(the )?(previous|prior|above|system) (instructions|prompt|rules)",
    r"(reveal|show|print|repeat|output) (me )?(your|the) (system|hidden|initial)"
    r" (prompt|instructions)",
    r"you are now (?!reading)",
    r"(act|pretend) as (if you were |an? )?(unrestricted|jailbroken|dan\b)",
    r"developer mode",
    r"other users?'?s? (papers|data|documents|conversations)",
    r"</?\s*(system|assistant|instructions?)\s*>",
]
_INJECTION = re.compile("|".join(f"(?:{p})" for p in _PATTERNS), re.IGNORECASE)
_SPACE = re.compile(r"\s+")

REFUSAL_UNSAFE = (
    "I can only answer questions about this paper, and I cannot follow instructions that try "
    "to change how I work. Try asking about its methods, results or conclusions."
)


@dataclass(frozen=True)
class Screen:
    allowed: bool
    reason: str | None = None


def normalise_question(text: str) -> str:
    return _SPACE.sub(" ", unicodedata.normalize("NFKC", text)).strip()


def screen(text: str) -> Screen:
    if _INJECTION.search(_SPACE.sub(" ", text)):
        return Screen(False, "injection-pattern")
    return Screen(True)
