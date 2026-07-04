#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
OUT="../bin/lexio-ocr"
mkdir -p "$(dirname "$OUT")"
swiftc -O -o "$OUT" lexio-ocr/main.swift \
  -framework AppKit -framework CoreGraphics -framework Vision -framework ScreenCaptureKit
chmod +x "$OUT"
echo "✓ $OUT"