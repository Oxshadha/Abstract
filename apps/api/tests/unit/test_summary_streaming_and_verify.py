"""Spec 006 AC3 (fields complete while streaming) and AC4 (deterministic quote verification)."""

import json

from app.modules.summaries.streaming import FieldStream
from app.modules.summaries.verify import normalise, verify_quote

DOC = {
    "title": "Attention Is All You Need",
    "authors": ["A. Vaswani", "N. Shazeer"],
    "year": 2017,
    "abstract": {
        "value": 'We propose the Transformer, with "quotes" and {braces}.',
        "status": "found",
        "evidence": [{"page": 1, "quote": "We propose"}],
    },
    "key_results": {"value": "BLEU 28.4", "status": "found", "evidence": []},
}


def test_AC3_fields_complete_one_by_one_across_arbitrary_chunks() -> None:
    text = json.dumps(DOC, indent=1)
    stream, order = FieldStream(), []
    for i in range(0, len(text), 7):  # chunk boundaries land inside strings and escapes
        for key in stream.feed(text[i : i + 7]):
            order.append(key)
    assert order == ["title", "authors", "year", "abstract", "key_results"]
    assert stream.done == DOC


def test_AC3_a_field_is_reported_only_once_its_value_is_complete() -> None:
    stream = FieldStream()
    assert stream.feed('{"title": "Atten') == {}
    assert stream.feed('tion", "abstract": {"value": "x"') == {"title": "Attention"}
    assert stream.feed(', "status": "found", "evidence": []}}') == {
        "abstract": {"value": "x", "status": "found", "evidence": []}
    }


PAGES = {
    1: normalise(
        "The dominant sequence transduction models are based on complex recurrent "
        "or convolutional neural networks. We propose a new simple network architec-\n"
        "ture, the Transformer, based solely on attention mechanisms."
    ),
    7: normalise(
        "On the WMT 2014 English-to-German translation task, the big transformer model "
        "outperforms the best previously reported models by more than 2.0 BLEU."
    ),
}


def test_AC4_exact_and_lightly_reformatted_quotes_verify_on_their_page() -> None:
    result = verify_quote("a new simple network architecture, the Transformer", 1, PAGES)
    assert (result.page, result.verified) == (1, True)  # hyphen across lines rejoined


def test_AC4_a_quote_on_another_page_is_verified_and_its_page_corrected() -> None:
    result = verify_quote("outperforms the best previously reported models", 3, PAGES)
    assert (result.page, result.verified) == (7, True)


def test_AC4_paraphrases_and_inventions_stay_unverified() -> None:
    assert not verify_quote(
        "The Transformer uses only recurrence and convolutions to win", 1, PAGES
    ).verified
    assert not verify_quote("short", 1, PAGES).verified
    assert not verify_quote("anything at all here", 1, {}).verified
