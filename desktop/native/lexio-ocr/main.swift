#!/usr/bin/env swift
/**
 * lexio-ocr — Point-at-word screen OCR for Lexio Glance (macOS 14+)
 *
 * Captures a rectangle around the cursor via ScreenCaptureKit, runs Vision OCR,
 * finds the word under the pointer, returns surrounding sentence as JSON.
 *
 * Usage: lexio-ocr --x <cx> --y <cy> [--width 600] [--height 200] [--hint "bat"]
 *
 * Requires Screen Recording permission for Lexio Glance.
 */
import AppKit
import CoreGraphics
import Foundation
import ScreenCaptureKit
import Vision

struct OCRResult: Codable {
    let word: String
    let context: String
    let confidence: Float
    let ms: Int
}

struct Args {
    var x = 0.0
    var y = 0.0
    var width = 600.0
    var height = 200.0
    var hint = ""
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
        case "--hint": i += 1; if i < v.count { a.hint = v[i] }
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

func visionBoxToScreen(_ box: CGRect, region: CGRect) -> CGRect {
    let x = region.minX + box.minX * region.width
    let y = region.minY + (1.0 - box.maxY) * region.height
    let w = box.width * region.width
    let h = box.height * region.height
    return CGRect(x: x, y: y, width: w, height: h)
}

func containsPoint(_ box: CGRect, point: CGPoint, region: CGRect) -> Bool {
    visionBoxToScreen(box, region: region).contains(point)
}

func expandToSentence(_ text: String, around word: String) -> String {
    let lower = text.lowercased()
    let target = word.lowercased()
    guard let range = lower.range(of: target) else { return text }
    let before = String(text[..<range.lowerBound])
    let wordEnd = text.index(range.lowerBound, offsetBy: word.count, limitedBy: text.endIndex) ?? text.endIndex
    let after = String(text[wordEnd...])
    var start = text.startIndex
    for sep in [". ", "! ", "? ", "\n"] {
        if let r = before.range(of: sep, options: .backwards) {
            start = r.upperBound
            break
        }
    }
    var end = text.endIndex
    if let p = after.firstIndex(where: { ".!?".contains($0) }) {
        end = text.index(wordEnd, offsetBy: after.distance(from: after.startIndex, to: after.index(after: p)))
    }
    return String(text[start..<end]).trimmingCharacters(in: .whitespacesAndNewlines)
}

func runOCR(image: CGImage, cursor: CGPoint, region: CGRect, hint: String) -> OCRResult? {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true

    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    do { try handler.perform([request]) } catch { fputs("vision error: \(error)\n", stderr); return nil }
    guard let observations = request.results, !observations.isEmpty else { return nil }

    struct WordHit {
        let word: String
        let line: String
        let box: CGRect
        let confidence: Float
    }
    var hits: [WordHit] = []

    for obs in observations {
        guard let candidate = obs.topCandidates(1).first else { continue }
        let line = candidate.string
        var searchStart = line.startIndex
        for part in line.split(whereSeparator: { !$0.isLetter && !$0.isNumber && $0 != "'" && $0 != "-" }) {
            let word = String(part)
            guard let range = line.range(of: word, range: searchStart..<line.endIndex) else { continue }
            searchStart = range.upperBound
            guard let rectObs = try? candidate.boundingBox(for: range) else { continue }
            let box = rectObs.boundingBox
            hits.append(WordHit(word: word, line: line, box: box, confidence: candidate.confidence))
        }
    }

    if hits.isEmpty { return nil }

    let hintLower = hint.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    let picked: WordHit
    if let underCursor = hits.first(where: { containsPoint($0.box, point: cursor, region: region) }) {
        picked = underCursor
    } else if !hintLower.isEmpty, let hinted = hits.first(where: { $0.word.lowercased() == hintLower }) {
        picked = hinted
    } else if !hintLower.isEmpty, let partial = hits.first(where: { $0.line.lowercased().contains(hintLower) }) {
        picked = partial
    } else {
        picked = hits.min(by: {
            let a = visionBoxToScreen($0.box, region: region)
            let b = visionBoxToScreen($1.box, region: region)
            return hypot(a.midX - cursor.x, a.midY - cursor.y) < hypot(b.midX - cursor.x, b.midY - cursor.y)
        })!
    }

    let context = expandToSentence(picked.line, around: picked.word)
    return OCRResult(word: picked.word, context: context.isEmpty ? picked.line : context, confidence: picked.confidence, ms: 0)
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
guard var result = runOCR(image: image, cursor: cursor, region: region, hint: args.hint) else {
    fputs("ocr: no text found in region\n", stderr)
    exit(3)
}

let ms = Int((DispatchTime.now().uptimeNanoseconds - start.uptimeNanoseconds) / 1_000_000)
result = OCRResult(word: result.word, context: result.context, confidence: result.confidence, ms: ms)

let enc = JSONEncoder()
enc.outputFormatting = [.sortedKeys]
guard let data = try? enc.encode(result), let json = String(data: data, encoding: .utf8) else { exit(4) }
print(json)