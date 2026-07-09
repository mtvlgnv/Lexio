#!/usr/bin/env python3
"""
Lexio Glance — app compatibility tester.

Opens each target app with a known paragraph, selects the target word
("adventitious"), runs ax-reader.py at the current cursor, and scores
whether surrounding context was captured.

Usage: python3 scripts/test-app-compat.py [--apps Safari,TextEdit]
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
AX_READER = ROOT / "lib" / "ax-reader.py"

TARGET = "adventitious"
PARAGRAPH = (
    "The adventitious growth rings visible in the cross-section "
    "revealed centuries of environmental stress."
)
MIN_FULL_CONTEXT = 55  # full sentence is ~95 chars

TEST_HTML = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Lexio test</title>
<style>body{{font:18px Georgia;max-width:640px;margin:48px auto;line-height:1.6}}</style>
</head><body><p id="p">{PARAGRAPH}</p></body></html>"""

TEST_TXT = PARAGRAPH + "\n"


def run(cmd, timeout=12, **kwargs):
    kwargs.setdefault("text", True)
    return subprocess.run(
        cmd, capture_output=True, timeout=timeout, **kwargs
    )


def pbcopy(text):
    run(["pbcopy"], input=text)


def osa(script, timeout=20):
    r = run(["osascript", "-e", script], timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip() or "osascript failed")
    return r.stdout.strip()


def mouse_screen_point():
    """Top-left origin, matching Electron screen.getCursorScreenPoint()."""
    script = r"""
import ctypes, ctypes.util
cg = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreGraphics"))
CoreGraphics = cg

class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

CoreGraphics.CGEventCreate.restype = ctypes.c_void_p
CoreGraphics.CGEventGetLocation.restype = CGPoint
CoreGraphics.CGEventGetLocation.argtypes = [ctypes.c_void_p]
CoreGraphics.CGMainDisplayID.restype = ctypes.c_uint32
CoreGraphics.CGDisplayPixelsHigh.restype = ctypes.c_size_t
CoreGraphics.CGDisplayPixelsHigh.argtypes = [ctypes.c_uint32]

ev = CoreGraphics.CGEventCreate(None)
loc = CoreGraphics.CGEventGetLocation(ev)
h = CoreGraphics.CGDisplayPixelsHigh(CoreGraphics.CGMainDisplayID())
print(f"{loc.x:.0f},{h - loc.y:.0f}")
"""
    r = run([sys.executable, "-c", script], timeout=5)
    if r.returncode != 0:
        raise RuntimeError("mouse position failed: " + r.stderr)
    x, y = r.stdout.strip().split(",")
    return float(x), float(y)


def ax_read(cursor=None):
    args = [str(AX_READER)]
    if cursor:
        args += [str(int(cursor[0])), str(int(cursor[1]))]
    r = run([sys.executable] + args, timeout=5)
    stderr = r.stderr or ""
    stdout = (r.stdout or "").strip()
    strategy = None
    for line in stderr.splitlines():
        if "strategy:" in line:
            strategy = line.split("strategy:", 1)[1].strip()
    return stdout, strategy, stderr


def score_context(text):
    if not text:
        return "empty", 0, ""
    n = len(text)
    low = text.lower()
    t = TARGET.lower()
    if t not in low:
        return "no_match", n, text[:120]
    idx = low.index(t)
    before = text[:idx].strip()
    after = text[idx + len(TARGET):].strip()
    if n >= MIN_FULL_CONTEXT and before and after:
        return "full", n, text[:120]
    if n > len(TARGET) + 5:
        return "partial", n, text[:120]
    if n <= len(TARGET) + 3:
        return "selection_only", n, text[:120]
    return "partial", n, text[:120]


def app_running(name):
    try:
        osa(f'tell application "System Events" to (name of processes) contains "{name}"')
        return True
    except Exception:
        return False


def select_via_find(app_process, word=TARGET):
    """Cmd+F → word → Return; works in most Cocoa/Chromium text views."""
    osa(f'''
        tell application "System Events"
            tell process "{app_process}"
                set frontmost to true
                delay 0.25
                keystroke "f" using command down
                delay 0.35
                keystroke "{word}"
                delay 0.2
                key code 36
                delay 0.35
            end tell
        end tell
    ''')


def write_fixture_files(tmp):
    html = tmp / "lexio-test.html"
    txt = tmp / "lexio-test.txt"
    html.write_text(TEST_HTML, encoding="utf-8")
    txt.write_text(TEST_TXT, encoding="utf-8")
    return html, txt


@dataclass
class Result:
    app: str
    category: str
    status: str  # full | partial | selection_only | empty | no_match | error | skipped
    chars: int
    strategy: Optional[str]
    notes: str
    installed: bool = True
    sample: str = ""


def make_result(app, category, text, strategy, notes, installed=True):
    status, chars, sample = score_context(text)
    return Result(app, category, status, chars, strategy, notes, installed, sample)


def test_textedit(html_path, txt_path):
    osa(f'''
        tell application "TextEdit"
            activate
            if (count of documents) = 0 then make new document
            set text of front document to "{PARAGRAPH}"
        end tell
    ''')
    time.sleep(0.6)
    select_via_find("TextEdit")
    time.sleep(0.2)
    cursor = mouse_screen_point()
    text, strategy, _ = ax_read(cursor)
    return make_result("TextEdit", "native", text, strategy, "plain text editor")


def test_safari(html_path, _):
    osa(f'''
        tell application "Safari"
            activate
            if (count of windows) = 0 then make new document
            set URL of front document to "file://{html_path}"
        end tell
    ''')
    time.sleep(1.8)
    select_via_find("Safari")
    time.sleep(0.3)
    cursor = mouse_screen_point()
    text, strategy, _ = ax_read(cursor)
    return make_result("Safari", "browser", text, strategy, "local HTML via file://")


def test_chrome(html_path, _):
    chrome = "/Applications/Google Chrome 2.app"
    if not Path(chrome).exists():
        return Result("Google Chrome", "browser", "skipped", 0, None, "not installed", False)
    osa(f'''
        tell application "Google Chrome 2"
            activate
            if (count of windows) = 0 then make new window
            set URL of active tab of front window to "file://{html_path}"
        end tell
    ''')
    time.sleep(2.0)
    select_via_find("Google Chrome")
    time.sleep(0.4)
    cursor = mouse_screen_point()
    text, strategy, _ = ax_read(cursor)
    return make_result("Google Chrome", "chromium", text, strategy, "Chromium AX tree flip required")


def test_notes(_a, _b):
    osa(f'''
        tell application "Notes"
            activate
            delay 0.5
        end tell
    ''')
    # Notes resists pure AppleScript text injection — type via clipboard.
    pbcopy(PARAGRAPH)
    osa('''
        tell application "System Events"
            tell process "Notes"
                set frontmost to true
                delay 0.4
                keystroke "n" using command down
                delay 0.8
                keystroke "v" using command down
                delay 0.5
            end tell
        end tell
    ''')
    select_via_find("Notes")
    time.sleep(0.3)
    cursor = mouse_screen_point()
    text, strategy, _ = ax_read(cursor)
    return make_result("Notes", "native", text, strategy, "new note via paste")


def test_vscode(_a, txt_path):
    if not Path("/Applications/Visual Studio Code.app").exists():
        return Result("VS Code", "electron", "skipped", 0, None, "not installed", False)
    run(["open", "-a", "Visual Studio Code", str(txt_path)])
    time.sleep(2.5)
    osa('tell application "System Events" to tell process "Code" to key code 53')
    time.sleep(0.2)
    select_via_find("Code")
    time.sleep(0.4)
    cursor = mouse_screen_point()
    text, strategy, _ = ax_read(cursor)
    return make_result("VS Code", "electron", text, strategy, "editor buffer")


def test_cursor(_a, txt_path):
    if not Path("/Applications/Cursor.app").exists():
        return Result("Cursor", "electron", "skipped", 0, None, "not installed", False)
    run(["open", "-a", "Cursor", str(txt_path)])
    time.sleep(3.0)
    osa('tell application "System Events" to tell process "Cursor" to key code 53')
    time.sleep(0.2)
    select_via_find("Cursor")
    time.sleep(0.4)
    cursor = mouse_screen_point()
    text, strategy, _ = ax_read(cursor)
    return make_result("Cursor", "electron", text, strategy, "Electron IDE")


def test_discord(_a, _b):
    if not Path("/Applications/Discord.app").exists():
        return Result("Discord", "electron", "skipped", 0, None, "not installed", False)
    run(["open", "-a", "Discord"])
    time.sleep(4.0)
    # Paste into message box if focused; best-effort.
    pbcopy(PARAGRAPH)
    osa('''
        tell application "System Events"
            tell process "Discord"
                set frontmost to true
                delay 0.5
                keystroke "v" using command down
                delay 0.4
            end tell
        end tell
    ''')
    select_via_find("Discord")
    time.sleep(0.3)
    cursor = mouse_screen_point()
    text, strategy, _ = ax_read(cursor)
    return make_result("Discord", "electron", text, strategy, "message compose field")


def test_terminal(_a, _b):
    run(["open", "-a", "Terminal"])
    time.sleep(1.2)
    pbcopy(f"echo '{PARAGRAPH}'\n")
    osa('''
        tell application "System Events"
            tell process "Terminal"
                set frontmost to true
                delay 0.3
                keystroke "v" using command down
                key code 36
                delay 0.3
            end tell
        end tell
    ''')
    time.sleep(0.3)
    cursor = mouse_screen_point()
    text, strategy, _ = ax_read(cursor)
    return make_result("Terminal", "terminal", text, strategy, "shell echo output")


def test_pages(_a, _b):
    if not Path("/Applications/Pages.app").exists():
        return Result("Pages", "iwork", "skipped", 0, None, "not installed", False)
    run(["open", "-a", "Pages"])
    time.sleep(2.5)
    pbcopy(PARAGRAPH)
    osa('''
        tell application "System Events"
            tell process "Pages"
                set frontmost to true
                delay 0.5
                keystroke "v" using command down
                delay 0.5
            end tell
        end tell
    ''')
    select_via_find("Pages")
    time.sleep(0.3)
    cursor = mouse_screen_point()
    text, strategy, _ = ax_read(cursor)
    return make_result("Pages", "iwork", text, strategy, "document body")


def test_mail(_a, _b):
    run(["open", "-a", "Mail"])
    time.sleep(2.0)
    osa('''
        tell application "System Events"
            tell process "Mail"
                set frontmost to true
                delay 0.3
                keystroke "n" using command down
                delay 1.0
            end tell
        end tell
    ''')
    pbcopy(PARAGRAPH)
    osa('''
        tell application "System Events"
            tell process "Mail"
                keystroke "v" using command down
                delay 0.5
            end tell
        end tell
    ''')
    select_via_find("Mail")
    time.sleep(0.3)
    cursor = mouse_screen_point()
    text, strategy, _ = ax_read(cursor)
    return make_result("Mail", "native", text, strategy, "compose window")


def test_preview(_a, txt_path):
    run(["open", "-a", "Preview", str(txt_path)])
    time.sleep(1.5)
    select_via_find("Preview")
    time.sleep(0.3)
    cursor = mouse_screen_point()
    text, strategy, _ = ax_read(cursor)
    return make_result("Preview", "pdf/text", text, strategy, "plain .txt in Preview")


def test_antigravity(_a, txt_path):
    if not Path("/Applications/Antigravity.app").exists():
        return Result("Antigravity", "electron", "skipped", 0, None, "not installed", False)
    run(["open", "-a", "Antigravity", str(txt_path)])
    time.sleep(3.0)
    select_via_find("Antigravity")
    time.sleep(0.4)
    cursor = mouse_screen_point()
    text, strategy, _ = ax_read(cursor)
    return make_result("Antigravity", "electron", text, strategy, "Electron app")


def test_telegram(_a, _b):
    if not Path("/Applications/Telegram.app").exists():
        return Result("Telegram", "native", "skipped", 0, None, "not installed", False)
    run(["open", "-a", "Telegram"])
    time.sleep(3.0)
    pbcopy(PARAGRAPH)
    osa('''
        tell application "System Events"
            tell process "Telegram"
                set frontmost to true
                delay 0.5
                keystroke "v" using command down
                delay 0.4
            end tell
        end tell
    ''')
    select_via_find("Telegram")
    time.sleep(0.3)
    cursor = mouse_screen_point()
    text, strategy, _ = ax_read(cursor)
    return make_result("Telegram", "native", text, strategy, "compose field")


def test_whatsapp(_a, _b):
    if not Path("/Applications/WhatsApp.app").exists():
        return Result("WhatsApp", "electron", "skipped", 0, None, "not installed", False)
    run(["open", "-a", "WhatsApp"])
    time.sleep(3.0)
    pbcopy(PARAGRAPH)
    osa('''
        tell application "System Events"
            tell process "WhatsApp"
                set frontmost to true
                delay 0.5
                keystroke "v" using command down
                delay 0.4
            end tell
        end tell
    ''')
    select_via_find("WhatsApp")
    time.sleep(0.3)
    cursor = mouse_screen_point()
    text, strategy, _ = ax_read(cursor)
    return make_result("WhatsApp", "electron", text, strategy, "message field")


TESTS = [
    ("TextEdit", test_textedit),
    ("Safari", test_safari),
    ("Google Chrome", test_chrome),
    ("Notes", test_notes),
    ("VS Code", test_vscode),
    ("Cursor", test_cursor),
    ("Antigravity", test_antigravity),
    ("Discord", test_discord),
    ("Mail", test_mail),
    ("Pages", test_pages),
    ("Preview", test_preview),
    ("Terminal", test_terminal),
    ("Telegram", test_telegram),
    ("WhatsApp", test_whatsapp),
]


def main():
    if not AX_READER.exists():
        print(f"Missing {AX_READER}", file=sys.stderr)
        sys.exit(1)

    trust = run([sys.executable, "-c",
        "import ctypes,ctypes.util; AX=ctypes.cdll.LoadLibrary(ctypes.util.find_library('ApplicationServices')); exit(0 if AX.AXIsProcessTrusted() else 1)"])
    if trust.returncode != 0:
        print("ERROR: Terminal/python needs Accessibility permission for this test.", file=sys.stderr)
        sys.exit(2)

    filter_apps = None
    if len(sys.argv) > 1 and sys.argv[1] == "--apps":
        filter_apps = {a.strip().lower() for a in sys.argv[2].split(",")}

    tmp = Path(tempfile.mkdtemp(prefix="lexio-compat-"))
    html_path, txt_path = write_fixture_files(tmp)
    print(f"Fixtures: {html_path}", flush=True)

    results = []
    for name, fn in TESTS:
        if filter_apps and name.lower() not in filter_apps:
            continue
        print(f"\n── Testing {name}…", flush=True)
        try:
            r = fn(html_path, txt_path)
            results.append(r)
            sample = ""
            if r.status not in ("full", "skipped") and r.sample:
                sample = f'  sample="{r.sample[:60]}…"'
            print(f"   {r.status:16} {r.chars:4} chars  strategy={r.strategy or '-'}{sample}  ({r.notes})", flush=True)
        except Exception as e:
            results.append(Result(name, "?", "error", 0, None, str(e)[:120]))
            print(f"   error: {e}", flush=True)
        time.sleep(0.8)

    # Summary
    full = [r for r in results if r.status == "full"]
    partial = [r for r in results if r.status == "partial"]
    broken = [r for r in results if r.status in ("selection_only", "empty", "no_match", "error")]
    skipped = [r for r in results if r.status == "skipped"]

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Full context ({len(full)}):  {', '.join(r.app for r in full) or '—'}")
    print(f"Partial ({len(partial)}):     {', '.join(r.app for r in partial) or '—'}")
    print(f"Broken ({len(broken)}):    {', '.join(r.app for r in broken) or '—'}")
    print(f"Skipped ({len(skipped)}):   {', '.join(r.app for r in skipped) or '—'}")

    out = tmp / "results.json"
    out.write_text(json.dumps([asdict(r) for r in results], indent=2), encoding="utf-8")
    print(f"\nJSON: {out}")


if __name__ == "__main__":
    main()