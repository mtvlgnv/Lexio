#!/usr/bin/env swift
/**
 * lexio-ocr — Point-at-word screen capture for Lexio Glance (macOS 14+)
 *
 * Captures a rectangle around the cursor via ScreenCaptureKit and returns it
 * as a base64-encoded PNG. The definition itself is produced server-side by
 * a multimodal LLM (Gemini 2.5 Flash) given this image — no local OCR/text
 * recognition happens here anymore; this binary's only job is the capture.
 *
 * Two details make the server-side word identification reliable:
 *   1. A magenta ring is drawn at the exact cursor point before encoding —
 *      vision models are poor at "the word at the exact center" but very
 *      good at "the word inside the marker" (set-of-marks prompting).
 *   2. Windows owned by our parent process (the Lexio Glance app itself)
 *      are excluded from the capture, so the expanding overlay panel can
 *      never photobomb its own screenshot.
 *
 * Usage: lexio-ocr --x <cx> --y <cy> [--rx --ry --rw --rh]
 *   --x/--y   cursor position (Electron global coords, logical px)
 *   --rx..rh  capture region (Electron coords). The caller clamps this to
 *             the display so the cursor keeps a known offset inside it even
 *             at screen edges. Falls back to 800x500 centered on the cursor.
 *
 * Requires Screen Recording permission for Lexio Glance.
 */
import AppKit
import CoreGraphics
import Foundation
import ScreenCaptureKit

struct CaptureResult: Codable {
    let image_base64: String
    let width: Int
    let height: Int
    let ms: Int
}

struct Args {
    var x = 0.0
    var y = 0.0
    var rx: Double? = nil
    var ry: Double? = nil
    var rw = 800.0
    var rh = 500.0
}

func parseArgs() -> Args {
    var a = Args()
    var i = 1
    let v = CommandLine.arguments
    while i < v.count {
        switch v[i] {
        case "--x": i += 1; if i < v.count { a.x = Double(v[i]) ?? a.x }
        case "--y": i += 1; if i < v.count { a.y = Double(v[i]) ?? a.y }
        case "--rx": i += 1; if i < v.count { a.rx = Double(v[i]) }
        case "--ry": i += 1; if i < v.count { a.ry = Double(v[i]) }
        case "--rw", "--width", "-w": i += 1; if i < v.count { a.rw = Double(v[i]) ?? a.rw }
        case "--rh", "--height", "-h": i += 1; if i < v.count { a.rh = Double(v[i]) ?? a.rh }
        default: break
        }
        i += 1
    }
    return a
}

/// Electron global coords: origin at the PRIMARY display's top-left, y down.
/// SCStreamConfiguration.sourceRect wants the display's own coordinate space
/// with origin at ITS top-left, y down — so the only transform needed is
/// subtracting the display's electron-space origin. No cocoa y-flip: feeding
/// bottom-left-origin cocoa rects here is exactly the bug that made captures
/// grab a region mirrored about the display's horizontal midline (cursor in
/// the top third → screenshot of the bottom third).
func regionInDisplaySpace(_ electronRect: CGRect) -> (CGRect, NSScreen) {
    let primaryMaxY = NSScreen.screens.first?.frame.maxY ?? 0
    // Pick the display containing the rect's center (cocoa space for the test).
    let center = CGPoint(x: electronRect.midX, y: primaryMaxY - electronRect.midY)
    let screen = NSScreen.screens.first { $0.frame.contains(center) } ?? NSScreen.main!
    // The display's own origin expressed in electron global coords.
    let originE = CGPoint(x: screen.frame.minX, y: primaryMaxY - screen.frame.maxY)
    let local = CGRect(
        x: electronRect.minX - originE.x,
        y: electronRect.minY - originE.y,
        width: electronRect.width,
        height: electronRect.height
    )
    return (local, screen)
}

func captureRegion(_ electronRect: CGRect) -> (CGImage, CGFloat)? {
    guard #available(macOS 14.0, *) else {
        fputs("lexio-ocr requires macOS 14+\n", stderr)
        return nil
    }
    var result: (CGImage, CGFloat)?
    let sem = DispatchSemaphore(value: 0)
    Task {
        defer { sem.signal() }
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
            let (localRect, screen) = regionInDisplaySpace(electronRect)
            let displayID = screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? CGDirectDisplayID
            guard let display = content.displays.first(where: { $0.displayID == displayID }) ?? content.displays.first else {
                fputs("no display for capture region\n", stderr)
                return
            }
            // Exclude every window owned by our parent process — the Lexio
            // Glance app that spawned us. The overlay panel expands while
            // this capture is in flight; without this it lands in the shot.
            let ownPid = getppid()
            let ownWindows = content.windows.filter { $0.owningApplication?.processID == ownPid }
            let filter = SCContentFilter(display: display, excludingWindows: ownWindows)
            let config = SCStreamConfiguration()
            let scale = screen.backingScaleFactor
            config.sourceRect = localRect
            config.width = Int(localRect.width * scale)
            config.height = Int(localRect.height * scale)
            config.pixelFormat = kCVPixelFormatType_32BGRA
            config.showsCursor = false
            let image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: config)
            result = (image, scale)
        } catch {
            fputs("capture error: \(error) — grant Screen Recording to Lexio Glance\n", stderr)
        }
    }
    sem.wait()
    return result
}

/// Draw the cursor marker: a white halo + magenta ring centered on the
/// cursor point. Thin strokes so the word under it stays readable; high
/// contrast so it's findable on any background.
func drawMarker(on image: CGImage, atX mx: CGFloat, atYTopLeft myTop: CGFloat) -> CGImage {
    let w = image.width
    let h = image.height
    guard let space = CGColorSpace(name: CGColorSpace.sRGB),
          let ctx = CGContext(data: nil, width: w, height: h,
                              bitsPerComponent: 8, bytesPerRow: 0,
                              space: space,
                              bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
        return image
    }
    ctx.draw(image, in: CGRect(x: 0, y: 0, width: w, height: h))
    let my = CGFloat(h) - myTop          // CGContext is bottom-left origin
    let r: CGFloat = 24                   // retina px (~12pt) — rings one word
    let rect = CGRect(x: mx - r, y: my - r, width: r * 2, height: r * 2)
    ctx.setStrokeColor(CGColor(red: 1, green: 1, blue: 1, alpha: 0.95))
    ctx.setLineWidth(8)
    ctx.strokeEllipse(in: rect)
    ctx.setStrokeColor(CGColor(red: 1, green: 0, blue: 0.75, alpha: 1))
    ctx.setLineWidth(3.5)
    ctx.strokeEllipse(in: rect)
    return ctx.makeImage() ?? image
}

func pngBase64(_ image: CGImage) -> String? {
    let rep = NSBitmapImageRep(cgImage: image)
    guard let data = rep.representation(using: .png, properties: [:]) else { return nil }
    return data.base64EncodedString()
}

let start = DispatchTime.now()
let args = parseArgs()
let region = CGRect(
    x: args.rx ?? (args.x - args.rw / 2),
    y: args.ry ?? (args.y - args.rh / 2),
    width: args.rw,
    height: args.rh
)

guard let (raw, scale) = captureRegion(region) else { exit(2) }
let marked = drawMarker(
    on: raw,
    atX: CGFloat(args.x - region.minX) * scale,
    atYTopLeft: CGFloat(args.y - region.minY) * scale
)
guard let b64 = pngBase64(marked) else {
    fputs("png encode failed\n", stderr)
    exit(3)
}

let ms = Int((DispatchTime.now().uptimeNanoseconds - start.uptimeNanoseconds) / 1_000_000)
let result = CaptureResult(image_base64: b64, width: marked.width, height: marked.height, ms: ms)

let enc = JSONEncoder()
enc.outputFormatting = [.sortedKeys]
guard let data = try? enc.encode(result), let json = String(data: data, encoding: .utf8) else { exit(4) }
print(json)
