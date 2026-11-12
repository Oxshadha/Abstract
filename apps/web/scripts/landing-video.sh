#!/usr/bin/env bash
# Spec 016 (D94): cut the recorded demo and encode it for the landing page.
#   scripts/landing-video.sh [outDir]
# Needs ffmpeg with libx264. Writes demo.mp4 (H.264, plays in every browser) and
# demo-poster.webp (the first frame), muted, 1280 px wide.
set -euo pipefail
out="${1:-public/landing}"
read -r start end < <(python3 -c "import json;d=json.load(open('$out/demo-cut.json'));print(d['start'], d['end'])")
filters="scale=1280:-2:flags=lanczos,fps=30"
ffmpeg -loglevel error -y -ss "$start" -to "$end" -i "$out/demo-raw.webm" -an \
  -vf "$filters" -c:v libx264 -preset slow -crf 26 -pix_fmt yuv420p -movflags +faststart "$out/demo.mp4"
ffmpeg -loglevel error -y -ss "$start" -i "$out/demo-raw.webm" -frames:v 1 -vf "scale=1280:-2" "$out/demo-poster.png"
python3 -c "from PIL import Image; Image.open('$out/demo-poster.png').convert('RGB').save('$out/demo-poster.webp', 'WEBP', quality=80)" 2>/dev/null \
  || uv run --project ../api python -c "from PIL import Image; Image.open('$out/demo-poster.png').convert('RGB').save('$out/demo-poster.webp', 'WEBP', quality=80)"
rm -rf "$out/demo-poster.png" "$out/demo-raw.webm" "$out/demo-cut.json" "$out/.video"
ls -la "$out"/demo*
