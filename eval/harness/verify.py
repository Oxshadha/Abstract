"""Deterministic verification of drafted golden data against the PDF text (owner-delegated).

An item is marked verified only when the PDF text proves it:
- facts: every number (citation markers removed) appears on the cited page; if it appears on
  exactly one other page instead, the page is corrected and recorded.
- answerable questions: the answer's numbers, or the answer text (fuzzy >= 85), appear on a
  cited page.
- layout probes: both text pieces exist on that page (order is guaranteed by the geometry the
  probes were derived from, so this check stays neutral between parsers).
Not provable from text, left for a human: unanswerable questions and present_fields.
Page text is the union of two independent extractors so neither parser is favoured.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from rapidfuzz import fuzz

from harness.corpus import PDF_DIR
from harness.metrics import CITATION_MARKER, normalize, numbers_in
from harness.parsers import parse_pdfium, parse_pymupdf

EVAL_DIR = Path(__file__).resolve().parents[1]
GOLDEN_DIR = EVAL_DIR / "corpus" / "golden"
METHOD = "deterministic-text-v1"


def page_texts(pdf: Path) -> list[str]:
    a, b = parse_pdfium(pdf).pages, parse_pymupdf(pdf).pages
    return [f"{x}\n{y}" for x, y in zip(a, b, strict=False)]


def _numbers(text: str) -> set[str]:
    return numbers_in(CITATION_MARKER.sub(" ", text))


def verify_fact(fact: dict[str, Any], pages: list[str]) -> str:
    wanted = _numbers(str(fact["fact"]))
    if not wanted:
        return "no numbers to check"
    page = int(fact["page"])
    if 1 <= page <= len(pages) and wanted <= numbers_in(pages[page - 1]):
        fact["verified"] = True
        return "ok"
    hits = [i + 1 for i, text in enumerate(pages) if wanted <= numbers_in(text)]
    if len(hits) == 1:
        fact["page_corrected_from"], fact["page"], fact["verified"] = page, hits[0], True
        return f"page corrected {page} -> {hits[0]}"
    return "numbers not found on cited page" if not hits else f"ambiguous pages {hits}"


def verify_question(question: dict[str, Any], pages: list[str]) -> str:
    if question["kind"] == "unanswerable":
        return "needs human (absence cannot be proven from text)"
    cited = [pages[p - 1] for p in question.get("pages", []) if 1 <= p <= len(pages)]
    if not cited:
        return "no valid cited page"
    answer = str(question["answer"])
    wanted = _numbers(answer)
    if wanted and any(wanted <= numbers_in(text) for text in cited):
        question["verified"] = True
        return "ok (numbers)"
    norm = normalize(answer)
    if len(norm) >= 3 and any(fuzz.partial_ratio(norm, normalize(t)) >= 85 for t in cited):
        question["verified"] = True
        return "ok (text)"
    return "answer not found on cited pages"


def verify_probe(probe: dict[str, Any], pages: list[str]) -> str:
    page = int(probe["page"])
    if not 1 <= page <= len(pages):
        return "page out of range"
    text = normalize(pages[page - 1])
    if normalize(probe["first"]) in text and normalize(probe["second"]) in text:
        probe["verified"] = True
        return "ok"
    return "probe text not found on page"


def verify_record(record: dict[str, Any], pages: list[str]) -> dict[str, list[str]]:
    notes: dict[str, list[str]] = {"facts": [], "questions": [], "layout_probes": []}
    for fact in record.get("facts", []):
        notes["facts"].append(verify_fact(fact, pages))
    for question in record.get("questions", []):
        notes["questions"].append(verify_question(question, pages))
    for probe in record.get("layout_probes", []):
        notes["layout_probes"].append(verify_probe(probe, pages))
    record["verification"] = {
        "method": METHOD,
        "at": datetime.now(UTC).strftime("%Y-%m-%d"),
        "needs_human": ["present_fields", "unanswerable questions"],
    }
    return notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify golden data against PDF text")
    parser.add_argument("ids", nargs="*")
    args = parser.parse_args(argv)
    total = {"verified": 0, "items": 0}
    for path in sorted(GOLDEN_DIR.glob("*.yaml")):
        paper = path.stem
        if args.ids and paper not in args.ids:
            continue
        text = path.read_text()
        header = "".join(line for line in text.splitlines(keepends=True) if line.startswith("#"))
        record = yaml.safe_load(text)
        notes = verify_record(record, page_texts(PDF_DIR / f"{paper}.pdf"))
        items = [*record["facts"], *record["questions"], *record.get("layout_probes", [])]
        done = sum(bool(i.get("verified")) for i in items)
        total["verified"] += done
        total["items"] += len(items)
        path.write_text(header + yaml.safe_dump(record, sort_keys=False, allow_unicode=True))
        problems = [
            f"{k}[{i}]: {n}"
            for k, v in notes.items()
            for i, n in enumerate(v)
            if not n.startswith("ok")
        ]
        print(
            f"  {paper:<12} {done}/{len(items)} verified"
            + (f"  | {'; '.join(problems)}" if problems else "")
        )
    print(f"Total: {total['verified']}/{total['items']} items verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
