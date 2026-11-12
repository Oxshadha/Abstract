"""Build small, real PDFs for tests (the eval corpus is not in git)."""

import io

import pikepdf
from pikepdf import Array, Dictionary, Name, Pdf, String


def _escape(line: str) -> str:
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _content(lines: list[str]) -> bytes:
    ops = ["BT", "/F1 11 Tf", "14 TL", "72 760 Td"]
    for line in lines:
        ops.append(f"({_escape(line)}) Tj T*")
    ops.append("ET")
    return "\n".join(ops).encode("latin-1")


def make_pdf(
    pages: list[list[str]] | None = None,
    *,
    title: str | None = None,
    javascript: bool = False,
    open_action: bool = False,
    launch: bool = False,
    embedded_file: bool = False,
    page_aa: bool = False,
    password: str | None = None,
    trailing_garbage: bytes = b"",
) -> bytes:
    """One page per entry; an empty list makes a page with no text layer."""
    pdf = Pdf.new()
    font = pdf.make_indirect(
        Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica)
    )
    for lines in pages if pages is not None else [["Hello world"]]:
        page = pikepdf.Page(
            Dictionary(
                Type=Name.Page,
                MediaBox=Array([0, 0, 612, 792]),
                Resources=Dictionary(Font=Dictionary(F1=font)),
                Contents=pdf.make_stream(_content(lines) if lines else b""),
            )
        )
        pdf.pages.append(page)
    if title:
        pdf.docinfo[Name.Title] = String(title)
    root = pdf.Root
    if javascript:
        js = pdf.make_indirect(Dictionary(S=Name.JavaScript, JS=String("app.alert('x')")))
        root.Names = Dictionary(JavaScript=Dictionary(Names=Array([String("a"), js])))
    if open_action:
        root.OpenAction = Dictionary(S=Name.JavaScript, JS=String("app.alert('open')"))
    if launch:
        pdf.pages[0].obj.Annots = Array(
            [
                pdf.make_indirect(
                    Dictionary(
                        Type=Name.Annot,
                        Subtype=Name.Link,
                        Rect=Array([0, 0, 10, 10]),
                        A=Dictionary(S=Name.Launch, F=String("calc.exe")),
                    )
                )
            ]
        )
    if embedded_file:
        stream = pdf.make_stream(b"MZ fake executable")
        stream.Type = Name.EmbeddedFile
        spec = Dictionary(Type=Name.Filespec, F=String("a.exe"), EF=Dictionary(F=stream))
        names = root.get("/Names", Dictionary())
        names.EmbeddedFiles = Dictionary(Names=Array([String("a.exe"), spec]))
        root.Names = names
    if page_aa:
        pdf.pages[0].obj.AA = Dictionary(
            O=Dictionary(S=Name.JavaScript, JS=String("app.alert('page')"))
        )
    out = io.BytesIO()
    if password:
        pdf.save(out, encryption=pikepdf.Encryption(owner=password, user=password))
    else:
        pdf.save(out)
    return out.getvalue() + trailing_garbage


def make_scanned_pdf(lines: list[str]) -> bytes:
    """An image-only page (no text layer), like a scan: render a text page, embed the picture."""
    import pypdfium2 as pdfium

    page = pdfium.PdfDocument(make_pdf([lines]))[0]
    image = page.render(scale=200 / 72).to_pil().convert("RGB")
    out = io.BytesIO()
    image.save(out, "PDF", resolution=200)
    return out.getvalue()


def _table_ops(top: int, rows: int, cols: int) -> list[str]:
    """Ruled grid: horizontal and vertical lines like a typical results table."""
    left, width, height = 72, 400, 18
    ops = ["0.5 w"]
    for r in range(rows + 1):
        y = top - r * height
        ops.append(f"{left} {y} m {left + width} {y} l S")
    for c in range(cols + 1):
        x = left + c * width // cols
        ops.append(f"{x} {top} m {x} {top - rows * height} l S")
    return ops


def make_rich_pdf(pages: list[dict[str, object]]) -> bytes:
    """Pages with optional text lines, a ruled table and an embedded picture, for enrichment
    tests. Each entry: {"lines": [...], "table": [[cells...], ...] | None, "image": bool}."""
    from PIL import Image

    pdf = Pdf.new()
    font = pdf.make_indirect(
        Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica)
    )
    for spec in pages:
        lines = [str(x) for x in spec.get("lines", [])]  # type: ignore[attr-defined]
        ops = _content(lines).decode("latin-1").split("\n") if lines else []
        resources = Dictionary(Font=Dictionary(F1=font))
        table = spec.get("table")
        if isinstance(table, list) and table:
            top = 600
            ops += _table_ops(top, len(table), len(table[0]))
            ops += ["BT", "/F1 9 Tf"]
            for r, row in enumerate(table):
                for c, cell in enumerate(row):
                    x = 76 + c * 400 // len(row)
                    y = top - r * 18 - 13
                    ops.append(f"1 0 0 1 {x} {y} Tm ({_escape(str(cell))}) Tj")
            ops.append("ET")
        if spec.get("image"):
            picture = Image.new("RGB", (240, 160), (40, 90, 160))
            raw = picture.tobytes()
            xobj = pdf.make_stream(raw)
            xobj.Type, xobj.Subtype = Name.XObject, Name.Image
            xobj.Width, xobj.Height, xobj.BitsPerComponent = 240, 160, 8
            xobj.ColorSpace = Name.DeviceRGB
            resources.XObject = Dictionary(Im1=xobj)
            ops += ["q 240 0 0 160 72 200 cm /Im1 Do Q"]
        page = pikepdf.Page(
            Dictionary(
                Type=Name.Page,
                MediaBox=Array([0, 0, 612, 792]),
                Resources=resources,
                Contents=pdf.make_stream("\n".join(ops).encode("latin-1")),
            )
        )
        pdf.pages.append(page)
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()
