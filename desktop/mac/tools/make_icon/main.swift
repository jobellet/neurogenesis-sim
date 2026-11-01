import AppKit

// Draws the app icon (a small grown network on a dark rounded square) as a 1024 px PNG: make_icon <out.png>
let size = 1024
let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size, bitsPerSample: 8, samplesPerPixel: 4,
                           hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
let ctx = NSGraphicsContext.current!.cgContext
let S = CGFloat(size)
let rect = CGRect(x: S * 0.1, y: S * 0.1, width: S * 0.8, height: S * 0.8)
let shape = CGPath(roundedRect: rect, cornerWidth: S * 0.18, cornerHeight: S * 0.18, transform: nil)
ctx.addPath(shape); ctx.clip()
let grad = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(),
                      colors: [CGColor(red: 0.07, green: 0.10, blue: 0.20, alpha: 1), CGColor(red: 0.02, green: 0.03, blue: 0.06, alpha: 1)] as CFArray,
                      locations: [0, 1])!
ctx.drawLinearGradient(grad, start: CGPoint(x: 0, y: S), end: CGPoint(x: S, y: 0), options: [])
var g = Xorshift(seed: 7)
struct Xorshift { var s: UInt32; init(seed: UInt32) { s = seed }
    mutating func next() -> CGFloat { s ^= s << 13; s ^= s >> 17; s ^= s << 5; return CGFloat(s) / CGFloat(UInt32.max) } }
var pts: [(CGPoint, Int)] = []
for k in 0..<46 {
    let layer = k % 3
    let x = S * (0.2 + 0.6 * g.next())
    let y = S * (0.25 + 0.17 * CGFloat(layer) + 0.12 * g.next())
    pts.append((CGPoint(x: x, y: y), layer))
}
let colors = [CGColor(red: 0.33, green: 0.62, blue: 0.98, alpha: 1), CGColor(red: 0.98, green: 0.55, blue: 0.24, alpha: 1),
              CGColor(red: 0.35, green: 0.80, blue: 0.45, alpha: 1)]
ctx.setLineWidth(S * 0.004)
for (a, la) in pts {
    for (b, lb) in pts where lb == la + 1 && hypot(a.x - b.x, a.y - b.y) < S * 0.22 {
        ctx.setStrokeColor(CGColor(red: 1, green: 0.85, blue: 0.6, alpha: 0.28))
        ctx.move(to: a); ctx.addLine(to: b); ctx.strokePath()
    }
}
for (k, (p, l)) in pts.enumerated() {
    let r = S * (k % 7 == 0 ? 0.03 : 0.02)
    if k % 7 == 0 {
        ctx.setFillColor(CGColor(red: 1, green: 0.95, blue: 0.7, alpha: 0.25))
        ctx.fillEllipse(in: CGRect(x: p.x - r * 2.2, y: p.y - r * 2.2, width: r * 4.4, height: r * 4.4))
    }
    ctx.setFillColor(k % 7 == 0 ? CGColor(red: 1, green: 0.96, blue: 0.75, alpha: 1) : colors[l])
    ctx.fillEllipse(in: CGRect(x: p.x - r, y: p.y - r, width: 2 * r, height: 2 * r))
}
NSGraphicsContext.restoreGraphicsState()
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
