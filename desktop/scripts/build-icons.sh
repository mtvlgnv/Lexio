#!/usr/bin/env bash
set -euo pipefail

SRC="build/icon.png"
SET="build/icon.iconset"

[ -f "$SRC" ] || { echo "Error: $SRC not found. Run 'npm run create-icon' first." >&2; exit 1; }

mkdir -p "$SET"

resize() { sips -z "$1" "$2" "$SRC" --out "$SET/$3"; }

resize 16  16  "icon_16x16.png"
resize 32  32  "icon_16x16@2x.png"
resize 32  32  "icon_32x32.png"
resize 64  64  "icon_32x32@2x.png"
resize 128 128 "icon_128x128.png"
resize 256 256 "icon_128x128@2x.png"
resize 256 256 "icon_256x256.png"
resize 512 512 "icon_256x256@2x.png"
resize 512 512 "icon_512x512.png"
cp "$SRC"      "$SET/icon_512x512@2x.png"

iconutil -c icns "$SET" -o build/icon.icns
echo "✓ build/icon.icns ready"
