#!/usr/bin/env swift
/**
 * lexio-ocr — Point-at-word screen capture for Lexio Glance (macOS 14+)
 *
 * Captures a rectangle around the cursor via ScreenCaptureKit and returns it
 * as a base64-encoded PNG. The definition itself is produced server-side by
 * a multimodal LLM (Gemini 2.5 Flash) given this image — no local OCR/text
 * recognition happens here anymore; this binary's only job is the capture.
 *
 * Usage: lexio-ocr --x <cx> --y <cy> [--width 800] [--height 500]
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
    var width = 800.0
    var height = 500.0
}

func parseArgs() -> Args {
    var a = Args()
    var i = 1
    let v = CommandLine.arguments
    while i < v.count {
        switch v[i] {
        case "--x": i += 1; if i < v.count { a.x = Double(v[i]) ?? a.x }
        case "--y": i += 1; if i < v.count { a.y = Double(v[i]) ?? a.y }
        case "--width", "-w": i += 1; if i < v.count { a.width = Double(v[i]) ?? a.width }
        case "--height", "-h": i += 1; if i < v.count { a.height = Double(v[i]) ?? a.height }
        default: break
        }
        i += 1
    }
    return a
}

/// Electron screen coords: origin top-left of primary display. Cocoa: bottom-left.
func electronToCocoa(_ point: CGPoint) -> CGPoint {
    for screen in NSScreen.screens {
        let flipped = CGPoint(x: point.x, y: screen.frame.maxY - point.y)
        if screen.frame.contains(flipped) { return flipped }
    }
    if let s = NSScreen.main {
        return CGPoint(x: point.x, y: s.frame.maxY - point.y)
    }
    return point
}

func electronRectToCocoa(_ rect: CGRect) -> (CGRect, NSScreen) {
    let topLeft = CGPoint(x: rect.minX, y: rect.minY)
    let bottomRight = CGPoint(x: rect.maxX, y: rect.maxY)
    let cTL = electronToCocoa(topLeft)
    let cBR = electronToCocoa(bottomRight)
    let cocoaRect = CGRect(x: min(cTL.x, cBR.x), y: min(cTL.y, cBR.y), width: abs(cBR.x - cTL.x), height: abs(cTL.y - cBR.y))
    let screen = NSScreen.screens.first { $0.frame.intersects(cocoaRect) } ?? NSScreen.main!
    let local = CGRect(
        x: cTL.x - screen.frame.minX,
        y: cBR.y - screen.frame.minY,
        width: cBR.x - cTL.x,
        height: cTL.y - cBR.y
    )
    return (local, screen)
}

func captureRegion(_ electronRect: CGRect) -> CGImage? {
    guard #available(macOS 14.0, *) else {
        fputs("lexio-ocr requires macOS 14+\n", stderr)
        return nil
    }
    var image: CGImage?
    let sem = DispatchSemaphore(value: 0)
    Task {
        defer { sem.signal() }
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
            let (localRect, screen) = electronRectToCocoa(electronRect)
            let displayID = screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? CGDirectDisplayID
            guard let display = content.displays.first(where: { $0.displayID == displayID }) ?? content.displays.first else {
                fputs("no display for capture region\n", stderr)
                return
            }
            let filter = SCContentFilter(display: display, excludingWindows: [])
            let config = SCStreamConfiguration()
            let scale = screen.backingScaleFactor
            config.sourceRect = localRect
            config.width = Int(localRect.width * scale)
            config.height = Int(localRect.height * scale)
            config.pixelFormat = kCVPixelFormatType_32BGRA
            config.showsCursor = false
            image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: config)
        } catch {
            fputs("capture error: \(error) — grant Screen Recording to Lexio Glance\n", stderr)
        }
    }
    sem.wait()
    return image
}

func pngBase64(_ image: CGImage) -> String? {
    let rep = NSBitmapImageRep(cgImage: image)
    guard let data = rep.representation(using: .png, properties: [:]) else { return nil }
    return data.base64EncodedString()
}

let start = DispatchTime.now()
let args = parseArgs()
let cursor = CGPoint(x: args.x, y: args.y)
let region = CGRect(
    x: cursor.x - args.width / 2,
    y: cursor.y - args.height / 2,
    width: args.width,
    height: args.height
)

guard let image = captureRegion(region) else { exit(2) }
guard let b64 = pngBase64(image) else {
    fputs("png encode failed\n", stderr)
    exit(3)
}

let ms = Int((DispatchTime.now().uptimeNanoseconds - start.uptimeNanoseconds) / 1_000_000)
let result = CaptureResult(image_base64: b64, width: image.width, height: image.height, ms: ms)

let enc = JSONEncoder()
enc.outputFormatting = [.sortedKeys]
guard let data = try? enc.encode(result), let json = String(data: data, encoding: .utf8) else { exit(4) }
print(json)
