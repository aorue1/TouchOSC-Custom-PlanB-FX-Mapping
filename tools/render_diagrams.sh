#!/usr/bin/env bash
# Rasterise the docs diagrams. SVG is the source; GitHub renders PNG more
# predictably in a README, so both are committed.
set -euo pipefail
cd "$(dirname "$0")/.."
CHROME="${CHROME:-/opt/pw-browsers/chromium-1194/chrome-linux/chrome}"

python3 tools/page_diagram.py

for svg in docs/img/page-*.svg; do
  png="${svg%.svg}.png"
  # Size the window to the SVG so the PNG has no dead margin.
  read -r w h < <(python3 - "$svg" <<'PY'
import re, sys
head = open(sys.argv[1]).read(400)
w = re.search(r'width="(\d+)"', head).group(1)
h = re.search(r'height="(\d+)"', head).group(1)
print(int(w) + 16, int(h) + 60)
PY
)
  "$CHROME" --headless --disable-gpu --no-sandbox --hide-scrollbars \
    --window-size="$w,$h" --screenshot="$png" "file://$PWD/$svg" 2>/dev/null
  echo "wrote $png (${w}x${h})"
done
