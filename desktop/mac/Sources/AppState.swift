import AppKit
import Foundation
import simd
import SwiftUI
import UniformTypeIdentifiers

/// Everything the window shows and edits: the current network, the Project (geometry, fields, schedule, genome, plan),
/// the live simulation, and the calls into the Python toolbox.
@MainActor
final class AppState: ObservableObject {
    // network and view
    @Published private(set) var network = Network()
    @Published var selection: [Int] = [] { didSet { selectionChanged() } }
    @Published var colorMode: ColorMode = .region { didSet { rebuildNeurons() } }
    @Published var synapseDisplay: SynapseDisplay = .all { didSet { rebuildSynapses(); rebuildOverlay() } }
    @Published var synapseCap = 60000.0 { didSet { rebuildSynapses() } }
    @Published var pointSize: Double = 4 { didSet { renderer?.pointSize = Float(pointSize) } }
    @Published var perspectiveSize = true { didSet { renderer?.attenuation = perspectiveSize ? 1 : 0 } }
    @Published var flashTau: Double = 25 { didSet { renderer?.flashTau = Float(flashTau) } }
    @Published var showGrid = true { didSet { renderer?.showGrid = showGrid } }
    @Published var showRegionBoxes = true { didSet { rebuildOverlay() } }
    @Published var tool: Tool = .select { didSet { rebuildOverlay(); if tool != .add { renderer?.setGhost(nil) } } }
    /// The Add tool places neurons on the plane {x[placeAxis] = placeLevel} (0 x, 1 y, 2 z): no depth ambiguity.
    @Published var placeAxis = 2 { didSet { let (lo, hi) = sceneBounds(); placeLevel = Double((lo[placeAxis] + hi[placeAxis]) / 2) } }
    @Published var placeLevel: Double = 0 { didSet { rebuildOverlay(); updateGhost() } }
    private var hoverPoint: CGPoint?
    private var viewSize: CGSize = .zero
    @Published var section: Section = .network
    @Published var showInspector = true
    @Published var showRaster = true

    // simulation
    @Published var running = false { didSet { engine.running = running } }
    @Published var speed: Double = 1000 { didSet { engine.ticksPerSecond = speed } }
    @Published var driveInputs = false { didSet { updateExternal() } }
    @Published var inputCurrent: Double = 40 { didSet { updateExternal() } }
    @Published var selectionCurrent: Double = 0 { didSet { updateExternal() } }
    @Published var pulseCurrent: Double = 400
    @Published var kernelSeed: Double = 12345
    let live = LiveStats()          // 10 Hz counters, observed only by the views that show them
    @Published var simModel = "lif_int"
    @Published var models: [[String: Any]] = []
    @Published var offlineResult: OfflineRun?

    // editing defaults
    @Published var newNeuron = Neuron(pos: .zero, refractory: 3) { didSet { updateGhost() } }
    @Published var newWeight: Double = 200
    @Published var newDelay: Double = 2

    // project
    @Published var project: [String: JSONValue] = AppState.emptyProject()
    @Published var projectURL: URL?
    @Published var plan = PlanSpec.example() { didSet { rebuildOverlay() } }
    @Published var genome: JSONValue = .object([:])
    @Published var devSeed: Double = 0
    @Published var geometries: [GeometryItem] = [] { didSet { rebuildCloud(); rebuildOverlay() } }
    @Published var geometryTypes: [GeometryType] = []
    @Published var stages: [StageInfo] = []
    @Published var stagesAvailable = false
    @Published var checkpoints: [Checkpoint] = []
    @Published var checkpointSource = ""
    @Published var checkpointIndex = 0
    @Published var capabilities: [TaskCap] = []
    @Published var pythonInfo = ""
    @Published var rules: [String: [String]] = [:]

    // results
    @Published var estimates: [[String: Any]] = []
    @Published var fiCurve: ([Double], [Double])?
    @Published var evolution: [[String: Any]] = []
    @Published var evolvedGenome: JSONValue?
    @Published var stats: JSONValue?
    @Published var plasticityRules: [(String, [(String, JSONValue)])] = []
    @Published var plasticityReport = ""
    @Published var recordingPlasticity = false
    @Published var scheduleReport = ""

    // status
    @Published var status = "Ready"
    @Published var busy: String?
    @Published var log: [LogLine] = []
    @Published var bridgeStatus = "Python not started"
    @Published var lastError: String?
    @Published var alert: AppAlert?
    @Published var machine = MachineResources.current()
    @Published var growEstimate: [String: Any] = [:]

    struct AppAlert: Identifiable { let id = UUID(); let title: String; let message: String }

    func showAlert(_ title: String, _ message: String) { alert = AppAlert(title: title, message: message) }

    /// Runs a resource check; on refusal shows why and returns false.
    func allowed(_ check: () throws -> Void) -> Bool {
        do { try check(); return true } catch {
            showAlert("Not enough resources", error.localizedDescription)
            status = "Refused: " + error.localizedDescription
            return false
        }
    }

    struct OfflineRun { let model: String; let ticks: Int; let t: [Int]; let i: [Int]; let rateHz: Double }

    let engine: SimEngine
    let bridge: Bridge
    private(set) weak var renderer: Renderer?
    private var undoStack: [Network] = [], redoStack: [Network] = []
    private var timer: Timer?
    private var positions: [SIMD3<Float>] = []
    private var inhibitory: [Bool] = []
    private var lastRates: [Float] = []
    private var fpsSmooth = 60.0
    private var evolveJob: Int?

    static let defaults = UserDefaults.standard

    static func emptyProject() -> [String: JSONValue] {
        ["version": .string("1.0.0"), "geometry": .object([:]), "fields": .object([:]), "schedule": .array([]),
         "genome": .object([:]), "plugins": .array([]), "neuron_model": .string("lif_int"),
         "metadata": .object(["created_with": .string("Neurogenesis desktop app")])]
    }

    init() {
        engine = SimEngine(Network())
        let cfg = AppConfig.load()
        bridge = Bridge(python: cfg.python, repo: cfg.repo)
        bridge.onStatus = { [weak self] s in
            self?.bridgeStatus = s
            if s == "Python ready" { self?.refreshToolbox() }
            if s.hasPrefix("cannot start") { self?.showAlert("The toolbox cannot start", s) }
        }
        bridge.onLog = { [weak self] s in
            for line in s.split(separator: "\n") where !line.trimmingCharacters(in: .whitespaces).isEmpty {
                self?.appendLog(String(line), error: line.contains("Error") || line.contains("Traceback"))
            }
        }
        bridge.onProgress = { [weak self] job, data in
            guard let self, job == self.evolveJob else { return }
            self.evolution.append(data)
            self.status = "evolution: generation \(data["generation"] ?? "?"), best \(data["best"] ?? "?")"
        }
        bridge.start()
        timer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.poll() }
        }
        engine.ticksPerSecond = speed
    }

    // MARK: rendering

    func attach(renderer r: Renderer) {
        renderer = r
        r.engine = engine
        r.pointSize = Float(pointSize)
        r.flashTau = Float(flashTau)
        r.onFrame = { [weak self] dt in
            DispatchQueue.main.async {
                guard let self, dt > 0 else { return }
                self.fpsSmooth = 0.95 * self.fpsSmooth + 0.05 * (1 / dt)
            }
        }
        if network.isEmpty { loadDemoNetwork() } else { rebuildAll(frame: true) }
    }

    private func loadDemoNetwork() {
        Task {
            await run("Growing the example plan") {
                try await self.completeGenome()
                let r = try await self.bridge.dict("grow", ["plan": self.plan.dict, "genome": self.genome.any, "seed": Int(self.devSeed)])
                try self.loadNGB(r, frame: true, undoable: false)
                self.status = "Example network grown from the body plan (Body plan panel)"
            }
        }
    }

    func rebuildAll(frame: Bool = false) {
        positions = network.neurons.map { SIMD3<Float>($0.pos) }
        inhibitory = network.inhibitoryMask()
        rebuildNeurons(); rebuildSynapses(); rebuildOverlay(); rebuildCloud()
        let (lo, hi) = sceneBounds()
        renderer?.setGrid(lo: lo, hi: hi)
        if frame { frameAll() }
    }

    func sceneBounds() -> (SIMD3<Float>, SIMD3<Float>) {
        var (lo, hi) = network.bounds()
        if network.isEmpty { lo = SIMD3(repeating: .infinity); hi = SIMD3(repeating: -.infinity) }
        for g in geometries where g.visible && !g.preview.isEmpty { lo = simd_min(lo, g.lo); hi = simd_max(hi, g.hi) }
        if lo.x == .infinity { return (SIMD3(-50, -50, -50), SIMD3(50, 50, 50)) }
        return (lo, hi)
    }

    func frameAll() {
        let (lo, hi) = sceneBounds()
        renderer?.camera.frame(lo, hi)
    }

    func neuronColor(_ i: Int) -> SIMD4<Float> {
        let n = network.neurons[i]
        switch colorMode {
        case .region: return n.compartment < 0 ? signColor(inhibitory[i]) : paletteColor(Int(n.compartment))
        case .sign: return signColor(inhibitory[i])
        case .role: return [SIMD4<Float>(0.62, 0.66, 0.72, 1), SIMD4(0.35, 0.85, 0.45, 1), SIMD4(0.98, 0.70, 0.25, 1)][Int(max(0, min(2, n.role)))]
        case .mode: return [SIMD4<Float>(0.55, 0.62, 0.75, 1), SIMD4(0.95, 0.35, 0.65, 1), SIMD4(0.40, 0.85, 0.90, 1)][Int(max(0, min(2, n.mode)))]
        case .threshold: return heat((Float(n.threshold) - 512) / 1536)
        case .activity:
            let r = i < lastRates.count ? lastRates[i] : 0
            return heat(log1p(r) / log1p(100))
        }
    }

    func rebuildNeurons() {
        guard let r = renderer, positions.count == network.neurons.count, inhibitory.count == network.neurons.count else { return }
        let sel = Set(selection)
        let inst = network.neurons.indices.map { i -> PointInstance in
            let p = positions[i]
            var c = neuronColor(i)
            var s: Float = network.neurons[i].mode != 0 ? 1.15 : 1
            if sel.contains(i) { c = SIMD4(1, 1, 1, 1); s *= 1.8 }
            return PointInstance(x: p.x, y: p.y, z: p.z, size: s, color: c)
        }
        r.setNeurons(inst)
    }

    func rebuildSynapses() {
        guard let r = renderer, positions.count == network.neurons.count else { return }
        guard synapseDisplay == .all, !network.synapses.isEmpty else { r.setSynapses([]); return }
        let E = network.synapses.count, cap = Int(synapseCap)
        let stride = max(1, (E + cap - 1) / cap)
        var v: [LineVertex] = []
        v.reserveCapacity(2 * min(E, cap))
        let alpha: Float = E > 20000 ? 0.07 : (E > 4000 ? 0.12 : 0.22)
        var k = 0
        while k < E {
            let s = network.synapses[k]
            k += stride
            let a = Int(s.pre), b = Int(s.post)
            guard a < positions.count, b < positions.count else { continue }
            let c = s.weight < 0 ? SIMD4<Float>(0.35, 0.55, 1.0, alpha) : SIMD4<Float>(0.98, 0.55, 0.35, alpha)
            arrow(&v, positions[a], positions[b], c, pre: Int32(a), head: arrowHead)
        }
        r.setSynapses(v)
    }

    func rebuildOverlay() {
        guard let r = renderer, positions.count == network.neurons.count else { return }
        var v: [LineVertex] = []
        func seg(_ a: SIMD3<Float>, _ b: SIMD3<Float>, _ c: SIMD4<Float>, pre: Int32 = -1) {
            v.append(LineVertex(x: a.x, y: a.y, z: a.z, pre: pre, color: c))
            v.append(LineVertex(x: b.x, y: b.y, z: b.z, pre: pre, color: c))
        }
        func box(_ lo: SIMD3<Float>, _ hi: SIMD3<Float>, _ c: SIMD4<Float>) {
            let p = (0..<8).map { k in SIMD3<Float>(k & 1 == 0 ? lo.x : hi.x, k & 2 == 0 ? lo.y : hi.y, k & 4 == 0 ? lo.z : hi.z) }
            for (a, b) in [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)] { seg(p[a], p[b], c) }
        }
        if synapseDisplay != .none, !selection.isEmpty, network.synapses.count > 0 {
            let sel = Set(selection.map { Int32($0) })
            for s in network.synapses where sel.contains(s.pre) || sel.contains(s.post) {
                let a = Int(s.pre), b = Int(s.post)
                guard a < positions.count, b < positions.count else { continue }
                let c: SIMD4<Float> = sel.contains(s.pre) ? SIMD4(1, 0.75, 0.3, 0.9) : SIMD4(0.4, 0.85, 1, 0.9)
                arrow(&v, positions[a], positions[b], c, pre: s.pre, head: arrowHead * 1.3)
            }
        }
        if tool == .add {                                   // the placement plane: a grid at x[axis] = level
            let (lo0, hi0) = sceneBounds()
            let pad = max(simd_reduce_max(hi0 - lo0) * 0.15, 10)
            let lo = lo0 - pad, hi = hi0 + pad
            let ax = placeAxis, u = (ax + 1) % 3, w = (ax + 2) % 3
            let lv = Float(placeLevel)
            func pt(_ a: Float, _ b: Float) -> SIMD3<Float> { var p = SIMD3<Float>(repeating: lv); p[u] = a; p[w] = b; return p }
            let c = SIMD4<Float>(0.35, 0.85, 0.95, 0.22), edge = SIMD4<Float>(0.35, 0.85, 0.95, 0.75)
            let k = 12
            for j in 0...k {
                let a = lo[u] + (hi[u] - lo[u]) * Float(j) / Float(k), b = lo[w] + (hi[w] - lo[w]) * Float(j) / Float(k)
                seg(pt(a, lo[w]), pt(a, hi[w]), j == 0 || j == k ? edge : c)
                seg(pt(lo[u], b), pt(hi[u], b), j == 0 || j == k ? edge : c)
            }
        }
        if showRegionBoxes {
            for (k, reg) in plan.regions.enumerated() {
                let lo = SIMD3<Float>(reg.origin), hi = lo + SIMD3<Float>(reg.size)
                var c = paletteColor(k); c.w = 0.35
                box(lo, hi, c)
            }
        }
        for (k, g) in geometries.enumerated() where g.visible && !g.preview.isEmpty {
            var c = paletteColor(k + 3); c.w = 0.5
            box(g.lo, g.hi, c)
        }
        r.setOverlay(v)
    }

    func signColor(_ inh: Bool) -> SIMD4<Float> { inh ? SIMD4(0.35, 0.55, 1.0, 1) : SIMD4(0.98, 0.42, 0.30, 1) }

    /// Arrowhead length for this scene: a fortieth of its size.
    var arrowHead: Float { let (lo, hi) = sceneBounds(); return max(simd_length(hi - lo) / 40, 0.5) }

    /// A synapse as an arrow from pre to post: a shaft and a four-barbed head (visible from every side), stopping a
    /// little before the postsynaptic cell so that the head is not hidden in it.
    func arrow(_ v: inout [LineVertex], _ a: SIMD3<Float>, _ b: SIMD3<Float>, _ c: SIMD4<Float>, pre: Int32, head: Float) {
        let d = b - a, len = simd_length(d)
        guard len > 1e-4 else { return }
        let dir = d / len
        let tip = b - dir * min(len * 0.12, head * 0.5)
        let h = min(head, len * 0.35)
        var u = simd_cross(dir, abs(dir.y) < 0.9 ? SIMD3<Float>(0, 1, 0) : SIMD3<Float>(1, 0, 0))
        u = simd_normalize(u)
        let w = simd_cross(dir, u)
        func add(_ p: SIMD3<Float>, _ col: SIMD4<Float>) { v.append(LineVertex(x: p.x, y: p.y, z: p.z, pre: pre, color: col)) }
        add(a, c); add(tip, c * SIMD4(1, 1, 1, 0.8))
        var hc = c; hc.w = min(1, c.w * 2.2)
        for side in [u, -u, w, -w] { add(tip, hc); add(tip - dir * h + side * h * 0.35, hc) }
    }

    func rebuildCloud() {
        guard let r = renderer else { return }
        var pts: [PointInstance] = []
        for (k, g) in geometries.enumerated() where g.visible {
            var c = paletteColor(k + 3); c.w = 0.55
            for p in g.preview { pts.append(PointInstance(x: p.x, y: p.y, z: p.z, size: 0.35, color: c)) }
        }
        r.setCloud(pts)
    }

    private func selectionChanged() {
        rebuildNeurons(); rebuildOverlay(); updateExternal()
    }

    // MARK: polling (10 Hz)

    private var pollCount = 0

    private func poll() {
        pollCount += 1
        let (_, _, c) = engine.recent(200)
        let total = c.reduce(0) { $0 + Int($1) }
        let rate = c.isEmpty || network.neurons.isEmpty ? 0 : Double(total) / Double(network.neurons.count) / (Double(c.count) / 1000)
        live.update(tick: engine.tick, rateHz: rate, tps: engine.measuredTPS, fps: fpsSmooth)
        if pollCount % 10 == 0 && section == .analysis && !network.regionNames.isEmpty {
            let r = engine.rates(1000)
            var sum = [Double](repeating: 0, count: network.regionNames.count), cnt = sum
            for (i, n) in network.neurons.enumerated() where n.compartment >= 0 && Int(n.compartment) < sum.count && i < r.count {
                sum[Int(n.compartment)] += Double(r[i]); cnt[Int(n.compartment)] += 1
            }
            live.regionRates = zip(sum, cnt).map { $1 > 0 ? $0 / $1 : 0 }
        }
        if colorMode == .activity, pollCount % 3 == 0, engine.running {
            lastRates = engine.rates(500)
            rebuildNeurons()
        }
    }

    /// A Project section as it will be saved, without modifying state (safe to call while views render).
    func projectValue(_ key: String) -> JSONValue {
        switch key {
        case "plan": return JSONValue(plan.dict)
        case "genome": return genome
        case "geometry":
            var geo: [String: JSONValue] = [:]
            for g in geometries { geo[g.name] = g.spec }
            return .object(geo)
        default: return project[key] ?? .null
        }
    }

    // MARK: network changes

    func setNetwork(_ net: Network, frame: Bool = false, undoable: Bool = true) {
        if undoable { undoStack.append(network); if undoStack.count > 40 { undoStack.removeFirst() }; redoStack.removeAll() }
        network = net
        positions = net.neurons.map { SIMD3<Float>($0.pos) }
        inhibitory = net.inhibitoryMask()
        let kept = selection.filter { $0 < net.neurons.count }
        if kept != selection { selection = kept }
        engine.seed = UInt32(truncatingIfNeeded: Int(kernelSeed))
        engine.load(net)
        updateExternal()
        rebuildAll(frame: frame)
    }

    var canUndo: Bool { !undoStack.isEmpty }
    var canRedo: Bool { !redoStack.isEmpty }

    func undo() {
        guard let prev = undoStack.popLast() else { return }
        redoStack.append(network)
        setNetwork(prev, undoable: false)
    }

    func redo() {
        guard let next = redoStack.popLast() else { return }
        undoStack.append(network)
        setNetwork(next, undoable: false)
    }

    func resetSimulation() {
        engine.seed = UInt32(truncatingIfNeeded: Int(kernelSeed))
        engine.load(network)
        updateExternal()
    }

    func updateExternal() {
        var e = [Int32](repeating: 0, count: network.neurons.count)
        if driveInputs { for (i, n) in network.neurons.enumerated() where n.role == 1 { e[i] = Int32(inputCurrent) } }
        if selectionCurrent != 0 { for i in selection where i < e.count { e[i] &+= Int32(selectionCurrent) } }
        engine.setExternal(e)
    }

    func modifyNetwork(_ f: (inout Network) -> Void) {
        var n = network
        f(&n)
        setNetwork(n)
    }

    func addNeuron(at p: SIMD3<Float>) {
        var nn = newNeuron
        nn.pos = SIMD3<Double>(p)
        modifyNetwork { $0.neurons.append(nn) }
        selection = [network.neurons.count - 1]
        status = "Added neuron #\(network.neurons.count - 1)"
    }

    func deleteSelection() {
        guard !selection.isEmpty else { return }
        let del = Set(selection)
        var map = [Int32](repeating: -1, count: network.neurons.count)
        var k: Int32 = 0
        for i in network.neurons.indices where !del.contains(i) { map[i] = k; k += 1 }
        modifyNetwork { n in
            n.neurons = n.neurons.enumerated().filter { !del.contains($0.offset) }.map { $0.element }
            n.synapses = n.synapses.compactMap { s in
                guard Int(s.pre) < map.count, Int(s.post) < map.count, map[Int(s.pre)] >= 0, map[Int(s.post)] >= 0 else { return nil }
                return Synapse(pre: map[Int(s.pre)], post: map[Int(s.post)], weight: s.weight, delay: s.delay)
            }
        }
        status = "Deleted \(del.count) neuron(s)"
        selection = []
    }

    func connect(from pres: [Int], to post: Int) {
        let w = Int32(newWeight), d = Int32(max(0, min(31, newDelay)))
        let existing = Set(network.synapses.map { SIMD2($0.pre, $0.post) })
        let new = pres.filter { $0 != post && !existing.contains(SIMD2(Int32($0), Int32(post))) }
        guard !new.isEmpty else { return }
        modifyNetwork { n in
            for p in new { n.synapses.append(Synapse(pre: Int32(p), post: Int32(post), weight: n.neurons[p].baseWeight < 0 ? -abs(w) : w, delay: d)) }
        }
        status = "Connected \(new.count) neuron(s) → #\(post)"
    }

    func removeSynapses(of idx: Set<Int>, incoming: Bool, outgoing: Bool) {
        modifyNetwork { n in
            n.synapses.removeAll { (outgoing && idx.contains(Int($0.pre))) || (incoming && idx.contains(Int($0.post))) }
        }
    }

    func clearNetwork() {
        setNetwork(Network(morphology: "Manual"))
        status = "Empty network: use the Add neuron tool (⌘2) or sample cells in a geometry"
    }

    func updateSelected(_ f: (inout Neuron) -> Void) {
        guard !selection.isEmpty else { return }
        modifyNetwork { n in for i in selection where i < n.neurons.count { f(&n.neurons[i]) } }
    }

    // MARK: view interaction

    func viewClicked(_ p: CGPoint, size: CGSize, modifiers: NSEvent.ModifierFlags) {
        guard let r = renderer else { return }
        let hit = r.pick(p, size: size, positions: positions)
        if modifiers.contains(.option), let h = hit {
            engine.inject(h, current: Int32(pulseCurrent)); status = "Pulse \(Int(pulseCurrent)) → #\(h)"; return
        }
        switch tool {
        case .select:
            if let h = hit {
                if modifiers.contains(.shift) || modifiers.contains(.command) {
                    if let k = selection.firstIndex(of: h) { selection.remove(at: k) } else { selection.append(h) }
                } else { selection = [h] }
            } else if !modifiers.contains(.shift) { selection = [] }
        case .add:
            guard let q = r.axisPlanePoint(p, size: size, axis: placeAxis, level: Float(placeLevel)) else {
                status = "Click on the placement plane (it is seen edge-on or behind you: orbit the view)"; return
            }
            addNeuron(at: q)
        case .connect:
            guard let h = hit else { return }
            if selection.isEmpty { selection = [h]; status = "Source selected: click a target" }
            else { connect(from: selection, to: h); if !modifiers.contains(.shift) { selection = [h] } }
        case .stimulate:
            if let h = hit { engine.inject(h, current: Int32(pulseCurrent)); status = "Pulse \(Int(pulseCurrent)) → #\(h)" }
        }
    }

    func viewHovered(_ p: CGPoint?, size: CGSize) {
        hoverPoint = p; viewSize = size
        updateGhost()
    }

    func cameraMoved() { if tool == .add { updateGhost() } }

    /// The neuron the Add tool would place under the pointer, in its excitatory / inhibitory colour.
    func updateGhost() {
        guard let r = renderer else { return }
        guard tool == .add, let p = hoverPoint, let q = r.axisPlanePoint(p, size: viewSize, axis: placeAxis, level: Float(placeLevel)) else {
            r.setGhost(nil); return
        }
        var c = signColor(newNeuron.baseWeight < 0); c.w = 0.75
        r.setGhost(PointInstance(x: q.x, y: q.y, z: q.z, size: 1.4, color: c))
    }

    func placeLevelFromSelection() {
        guard let i = selection.first, i < network.neurons.count else { return }
        placeLevel = network.neurons[i].pos[placeAxis]
    }

    func viewDoubleClicked(_ p: CGPoint, size: CGSize) {
        guard let r = renderer, let h = r.pick(p, size: size, positions: positions) else { return }
        r.camera.target = positions[h]
        selection = [h]
    }

    func viewKey(_ e: NSEvent) -> Bool {
        switch e.keyCode {
        case 51, 117: deleteSelection(); return true             // delete
        case 53: selection = []; return true                      // escape
        case 3: frameAll(); return true                           // F
        case 49: running.toggle(); return true                    // space
        case 33 where tool == .add, 30 where tool == .add:        // [ and ]: move the placement plane
            let (lo, hi) = sceneBounds()
            placeLevel += Double(max((hi[placeAxis] - lo[placeAxis]) / 20, 0.5)) * (e.keyCode == 30 ? 1 : -1)
            return true
        default: return false
        }
    }

    func selectAll() { selection = Array(network.neurons.indices) }

    func selectRegion(_ c: Int32) { selection = network.neurons.indices.filter { network.neurons[$0].compartment == c } }

    // MARK: toolbox calls

    func appendLog(_ s: String, error: Bool = false) {
        log.append(LogLine(text: s, error: error))
        if log.count > 600 { log.removeFirst(log.count - 600) }
    }

    func run(_ label: String, _ body: @escaping () async throws -> Void) async {
        busy = label
        status = label + "…"
        let t0 = Date()
        do {
            try await body()
            appendLog("\(label): done in \(String(format: "%.2f", Date().timeIntervalSince(t0))) s")
            if status == label + "…" { status = label + ": done" }
        } catch {
            let msg = (error as? BridgeError)?.message ?? error.localizedDescription
            let resource = error is ResourceError || (error as? BridgeError)?.isResource == true
            lastError = msg
            status = "\(label) \(resource ? "refused" : "failed"): \(msg)"
            appendLog(status, error: true)
            if let t = (error as? BridgeError)?.trace, !t.isEmpty { appendLog(t, error: true) }
            showAlert(resource ? "Not enough resources" : "\(label) failed", msg)
        }
        machine = MachineResources.current()
        busy = nil
    }

    func action(_ label: String, _ body: @escaping () async throws -> Void) {
        Task { await run(label, body) }
    }

    func loadNGB(_ r: [String: Any], frame: Bool = false, undoable: Bool = true) throws {
        guard let path = r["path"] as? String else { throw BridgeError(message: "no network in reply") }
        if let (n, e) = ResourceGuard.ngbHeader(path) {
            try ResourceGuard.checkNetwork(neurons: n, synapses: e, drawn: Int(synapseCap), action: "Showing a network of \(n) neurons and \(e) synapses")
        }
        var net = try Network.readNGB(URL(fileURLWithPath: path))
        net.morphology = r["morphology"] as? String ?? net.morphology
        net.regionNames = r["regions"] as? [String] ?? []
        setNetwork(net, frame: frame, undoable: undoable)
    }

    func networkFile() throws -> String {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("ng-desktop-\(UUID().uuidString).ngb")
        try network.writeNGB(url)
        return url.path
    }

    func refreshToolbox() {
        Task {
            do {
                let c = try await bridge.dict("capabilities")
                capabilities = (c["tasks"] as? [[String: Any]] ?? []).map {
                    TaskCap(task: $0["task"] as? String ?? "", name: $0["name"] as? String ?? "", available: $0["available"] as? Bool ?? false)
                }
                pythonInfo = "Python \(c["python"] ?? "?") · \(c["executable"] ?? "") · toolbox \(c["repo"] ?? "")"
                let g = try await bridge.dict("geometry_types")
                geometryTypes = (g["types"] as? [[String: Any]] ?? []).map { t in
                    GeometryType(type: t["type"] as? String ?? "", params: (t["params"] as? [[String: Any]] ?? []).map {
                        GeometryParam(name: $0["name"] as? String ?? "", kind: $0["kind"] as? String ?? "float", def: JSONValue($0["default"]))
                    })
                }
                let s = try await bridge.dict("stages")
                stagesAvailable = s["available"] as? Bool ?? false
                stages = (s["stages"] as? [[String: Any]] ?? []).map { d in
                    StageInfo(name: d["name"] as? String ?? "", task: d["task"] as? String ?? "", available: d["available"] as? Bool ?? false,
                              doc: d["doc"] as? String ?? "",
                              params: (d["params"] as? [[String: Any]] ?? []).map { ($0["name"] as? String ?? "", JSONValue($0["default"])) })
                }
                models = (try await bridge.dict("models"))["models"] as? [[String: Any]] ?? []
                let pr = try await bridge.dict("plasticity_rules")
                plasticityRules = (pr["rules"] as? [[String: Any]] ?? []).map { r in
                    (r["name"] as? String ?? "", (r["params"] as? [[String: Any]] ?? []).map { ($0["name"] as? String ?? "", JSONValue($0["default"])) })
                }
                rules = (try await bridge.dict("rules")).mapValues { ($0 as? [String]) ?? [] }
            } catch {
                appendLog("toolbox probe failed: \(error.localizedDescription)", error: true)
            }
        }
    }

    func isAvailable(_ task: String) -> Bool? {
        let c = capabilities.filter { $0.task == task }
        if c.isEmpty { return nil }
        return c.contains { $0.available }
    }

    // MARK: presets, growth, development

    func generate(_ morphology: String, neurons: Int, seed: Int, extra: [String: Any] = [:]) {
        action("Generating \(morphology)") {
            var p: [String: Any] = ["morphology": morphology, "neurons": neurons, "seed": seed]
            p.merge(extra) { $1 }
            try self.loadNGB(try await self.bridge.dict("generate", p), frame: true)
        }
    }

    func completeGenome() async throws {
        let r = try await bridge.dict("plan_defaults", ["plan": plan.dict, "genome": genome.any])
        genome = JSONValue(r["genome"])
    }

    /// What growing the current plan will cost, and whether it fits (Body plan panel).
    func checkGrowResources() {
        action("Estimating growth") {
            try await self.completeGenome()
            self.growEstimate = try await self.bridge.dict("estimate_grow", ["plan": self.plan.dict, "genome": self.genome.any])
            if self.growEstimate["fits"] as? Bool == false { self.showAlert("Not enough resources", self.growEstimate["message"] as? String ?? "") }
        }
    }

    func grow() {
        action("Growing \(plan.name)") {
            try await self.completeGenome()
            let r = try await self.bridge.dict("grow", ["plan": self.plan.dict, "genome": self.genome.any, "seed": Int(self.devSeed)])
            try self.loadNGB(r, frame: true)
        }
    }

    func growSteps() {
        action("Developing \(plan.name) step by step") {
            try await self.completeGenome()
            let r = try await self.bridge.dict("grow_steps", ["plan": self.plan.dict, "genome": self.genome.any, "seed": Int(self.devSeed)])
            self.setCheckpoints(r)
        }
    }

    func runSchedule() {
        action("Running the schedule") {
            self.syncProject()
            let r = try await self.bridge.dict("run_schedule", ["project": self.projectDict(), "seed": Int(self.devSeed)])
            self.setCheckpoints(r)
        }
    }

    func scheduleInfo() {
        action("Schedule genes and cost") {
            self.syncProject()
            let r = try await self.bridge.dict("schedule_info", ["project": self.projectDict(), "N": max(self.network.neurons.count, 1000),
                                                                 "E": max(self.network.synapses.count, 10000)])
            var parts: [String] = []
            if let g = r["genes"] as? [String] { parts.append(g.isEmpty ? "no genes" : "genes: " + g.joined(separator: ", ")) }
            if let c = r["cost"] as? [String: Any] {
                parts.append(String(format: "cost: %.2f MB, %.3g operations", Double(c["bytes"] as? Int ?? 0) / 1e6, Double(c["ops"] as? Int ?? 0)))
            }
            if let e = r["cost_error"] as? String { parts.append("cost: \(e)") }
            self.scheduleReport = parts.joined(separator: " · ")
        }
    }

    private func setCheckpoints(_ r: [String: Any]) {
        checkpointSource = r["source"] as? String ?? ""
        checkpoints = (r["steps"] as? [[String: Any]] ?? []).map {
            Checkpoint(label: $0["label"] as? String ?? "", path: $0["path"] as? String ?? "", neurons: $0["neurons"] as? Int ?? 0,
                       synapses: $0["synapses"] as? Int ?? 0, regions: $0["regions"] as? [String] ?? [])
        }
        section = .development
        showCheckpoint(max(0, checkpoints.count - 1), frame: true)
    }

    func showCheckpoint(_ k: Int, frame: Bool = false) {
        guard k >= 0, k < checkpoints.count else { return }
        checkpointIndex = k
        let c = checkpoints[k]
        guard allowed({ try ResourceGuard.checkNetwork(neurons: c.neurons, synapses: c.synapses, drawn: Int(synapseCap), action: "Showing checkpoint \(c.label)") }) else { return }
        do {
            var net = try Network.readNGB(URL(fileURLWithPath: c.path))
            net.regionNames = c.regions
            net.morphology = plan.name
            setNetwork(net, frame: frame, undoable: false)
        } catch { status = "cannot read checkpoint: \(error.localizedDescription)" }
    }

    func wireByDistance(seed: Int, velocity: Double) {
        action("Wiring by distance") {
            let r = try await self.bridge.dict("wire", ["ngb": try self.networkFile(), "seed": seed, "conduction_velocity": velocity])
            let names = self.network.regionNames
            try self.loadNGB(r)
            self.network.regionNames = names
        }
    }

    func computeStats() {
        action("Network statistics") {
            self.stats = JSONValue(try await self.bridge.call("stats", ["ngb": try self.networkFile()]))
        }
    }

    // MARK: geometry

    func addGeometry(_ type: GeometryType) {
        let (lo, hi) = network.isEmpty ? (SIMD3<Float>(-20, -20, -20), SIMD3<Float>(20, 20, 20)) : network.bounds()
        let c = (lo + hi) / 2, ext = max(simd_reduce_max(hi - lo), 20)
        var spec: [String: JSONValue] = ["type": .string(type.type)]
        for p in type.params {
            switch (p.kind, p.name) {
            case ("vec3", "size"), ("vec3", "radii"): spec[p.name] = .array([.number(Double(ext / 2)), .number(Double(ext / 2)), .number(Double(ext / 4))])
            case ("vec3", "u_vec"): spec[p.name] = .array([.number(Double(ext)), .number(0), .number(0)])
            case ("vec3", "v_vec"): spec[p.name] = .array([.number(0), .number(0), .number(Double(ext))])
            case ("vec3", "p0"): spec[p.name] = .array([.number(Double(c.x)), .number(Double(c.y - ext / 2)), .number(Double(c.z))])
            case ("vec3", "p1"): spec[p.name] = .array([.number(Double(c.x)), .number(Double(c.y + ext / 2)), .number(Double(c.z))])
            case ("vec3", _): spec[p.name] = .array([.number(Double(c.x)), .number(Double(c.y)), .number(Double(c.z))])
            case ("geometry", _): spec[p.name] = .object(["type": .string("Sphere"), "center": .array([.number(Double(c.x)), .number(Double(c.y)), .number(Double(c.z))]), "radius": .number(Double(ext / 3))])
            case ("string", "x_expr"): spec[p.name] = .string("40*u")
            case ("string", "y_expr"): spec[p.name] = .string("10*sin(3*u)")
            case ("string", "z_expr"): spec[p.name] = .string("40*v")
            case ("string", _): spec[p.name] = .string("")
            default: spec[p.name] = p.def == .null ? .number(p.name.contains("thick") ? 4 : Double(ext / 3)) : p.def
            }
        }
        var name = type.type.lowercased(), k = 1
        while geometries.contains(where: { $0.name == name }) { k += 1; name = "\(type.type.lowercased())\(k)" }
        geometries.append(GeometryItem(name: name, spec: .object(spec)))
        previewGeometry(geometries.count - 1)
    }

    func previewGeometry(_ k: Int) {
        guard k < geometries.count else { return }
        let g = geometries[k]
        Task {
            do {
                let r = try await bridge.dict("geometry_preview", ["geometry": g.spec.any, "n": 2500])
                guard let idx = geometries.firstIndex(where: { $0.id == g.id }) else { return }
                let pts = (r["points"] as? [[Double]] ?? []).map { SIMD3<Float>(Float($0[0]), Float($0[1]), Float($0[2])) }
                let lo = r["lo"] as? [Double] ?? [0, 0, 0], hi = r["hi"] as? [Double] ?? [0, 0, 0]
                geometries[idx].preview = pts
                geometries[idx].lo = SIMD3(Float(lo[0]), Float(lo[1]), Float(lo[2]))
                geometries[idx].hi = SIMD3(Float(hi[0]), Float(hi[1]), Float(hi[2]))
                geometries[idx].error = nil
                renderer?.setGrid(lo: sceneBounds().0, hi: sceneBounds().1)
            } catch {
                if let idx = geometries.firstIndex(where: { $0.id == g.id }) {
                    geometries[idx].error = (error as? BridgeError)?.message ?? error.localizedDescription
                    geometries[idx].preview = []
                }
            }
        }
    }

    func sampleCells(in k: Int, n: Int, inhFraction: Double, role: Int, replace: Bool, seed: Int) {
        guard k < geometries.count else { return }
        let g = geometries[k]
        let total = (replace ? 0 : network.neurons.count) + n
        guard allowed({ try ResourceGuard.checkNetwork(neurons: total, synapses: replace ? 0 : network.synapses.count, drawn: Int(synapseCap), action: "Sampling \(n) cells") }) else { return }
        action("Sampling \(n) cells in \(g.name)") {
            let comp = replace ? 0 : Int(self.network.neurons.map { $0.compartment }.max() ?? -1) + 1
            let r = try await self.bridge.dict("geometry_cells", ["geometry": g.spec.any, "n": n, "inh_fraction": inhFraction,
                                                                   "role": role, "seed": seed, "compartment": comp,
                                                                   "refractory": Int(self.newNeuron.refractory)])
            var cells = try Network.readNGB(URL(fileURLWithPath: r["path"] as! String))
            if replace {
                cells.regionNames = [g.name]; cells.morphology = g.name
                self.setNetwork(cells, frame: true)
            } else {
                var net = self.network
                let off = Int32(net.neurons.count)
                net.neurons += cells.neurons
                net.synapses += cells.synapses.map { Synapse(pre: $0.pre + off, post: $0.post + off, weight: $0.weight, delay: $0.delay) }
                while net.regionNames.count < comp { net.regionNames.append("#\(net.regionNames.count)") }
                net.regionNames.append(g.name)
                self.setNetwork(net, frame: true)
            }
        }
    }

    // MARK: project

    func syncProject() {
        project["plan"] = JSONValue(plan.dict)
        project["genome"] = genome
        var geo: [String: JSONValue] = [:]
        for g in geometries { geo[g.name] = g.spec }
        project["geometry"] = .object(geo)
    }

    func projectDict() -> [String: Any] { project.mapValues { $0.any } }

    func adoptProject(_ p: [String: JSONValue]) {
        project = p
        if let pl = p["plan"], case .object = pl { plan = PlanSpec(pl) }
        genome = p["genome"] ?? .object([:])
        geometries = (p["geometry"]?.objectValue ?? [:]).sorted { $0.key < $1.key }.map { GeometryItem(name: $0.key, spec: $0.value) }
        for k in geometries.indices { previewGeometry(k) }
    }

    func newProject() {
        project = AppState.emptyProject(); projectURL = nil
        plan = PlanSpec.example(); genome = .object([:]); geometries = []; checkpoints = []
        status = "New project"
    }

    func openProject() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.json]
        panel.message = "Open a neurogenesis Project (.json), body plan, module or network"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        openFile(url)
    }

    /// Opens a Project, a module, a body plan or a network JSON, recognised by its content.
    func openFile(_ url: URL) {
        guard allowed({ try ResourceGuard.checkJSONFile(url, action: "Opening \(url.lastPathComponent)") }) else { return }
        guard let data = try? Data(contentsOf: url), let d = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else {
            status = "\(url.lastPathComponent) is not JSON"; return
        }
        if d["neurons"] != nil {
            do { var net = try Network.readJSON(url); if net.morphology.isEmpty { net.morphology = url.lastPathComponent }; setNetwork(net, frame: true); status = "Opened network \(url.lastPathComponent)" }
            catch { status = "cannot read network: \(error.localizedDescription)" }
        } else if (d["format"] as? String)?.hasPrefix("neurogenesis-module") == true {
            loadModule(url)
        } else if d["regions"] != nil && d["projections"] != nil {
            plan = PlanSpec(JSONValue(d)); section = .plan; status = "Opened body plan \(url.lastPathComponent)"
        } else {
            action("Opening project \(url.lastPathComponent)") {
                let r = try await self.bridge.dict("project_load", ["path": url.path])
                self.adoptProject(JSONValue(r["project"]).objectValue)
                self.projectURL = url
                self.section = .project
            }
        }
        NSDocumentController.shared.noteNewRecentDocumentURL(url)
    }

    func saveProject(as: Bool = false) {
        syncProject()
        var url = projectURL
        if url == nil || `as` {
            let panel = NSSavePanel()
            panel.allowedContentTypes = [.json]
            panel.nameFieldStringValue = (projectURL?.lastPathComponent) ?? "project.json"
            guard panel.runModal() == .OK, let u = panel.url else { return }
            url = u
        }
        guard let url else { return }
        action("Saving project \(url.lastPathComponent)") {
            _ = try await self.bridge.call("project_save", ["project": self.projectDict(), "path": url.path])
            self.projectURL = url
            NSDocumentController.shared.noteNewRecentDocumentURL(url)
        }
    }

    func validateProject() {
        syncProject()
        action("Validating project") {
            let r = try await self.bridge.dict("project_validate", ["project": self.projectDict()])
            self.status = (r["ok"] as? Bool == true ? "✓ " : "✗ ") + (r["message"] as? String ?? "")
        }
    }

    func openNetwork() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.json]
        guard panel.runModal() == .OK, let url = panel.url else { return }
        openFile(url)
    }

    func saveNetwork() {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.json]
        panel.nameFieldStringValue = "network.json"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do { try network.writeJSON(url); status = "Saved \(network.neurons.count) neurons to \(url.lastPathComponent) (opens in viz/ too)" }
        catch { status = "save failed: \(error.localizedDescription)" }
    }

    func savePlan() {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.json]
        panel.nameFieldStringValue = "\(plan.name).plan.json"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        action("Saving plan") { _ = try await self.bridge.call("plan_save", ["plan": self.plan.dict, "path": url.path]) }
    }

    // MARK: modules

    func loadModule(_ url: URL? = nil) {
        var u = url
        if u == nil {
            let panel = NSOpenPanel(); panel.allowedContentTypes = [.json]
            guard panel.runModal() == .OK else { return }
            u = panel.url
        }
        guard let u else { return }
        action("Loading module \(u.lastPathComponent)") {
            let r = try await self.bridge.dict("module_load", ["path": u.path, "seed": Int(self.devSeed)])
            self.plan = PlanSpec(JSONValue(r["plan"]))
            self.genome = JSONValue(r["genome"])
            if let net = r["network"] as? [String: Any] { try self.loadNGB(net, frame: true) }
            self.status = "Module \(r["name"] ?? ""): inputs \(r["inputs"] ?? []), outputs \(r["outputs"] ?? [])"
        }
    }

    func saveModule(name: String, inputs: [String], outputs: [String], description: String) {
        let panel = NSSavePanel(); panel.allowedContentTypes = [.json]
        panel.nameFieldStringValue = "\(name).module.json"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        action("Saving module") {
            try await self.completeGenome()
            _ = try await self.bridge.call("module_save", ["name": name, "plan": self.plan.dict, "genome": self.genome.any, "inputs": inputs,
                                                           "outputs": outputs, "description": description, "neuron_model": self.simModel, "path": url.path])
        }
    }

    func composeModules(_ urls: [URL], links: [[String]], name: String) {
        action("Composing \(urls.count) modules") {
            let r = try await self.bridge.dict("module_compose", ["paths": urls.map { $0.path }, "links": links, "name": name, "seed": Int(self.devSeed)])
            self.plan = PlanSpec(JSONValue(r["plan"]))
            self.genome = JSONValue(r["genome"])
            if let net = r["network"] as? [String: Any] { try self.loadNGB(net, frame: true) }
        }
    }

    // MARK: simulation with other models, cost, analysis

    func simulateOffline(model: String, ticks: Int) {
        action("Simulating \(ticks) ms with \(model)") {
            var ext: [String: Int] = [:]
            if self.driveInputs { for (i, n) in self.network.neurons.enumerated() where n.role == 1 { ext["\(i)"] = Int(self.inputCurrent) } }
            if self.selectionCurrent != 0 { for i in self.selection { ext["\(i)", default: 0] += Int(self.selectionCurrent) } }
            let r = try await self.bridge.dict("simulate", ["ngb": try self.networkFile(), "model": model, "ticks": ticks, "ext": ext,
                                                            "seed": Int(self.kernelSeed)])
            let t = r["t"] as? [Int] ?? [], i = r["i"] as? [Int] ?? []
            let rate = Double(t.count) / Double(max(self.network.neurons.count, 1)) / (Double(ticks) / 1000)
            self.offlineResult = OfflineRun(model: model, ticks: ticks, t: t, i: i, rateHz: rate)
        }
    }

    func estimate(neurons: Int, synapses: Int, ticks: Int, calibrate: Bool) {
        action(calibrate ? "Calibrating and estimating" : "Estimating cost") {
            let r = try await self.bridge.dict("estimate", ["neurons": neurons, "synapses": synapses, "ticks": ticks, "calibrate": calibrate])
            self.estimates = r["estimates"] as? [[String: Any]] ?? []
        }
    }

    func runFI(shiftV: Int, shiftS: Int, threshold: Int, refractory: Int, hi: Int, model: String) {
        action("F–I curve") {
            let r = try await self.bridge.dict("fi_curve", ["shift_v": shiftV, "shift_s": shiftS, "threshold": threshold, "refractory": refractory,
                                                            "hi": hi, "step": max(1, hi / 30), "model": model])
            self.fiCurve = ((r["currents"] as? [Double]) ?? (r["currents"] as? [Int])?.map(Double.init) ?? [], r["rate_hz"] as? [Double] ?? [])
        }
    }

    func regularity() {
        action("Mosaic regularity") {
            let idx = self.selection.isEmpty ? Array(self.network.neurons.indices) : self.selection
            let r = try await self.bridge.dict("regularity", ["ngb": try self.networkFile(), "indices": idx])
            self.status = String(format: "Nearest-neighbour regularity of %d cells: %.2f (≈1.9 random, larger = more regular)",
                                 r["cells"] as? Int ?? 0, r["regularity"] as? Double ?? 0)
        }
    }

    // MARK: plasticity and evolution

    func recordForPlasticity(ticks: Int, rule: String, params: [String: Any]) {
        guard !network.synapses.isEmpty else { status = "no synapses to modify"; return }
        recordingPlasticity = true
        engine.startRecording()
        let wasRunning = running
        running = true
        let start = engine.tick
        Task {
            while engine.tick - start < ticks { try? await Task.sleep(nanoseconds: 50_000_000) }
            let (n, t, i) = engine.stopRecording()
            running = wasRunning
            recordingPlasticity = false
            await run("Applying \(rule) to \(t.count) spikes") {
                let r = try await self.bridge.dict("plasticity", ["ngb": try self.networkFile(), "rule": rule, "params": params, "ticks": n,
                                                                  "t": t.map { Int($0) }, "i": i.map { Int($0) }])
                let w = r["weights"] as? [Int] ?? []
                guard w.count == self.network.synapses.count else { throw BridgeError(message: "weights: \(w.count) for \(self.network.synapses.count) synapses") }
                self.modifyNetwork { net in for k in net.synapses.indices { net.synapses[k].weight = Int32(clamping: w[k]) } }
                self.plasticityReport = String(format: "%@ on %d ms of activity (%d spikes): mean |Δw| = %.3f", rule, n, t.count, r["mean_change"] as? Double ?? 0)
            }
        }
    }

    func evolve(genes: [[String: Any]], target: Double, gens: Int, pop: Int, seeds: Int, current: Int) {
        evolution = []; evolvedGenome = nil
        action("Evolving \(genes.count) genes") {
            try await self.completeGenome()
            let r = try await self.bridge.dict("evolve", ["plan": self.plan.dict, "genome": self.genome.any, "genes": genes, "target_hz": target,
                                                          "gens": gens, "pop": pop, "seeds": seeds, "input_current": current]) { id in
                Task { @MainActor in self.evolveJob = id }
            }
            self.evolvedGenome = JSONValue(r["genome"])
        }
    }

    func restartBridge(python: String, repo: String) {
        guard !AppConfig.load().isRelease else { bridge.restart(); return }       // release builds: embedded runtime only
        var cfg = AppConfig.load()
        cfg.python = python; cfg.repo = repo
        cfg.save()
        bridge.restart(python: python, repo: repo)
    }
}

/// Which Python runs the bridge and which toolbox checkout it imports (empty: the toolbox installed in that Python).
/// Release builds (Info.plist NGPython "@bundled") always use the runtime embedded in Contents/Resources/python
/// (desktop/common/runtime): no stored setting overrides it and nothing falls back to another Python. Development
/// builds use the Python and checkout written by build.sh, which Roadmap status → Python can override.
struct AppConfig {
    var python: String
    var repo: String
    var isRelease = false

    /// The embedded runtime's interpreter, if this app has one.
    static var bundledPython: String? {
        guard let r = Bundle.main.resourcePath else { return nil }
        let p = r + "/python/bin/python3"
        return FileManager.default.isExecutableFile(atPath: p) ? p : nil
    }

    static func load() -> AppConfig {
        let info = Bundle.main.infoDictionary ?? [:]
        if info["NGPython"] as? String == "@bundled" {
            return AppConfig(python: bundledPython ?? "", repo: "", isRelease: true)
        }
        let d = UserDefaults.standard
        return AppConfig(python: d.string(forKey: "python") ?? info["NGPython"] as? String ?? "/usr/bin/python3",
                         repo: d.string(forKey: "repo") ?? info["NGRepo"] as? String ?? "")
    }

    /// Version of the embedded runtime (runtime.json), for display.
    static var runtimeDescription: String {
        guard let r = Bundle.main.path(forResource: "runtime", ofType: "json"), let d = FileManager.default.contents(atPath: r),
              let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return "embedded runtime" }
        let pk = j["packages"] as? [String: Any] ?? [:]
        return "Python \(j["python"] ?? "?") · jax \(pk["jax"] ?? "?") · numpy \(pk["numpy"] ?? "?") · \(j["target"] ?? "")"
    }

    func save() {
        UserDefaults.standard.set(python, forKey: "python")
        UserDefaults.standard.set(repo, forKey: "repo")
    }
}
