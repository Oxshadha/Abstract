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
