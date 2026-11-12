"""Follow-up questions from the same answer call (spec 015 AC2, D88).

The answer prompt asks the model to end with a marker line and up to three follow-up questions.
The splitter forwards only the answer while it streams (holding back any text that could be the
start of the marker), so the questions never flash in the chat; they come in the `done` event.
"""

import re

MARK = "<<FOLLOW-UPS>>"
MAX_FOLLOW_UPS = 3
MAX_CHARS = 140


class FollowUpSplitter:
    def __init__(self) -> None:
        self._text = ""
        self._sent = 0

    def feed(self, chunk: str) -> str:
        """The part of the answer that is safe to show now."""
        self._text += chunk
        at = self._text.find(MARK)
        if at >= 0:
            safe = at
        else:
            # Hold back a tail that could be the beginning of the marker.
            prefixes = range(len(MARK) - 1, 0, -1)
            hold = next((k for k in prefixes if self._text.endswith(MARK[:k])), 0)
            safe = len(self._text) - hold
        out = self._text[self._sent : max(self._sent, safe)]
        self._sent = max(self._sent, safe)
        return out

    def finish(self) -> tuple[str, str, list[str]]:
        """(rest of the answer not yet shown, the whole answer, the follow-up questions)."""
        at = self._text.find(MARK)
        answer = self._text if at < 0 else self._text[:at]
        rest = answer[self._sent :] if self._sent < len(answer) else ""
        questions: list[str] = []
        if at >= 0:
            for line in self._text[at + len(MARK) :].splitlines():
                q = re.sub(r"^\s*(?:[-*\d.)]+\s*)?", "", line).strip()
                if q and q.endswith("?") and len(q) <= MAX_CHARS and q not in questions:
                    questions.append(q)
                if len(questions) == MAX_FOLLOW_UPS:
                    break
        return rest, answer.rstrip(), questions
