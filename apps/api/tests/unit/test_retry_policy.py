from app.adapters.llm.retry import backoff_delay


def test_retry_after_seconds_is_honoured_and_capped() -> None:
    assert backoff_delay(1, "3") == 3.0
    assert backoff_delay(1, "999") == 20.0


def test_full_jitter_stays_within_exponential_bound() -> None:
    delays = [backoff_delay(3) for _ in range(200)]
    assert all(0 <= d <= 8 for d in delays)
    assert len({round(d, 3) for d in delays}) > 50  # actually jittered


def test_http_date_retry_after_falls_back_to_backoff() -> None:
    assert 0 <= backoff_delay(2, "Wed, 21 Oct 2026 07:28:00 GMT") <= 4
