import AppKit
import MetalKit
import SwiftUI

/// MTKView with the 3D navigation: drag to orbit, shift-drag or right-drag to pan, scroll / pinch to zoom (two-finger
/// trackpad scroll orbits, with shift it pans), double-click to centre on a neuron, keys W A S D Q E to move, F to frame.
final class InteractiveMTKView: MTKView {
    var renderer: Renderer?
    var onClick: ((CGPoint, NSEvent.ModifierFlags) -> Void)?
    var onDoubleClick: ((CGPoint) -> Void)?
    var onKey: ((NSEvent) -> Bool)?
    var onCameraChange: (() -> Void)?
    private var downAt: CGPoint?
    private var dragged = false
    private var lastDrag: CGPoint = .zero
    private var keysDown = Set<UInt16>()
    private var keyTimer: Timer?

    override var acceptsFirstResponder: Bool { true }
    override var isFlipped: Bool { true }

    private func loc(_ e: NSEvent) -> CGPoint { convert(e.locationInWindow, from: nil) }

    override func mouseDown(with e: NSEvent) {
        window?.makeFirstResponder(self)
        downAt = loc(e); lastDrag = downAt!; dragged = false
        if e.clickCount == 2 { onDoubleClick?(loc(e)) }
    }

    override func mouseDragged(with e: NSEvent) {
        guard let r = renderer else { return }
        let p = loc(e)
        if let d = downAt, hypot(p.x - d.x, p.y - d.y) > 3 { dragged = true }
        let dx = Float(p.x - lastDrag.x), dy = Float(p.y - lastDrag.y)
        lastDrag = p
        guard dragged else { return }
        if e.modifierFlags.contains(.shift) || e.modifierFlags.contains(.command) { pan(dx, dy) } else {
            r.camera.yaw -= dx * 0.008
            r.camera.pitch = max(-1.55, min(1.55, r.camera.pitch + dy * 0.008))
        }
        onCameraChange?()
    }

    override func mouseUp(with e: NSEvent) {
        if !dragged, e.clickCount < 2 { onClick?(loc(e), e.modifierFlags) }
        downAt = nil
    }

    override func rightMouseDown(with e: NSEvent) { lastDrag = loc(e) }
    override func rightMouseDragged(with e: NSEvent) {
        let p = loc(e)
        pan(Float(p.x - lastDrag.x), Float(p.y - lastDrag.y))
        lastDrag = p
    }
    override func otherMouseDown(with e: NSEvent) { lastDrag = loc(e) }
    override func otherMouseDragged(with e: NSEvent) { rightMouseDragged(with: e) }

    private func pan(_ dx: Float, _ dy: Float) {
        guard let r = renderer else { return }
        let k = r.camera.distance * 2 * tan(r.camera.fov / 2) / Float(max(bounds.height, 1))
        r.camera.target += (-r.camera.right * dx + r.camera.up * dy) * k
        onCameraChange?()
    }

    private func zoom(_ f: Float) {
        guard let r = renderer else { return }
        r.camera.distance = max(0.5, min(1e6, r.camera.distance * f))
        onCameraChange?()
    }

    override func scrollWheel(with e: NSEvent) {
        guard let r = renderer else { return }
        if e.hasPreciseScrollingDeltas && !e.modifierFlags.contains(.option) {
            if e.modifierFlags.contains(.shift) {
                pan(-Float(e.scrollingDeltaX), -Float(e.scrollingDeltaY))
            } else {
                r.camera.yaw -= Float(e.scrollingDeltaX) * 0.006
                r.camera.pitch = max(-1.55, min(1.55, r.camera.pitch - Float(e.scrollingDeltaY) * 0.006))
                onCameraChange?()
            }
        } else {
            let d = e.hasPreciseScrollingDeltas ? e.scrollingDeltaY * 0.01 : e.scrollingDeltaY * 0.1
            zoom(Float(exp(-d)))
        }
    }

    override func magnify(with e: NSEvent) { zoom(Float(exp(-e.magnification * 1.5))) }

    override func keyDown(with e: NSEvent) {
        if onKey?(e) == true { return }
        let movement: Set<UInt16> = [13, 0, 1, 2, 12, 14, 123, 124, 125, 126]
        if movement.contains(e.keyCode) {
            keysDown.insert(e.keyCode)
            if keyTimer == nil {
                keyTimer = Timer.scheduledTimer(withTimeInterval: 1 / 60, repeats: true) { [weak self] _ in self?.moveTick() }
            }
        } else {
            super.keyDown(with: e)
        }
    }

    override func keyUp(with e: NSEvent) {
        keysDown.remove(e.keyCode)
        if keysDown.isEmpty { keyTimer?.invalidate(); keyTimer = nil }
    }

    private func moveTick() {
        guard let r = renderer else { return }
        let s = r.camera.distance * 0.012
        var f = r.camera.forward; f.y = 0
        if simd_length(f) > 1e-4 { f = simd_normalize(f) }
        var d = SIMD3<Float>(0, 0, 0)
        for k in keysDown {
            switch k {
            case 13, 126: d += f          // W, up
            case 1, 125: d -= f           // S, down
            case 0, 123: d -= r.camera.right   // A, left
            case 2, 124: d += r.camera.right   // D, right
            case 12: d.y -= 1             // Q
            case 14: d.y += 1             // E
            default: break
            }
        }
        r.camera.target += d * s
        onCameraChange?()
    }
}

struct MetalViewport: NSViewRepresentable {
    @ObservedObject var app: AppState

    func makeNSView(context: Context) -> InteractiveMTKView {
        let v = InteractiveMTKView(frame: .zero, device: MTLCreateSystemDefaultDevice())
        guard let r = Renderer(view: v) else { return v }
        v.renderer = r
        v.delegate = r
        app.attach(renderer: r)
        v.onClick = { [weak app] p, mods in app?.viewClicked(p, size: v.bounds.size, modifiers: mods) }
        v.onDoubleClick = { [weak app] p in app?.viewDoubleClicked(p, size: v.bounds.size) }
        v.onKey = { [weak app] e in app?.viewKey(e) ?? false }
        return v
    }

    func updateNSView(_ nsView: InteractiveMTKView, context: Context) {}
}
