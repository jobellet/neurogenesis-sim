import AppKit
import SwiftUI

struct ContentView: View {
    @EnvironmentObject var app: AppState
    @State private var columns = NavigationSplitViewVisibility.all

    var body: some View {
        NavigationSplitView(columnVisibility: $columns) {
            List(selection: Binding(get: { app.section }, set: { if let s = $0 { app.section = s } })) {
                ForEach(Section.allCases) { s in
                    Label { HStack { Text(s.rawValue); Spacer(); TaskBadge(tasks: s.tasks) } } icon: { Image(systemName: s.icon) }
                        .tag(s)
                }
            }
            .navigationSplitViewColumnWidth(min: 170, ideal: 190, max: 240)
        } content: {
            PanelHost()
                .navigationSplitViewColumnWidth(min: 300, ideal: 350, max: 520)
        } detail: {
            VSplitView {
                ZStack(alignment: .topLeading) {
                    MetalViewport(app: app)
                    HUD()
                }
                .frame(minHeight: 260)
                if app.showRaster {
                    RasterView(app: app).frame(minHeight: 90, idealHeight: 170, maxHeight: 420)
                }
            }
            .safeAreaInset(edge: .bottom, spacing: 0) { StatusBar() }
        }
        .inspector(isPresented: $app.showInspector) {
            InspectorView().inspectorColumnWidth(min: 240, ideal: 280, max: 400)
        }
        .toolbar { MainToolbar() }
        .alert(item: $app.alert) { a in Alert(title: Text(a.title), message: Text(a.message), dismissButton: .default(Text("OK"))) }
        .navigationTitle(app.projectURL?.lastPathComponent ?? "Neurogenesis")
        .navigationSubtitle("\(app.network.morphology) · \(app.network.neurons.count) neurons · \(app.network.synapses.count) synapses")
        .onDrop(of: [.fileURL], isTargeted: nil) { providers in
            for p in providers {
                _ = p.loadObject(ofClass: URL.self) { url, _ in
                    if let url { DispatchQueue.main.async { app.openFile(url) } }
                }
            }
            return true
        }
    }
}

/// Green when the roadmap tasks of a panel are merged, grey while they are being built.
struct TaskBadge: View {
    @EnvironmentObject var app: AppState
    let tasks: [String]
    var body: some View {
        let missing = tasks.filter { app.isAvailable($0) == false }
        if !tasks.isEmpty && !missing.isEmpty {
            Text(missing.joined(separator: " "))
                .font(.system(size: 9, weight: .semibold, design: .monospaced))
                .padding(.horizontal, 4).padding(.vertical, 1)
                .background(Capsule().fill(Color.secondary.opacity(0.18)))
                .foregroundStyle(.secondary)
                .help("Being implemented: \(missing.joined(separator: ", ")). These controls light up when the code is merged.")
        }
    }
}

struct MainToolbar: ToolbarContent {
    @EnvironmentObject var app: AppState
    var body: some ToolbarContent {
        ToolbarItemGroup(placement: .navigation) {
            Button { app.running.toggle() } label: { Image(systemName: app.running ? "pause.fill" : "play.fill") }
                .help(app.running ? "Pause (space)" : "Run the simulation (space)")
            Button { app.engine.step(1) } label: { Image(systemName: "forward.frame") }.help("One tick (1 ms)")
            Button { app.resetSimulation() } label: { Image(systemName: "arrow.counterclockwise") }.help("Reset the simulation state")
            Menu {
                ForEach([("0.1×  (100 ms/s)", 100.0), ("0.25×", 250), ("Real time  (1000 ms/s)", 1000), ("4×", 4000), ("20×", 20000), ("Maximum", 0)], id: \.1) { l, v in
                    Button(l) { app.speed = v }
                }
            } label: { Text(app.speed == 0 ? "max" : "\(app.speed >= 1000 ? String(format: "%g×", app.speed / 1000) : String(format: "%g×", app.speed / 1000))").monospacedDigit() }
                .help("Simulation speed")
        }
        ToolbarItemGroup(placement: .principal) {
            Picker("Tool", selection: $app.tool) {
                ForEach(Tool.allCases) { t in Image(systemName: t.icon).help("\(t.rawValue): \(t.help)").tag(t) }
            }
            .pickerStyle(.segmented)
        }
        ToolbarItemGroup(placement: .primaryAction) {
            Picker("Colour", selection: $app.colorMode) { ForEach(ColorMode.allCases) { Text($0.rawValue).tag($0) } }
                .help("Colour neurons by")
            Picker("Synapses", selection: $app.synapseDisplay) { ForEach(SynapseDisplay.allCases) { Text($0.rawValue).tag($0) } }
                .help("Synapses drawn")
            Button { app.frameAll() } label: { Image(systemName: "viewfinder") }.help("Frame everything (F)")
            Toggle(isOn: $app.showRaster) { Image(systemName: "chart.bar.xaxis") }.help("Raster")
            Toggle(isOn: $app.showInspector) { Image(systemName: "sidebar.right") }.help("Inspector")
        }
    }
}

struct HUD: View {
    @EnvironmentObject var app: AppState
    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HUDCounters(live: app.live)
            Text(app.tool.help).font(.system(size: 10)).foregroundStyle(.secondary)
            if app.colorMode == .region, !app.network.regionNames.isEmpty {
                HStack(spacing: 8) {
                    ForEach(Array(app.network.regionNames.enumerated()), id: \.offset) { k, n in
                        HStack(spacing: 3) { Circle().fill(paletteColor(k).swiftUI).frame(width: 7, height: 7); Text(n) }
                            .onTapGesture { app.selectRegion(Int32(k)) }
                    }
                }.font(.system(size: 10))
            }
        }
        .padding(8)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 8))
        .padding(10)
        .allowsHitTesting(app.colorMode == .region)
    }
}

struct StatusBar: View {
    @EnvironmentObject var app: AppState
    var body: some View {
        HStack(spacing: 8) {
            if app.busy != nil { ProgressView().controlSize(.small) }
            Text(app.status).lineLimit(1).truncationMode(.middle)
            Spacer()
            Text(app.bridgeStatus).foregroundStyle(.secondary)
            Circle().fill(app.bridgeStatus == "Python ready" ? Color.green : Color.orange).frame(width: 7, height: 7)
        }
        .font(.system(size: 11))
        .padding(.horizontal, 10).padding(.vertical, 4)
        .background(.bar)
    }
}

// MARK: raster

struct RasterView: NSViewRepresentable {
    @ObservedObject var app: AppState
    func makeNSView(context: Context) -> RasterNSView { let v = RasterNSView(); v.engine = app.engine; return v }
    func updateNSView(_ v: RasterNSView, context: Context) { v.configure(app.network, mode: app.colorMode) }
}

/// Spike raster of the last ticks (neurons sorted by region) above the population spike count, redrawn at 30 Hz from a
/// bitmap (one pixel per tick and row), so that thousands of neurons cost the same as ten.
final class RasterNSView: NSView {
    weak var engine: SimEngine?
    private var rowOf: [Int] = []
    private var color: [UInt32] = []
    private var rows = 1
    private var bounds_: [Int] = []
    private var timer: Timer?
    private var key = ""
    var windowTicks = 1000

    override init(frame: NSRect) {
        super.init(frame: frame)
        timer = Timer.scheduledTimer(withTimeInterval: 1 / 30, repeats: true) { [weak self] _ in self?.needsDisplay = true }
    }
    required init?(coder: NSCoder) { fatalError() }
    override var isFlipped: Bool { true }

    func configure(_ net: Network, mode: ColorMode) {
        let k = "\(net.neurons.count)-\(net.synapses.count)-\(net.morphology)-\(mode)"
        guard k != key else { return }
        key = k
        let order = net.neurons.indices.sorted { (net.neurons[$0].compartment, $0) < (net.neurons[$1].compartment, $1) }
        rowOf = .init(repeating: 0, count: net.neurons.count)
        for (r, i) in order.enumerated() { rowOf[i] = r }
        rows = max(net.neurons.count, 1)
        let inh = net.inhibitoryMask()
        color = net.neurons.indices.map { i in
            let c = mode == .sign ? (inh[i] ? SIMD4<Float>(0.35, 0.55, 1, 1) : SIMD4<Float>(0.98, 0.42, 0.3, 1)) : paletteColor(Int(net.neurons[i].compartment))
            let r = UInt32(c.x * 255), g = UInt32(c.y * 255), b = UInt32(c.z * 255)
            return 0xFF00_0000 | (b << 16) | (g << 8) | r
        }
        bounds_ = []
        var last: Int32 = .min
        for (r, i) in order.enumerated() where net.neurons[i].compartment != last { bounds_.append(r); last = net.neurons[i].compartment }
    }

    override func draw(_ dirty: NSRect) {
        guard let ctx = NSGraphicsContext.current?.cgContext else { return }
        ctx.setFillColor(NSColor(calibratedRed: 0.05, green: 0.06, blue: 0.08, alpha: 1).cgColor)
        ctx.fill(bounds)
        guard let e = engine, e.n == rowOf.count, e.n > 0 else {
            ("No network" as NSString).draw(at: CGPoint(x: 10, y: 10), withAttributes: [.foregroundColor: NSColor.secondaryLabelColor])
            return
        }
        let W = windowTicks
        let rateH: CGFloat = 34
        let rasterRect = CGRect(x: 0, y: 0, width: bounds.width, height: max(bounds.height - rateH, 10))
        let H = max(1, min(rows, Int(rasterRect.height * 2)))
        let (first, lists, counts) = e.recent(W)
        var px = [UInt32](repeating: 0, count: W * H)
        let off = W - lists.count
        for (k, l) in lists.enumerated() {
            let x = off + k
            for i in l where Int(i) < rowOf.count {
                let y = rowOf[Int(i)] * H / rows
                px[y * W + x] = color[Int(i)]
            }
        }
        let cs = CGColorSpaceCreateDeviceRGB()
        if let prov = CGDataProvider(data: Data(bytes: px, count: px.count * 4) as CFData),
           let img = CGImage(width: W, height: H, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: W * 4, space: cs,
                             bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue), provider: prov,
                             decode: nil, shouldInterpolate: false, intent: .defaultIntent) {
            ctx.saveGState()
            ctx.interpolationQuality = .none
            ctx.translateBy(x: 0, y: rasterRect.height); ctx.scaleBy(x: 1, y: -1)
            ctx.draw(img, in: CGRect(x: 0, y: 0, width: rasterRect.width, height: rasterRect.height))
            ctx.restoreGState()
        }
        ctx.setStrokeColor(NSColor.white.withAlphaComponent(0.12).cgColor)
        for b in bounds_.dropFirst() {
            let y = CGFloat(b) / CGFloat(rows) * rasterRect.height
            ctx.move(to: CGPoint(x: 0, y: y)); ctx.addLine(to: CGPoint(x: bounds.width, y: y))
        }
        ctx.strokePath()
        // population spike count per tick (5-tick mean)
        let top = rasterRect.maxY
        ctx.setFillColor(NSColor.black.withAlphaComponent(0.35).cgColor)
        ctx.fill(CGRect(x: 0, y: top, width: bounds.width, height: rateH))
        if !counts.isEmpty {
            var sm = [Double](repeating: 0, count: counts.count), acc = 0.0
            for k in counts.indices { acc += Double(counts[k]); if k >= 5 { acc -= Double(counts[k - 5]) }; sm[k] = acc / 5 }
            let mx = max(sm.max() ?? 1, 1)
            ctx.setStrokeColor(NSColor.systemTeal.cgColor); ctx.setLineWidth(1.2)
            for (k, v) in sm.enumerated() {
                let x = CGFloat(off + k) / CGFloat(W) * bounds.width
                let y = top + rateH - 3 - CGFloat(v / mx) * (rateH - 8)
                k == 0 ? ctx.move(to: CGPoint(x: x, y: y)) : ctx.addLine(to: CGPoint(x: x, y: y))
            }
            ctx.strokePath()
            let label = String(format: "%d–%d ms · peak %.0f spikes/ms", first, first + lists.count, mx) as NSString
            label.draw(at: CGPoint(x: 6, y: top + 2), withAttributes: [.foregroundColor: NSColor.secondaryLabelColor, .font: NSFont.systemFont(ofSize: 9)])
        }
    }
}

// MARK: inspector

struct InspectorView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if app.selection.isEmpty {
                    Text("Nothing selected").font(.headline)
                    Text("Click a neuron in the 3D view (shift-click for several, double-click to centre on it). Use the tools in the toolbar to add neurons, connect them or stimulate them; ⌫ deletes the selection, ⌘Z undoes.")
                        .font(.callout).foregroundStyle(.secondary)
                    Divider()
                    NetworkSummary()
                } else if let i = app.selection.first, i < app.network.neurons.count {
                    NeuronEditor(index: i, count: app.selection.count)
                }
            }
            .padding(12)
        }
    }
}

struct NetworkSummary: View {
    @EnvironmentObject var app: AppState
    var body: some View {
        let n = app.network
        let inh = n.neurons.filter { $0.baseWeight < 0 }.count
        VStack(alignment: .leading, spacing: 4) {
            Text(n.morphology).font(.headline)
            Text("\(n.neurons.count) neurons (\(inh) with negative base weight)")
            Text("\(n.synapses.count) synapses, \(String(format: "%.1f", Double(n.synapses.count) / Double(max(n.neurons.count, 1)))) per neuron")
            Text("Drivers: \(n.neurons.filter { $0.mode == 1 }.count) Poisson, \(n.neurons.filter { $0.mode == 2 }.count) bursters")
            Text("Inputs: \(n.neurons.filter { $0.role == 1 }.count) · outputs: \(n.neurons.filter { $0.role == 2 }.count)")
            if !n.regionNames.isEmpty {
                Divider()
                ForEach(Array(n.regionNames.enumerated()), id: \.offset) { k, name in
                    Button { app.selectRegion(Int32(k)) } label: {
                        HStack { Circle().fill(paletteColor(k).swiftUI).frame(width: 8, height: 8); Text(name); Spacer()
                            Text("\(n.neurons.filter { $0.compartment == Int32(k) }.count)").foregroundStyle(.secondary) }
                    }.buttonStyle(.plain)
                }
            }
        }.font(.callout)
    }
}

struct NeuronEditor: View {
    @EnvironmentObject var app: AppState
    let index: Int
    let count: Int

    private func b<T>(_ kp: WritableKeyPath<Neuron, T>) -> Binding<T> {
        Binding(get: { app.network.neurons[min(index, app.network.neurons.count - 1)][keyPath: kp] },
                set: { v in app.updateSelected { $0[keyPath: kp] = v } })
    }

    var body: some View {
        let n = app.network.neurons[index]
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(count > 1 ? "\(count) neurons" : "Neuron #\(index)").font(.headline)
                Spacer()
                Button(role: .destructive) { app.deleteSelection() } label: { Image(systemName: "trash") }.help("Delete (⌫)")
            }
            if count > 1 { Text("Edits apply to every selected neuron; values shown are #\(index)'s.").font(.caption).foregroundStyle(.secondary) }
            Text("Region: \(app.network.regionName(n.compartment))").font(.caption).foregroundStyle(.secondary)
            Form {
                if count == 1 {
                    Vec3Field(label: "Position", value: Binding(get: { app.network.neurons[index].pos },
                                                                 set: { v in app.updateSelected { $0.pos = v } }))
                }
                Picker("Driver", selection: b(\.mode)) { Text("LIF").tag(Int32(0)); Text("Poisson").tag(Int32(1)); Text("Burster").tag(Int32(2)) }
                Picker("Role", selection: b(\.role)) { Text("internal").tag(Int32(0)); Text("input").tag(Int32(1)); Text("output").tag(Int32(2)) }
                IntField("Threshold", b(\.threshold))
                IntField("Leak shift (shift_v)", b(\.shiftV))
                IntField("Synaptic shift (shift_s)", b(\.shiftS))
                IntField("Refractory (ticks)", b(\.refractory))
                IntField("Base weight", b(\.baseWeight))
                IntField("Compartment", b(\.compartment))
                if n.mode == 1 { DoubleField("Poisson rate (Hz)", b(\.poissonHz)) }
                if n.mode == 2 { IntField("Burst period", b(\.burstPeriod)); IntField("Burst duty", b(\.burstDuty)) }
                DoubleField("Wiring radius", b(\.connRadius))
                DoubleField("Wiring probability", b(\.connProb))
            }
            .formStyle(.columns)
            HStack {
                Button("Pulse") { for i in app.selection { app.engine.inject(i, current: Int32(app.pulseCurrent)) } }
                    .help("Inject \(Int(app.pulseCurrent)) units of current once")
                Button("Centre") { app.renderer?.camera.target = SIMD3<Float>(n.pos) }
            }
            SynapseList(index: index)
        }
    }
}

struct SynapseList: View {
    @EnvironmentObject var app: AppState
    let index: Int
    var body: some View {
        let ins = app.network.synapses.indices.filter { Int(app.network.synapses[$0].post) == index }
        let outs = app.network.synapses.indices.filter { Int(app.network.synapses[$0].pre) == index }
        VStack(alignment: .leading, spacing: 6) {
            DisclosureGroup("Outgoing (\(outs.count))") { rows(outs, other: \.post) }
            DisclosureGroup("Incoming (\(ins.count))") { rows(ins, other: \.pre) }
            HStack {
                Button("Remove outgoing") { app.removeSynapses(of: Set(app.selection), incoming: false, outgoing: true) }
                Button("Remove incoming") { app.removeSynapses(of: Set(app.selection), incoming: true, outgoing: false) }
            }.controlSize(.small)
        }
    }

    @ViewBuilder func rows(_ idx: [Int], other: KeyPath<Synapse, Int32>) -> some View {
        ForEach(idx.prefix(200), id: \.self) { k in
            let s = app.network.synapses[k]
            HStack {
                Button("#\(s[keyPath: other])") { app.selection = [Int(s[keyPath: other])] }.buttonStyle(.link)
                TextField("w", value: Binding(get: { Int(app.network.synapses[k].weight) },
                                              set: { v in app.modifyNetwork { $0.synapses[k].weight = Int32(clamping: v) } }), format: .number)
                    .frame(width: 60)
                Stepper("d \(s.delay)", value: Binding(get: { Int(app.network.synapses[k].delay) },
                                                       set: { v in app.modifyNetwork { $0.synapses[k].delay = Int32(max(0, min(31, v))) } }), in: 0...31)
                Button { app.modifyNetwork { $0.synapses.remove(at: k) } } label: { Image(systemName: "xmark") }.buttonStyle(.borderless)
            }.font(.caption)
        }
        if idx.count > 200 { Text("… and \(idx.count - 200) more").font(.caption).foregroundStyle(.secondary) }
    }
}

// MARK: small fields

struct IntField: View {
    let label: String
    @Binding var value: Int32
    init(_ label: String, _ value: Binding<Int32>) { self.label = label; _value = value }
    var body: some View {
        TextField(label, value: Binding(get: { Int(value) }, set: { value = Int32(clamping: $0) }), format: .number)
    }
}

struct DoubleField: View {
    let label: String
    @Binding var value: Double
    init(_ label: String, _ value: Binding<Double>) { self.label = label; _value = value }
    var body: some View { TextField(label, value: $value, format: .number.precision(.fractionLength(0...4))) }
}

struct Vec3Field: View {
    let label: String
    @Binding var value: SIMD3<Double>
    var body: some View {
        LabeledContent(label) {
            HStack(spacing: 4) {
                TextField("x", value: $value.x, format: .number.precision(.fractionLength(0...3)))
                TextField("y", value: $value.y, format: .number.precision(.fractionLength(0...3)))
                TextField("z", value: $value.z, format: .number.precision(.fractionLength(0...3)))
            }
        }
    }
}

// MARK: live counters (their own observable object: 10 Hz updates redraw only these views)

final class LiveStats: ObservableObject {
    @Published private(set) var tick = 0
    @Published private(set) var rateHz = 0.0
    @Published private(set) var tps = 0.0
    @Published private(set) var fps = 0.0
    @Published var regionRates: [Double] = []

    func update(tick t: Int, rateHz r: Double, tps s: Double, fps f: Double) {
        if t != tick { tick = t }
        if abs(r - rateHz) > 0.05 { rateHz = r }
        if abs(s - tps) > 1 { tps = s }
        if abs(f - fps) > 1 { fps = f }
    }
}

struct HUDCounters: View {
    @ObservedObject var live: LiveStats
    var body: some View {
        HStack(spacing: 10) {
            Label("\(live.tick) ms", systemImage: "clock").monospacedDigit()
            Text(String(format: "%.1f Hz", live.rateHz)).monospacedDigit()
            Text(String(format: "%.0f ticks/s", live.tps)).monospacedDigit().foregroundStyle(.secondary)
            Text(String(format: "%.0f fps", live.fps)).monospacedDigit().foregroundStyle(.secondary)
        }
        .font(.system(size: 11, weight: .medium))
    }
}

struct LiveLine: View {
    @ObservedObject var live: LiveStats
    var body: some View {
        Text(String(format: "t = %d ms · %.1f Hz mean · %.0f ticks/s", live.tick, live.rateHz, live.tps))
            .font(.caption).monospacedDigit().foregroundStyle(.secondary)
    }
}

struct RegionRates: View {
    @ObservedObject var live: LiveStats
    let names: [String]
    var body: some View {
        if names.isEmpty {
            Text(String(format: "%.1f Hz mean", live.rateHz)).font(.caption)
        } else {
            ForEach(Array(names.enumerated()), id: \.offset) { k, name in
                HStack {
                    Circle().fill(paletteColor(k).swiftUI).frame(width: 8, height: 8); Text(name); Spacer()
                    Text(k < live.regionRates.count ? String(format: "%.1f Hz", live.regionRates[k]) : "–").monospacedDigit()
                }.font(.caption)
            }
        }
    }
}
