"""Benchmark runner: experiments A, B, B', B-fast (summary) and E (embeddings). Spec 000.

make eval EXP=all            # or EXP=A, EXP=B, EXP=E ...
make eval EXP=B IDS="bert resnet" UNVERIFIED=1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from app.ports.llm import LLMGateway
from harness import metrics
from harness.budget import BudgetExceededError, BudgetGuard
from harness.corpus import PDF_DIR, load_manifest
from harness.parsers import PARSERS, ParsedDoc, parse_pymupdf
from harness.providers import build_gateway, embedding_entries, load_config
from harness.summary import (
    SUMMARY_MAX_TOKENS,
    first_field_offset,
    json_schema,
    parse_summary,
    pdf_messages,
    text_messages,
)

EVAL_DIR = Path(__file__).resolve().parents[1]
GOLDEN_DIR = EVAL_DIR / "corpus" / "golden"
RUNS_DIR = EVAL_DIR / "runs"
REPORTS_DIR = EVAL_DIR / "reports"

# Summary experiments: name -> parser (None = whole PDF to a multimodal model).
SUMMARY_EXPERIMENTS: dict[str, str | None] = {
    "A": None,
    "B": "pymupdf",
    "B'": "pdfium",
    "B-fast": "pymupdf_fast",
}


@dataclass
class SummaryResult:
    experiment: str
    paper: str
    run: int
    ok: bool
    error: str | None = None
    parse_s: float = 0.0
    ttft_s: float | None = None
    ttff_s: float | None = None
    total_s: float = 0.0
    est_tokens: int = 0
    tier: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    model: str = ""
    scores: dict[str, float | None] = field(default_factory=dict)
    summary: dict[str, Any] | None = None


# ---------- golden data ----------


def load_golden(paper: str, include_unverified: bool) -> dict[str, Any] | None:
    path = GOLDEN_DIR / f"{paper}.yaml"
    if not path.exists():
        return None
    data: dict[str, Any] = yaml.safe_load(path.read_text())

    def keep(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [i for i in items if include_unverified or i.get("verified")]

    data["facts"] = keep(data.get("facts", []))
    data["questions"] = keep(data.get("questions", []))
    data["layout_probes"] = keep(data.get("layout_probes", []))
    if not (include_unverified or data.get("present_fields_verified")):
        data["present_fields"] = {}
    return data


# ---------- scoring ----------


def score_summary(
    summary: dict[str, Any], golden: dict[str, Any] | None, reference: ParsedDoc
) -> dict[str, float | None]:
    parsed = parse_summary(json.dumps(summary))
    quotes = [
        (ev.page, ev.quote)
        for name in ("abstract", "problem_statement", "methodology", "key_results", "conclusion")
        for ev in getattr(parsed, name).evidence
    ]

    def supported(page: int, quote: str) -> bool:
        return 1 <= page <= len(reference.pages) and metrics.quote_supported(
            quote, reference.pages[page - 1]
        )

    scores: dict[str, float | None] = {
        "citation_valid": (sum(supported(p, q) for p, q in quotes) / len(quotes))
        if quotes
        else None,
        "citation_any_page": (
            sum(metrics.quote_supported(q, reference.text) for _, q in quotes) / len(quotes)
        )
        if quotes
        else None,
        "field_recall": None,
        "false_found": None,
        "numeric_accuracy": None,
        "numbers_grounded": metrics.numbers_grounded(parsed.all_text(), reference.text),
    }
    if golden:
        if golden.get("present_fields"):
            recall, false_found = metrics.field_coverage(
                parsed.field_statuses(), golden["present_fields"]
            )
            scores["field_recall"], scores["false_found"] = recall, false_found
        facts = golden.get("facts", [])
        if facts:
            text = parsed.all_text()
            scores["numeric_accuracy"] = sum(
                metrics.fact_reproduced(text, f["fact"]) for f in facts
            ) / len(facts)
    return scores


def reading_order_score(parsed: ParsedDoc, golden: dict[str, Any] | None) -> float | None:
    probes = (golden or {}).get("layout_probes", [])
    if not probes:
        return None
    return sum(
        metrics.reading_order_ok(parsed.text, p["first"], p["second"]) for p in probes
    ) / len(probes)


# ---------- experiments ----------


async def run_summary(
    experiment: str,
    paper: str,
    pdf: Path,
    run: int,
    gateway: LLMGateway,
    guard: BudgetGuard,
    golden: dict[str, Any] | None,
    reference: ParsedDoc,
) -> SummaryResult:
    parser = SUMMARY_EXPERIMENTS[experiment]
    result = SummaryResult(experiment=experiment, paper=paper, run=run, ok=False)
    started = time.perf_counter()
    if parser is None:
        messages = pdf_messages(pdf.name, await asyncio.to_thread(pdf.read_bytes))
        result.est_tokens, result.tier = reference.est_tokens, reference.tier
    else:
        parsed = await asyncio.to_thread(PARSERS[parser], pdf)  # CPU-bound; keep the loop free
        result.parse_s = round(parsed.seconds, 3)
        result.est_tokens, result.tier = parsed.est_tokens, parsed.tier
        messages = text_messages(parsed.text)
    guard.check()
    text = ""
    try:
        stream = gateway.stream(
            task="summarize",
            messages=messages,
            json_schema=json_schema(),
            max_tokens=SUMMARY_MAX_TOKENS,
        )
        async for chunk in stream:
            now = time.perf_counter() - started
            if chunk.text:
                text += chunk.text
                if result.ttft_s is None:
                    result.ttft_s = round(now, 3)
                if result.ttff_s is None and first_field_offset(text) is not None:
                    result.ttff_s = round(now, 3)
            if chunk.usage is not None:
                guard.record(chunk.usage)
                result.input_tokens = chunk.usage.input_tokens
                result.output_tokens = chunk.usage.output_tokens
                result.cached_tokens = chunk.usage.cached_tokens
                result.cost_usd = chunk.usage.cost_usd
                result.model = chunk.usage.model
        result.total_s = round(time.perf_counter() - started, 3)
        result.summary = json.loads(text)
        result.scores = score_summary(result.summary, golden, reference)
        result.ok = True
    except BudgetExceededError:
        raise
    except Exception as exc:  # recorded, not dropped (spec 000 edge cases)
        result.total_s = round(time.perf_counter() - started, 3)
        result.error = f"{type(exc).__name__}: {str(exc)[:300]}"
    return result


def _chunks(parsed: ParsedDoc, max_chars: int = 2400) -> list[tuple[int, str]]:
    """Page-bounded windows (about 600 tokens) until real chunking lands in spec 004."""
    out: list[tuple[int, str]] = []
    for page_number, text in enumerate(parsed.pages, 1):
        for start in range(0, max(len(text), 1), max_chars):
            piece = text[start : start + max_chars].strip()
            if piece:
                out.append((page_number, piece))
    return out


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


async def run_embeddings(
    config_entry: dict[str, Any],
    paper: str,
    reference: ParsedDoc,
    golden: dict[str, Any] | None,
    gateway: LLMGateway,
    guard: BudgetGuard,
) -> dict[str, Any] | None:
    questions = [
        q
        for q in (golden or {}).get("questions", [])
        if q["kind"] in ("specific", "table_figure") and q.get("pages")
    ]
    if not questions:
        return None
    chunks = _chunks(reference)
    dims = int(config_entry["dimensions"])
    guard.check()
    doc_vectors = await gateway.embed(
        task=config_entry["name"], texts=[c[1] for c in chunks], dimensions=dims
    )
    guard.record(doc_vectors.usage)
    q_vectors = await gateway.embed(
        task=config_entry["name"], texts=[q["question"] for q in questions], dimensions=dims
    )
    guard.record(q_vectors.usage)
    if len(doc_vectors.vectors) != len(chunks) or len(q_vectors.vectors) != len(questions):
        raise ValueError(
            f"embedding count mismatch: {len(doc_vectors.vectors)} vectors for {len(chunks)} "
            f"chunks, {len(q_vectors.vectors)} for {len(questions)} questions"
        )
    hits, rr = [], []
    for question, qv in zip(questions, q_vectors.vectors, strict=True):
        ranked = sorted(
            range(len(chunks)), key=lambda i: _cosine(qv, doc_vectors.vectors[i]), reverse=True
        )
        pages = [chunks[i][0] for i in ranked]
        expected = set(question["pages"])
        hits.append(metrics.hit_at_k(pages, expected, k=5))
        rr.append(metrics.reciprocal_rank(pages, expected))
    return {
        "embedding": config_entry["name"],
        "paper": paper,
        "questions": len(questions),
        "hit_at_5": sum(hits) / len(hits),
        "mrr": sum(rr) / len(rr),
        "bytes_per_chunk": dims * 2,  # halfvec: 2 bytes per dimension (D24)
        "cost_usd": doc_vectors.usage.cost_usd + q_vectors.usage.cost_usd,
    }


# ---------- report ----------


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def _fmt(value: float | None, unit: str = "", digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}{unit}"


def _mean(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return statistics.fmean(clean) if clean else None


def build_report(
    results: list[SummaryResult],
    reading: dict[str, dict[str, float | None]],
    embeddings: list[dict[str, Any]],
    *,
    indicative: bool,
    spent: float,
) -> str:
    lines = [f"# Benchmark report ({datetime.now(UTC):%Y-%m-%d %H:%M} UTC)", ""]
    if indicative:
        lines += [
            "> **Indicative only:** scored against unverified golden data.",
            "",
        ]
    lines += [f"Total spend: **${spent:.4f}**", "", "## Summary experiments", ""]
    lines += [
        "| Exp | Runs ok | Parse p50 | TTFT p50 | First field p50 / p95 | Total p50 / p95 "
        "| Cost / paper | Field recall | False found | Facts covered | Numbers grounded "
        "| Citations valid |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    by_exp: dict[str, list[SummaryResult]] = {}
    for r in results:
        by_exp.setdefault(r.experiment, []).append(r)
    for exp, rows in by_exp.items():
        ok = [r for r in rows if r.ok]
        first = [r.ttff_s for r in ok if r.ttff_s is not None]
        total = [r.total_s for r in ok]
        papers_n = len({r.paper for r in rows}) or 1
        runs_n = max(1, len(rows) // papers_n)
        lines.append(
            f"| {exp} | {len(ok)}/{len(rows)} | {_fmt(_pct([r.parse_s for r in ok], 0.5), 's')} "
            f"| {_fmt(_pct([r.ttft_s for r in ok if r.ttft_s is not None], 0.5), 's')} "
            f"| {_fmt(_pct(first, 0.5), 's')} / {_fmt(_pct(first, 0.95), 's')} "
            f"| {_fmt(_pct(total, 0.5), 's')} / {_fmt(_pct(total, 0.95), 's')} "
            f"| ${sum(r.cost_usd for r in rows) / papers_n / runs_n:.4f} "
            f"| {_fmt(_mean([r.scores.get('field_recall') for r in ok]))} "
            f"| {_fmt(_mean([r.scores.get('false_found') for r in ok]))} "
            f"| {_fmt(_mean([r.scores.get('numeric_accuracy') for r in ok]))} "
            f"| {_fmt(_mean([r.scores.get('numbers_grounded') for r in ok]))} "
            f"| {_fmt(_mean([r.scores.get('citation_valid') for r in ok]))} |"
        )
    lines += ["", "## Per paper (median over runs)", ""]
    lines += ["| Paper | Tier | Est. tokens | " + " | ".join(f"{e} total" for e in by_exp) + " |"]
    lines += ["|---|---|---|" + "---|" * len(by_exp)]
    for paper in sorted({r.paper for r in results}):
        rows = [r for r in results if r.paper == paper]
        cells = []
        for exp in by_exp:
            mine = [r for r in rows if r.experiment == exp]
            totals = [r.total_s for r in mine if r.ok]
            if totals:
                cells.append(_fmt(statistics.median(totals), "s"))
            elif mine:
                cells.append("failed: " + (mine[0].error or "")[:60])
            else:
                cells.append("n/a")
        tier = next((r.tier for r in rows if r.tier), "")
        tokens = max(r.est_tokens for r in rows)
        lines.append(f"| {paper} | {tier} | {tokens} | " + " | ".join(cells) + " |")
    if reading:
        lines += [
            "",
            "## Reading order (layout probes)",
            "",
            "| Parser | Probes passed |",
            "|---|---|",
        ]
        for parser, per_paper in reading.items():
            lines.append(f"| {parser} | {_fmt(_mean(list(per_paper.values())))} |")
    if embeddings:
        lines += [
            "",
            "## Embeddings (experiment E)",
            "",
            "| Config | hit@5 | MRR | Bytes / chunk | Cost |",
            "|---|---|---|---|---|",
        ]
        for name in dict.fromkeys(e["embedding"] for e in embeddings):
            rows_e = [e for e in embeddings if e["embedding"] == name]
            lines.append(
                f"| {name} | {_fmt(_mean([e['hit_at_5'] for e in rows_e]))} "
                f"| {_fmt(_mean([e['mrr'] for e in rows_e]))} | {rows_e[0]['bytes_per_chunk']} "
                f"| ${sum(e['cost_usd'] for e in rows_e):.5f} |"
            )
    lines += ["", "## Verdict", ""]
    lines += verdict(by_exp, reading, embeddings)
    return "\n".join(lines) + "\n"


def verdict(
    by_exp: dict[str, list[SummaryResult]],
    reading: dict[str, dict[str, float | None]],
    embeddings: list[dict[str, Any]],
) -> list[str]:
    """Rule-based statements with numbers. A contradiction means an EDP is needed."""
    out: list[str] = []

    def med(exp: str, attr: str) -> float | None:
        vals = [
            getattr(r, attr) for r in by_exp.get(exp, []) if r.ok and getattr(r, attr) is not None
        ]
        return statistics.median(vals) if vals else None

    def acc(exp: str) -> float | None:
        return _mean([r.scores.get("numeric_accuracy") for r in by_exp.get(exp, []) if r.ok])

    text_exps = [e for e in ("B", "B'", "B-fast") if e in by_exp]
    if "A" in by_exp and text_exps:
        best = min(text_exps, key=lambda e: med(e, "ttff_s") or float("inf"))
        a, t = med("A", "ttff_s"), med(best, "ttff_s")
        faster = a is not None and t is not None and t <= a
        out.append(
            f"- **D12 (two-path pipeline):** first field: direct PDF (A) {_fmt(a, 's')}, best text "
            f"pipeline ({best}) {_fmt(t, 's')}. "
            + (
                f"Our own extraction reaches first content sooner via {best}; "
                "compare its quality columns before changing the fast path."
                if faster
                else "Direct PDF is faster to first content; an EDP is needed."
            )
        )
    if "B" in by_exp and "B'" in by_exp:
        bp = "B'"
        read_b = _mean(list(reading.get("pymupdf", {}).values()))
        read_bp = _mean(list(reading.get("pdfium", {}).values()))
        parse_b, parse_bp = med("B", "parse_s"), med(bp, "parse_s")
        out.append(
            f"- **D19/D64 (parser):** reading order B {_fmt(read_b)} vs B' {_fmt(read_bp)}; "
            f"parse p50 B {_fmt(parse_b, 's')} vs B' {_fmt(parse_bp, 's')}; "
            f"numeric accuracy B {_fmt(acc('B'))} vs B' {_fmt(acc(bp))}."
        )
    tiers = [r for rows in by_exp.values() for r in rows if r.tier == "L"]
    if tiers:
        out.append(
            f"- **D20 (single call up to about 60k tokens):** {sum(r.ok for r in tiers)}/"
            f"{len(tiers)} tier-L runs succeeded in a single call."
        )
    if embeddings:

        def hit(name: str) -> float:
            return _mean([e["hit_at_5"] for e in embeddings if e["embedding"] == name]) or 0.0

        best = max(dict.fromkeys(e["embedding"] for e in embeddings), key=hit)
        out.append(f"- **D24 (embeddings):** best hit@5 is `{best}`.")
    return out or ["- Not enough data for a verdict."]


# ---------- CLI ----------


async def _main(
    experiments: list[str],
    ids: list[str] | None,
    include_unverified: bool,
    runs_override: int | None,
) -> int:
    config = load_config()
    gateway = build_gateway(config)
    guard = BudgetGuard(max_usd=float(os.environ.get("EVAL_MAX_USD", config["budget_usd"])))
    runs = runs_override or int(config["runs"])
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    run_dir = RUNS_DIR / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    raw = (run_dir / "results.jsonl").open("w")
    manifest = load_manifest()
    # Synthetic documents (e.g. the scanned ResNet) are scored against their source's golden data.
    golden_source = {s["id"]: s["source"] for s in manifest.get("synthetic", [])}
    papers = [p["id"] for p in manifest["papers"]] + list(golden_source)
    papers = [p for p in papers if not ids or p in ids]
    results: list[SummaryResult] = []
    reading: dict[str, dict[str, float | None]] = {}
    embedding_rows: list[dict[str, Any]] = []
    try:
        for paper in papers:
            pdf = PDF_DIR / f"{paper}.pdf"
            golden = load_golden(golden_source.get(paper, paper), include_unverified)
            reference = parse_pymupdf(pdf)
            for parser in {
                SUMMARY_EXPERIMENTS[e] for e in experiments if SUMMARY_EXPERIMENTS.get(e)
            }:
                assert parser is not None
                reading.setdefault(parser, {})[paper] = reading_order_score(
                    PARSERS[parser](pdf), golden
                )
            for exp in [e for e in experiments if e in SUMMARY_EXPERIMENTS]:
                for run in range(1, runs + 1):
                    result = await run_summary(
                        exp, paper, pdf, run, gateway, guard, golden, reference
                    )
                    results.append(result)
                    raw.write(json.dumps(asdict(result)) + "\n")
                    raw.flush()
                    status = "ok" if result.ok else f"FAILED {result.error}"
                    print(
                        f"  {exp:<6} {paper:<14} run {run}: "
                        f"{result.total_s:6.1f}s ${result.cost_usd:.4f} {status}"
                    )
            if "E" in experiments:
                for entry in embedding_entries(config):
                    try:
                        row = await run_embeddings(entry, paper, reference, golden, gateway, guard)
                    except BudgetExceededError:
                        raise
                    except Exception as exc:  # one failing config must not abort the run
                        failure = {"embedding": entry["name"], "paper": paper, "error": repr(exc)}
                        raw.write(json.dumps({"type": "embedding_error", **failure}) + "\n")
                        print(f"  E      {paper:<14} {entry['name']}: FAILED {exc!r}")
                        continue
                    if row:
                        embedding_rows.append(row)
                        raw.write(json.dumps({"type": "embedding", **row}) + "\n")
    except BudgetExceededError as exc:
        print(f"Stopped: {exc}. Partial results are recorded.")
    finally:
        raw.close()
        closer = getattr(gateway, "aclose", None)
        if closer is not None:
            await closer()
    report = build_report(
        results, reading, embedding_rows, indicative=include_unverified, spent=guard.spent_usd
    )
    REPORTS_DIR.mkdir(exist_ok=True)
    report_path = REPORTS_DIR / f"{stamp[:8]}-{'-'.join(experiments).replace(chr(39), 'p')}.md"
    report_path.write_text(report)
    print(f"Raw: {run_dir / 'results.jsonl'}\nReport: {report_path}\nSpent: ${guard.spent_usd:.4f}")
    return 0


def rescore(run_dir: Path, *, include_unverified: bool) -> int:
    """Re-score saved summaries against current golden data and metrics. Free: no LLM calls."""
    manifest = load_manifest()
    golden_source = {s["id"]: s["source"] for s in manifest.get("synthetic", [])}
    rows = [json.loads(line) for line in (run_dir / "results.jsonl").open()]
    results: list[SummaryResult] = []
    references: dict[str, ParsedDoc] = {}
    reading: dict[str, dict[str, float | None]] = {}
    for row in rows:
        if "experiment" not in row:
            continue
        result = SummaryResult(**row)
        paper = result.paper
        golden = load_golden(golden_source.get(paper, paper), include_unverified)
        if paper not in references:
            pdf = PDF_DIR / f"{paper}.pdf"
            references[paper] = parse_pymupdf(pdf)
            for parser_name in {v for v in SUMMARY_EXPERIMENTS.values() if v}:
                reading.setdefault(parser_name, {})[paper] = reading_order_score(
                    PARSERS[parser_name](pdf), golden
                )
        if result.ok and result.summary:
            result.scores = score_summary(result.summary, golden, references[paper])
        results.append(result)
    embeddings = [r for r in rows if r.get("type") == "embedding"]
    dims = {e["name"]: int(e["dimensions"]) for e in embedding_entries(load_config())}
    for e in embeddings:  # recompute with the current storage formula (halfvec)
        e["bytes_per_chunk"] = dims.get(e["embedding"], 0) * 2
    spent = sum(r.cost_usd for r in results) + sum(e.get("cost_usd", 0.0) for e in embeddings)
    report = build_report(results, reading, embeddings, indicative=include_unverified, spent=spent)
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"{run_dir.name[:8]}-rescored.md"
    path.write_text(report)
    print(f"Rescored report: {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run benchmark experiments")
    parser.add_argument("--exp", default="all", help="A, B, B', B-fast, E or all (comma separated)")
    parser.add_argument("--ids", nargs="*", help="paper ids (default: all)")
    parser.add_argument("--runs", type=int, help="override runs per paper")
    parser.add_argument("--include-unverified", action="store_true")
    parser.add_argument(
        "--rescore", metavar="RUN_DIR", help="recompute scores/report from saved results (no LLM)"
    )
    args = parser.parse_args(argv)
    if args.rescore:
        return rescore(Path(args.rescore), include_unverified=args.include_unverified)
    exps = (
        [*SUMMARY_EXPERIMENTS, "E"]
        if args.exp == "all"
        else [e.strip() for e in args.exp.split(",")]
    )
    unknown = [e for e in exps if e not in SUMMARY_EXPERIMENTS and e != "E"]
    if unknown:
        parser.error(f"unknown experiment(s): {unknown}")
    return asyncio.run(_main(exps, args.ids, args.include_unverified, args.runs))


if __name__ == "__main__":
    sys.exit(main())
