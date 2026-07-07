#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
OUT="../bin/lexio-ocr"
mkdir -p "$(dirname "$OUT")"

swiftc -O -o "$OUT" lexio-ocr/main.swift \
  -framework AppKit -framework CoreGraphics -framework ScreenCaptureKit
chmod +x "$OUT"

# ── Code signing (this is what broke Glance 1.2.0 and got it reverted) ──────
# swiftc leaves the binary ad-hoc signed. In a NOTARIZED build, every nested
# Mach-O must carry a Developer ID signature + hardened runtime + a secure
# timestamp, or Apple's notary service rejects the ENTIRE app (not just this
# binary). Ad-hoc = rejection. So sign it properly here, before electron-
# builder packages it.
#
# Uses the first "Developer ID Application" identity in the keychain (override
# with LEXIO_SIGN_IDENTITY). Falls back to ad-hoc when no Developer ID is
# present (local dev / unnotarized runs, where ad-hoc is fine).
IDENTITY="${LEXIO_SIGN_IDENTITY:-}"
if [ -z "$IDENTITY" ] && security find-identity -v -p codesigning 2>/dev/null | grep -q "Developer ID Application"; then
  IDENTITY="Developer ID Application"
fi

if [ -n "$IDENTITY" ]; then
  codesign --force --options runtime --timestamp --sign "$IDENTITY" "$OUT"
  echo "✓ $OUT (Developer ID + hardened runtime + timestamp)"
else
  codesign --force --sign - "$OUT"
  echo "✓ $OUT (ad-hoc — dev only; no Developer ID in keychain, NOT notarizable)"
fi
