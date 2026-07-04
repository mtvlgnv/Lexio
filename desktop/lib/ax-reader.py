#!/usr/bin/env python3
"""
ax-reader.py — Fast, reliable AX text reader for Lexio Glance.

Calls the macOS Accessibility API directly via ctypes (system Python only,
no pip packages). Prints the text surrounding the user's selection to
stdout; diagnostics go to stderr (surfaced in the app log by context.js).

Usage: ax-reader.py [cursorX cursorY]
  The cursor position (global screen coords, top-left origin — exactly what
  Electron's screen.getCursorScreenPoint() returns) anchors the
  element-at-position strategy: the user just selected a word THERE, so the
  deepest AX element under that point is almost always the text node
  containing it — far more reliable than focus-based lookups in web pages
  and web-like views, where the "focused" element is often a giant
  container or nothing at all.

HARD-WON PLATFORM NOTES (do not "simplify" these away):

1. AXUIElementCreateSystemWide() is USELESS from spawned child processes on
   current macOS — every attribute read returns kAXErrorCannotComplete
   (-25204) even with AXIsProcessTrusted() == true. This was the root cause
   of this script silently returning nothing for every app: the previous
   version's very first call (system-wide AXFocusedUIElement) always failed
   and it exited without a word of diagnostics. App-scoped elements
   (AXUIElementCreateApplication(pid)) work fine from the same process.
   Same finding reproduced via osascript/JXA earlier — it's the API scope
   that matters, not the host language.

2. Chromium-family apps (Chrome, Electron apps: VS Code, Slack, Discord,
   Antigravity...) do not build their accessibility tree AT ALL until an
   assistive client announces itself. Reading them cold returns an empty
   husk — this is why "couldn't read the surrounding text" showed up
   precisely in the apps the user reads most. Setting the app-level
   attributes AXManualAccessibility (Electron) / AXEnhancedUserInterface
   (Chrome, and what VoiceOver itself sets) to true flips the tree on;
   it builds asynchronously, hence the brief settle-and-retry below.
"""
import ctypes
import ctypes.util
import subprocess
import sys
import time

DEADLINE = time.monotonic() + 2.2   # hard internal budget; context.js kills us at 3s anyway
MAX_CHARS = 8000

def log(*args):
    print(*args, file=sys.stderr, flush=True)

# ── Load frameworks ──────────────────────────────────────────────────────
CF = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
AX = ctypes.cdll.LoadLibrary(ctypes.util.find_library("ApplicationServices"))

CFTypeRef = ctypes.c_void_p
CFStringRef = ctypes.c_void_p
CFArrayRef = ctypes.c_void_p
CFIndex = ctypes.c_long

kCFStringEncodingUTF8 = 0x08000100

CF.CFStringCreateWithCString.restype = CFStringRef
CF.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
CF.CFStringGetLength.restype = CFIndex
CF.CFStringGetLength.argtypes = [CFStringRef]
CF.CFStringGetCString.restype = ctypes.c_bool
CF.CFStringGetCString.argtypes = [CFStringRef, ctypes.c_char_p, CFIndex, ctypes.c_uint32]
CF.CFArrayGetCount.restype = CFIndex
CF.CFArrayGetCount.argtypes = [CFArrayRef]
CF.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
CF.CFArrayGetValueAtIndex.argtypes = [CFArrayRef, CFIndex]
CF.CFRelease.restype = None
CF.CFRelease.argtypes = [ctypes.c_void_p]
CF.CFGetTypeID.restype = ctypes.c_ulong
CF.CFGetTypeID.argtypes = [ctypes.c_void_p]
CF.CFStringGetTypeID.restype = ctypes.c_ulong
CF.CFStringGetTypeID.argtypes = []

AX.AXIsProcessTrusted.restype = ctypes.c_bool
AX.AXIsProcessTrusted.argtypes = []
AX.AXUIElementCreateApplication.restype = ctypes.c_void_p
AX.AXUIElementCreateApplication.argtypes = [ctypes.c_int32]
AX.AXUIElementCopyAttributeValue.restype = ctypes.c_int32
AX.AXUIElementCopyAttributeValue.argtypes = [ctypes.c_void_p, CFStringRef, ctypes.POINTER(CFTypeRef)]
AX.AXUIElementSetAttributeValue.restype = ctypes.c_int32
AX.AXUIElementSetAttributeValue.argtypes = [ctypes.c_void_p, CFStringRef, CFTypeRef]
AX.AXUIElementCopyElementAtPosition.restype = ctypes.c_int32
AX.AXUIElementCopyElementAtPosition.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.POINTER(CFTypeRef)]

kCFBooleanTrue = ctypes.c_void_p.in_dll(CF, "kCFBooleanTrue")

# Cache CFStrings for attribute names (created once, never released).
_attr_cache = {}
def attr(name):
    if name not in _attr_cache:
        _attr_cache[name] = CF.CFStringCreateWithCString(None, name.encode("utf-8"), kCFStringEncodingUTF8)
    return _attr_cache[name]

def cfstr_to_py(ref):
    if not ref:
        return None
    length = CF.CFStringGetLength(ref)
    buf_size = length * 4 + 1
    buf = ctypes.create_string_buffer(buf_size)
    ok = CF.CFStringGetCString(ref, buf, buf_size, kCFStringEncodingUTF8)
    return buf.value.decode("utf-8", "replace") if ok else None

def ax_get(element, name):
    value = CFTypeRef()
    err = AX.AXUIElementCopyAttributeValue(element, attr(name), ctypes.byref(value))
    if err != 0 or not value.value:
        return None
    return value.value

def ax_get_str(element, name):
    ref = ax_get(element, name)
    if ref is None:
        return None
    if CF.CFGetTypeID(ref) != CF.CFStringGetTypeID():
        return None
    return cfstr_to_py(ref)

def ax_children(element):
    ref = ax_get(element, "AXChildren")
    if ref is None:
        return []
    count = CF.CFArrayGetCount(ref)
    return [CF.CFArrayGetValueAtIndex(ref, i) for i in range(min(count, 200))]

# Chrome/menu furniture that never contains reading material — descending
# into these wastes the time budget on toolbars and menus.
SKIP_ROLES = {"AXMenuBar", "AXMenuBarItem", "AXMenu", "AXMenuItem", "AXToolbar"}

def collect_text(element, depth=0, max_depth=8):
    if depth > max_depth or time.monotonic() > DEADLINE:
        return ""
    role = ax_get_str(element, "AXRole")
    if role in SKIP_ROLES:
        return ""
    if role == "AXStaticText":
        val = ax_get_str(element, "AXValue")
        return (val + " ") if val else ""
    if role in ("AXTextField", "AXTextArea", "AXWebArea"):
        val = ax_get_str(element, "AXValue")
        if val and len(val) > 1:
            return val + " "
    result = ""
    for child in ax_children(element):
        if len(result) > MAX_CHARS or time.monotonic() > DEADLINE:
            break
        result += collect_text(child, depth + 1, max_depth)
    return result

def climb_for_text(element, hops=10):
    """From a (deep) element, walk up looking for the nearest ancestor with
    real text — first as a direct AXValue, then as a subtree of static text.
    This is the workhorse for the at-cursor strategy: the hit element is
    usually the exact AXStaticText the user selected inside, and one of its
    close ancestors is the paragraph/document."""
    current = element
    for _ in range(hops):
        if current is None or time.monotonic() > DEADLINE:
            return None
        val = ax_get_str(current, "AXValue")
        if val and len(val) > 30:
            return val
        collected = collect_text(current, max_depth=4).strip()
        if len(collected) > 30:
            return collected
        current = ax_get(current, "AXParent")
    return None

def main():
    if not AX.AXIsProcessTrusted():
        log("NOT TRUSTED: this process has no Accessibility permission")
        sys.exit(3)

    cursor = None
    if len(sys.argv) >= 3:
        try:
            cursor = (float(sys.argv[1]), float(sys.argv[2]))
        except ValueError:
            pass

    # Frontmost app pid — lsappinfo is a few ms and needs no AppKit.
    try:
        front = subprocess.run(["lsappinfo", "front"], capture_output=True, text=True, timeout=1).stdout.strip()
        info = subprocess.run(["lsappinfo", "info", "-only", "pid", front], capture_output=True, text=True, timeout=1).stdout.strip()
        pid = int(info.split("=")[1].strip().strip('"'))
    except Exception as e:
        log(f"lsappinfo failed: {e}")
        sys.exit(4)
    log(f"frontmost pid: {pid}")

    app = AX.AXUIElementCreateApplication(pid)
    if not app:
        log("AXUIElementCreateApplication returned NULL")
        sys.exit(5)

    # Flip on the accessibility tree for Chromium-family apps (see header
    # note 2). Harmless no-ops everywhere else. The tree builds async, so
    # the retry pass below gives it a moment when the first pass is empty.
    AX.AXUIElementSetAttributeValue(app, attr("AXManualAccessibility"), kCFBooleanTrue)
    AX.AXUIElementSetAttributeValue(app, attr("AXEnhancedUserInterface"), kCFBooleanTrue)

    def attempt():
        # Strategy 1: element under the cursor — the user just selected a
        # word right there, so this pinpoints the exact text node even when
        # focus information is useless (web pages, custom views).
        if cursor is not None:
            hit = CFTypeRef()
            err = AX.AXUIElementCopyElementAtPosition(app, cursor[0], cursor[1], ctypes.byref(hit))
            if err == 0 and hit.value:
                text = climb_for_text(hit.value)
                if text:
                    log("strategy: at-cursor")
                    return text
            else:
                log(f"at-position err: {err}")

        # Strategy 2: focused element — native fields, web areas, selection.
        focused = ax_get(app, "AXFocusedUIElement")
        if focused:
            sel = ax_get_str(focused, "AXSelectedText")
            if sel and len(sel) > 1:
                parent = ax_get(focused, "AXParent")
                if parent:
                    doc = climb_for_text(parent, hops=8)
                    if doc and sel.lower() in doc.lower():
                        log("strategy: selection-in-parent")
                        return doc
                log("strategy: AXSelectedText-only")
                return sel
            val = ax_get_str(focused, "AXValue")
            if val and len(val) > 1:
                log("strategy: focused AXValue")
                return val
            text = climb_for_text(focused, hops=6)
            if text:
                log("strategy: focused-climb")
                return text
            collected = collect_text(focused).strip()
            if len(collected) > 1:
                log("strategy: focused-subtree")
                return collected
        else:
            log("no focused element")

        # Strategy 3: focused window subtree — last resort, bounded by the
        # shared deadline/char caps.
        window = ax_get(app, "AXFocusedWindow")
        if window:
            collected = collect_text(window, max_depth=10).strip()
            if len(collected) > 1:
                log("strategy: window-subtree")
                return collected
        return None

    text = attempt()
    if not text:
        # A Chromium tree we just enabled may still be building — give it a
        # beat and try once more.
        log("first pass empty, settling for a11y tree build...")
        time.sleep(0.5)
        text = attempt()

    if text:
        print(text[:MAX_CHARS])
    else:
        log("all strategies empty")

if __name__ == "__main__":
    main()
