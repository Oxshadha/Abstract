"""Spec 009: pure helpers of the enrichment job (labels, Markdown tables, number checks, crops)."""

import io

from PIL import Image

from app.adapters.pdf.render import render_crop
from app.modules.papers.enrich import label_for, numbers_in, table_markdown
from app.ports.layout import Box, TableElement
from tests.fakes.pdfs import make_rich_pdf


def test_AC3_tables_become_markdown_with_header_rows() -> None:
    table = TableElement(
        page=3,
        box=Box(0.1, 0.2, 0.6, 0.2),
        caption="Table 2: BLEU",
        cells=[["Model", "BLEU"], ["Base", "27.3"], ["Big | wide", "28.4"]],
    )
    assert table_markdown(table).splitlines() == [
        "| Model | BLEU |",
        "|---|---|",
        "| Base | 27.3 |",
        "| Big / wide | 28.4 |",  # a pipe in a cell cannot break the table
    ]


def test_AC5_labels_come_from_captions_or_order() -> None:
    assert label_for("table", "Table 3: Results on WMT", 1) == "Table 3"
    assert label_for("figure", "Fig. 2. Attention maps", 1) == "Figure 2"
    assert label_for("table", "TABLE IV Ablations", 2) == "Table IV"
    assert label_for("figure", None, 4) == "Figure 4"


def test_AC8_numbers_worth_checking_skip_years_and_small_counts() -> None:
    assert numbers_in(
        "Reaches 28.4 BLEU (vs 27.3) on 4 GPUs in 2017 with 1,024 tokens and 213 steps."
    ) == [
        "28.4",
        "27.3",
        "1024",
        "213",
    ]


def test_AC1_crops_are_rendered_from_the_pdf_box() -> None:
    pdf = make_rich_pdf([{"lines": ["Figure 1: A picture."], "image": True}])
    png = render_crop(pdf, 1, Box(0.1, 0.5, 0.4, 0.25))
    image = Image.open(io.BytesIO(png))
    assert image.format == "PNG"
    # 0.4 x 612 pt by 0.25 x 792 pt at scale 2
    assert abs(image.width - 490) <= 2
    assert abs(image.height - 396) <= 2


def test_AC2_time_left_uses_the_pace_so_far_or_the_guess() -> None:
    from app.modules.papers.elements import estimate_seconds_left

    assert estimate_seconds_left(40.0, 4, 10) == 60  # 10 s a page, 6 to go
    assert estimate_seconds_left(5.0, 0, 10, guess=6.0) == 55  # guess minus time already spent
    assert estimate_seconds_left(90.0, 0, 10, guess=6.0) == 1  # slower than the guess: still going
    assert estimate_seconds_left(30.0, 10, 10) == 0  # every page parsed
