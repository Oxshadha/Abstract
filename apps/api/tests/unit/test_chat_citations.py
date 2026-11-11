"""Spec 007 AC5: citation validation, including the marker formats real models produce."""

from app.modules.chat.citations import Passage, expand_groups, validate

PASSAGE = Passage(
    1,
    10,
    1,
    1,
    "1 Introduction",
    "Paper · 1 Introduction\n\nSelf attention relates positions of a sequence to "
    "compute a representation. It is used in the Transformer.",
)
OTHER = Passage(2, 11, 3, 4, "Results", "Paper · Results\n\nThe model reaches 28.4 BLEU on WMT.")


def test_AC5_grouped_markers_from_gemini_are_understood() -> None:
    # Exactly what gemini-3.6-flash returned in the live run.
    answer = "Self attention relates positions of a sequence to compute a representation [S1, S2]."
    result = validate(answer, [PASSAGE, OTHER])
    assert [c.marker for c in result.citations] == [1, 2]
    assert result.removed == 0
    assert expand_groups("x [S1; S3] y [S2 and S4]") == "x [S1][S3] y [S2][S4]"


def test_AC5_markers_outside_the_retrieved_set_are_removed() -> None:
    result = validate(
        "Self attention relates positions [S1]. Claim two [S7]. Mixed [S1, S9].", [PASSAGE]
    )
    assert "[S7]" not in result.text
    assert "[S9]" not in result.text
    assert result.removed == 2
    assert [c.marker for c in result.citations] == [1]
    assert "Self attention relates positions" in result.citations[0].quote


def test_AC5_no_markers_means_no_citations() -> None:
    assert validate("An answer without any sources.", [PASSAGE]).citations == []
