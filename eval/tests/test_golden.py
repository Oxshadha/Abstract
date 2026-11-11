from pathlib import Path

import pymupdf
import yaml

from app.adapters.llm.fake import FakeLLMGateway
from harness.budget import BudgetGuard
from harness.golden import draft_one, golden_schema, layout_probes, write_golden

LEFT = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi"
RIGHT = "rho sigma tau upsilon phi chi psi omega one two three four five six seven eight"


def _two_column_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    for i, y in enumerate((100, 300)):
        page.insert_textbox(pymupdf.Rect(50, y, 290, y + 150), f"L{i} {LEFT}", fontsize=10)
        page.insert_textbox(pymupdf.Rect(322, y, 562, y + 150), f"R{i} {RIGHT}", fontsize=10)
    document.save(path)
    document.close()


def test_layout_probe_pairs_end_of_left_column_with_start_of_right(tmp_path: Path) -> None:
    pdf = tmp_path / "two-col.pdf"
    _two_column_pdf(pdf)
    probes = layout_probes(pdf, words=4)
    assert len(probes) == 1
    assert probes[0]["first"] == "nu xi omicron pi"  # tail of the last left block (L1)
    assert probes[0]["second"].startswith("R0 rho")  # head of the first right block
    assert probes[0]["verified"] is False


async def test_draft_with_fake_provider_writes_unverified_yaml(tmp_path: Path) -> None:
    pdf = tmp_path / "doc.pdf"
    _two_column_pdf(pdf)
    guard = BudgetGuard(max_usd=1.0)
    record = await draft_one("doc", pdf, FakeLLMGateway(), guard)
    path = write_golden(record, tmp_path)
    saved = yaml.safe_load(path.read_text())
    assert saved["paper"] == "doc"
    assert all(item["verified"] is False for item in saved["facts"] + saved["questions"])
    assert set(saved["present_fields"]) == set(
        golden_schema()["properties"]["present_fields"]["required"]
    )
    assert path.read_text().startswith("# Drafted automatically")
    assert len(guard.calls) == 1
