"""Content disarm and reconstruction, lite (D77, spec 004 AC11).

Rewrites the PDF from its parsed object graph without active content: document JavaScript,
OpenAction and additional actions (/AA), Launch and other executing actions, embedded files and
XFA forms. Rewriting also drops bytes outside the object graph (data appended after %%EOF,
polyglot tricks, stale incremental updates). What was removed is reported, not treated as an
error: many ordinary papers carry harmless leftovers from their authoring tools. Counts are
indicative (an object reachable twice may be counted twice).
"""

import io
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pikepdf
from pikepdf import Dictionary

# Actions that run code, open other files or programs, or send data somewhere.
DANGEROUS_ACTIONS = frozenset(
    {
        "/JavaScript",
        "/Launch",
        "/ImportData",
        "/SubmitForm",
        "/GoToE",
        "/RichMediaExecute",
        "/Rendition",
        "/Sound",
        "/Movie",
    }
)


class PdfRejectedError(Exception):
    """The file cannot be processed; `user_message` is safe to show."""

    def __init__(self, user_message: str, reason: str) -> None:
        super().__init__(reason)
        self.user_message = user_message
        self.reason = reason


@dataclass(frozen=True)
class SanitizedPdf:
    data: bytes
    pages: int
    removed: dict[str, int] = field(default_factory=dict)


def walk(root: object) -> Iterator[Any]:
    """Every dictionary and stream reachable from `root`, direct or indirect, each once."""
    stack: list[Any] = [root]
    seen: set[tuple[int, int]] = set()
    while stack:
        obj = stack.pop()
        if isinstance(obj, (Dictionary, pikepdf.Stream, pikepdf.Array)):
            if obj.is_indirect:
                if obj.objgen in seen:
                    continue
                seen.add(obj.objgen)
            if isinstance(obj, pikepdf.Array):
                stack.extend(obj)
                continue
            yield obj
            stack.extend(obj.get(key) for key in list(obj.keys()))


def _is_dangerous_action(obj: object) -> bool:
    return isinstance(obj, Dictionary) and str(obj.get("/S", "")) in DANGEROUS_ACTIONS


def sanitize(data: bytes, *, max_pages: int) -> SanitizedPdf:
    try:
        pdf = pikepdf.open(io.BytesIO(data))
    except pikepdf.PasswordError as exc:
        raise PdfRejectedError(
            "This PDF is password-protected. Please upload a copy without a password.",
            "encrypted",
        ) from exc
    except pikepdf.PdfError as exc:
        raise PdfRejectedError("This PDF is damaged and cannot be read.", "unreadable") from exc

    with pdf:
        if pdf.is_encrypted:
            # Opened with an empty user password but restricted: still treat as protected.
            raise PdfRejectedError(
                "This PDF is password-protected. Please upload a copy without a password.",
                "encrypted",
            )
        pages = len(pdf.pages)
        if pages == 0:
            raise PdfRejectedError("This PDF has no pages.", "no-pages")
        if pages > max_pages:
            raise PdfRejectedError(
                f"This PDF has {pages} pages. The limit is {max_pages} pages.", "too-many-pages"
            )

        removed: Counter[str] = Counter()
        root = pdf.Root
        # A plain destination ("open at page 1") is harmless and very common; only an action
        # other than GoTo is removed.
        open_action = root.get("/OpenAction")
        if isinstance(open_action, Dictionary) and str(open_action.get("/S", "")) != "/GoTo":
            del root.OpenAction
            removed["open_action"] += 1
        if "/AA" in root:
            del root.AA
            removed["additional_actions"] += 1
        names = root.get("/Names")
        if isinstance(names, Dictionary):
            for key, label in (("/JavaScript", "javascript"), ("/EmbeddedFiles", "embedded_files")):
                if key in names:
                    del names[key]
                    removed[label] += 1
        acroform = root.get("/AcroForm")
        if isinstance(acroform, Dictionary) and "/XFA" in acroform:
            del acroform.XFA
            removed["xfa_forms"] += 1

        for page in pdf.pages:
            page_obj = page.obj
            if "/AA" in page_obj:
                del page_obj.AA
                removed["additional_actions"] += 1
            annots = page_obj.get("/Annots")
            if annots is None:
                continue
            kept = pikepdf.Array()
            for annot in annots:
                if str(annot.get("/Subtype", "")) == "/FileAttachment":
                    removed["embedded_files"] += 1
                    continue
                if _is_dangerous_action(annot.get("/A")):
                    del annot.A
                    removed["actions"] += 1
                if "/AA" in annot:
                    del annot.AA
                    removed["additional_actions"] += 1
                kept.append(annot)
            page_obj.Annots = kept

        # Anything left anywhere in the graph (form fields, outlines, nested /Next chains).
        # Collected first, then changed, so the walk never sees a half-edited graph.
        actions, with_aa = [], []
        for obj in walk(pdf.trailer):
            if isinstance(obj, Dictionary) and (_is_dangerous_action(obj) or "/JS" in obj):
                actions.append(obj)
            elif "/AA" in obj:
                with_aa.append(obj)
        for obj in actions:
            for key in list(obj.keys()):
                del obj[key]
            removed["actions"] += 1
        for obj in with_aa:
            del obj.AA
            removed["additional_actions"] += 1

        out = io.BytesIO()
        pdf.remove_unreferenced_resources()
        pdf.save(out, linearize=False)
    return SanitizedPdf(data=out.getvalue(), pages=pages, removed=dict(removed))
