import json

import pytest
import structlog

from app.core.logging import configure_logging


def test_AC6_logs_are_json_with_required_fields(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    structlog.contextvars.bind_contextvars(request_id="rid-1")
    structlog.get_logger("t").info("hello", answer=42)
    structlog.contextvars.clear_contextvars()
    record = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert record["event"] == "hello"
    assert record["level"] == "info"
    assert record["request_id"] == "rid-1"
    assert "timestamp" in record
