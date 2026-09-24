#!/usr/bin/env bash
# Rasterise the docs diagrams. SVG is the source; GitHub renders PNG more
# predictably in a README, so both are committed.
set -euo pipefail
cd "$(dirname "$0")/.."
CHROME="${CHROME:-/opt/pw-browsers/chromium-1194/chrome-linux/chrome}"
SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT

python3 tools/page_diagram.py

for svg in docs/img/page-*.svg; do
  png="${svg%.svg}.png"
  read -r w h < <(python3 - "$svg" <<'PY'
import re, sys
head = open(sys.argv[1]).read(400)
print(re.search(r'width="(\d+)"', head).group(1),
      re.search(r'height="(\d+)"', head).group(1))
PY
)
  # Wrap the SVG in a page whose background matches it: the viewport is given
  # slack so a large embedded screenshot is never clipped mid-decode, and the
  # slack is invisible rather than a white band.
  cat > "$SCRATCH/wrap.html" <<HTML
<html><body style="margin:0;background:#141416">
<img src="page-$(basename "${svg%.svg}" | sed 's/^page-//').svg" width="$w" height="$h" style="display:block">
</body></html>
HTML
  cp "$SCRATCH/wrap.html" docs/img/.wrap.html
  "$CHROME" --headless --disable-gpu --no-sandbox --hide-scrollbars \
    --virtual-time-budget=8000 --window-size="$w,$((h + 40))" \
    --screenshot="$png" "file://$PWD/docs/img/.wrap.html" 2>/dev/null
  rm -f docs/img/.wrap.html
  echo "wrote $png (${w}x$((h + 40)))"
done
