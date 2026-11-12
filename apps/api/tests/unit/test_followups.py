"""Spec 015 AC2: the follow-up splitter."""

from app.modules.chat.followups import MARK, FollowUpSplitter


def test_AC2_the_marker_is_held_back_across_chunk_boundaries() -> None:
    splitter = FollowUpSplitter()
    text = f"An answer [S1].\n{MARK}\n- One?\n- Two?"
    shown = "".join(splitter.feed(text[i : i + 3]) for i in range(0, len(text), 3))
    rest, answer, questions = splitter.finish()
    assert "<<" not in shown + rest
    assert (shown + rest).rstrip() == answer == "An answer [S1]."
    assert questions == ["One?", "Two?"]


def test_AC2_an_answer_without_follow_ups_is_shown_whole() -> None:
    splitter = FollowUpSplitter()
    shown = splitter.feed("Ends with <<")  # looks like the start of the marker
    rest, answer, questions = splitter.finish()
    assert shown + rest == "Ends with <<"
    assert questions == []
    assert answer == "Ends with <<"
