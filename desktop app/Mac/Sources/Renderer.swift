import Foundation
import Metal
import MetalKit
import simd

/// Orbit camera, Y up (as the browser viewer). Units are the network's space units.
struct Camera {
    var target = SIMD3<Float>(0, 0, 0)
    var distance: Float = 250
    var yaw: Float = 0.6
    var pitch: Float = 0.35
    var fov: Float = 45 * .pi / 180

    var eye: SIMD3<Float> {
        target + distance * SIMD3(cos(pitch) * sin(yaw), sin(pitch), cos(pitch) * cos(yaw))
    }
    var forward: SIMD3<Float> { simd_normalize(target - eye) }
    var right: SIMD3<Float> { simd_normalize(simd_cross(forward, SIMD3(0, 1, 0))) }
    var up: SIMD3<Float> { simd_cross(right, forward) }

    func view() -> simd_float4x4 {
        let f = forward, r = right, u = up, e = eye
        return simd_float4x4(rows: [SIMD4(r.x, r.y, r.z, -simd_dot(r, e)),
                                    SIMD4(u.x, u.y, u.z, -simd_dot(u, e)),
                                    SIMD4(-f.x, -f.y, -f.z, simd_dot(f, e)),
                                    SIMD4(0, 0, 0, 1)])
    }

    func projection(aspect: Float) -> simd_float4x4 {
        let near = max(distance * 0.002, 0.01), far = distance * 50 + 1000
        let y = 1 / tan(fov / 2), x = y / aspect, z = far / (near - far)
        return simd_float4x4(rows: [SIMD4(x, 0, 0, 0), SIMD4(0, y, 0, 0), SIMD4(0, 0, z, z * near), SIMD4(0, 0, -1, 0)])
    }

    mutating func frame(_ lo: SIMD3<Float>, _ hi: SIMD3<Float>) {
        target = (lo + hi) / 2
        distance = max(simd_length(hi - lo) * 1.1, 10) / (2 * tan(fov / 2)) * 1.2
    }

    /// World ray through a point in view coordinates (origin top-left, size in points).
    func ray(_ p: CGPoint, size: CGSize) -> (SIMD3<Float>, SIMD3<Float>) {
        let ndcX = Float(p.x / size.width) * 2 - 1, ndcY = 1 - Float(p.y / size.height) * 2
        let t = tan(fov / 2), aspect = Float(size.width / max(size.height, 1))
        let d = simd_normalize(forward + right * ndcX * t * aspect + up * ndcY * t)
        return (eye, d)
    }
}

struct PointInstance {
    var x: Float, y: Float, z: Float, size: Float
    var color: SIMD4<Float>
}

struct LineVertex {
    var x: Float, y: Float, z: Float
    var pre: Int32
    var color: SIMD4<Float>
}

struct Uniforms {
    var viewProj: simd_float4x4
    var viewport: SIMD2<Float>
    var pointSize: Float
    var flashTau: Float
    var tick: Int32
    var attenuation: Float
    var lineFlash: Float
    var pad: Float = 0
}

private let shaderSource = """
#include <metal_stdlib>
using namespace metal;
struct Uniforms { float4x4 viewProj; float2 viewport; float pointSize; float flashTau; int tick; float attenuation; float lineFlash; float pad; };
struct Inst { packed_float3 pos; float size; float4 color; };
struct LV { packed_float3 pos; int pre; float4 color; };
struct PO { float4 position [[position]]; float2 uv; float4 color; float flash; };
struct LO { float4 position [[position]]; float4 color; };

vertex PO point_vs(uint vid [[vertex_id]], uint iid [[instance_id]], const device Inst* inst [[buffer(0)]],
                   const device int* last [[buffer(1)]], constant Uniforms& u [[buffer(2)]], constant int& hasLast [[buffer(3)]]) {
    const float2 corners[4] = { float2(-1, -1), float2(1, -1), float2(-1, 1), float2(1, 1) };
    Inst I = inst[iid];
    float4 clip = u.viewProj * float4(float3(I.pos), 1.0);
    float flash = 0.0;
    if (hasLast != 0) {
        int age = u.tick - last[iid];
        flash = (age >= 0 && age < 400) ? exp(-float(age) / u.flashTau) : 0.0;
    }
    float r = u.pointSize * I.size * (1.0 + 0.9 * flash);
    r *= mix(1.0, clamp(400.0 / max(clip.w, 1e-3), 0.15, 6.0), u.attenuation);
    r = max(r, 1.0);
    float2 c = corners[vid];
    PO o;
    o.position = clip;
    o.position.xy += c * (2.0 * r / u.viewport) * clip.w;
    o.uv = c; o.color = I.color; o.flash = flash;
    return o;
}

fragment float4 point_fs(PO in [[stage_in]]) {
    float d2 = dot(in.uv, in.uv);
    if (d2 > 1.0) discard_fragment();
    float nz = sqrt(1.0 - d2);
    float3 L = normalize(float3(-0.4, 0.5, 0.75));
    float diff = max(dot(float3(in.uv.x, -in.uv.y, nz), L), 0.0);
    float3 col = in.color.rgb * (0.35 + 0.75 * diff) + pow(diff, 24.0) * 0.25;
    col = mix(col, float3(1.0, 0.96, 0.7), in.flash * 0.85);
    return float4(col, in.color.a);
}

vertex LO line_vs(uint vid [[vertex_id]], const device LV* v [[buffer(0)]], const device int* last [[buffer(1)]],
                  constant Uniforms& u [[buffer(2)]], constant int& hasLast [[buffer(3)]]) {
    LV x = v[vid];
    LO o;
    o.position = u.viewProj * float4(float3(x.pos), 1.0);
    float4 c = x.color;
    if (hasLast != 0 && x.pre >= 0) {
        int age = u.tick - last[x.pre];
        float f = (age >= 0 && age < 200) ? exp(-float(age) / (0.6 * u.flashTau)) : 0.0;
        c = mix(c, float4(1.0, 0.95, 0.6, min(1.0, c.a + 0.6)), f * u.lineFlash);
    }
    o.color = c;
    return o;
}

fragment float4 line_fs(LO in [[stage_in]]) { return in.color; }
"""

/// Draws neurons (shaded discs that flash when they spike), synapses (lines lit by presynaptic spikes), geometry
/// wireframes and sample clouds, and a ground grid. Everything is in instanced buffers rebuilt only when content changes.
final class Renderer: NSObject, MTKViewDelegate {
    let device: MTLDevice
    private let queue: MTLCommandQueue
    private var pointPipe: MTLRenderPipelineState!
    private var linePipe: MTLRenderPipelineState!
    private var depthOn: MTLDepthStencilState!
    private var depthRead: MTLDepthStencilState!

    var camera = Camera()
    var pointSize: Float = 4
    var attenuation: Float = 1
    var flashTau: Float = 25
    var lineFlash: Float = 1
    var showGrid = true
    var background = MTLClearColor(red: 0.06, green: 0.07, blue: 0.09, alpha: 1)
    weak var engine: SimEngine?
    var onFrame: ((Double) -> Void)?

    private var neurons: MTLBuffer?, neuronCount = 0
    private var lastSpike: MTLBuffer?
    private var synapses: MTLBuffer?, synapseCount = 0
    private var overlay: MTLBuffer?, overlayCount = 0         // selection links, wireframes, axes
    private var cloud: MTLBuffer?, cloudCount = 0              // geometry sample points
    private var grid: MTLBuffer?, gridCount = 0
    private var dummyLast: MTLBuffer
    private var lastFrame = CACurrentMediaTime()

    init?(view: MTKView) {
        guard let dev = view.device ?? MTLCreateSystemDefaultDevice(), let q = dev.makeCommandQueue() else { return nil }
        device = dev; queue = q
        dummyLast = dev.makeBuffer(length: 16, options: .storageModeShared)!
        super.init()
        view.colorPixelFormat = .bgra8Unorm
        view.depthStencilPixelFormat = .depth32Float
        view.sampleCount = 4
        view.clearColor = background
        view.preferredFramesPerSecond = 60
        do {
            let lib = try dev.makeLibrary(source: shaderSource, options: nil)
            func pipe(_ vs: String, _ fs: String, blend: Bool) throws -> MTLRenderPipelineState {
                let d = MTLRenderPipelineDescriptor()
                d.vertexFunction = lib.makeFunction(name: vs)
                d.fragmentFunction = lib.makeFunction(name: fs)
                d.colorAttachments[0].pixelFormat = view.colorPixelFormat
                d.depthAttachmentPixelFormat = view.depthStencilPixelFormat
                d.rasterSampleCount = view.sampleCount
                if blend {
                    let c = d.colorAttachments[0]!
                    c.isBlendingEnabled = true
                    c.sourceRGBBlendFactor = .sourceAlpha; c.destinationRGBBlendFactor = .oneMinusSourceAlpha
                    c.sourceAlphaBlendFactor = .one; c.destinationAlphaBlendFactor = .oneMinusSourceAlpha
                }
                return try dev.makeRenderPipelineState(descriptor: d)
            }
            pointPipe = try pipe("point_vs", "point_fs", blend: true)
            linePipe = try pipe("line_vs", "line_fs", blend: true)
        } catch {
            NSLog("Metal shader error: \(error)")
            return nil
        }
        let ds = MTLDepthStencilDescriptor()
        ds.depthCompareFunction = .less; ds.isDepthWriteEnabled = true
        depthOn = dev.makeDepthStencilState(descriptor: ds)
        ds.isDepthWriteEnabled = false
        depthRead = dev.makeDepthStencilState(descriptor: ds)
    }

    private func buffer<T>(_ a: [T]) -> MTLBuffer? {
        guard !a.isEmpty else { return nil }
        return a.withUnsafeBytes { device.makeBuffer(bytes: $0.baseAddress!, length: $0.count, options: .storageModeShared) }
    }

    func setNeurons(_ inst: [PointInstance]) {
        neurons = buffer(inst); neuronCount = inst.count
        if (lastSpike?.length ?? 0) < 4 * max(inst.count, 1) {
            lastSpike = device.makeBuffer(length: 4 * max(inst.count, 1), options: .storageModeShared)
        }
        if let ls = lastSpike { memset(ls.contents(), 0x80, ls.length) }      // very old spikes
    }
    func setSynapses(_ v: [LineVertex]) { synapses = buffer(v); synapseCount = v.count }
    func setOverlay(_ v: [LineVertex]) { overlay = buffer(v); overlayCount = v.count }
    func setCloud(_ p: [PointInstance]) { cloud = buffer(p); cloudCount = p.count }

    func setGrid(lo: SIMD3<Float>, hi: SIMD3<Float>) {
        let span = max(hi.x - lo.x, hi.z - lo.z, 50) * 1.4
        let step = pow(10, floor(log10(span / 10)))
        let half = (span / 2 / step).rounded(.up) * step
        let c = (lo + hi) / 2, y = lo.y - 0.02 * max(hi.y - lo.y, 1)
        var v: [LineVertex] = []
        var k: Float = -half
        while k <= half + 1e-3 {
            let major = abs((k / step).rounded().truncatingRemainder(dividingBy: 5)) < 0.5
            let col = SIMD4<Float>(0.5, 0.55, 0.65, major ? 0.22 : 0.09)
            v.append(LineVertex(x: c.x + k, y: y, z: c.z - half, pre: -1, color: col))
            v.append(LineVertex(x: c.x + k, y: y, z: c.z + half, pre: -1, color: col))
            v.append(LineVertex(x: c.x - half, y: y, z: c.z + k, pre: -1, color: col))
            v.append(LineVertex(x: c.x + half, y: y, z: c.z + k, pre: -1, color: col))
            k += step
        }
        let a: Float = step * 2
        let o = SIMD3<Float>(c.x - half, y, c.z - half)
        for (d, col) in [(SIMD3<Float>(a, 0, 0), SIMD4<Float>(0.95, 0.3, 0.3, 0.9)), (SIMD3<Float>(0, a, 0), SIMD4<Float>(0.3, 0.9, 0.4, 0.9)),
                         (SIMD3<Float>(0, 0, a), SIMD4<Float>(0.35, 0.55, 1, 0.9))] {
            v.append(LineVertex(x: o.x, y: o.y, z: o.z, pre: -1, color: col))
            v.append(LineVertex(x: o.x + d.x, y: o.y + d.y, z: o.z + d.z, pre: -1, color: col))
        }
        grid = buffer(v); gridCount = v.count
    }

    func mtkView(_ view: MTKView, drawableSizeWillChange size: CGSize) {}

    func draw(in view: MTKView) {
        let now = CACurrentMediaTime()
        onFrame?(now - lastFrame); lastFrame = now
        guard let rpd = view.currentRenderPassDescriptor, let drawable = view.currentDrawable,
              let cb = queue.makeCommandBuffer() else { return }
        rpd.colorAttachments[0].clearColor = background
        var tick: Int32 = 0
        var hasLast: Int32 = 0
        if let e = engine, let ls = lastSpike, e.n == neuronCount, neuronCount > 0 {
            tick = Int32(truncatingIfNeeded: e.snapshotLastSpike(into: ls.contents(), capacity: ls.length / 4))
            hasLast = 1
        }
        let size = view.drawableSize
        let aspect = Float(size.width / max(size.height, 1))
        var u = Uniforms(viewProj: camera.projection(aspect: aspect) * camera.view(),
                         viewport: SIMD2(Float(size.width), Float(size.height)),
                         pointSize: pointSize * Float(view.window?.backingScaleFactor ?? 2), flashTau: flashTau, tick: tick,
                         attenuation: attenuation, lineFlash: lineFlash)
        guard let enc = cb.makeRenderCommandEncoder(descriptor: rpd) else { return }
        var no: Int32 = 0
        enc.setVertexBytes(&u, length: MemoryLayout<Uniforms>.stride, index: 2)

        enc.setRenderPipelineState(linePipe)
        enc.setDepthStencilState(depthRead)
        if showGrid, let g = grid {
            enc.setVertexBuffer(g, offset: 0, index: 0)
            enc.setVertexBuffer(dummyLast, offset: 0, index: 1)
            enc.setVertexBytes(&no, length: 4, index: 3)
            enc.drawPrimitives(type: .line, vertexStart: 0, vertexCount: gridCount)
        }
        enc.setRenderPipelineState(pointPipe)
        enc.setDepthStencilState(depthOn)
        if let n = neurons, neuronCount > 0 {
            enc.setVertexBuffer(n, offset: 0, index: 0)
            enc.setVertexBuffer(hasLast == 1 ? lastSpike : dummyLast, offset: 0, index: 1)
            enc.setVertexBytes(&hasLast, length: 4, index: 3)
            enc.drawPrimitives(type: .triangleStrip, vertexStart: 0, vertexCount: 4, instanceCount: neuronCount)
        }
        if let c = cloud, cloudCount > 0 {
            enc.setVertexBuffer(c, offset: 0, index: 0)
            enc.setVertexBuffer(dummyLast, offset: 0, index: 1)
            enc.setVertexBytes(&no, length: 4, index: 3)
            enc.drawPrimitives(type: .triangleStrip, vertexStart: 0, vertexCount: 4, instanceCount: cloudCount)
        }
        enc.setRenderPipelineState(linePipe)
        enc.setDepthStencilState(depthRead)
        if let s = synapses, synapseCount > 0 {
            enc.setVertexBuffer(s, offset: 0, index: 0)
            enc.setVertexBuffer(hasLast == 1 ? lastSpike : dummyLast, offset: 0, index: 1)
            enc.setVertexBytes(&hasLast, length: 4, index: 3)
            enc.drawPrimitives(type: .line, vertexStart: 0, vertexCount: synapseCount)
        }
        if let o = overlay, overlayCount > 0 {
            enc.setVertexBuffer(o, offset: 0, index: 0)
            enc.setVertexBuffer(hasLast == 1 ? lastSpike : dummyLast, offset: 0, index: 1)
            enc.setVertexBytes(&hasLast, length: 4, index: 3)
            enc.drawPrimitives(type: .line, vertexStart: 0, vertexCount: overlayCount)
        }
        enc.endEncoding()
        cb.present(drawable)
        cb.commit()
    }

    /// Index of the neuron under a view point (within `radius` points), nearest to the camera.
    func pick(_ p: CGPoint, size: CGSize, positions: [SIMD3<Float>], radius: CGFloat = 9) -> Int? {
        let aspect = Float(size.width / max(size.height, 1))
        let m = camera.projection(aspect: aspect) * camera.view()
        var best: Int?, bestZ: Float = .infinity
        let r2 = Float(radius * radius)
        let w = Float(size.width), h = Float(size.height)
        for (i, q) in positions.enumerated() {
            let c = m * SIMD4(q, 1)
            if c.w <= 0 { continue }
            let sx = (c.x / c.w * 0.5 + 0.5) * w, sy = (0.5 - c.y / c.w * 0.5) * h
            let dx = sx - Float(p.x), dy = sy - Float(p.y)
            if dx * dx + dy * dy <= r2 && c.w < bestZ { best = i; bestZ = c.w }
        }
        return best
    }

    /// Point on the plane through the orbit target facing the camera, under a view point.
    func planePoint(_ p: CGPoint, size: CGSize) -> SIMD3<Float> {
        let (o, d) = camera.ray(p, size: size)
        let nrm = camera.forward
        let t = simd_dot(camera.target - o, nrm) / simd_dot(d, nrm)
        return o + d * t
    }
}
