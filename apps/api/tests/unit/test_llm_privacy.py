"""Spec 005 AC9 / D76: model calls leave metadata only in logs and errors, never content."""

import pytest

from app.modules.llm.gateway import AllRoutesFailedError
from app.ports.llm import ChatMessage
from tests.unit.test_llm_routing import Scripted, gateway

SECRET = "Unpublished result: drug X cures condition Y"


class Leaky(Scripted):
    """A provider whose error message echoes the prompt, as some APIs do."""

    async def complete(self, **kwargs: object):  # type: ignore[no-untyped-def]
        raise ValueError(f"bad request for prompt: {SECRET}")


async def test_AC9_logs_and_errors_never_contain_prompt_or_paper_text(
    capsys: pytest.CaptureFixture[str],
) -> None:
    gw, sink = gateway(Leaky("vertex"), Leaky("openrouter"))
    with pytest.raises(AllRoutesFailedError) as info:
        await gw.complete(task="summarize", messages=[ChatMessage(role="user", content=SECRET)])
    out = capsys.readouterr()
    assert SECRET not in out.out + out.err
    assert SECRET not in str(info.value)
    assert all(a.error_type == "ValueError" for a in sink.attempts)
    assert "drug X" not in repr(sink.attempts)
