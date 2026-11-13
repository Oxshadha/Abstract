"""Spec 014 AC5: the reference list is read from the page text, without a model call."""

import time

from app.modules.references.extract import MAX_REFERENCES, extract_references

NUMBERED = [
    """7 Conclusion
We presented the Transformer.
References
[1] Jimmy Lei Ba, Jamie Ryan Kiros, and Geoffrey E Hinton. Layer normalization. arXiv
preprint arXiv:1607.06450, 2016.
[2] Dzmitry Bahdanau, Kyunghyun Cho, and Yoshua Bengio. Neural machine translation by jointly
learning to align and translate. CoRR, abs/1409.0473, 2014.
[3] Denny Britz, Anna Goldie, Minh-Thang Luong, and Quoc V. Le. Massive exploration of neural
machine translation architectures. CoRR, abs/1703.03906, 2017.""",
    """[4] C. M. Bishop. Neural networks for pattern recognition. Oxford university press, 1995.
[5] Shiyue Zhang and Mohit Bansal. Addressing semantic drift in question generation. In
EMNLP, 2019. doi: 10.18653/v1/D19-1253.
A. Object Detection Baselines
In this section we introduce our detection method.""",
]

AUTHOR_YEAR = [
    """REFERENCES
Amari, Shun-Ichi. Natural gradient works efficiently in learning. Neural computation, 10(2),
1998.
Deng, Li, Li, Jinyu, Huang, Jui-Ting, Yao, Kaisheng, et al. Recent advances in deep learning for
speech research at microsoft. ICASSP 2013, 2013.
Michael Ahn, Anthony Brohan, Noah Brown, Yevgen Chebotar, et al. 2022. Do as I can, not as I
say: Grounding language in robotic affordances. arXiv preprint arXiv:2204.01691.
Abdelnabi, S., Gomaa, A., Sivaprasad, S., and Fritz, M. Llm-deliberation: Evaluating llms with
interactive multi-agent negotiation games. 2023.
G. Dahl, D. Yu, L. Deng, and A. Acero, “Context-Dependent Pre-Trained Deep Neural Networks
for Large-Vocabulary Speech Recognition,” IEEE Transactions, 2012.
10 APPENDIX
10.1 CONVERGENCE PROOF
Definition 10.1. A function f is convex if for all x, y."""
]


def test_AC5_a_numbered_list_keeps_labels_identifiers_and_titles() -> None:
    refs = extract_references(NUMBERED)
    assert [r.label for r in refs] == ["1", "2", "3", "4", "5"]
    assert refs[0].title == "Layer normalization"
    assert refs[0].arxiv_id == "1607.06450"
    assert refs[1].arxiv_id == "1409.0473"
    assert refs[1].raw.startswith("Dzmitry Bahdanau")
    assert "jointly learning" in refs[1].raw  # wrapped lines are joined
    assert refs[3].title == "Neural networks for pattern recognition"
    assert refs[4].doi == "10.18653/v1/d19-1253"
    assert "Object Detection" not in refs[4].raw  # the appendix is not part of the list


def test_AC5_an_author_year_list_is_split_at_each_new_author_list() -> None:
    refs = extract_references(AUTHOR_YEAR)
    assert [r.title for r in refs] == [
        "Natural gradient works efficiently in learning",
        "Recent advances in deep learning for speech research at microsoft",
        "Do as I can, not as I say: Grounding language in robotic affordances",
        "Llm-deliberation: Evaluating llms with interactive multi-agent negotiation games",
        "Context-Dependent Pre-Trained Deep Neural Networks for Large-Vocabulary Speech"
        " Recognition",
    ]
    assert all(r.label is None for r in refs)
    assert refs[2].arxiv_id == "2204.01691"
    assert "CONVERGENCE" not in refs[-1].raw


def test_AC5_no_reference_section_means_no_list() -> None:
    assert extract_references(["Introduction\nWe study attention.", "Conclusion\nIt works."]) == []


def test_AC5_long_lists_stop_at_300_and_extraction_is_fast() -> None:
    lines = [
        f"[{i}] Author Name and Other Person. A study of topic number {i}. In Venue, 2020."
        for i in range(1, 401)
    ]
    pages = ["References\n" + "\n".join(lines[:200]), "\n".join(lines[200:])]
    started = time.perf_counter()
    refs = extract_references(pages)
    assert time.perf_counter() - started < 0.2  # under 200 ms of processing (budget)
    assert len(refs) == MAX_REFERENCES
    assert refs[-1].label == "300"


def test_AC5_running_headers_are_not_read_as_references() -> None:
    header = "Published as a conference paper at ICLR 2022"
    pages = [
        f"{header}\nIntro text.",
        f"{header}\nREFERENCES\nArmen Aghajanyan and Sonal Gupta. Intrinsic dimensionality. 2020.",
        f"{header}\nZeyuan Allen-Zhu and Yuanzhi Li. What can ResNet learn efficiently? 2019.",
    ]
    refs = extract_references(pages)
    assert len(refs) == 2
    assert all(header not in r.raw for r in refs)
