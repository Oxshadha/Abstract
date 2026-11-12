"""Spec 016 (D93): turn the Workspace screenshots into the landing page's images.

    uv run --project ../api python scripts/landing-images.py public/landing

WebP at 1600 and 960 px wide for both themes, and a 1200 x 630 Open Graph image (light).
"""

import sys
from pathlib import Path

from PIL import Image

out = Path(sys.argv[1] if len(sys.argv) > 1 else "public/landing")
for theme in ("light", "dark"):
    source = out / f"workspace-{theme}.png"
    image = Image.open(source).convert("RGB")
    for width in (1600, 960):
        height = round(image.height * width / image.width)
        image.resize((width, height), Image.LANCZOS).save(
            out / f"workspace-{theme}-{width}.webp", "WEBP", quality=82, method=6
        )
    if theme == "light":
        og = image.resize((1200, 750), Image.LANCZOS).crop((0, 0, 1200, 630))
        og.save(out / "og.png", "PNG", optimize=True)
    source.unlink()
print(sorted(p.name for p in out.iterdir()))
