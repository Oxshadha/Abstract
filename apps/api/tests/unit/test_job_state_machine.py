"""Spec 004 AC6: allowed job transitions live in one place and are complete."""

from typing import get_args

from app.modules.papers.jobs import TRANSITIONS, JobStatus, can_transition, sources_for


def test_AC6_every_status_has_a_transition_entry() -> None:
    assert set(TRANSITIONS) == set(get_args(JobStatus))


def test_AC6_terminal_statuses_cannot_move() -> None:
    for terminal in ("succeeded", "cancelled"):
        assert not TRANSITIONS[terminal]


def test_AC6_allowed_and_forbidden_transitions() -> None:
    assert can_transition("queued", "running")
    assert can_transition("running", "succeeded")
    assert can_transition("running", "queued")  # retry
    assert can_transition("enqueue_failed", "queued")  # admin retry
    assert not can_transition("succeeded", "running")
    assert not can_transition("queued", "succeeded")  # must run first
    assert not can_transition("cancelled", "queued")


def test_AC6_sources_for_is_the_inverse_of_the_table() -> None:
    assert sources_for("running") == ["queued"]
    assert sources_for("queued") == ["enqueue_failed", "failed", "running"]
