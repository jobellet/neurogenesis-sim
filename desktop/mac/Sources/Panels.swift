import Charts
import SwiftUI
import UniformTypeIdentifiers

struct PanelHost: View {
    @EnvironmentObject var app: AppState
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text(app.section.rawValue).font(.title2.weight(.semibold))
                switch app.section {
                case .project: ProjectPanel()
                case .geometry: GeometryPanel()
                case .fields: FieldsPanel()
                case .plan: PlanPanel()
                case .genome: GenomePanel()
                case .schedule: SchedulePanel()
                case .development: DevelopmentPanel()
                case .network: NetworkPanel()
                case .simulation: SimulationPanel()
                case .plasticity: PlasticityPanel()
                case .evolution: EvolutionPanel()
                case .modules: ModulesPanel()
                case .cost: CostPanel()
                case .analysis: AnalysisPanel()
                case .roadmap: RoadmapPanel()
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

/// A group of controls with a title.
struct Card<Content: View>: View {
    let title: String
    var subtitle: String? = nil
    @ViewBuilder var content: Content
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.headline)
            if let s = subtitle { Text(s).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true) }
            content
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 8).fill(Color.primary.opacity(0.04)))
    }
}

/// Shown for a roadmap feature whose code is not merged yet: what it will do, and that the panel lights up by itself.
struct Placeholder: View {
    @EnvironmentObject var app: AppState
    let task: String
    let title: String
    let text: String
    var body: some View {
        let ok = app.isAvailable(task)
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: ok == true ? "checkmark.seal.fill" : "hammer").foregroundStyle(ok == true ? .green : .orange)
            VStack(alignment: .leading, spacing: 2) {
                Text("\(task) · \(title)").font(.callout.weight(.semibold))
                Text(ok == true ? "Merged: available in this checkout." : "Being implemented by another agent. \(text) This control enables itself when the code lands (Roadmap status → Refresh).")
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 6).strokeBorder(ok == true ? Color.green.opacity(0.4) : Color.orange.opacity(0.45), style: StrokeStyle(lineWidth: 1, dash: ok == true ? [] : [4, 3])))
    }
}

/// Meaning of the genes and project keys shown in JSON trees (the (?) of each entry).
let keyHelp: [String: String] = [
    "count": "Number of neurons of a grown region (clipped to its count bounds).",
    "migration": "Where a grown region's neurons settle: mean (local u, v, w in [0, 1]) and spread (s.d. of the Gaussian scatter).",
    "mean": "Mean local position (u, v, w), each in [0, 1] inside the region's box.",
    "spread": "Standard deviation of the positions around the mean, in local units (the box is 1 wide).",
    "inhibitory": "Probability that a grown neuron is inhibitory: sigmoid(a0 + a · position).",
    "a0": "Bias of the inhibitory probability: sigmoid(a0); −1.4 ≈ 20 % inhibitory, 0 = 50 %.",
    "a": "Gradient of the inhibitory probability along u, v, w.",
    "excitability": "Leak and synaptic decay shifts of a region's neurons (larger = slower).",
    "shift_v": "Membrane leak shift: v loses v >> shift_v per tick (time constant ≈ 2^shift_v ms).",
    "shift_s": "Synaptic current decay shift: I loses I >> shift_s per tick.",
    "guidance": "Axon guidance of each projection \"src->dst\": where axons aim (B, c), how wide (sigma), how likely (p0) and how strong (w).",
    "B": "3 × 3 matrix mapping the source position to the target position (topography). Identity = point to point.",
    "c": "Offset added to the target position (u, v, w).",
    "sigma": "Width of the target zone, in local units: larger = more divergent projections.",
    "p0": "Peak connection probability at the target point (0–1).",
    "w": "Synaptic weight of the projection (integer current; inhibitory sources are made negative).",
    "inh_weight_factor": "Inhibitory synapses get −inh_weight_factor × w.",
    "w_clip": "Largest allowed absolute weight (default 512).",
    "receptors": "Gene used by fixed placements to repeat each label (example plans).",
    "identity": "Molecular identity code of a region (guidance rules use it).",
    "differentiation": "Lateral-inhibition differentiation of a grown region (thresholds, time constants, pacemakers).",
    "tonic": "Standing current per cell type.",
    "knockout": "Virtual knockouts: regions and projections removed before growth.",
    "version": "Project schema version.",
    "neuron_model": "Neuron model used to simulate (lif_int, two_compartment, hh).",
    "plugins": "Python modules imported on load (they register rules, stages or models).",
    "type": "Kind of geometry shape or Param.",
    "center": "Centre of the shape (x, y, z, space units).",
    "size": "Edge lengths of the box (x, y, z).",
    "radius": "Radius (space units).",
    "radii": "Semi-axes of the ellipsoid (x, y, z).",
    "thickness": "Thickness across the sheet (space units).",
]

/// Edits any JSON value as a tree (numbers, strings, booleans; objects and arrays fold), with a raw-text mode.
struct JSONEditor: View {
    @Binding var value: JSONValue
    @State private var raw = false
    @State private var text = ""
    @State private var error: String?
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Picker("View as", selection: $raw) { Text("Tree").tag(false); Text("JSON").tag(true) }.pickerStyle(.segmented).fixedSize()
                HelpButton(text: "Tree: edit each value in place (each entry has its own (?)). JSON: edit the whole text, then Apply.")
            }
            if raw {
                TextEditor(text: $text).font(.system(size: 11, design: .monospaced)).frame(minHeight: 160, maxHeight: 360)
                    .onAppear { text = value.pretty() }
                Flow {
                    Button("Apply") {
                        do { value = try JSONValue.parse(text); error = nil } catch { self.error = error.localizedDescription }
                    }
                    Button("Revert") { text = value.pretty() }
                }
                if let e = error { Text(e).font(.caption).foregroundStyle(.red).fixedSize(horizontal: false, vertical: true) }
            } else {
                JSONNodeView(key: nil, value: $value, depth: 0)
            }
        }
        .onChange(of: raw) { _, r in if r { text = value.pretty() } }
    }
}

struct JSONNodeView: View {
    let key: String?
    @Binding var value: JSONValue
    let depth: Int

    var help: String {
        guard let key else { return "" }
        let k = key.hasPrefix("[") ? "item \(key)" : key
        return keyHelp[key] ?? (key.contains("->") ? "Projection \(key) (source -> target region)." : "Entry \"\(k)\". Edit its value; the toolbox reads it by this name.")
    }

    var body: some View {
        switch value {
        case .object(let d):
            group(title: key, count: d.count) {
                ForEach(d.keys.sorted(), id: \.self) { k in
                    JSONNodeView(key: k, value: Binding(get: { value[k] ?? .null }, set: { value[k] = $0 }), depth: depth + 1)
                }
            }
        case .array(let a):
            if a.count <= 4, a.allSatisfy({ $0.number != nil }) {
                VStack(alignment: .leading, spacing: 2) {
                    if let key { HStack(spacing: 4) { Text(key).foregroundStyle(.secondary); HelpButton(text: help) } }
                    HStack(spacing: 6) {
                        ForEach(a.indices, id: \.self) { j in
                            NumBox("[\(j)]", Binding(get: { value.arrayValue.indices.contains(j) ? (value.arrayValue[j].number ?? 0) : 0 },
                                                     set: { v in var arr = value.arrayValue; arr[j] = .number(v); value = .array(arr) }))
                        }
                    }
                }.font(.caption)
            } else {
                group(title: key, count: a.count) {
                    ForEach(a.indices, id: \.self) { j in
                        JSONNodeView(key: "[\(j)]", value: Binding(get: { value.arrayValue.indices.contains(j) ? value.arrayValue[j] : .null },
                                                                   set: { v in var arr = value.arrayValue; arr[j] = v; value = .array(arr) }), depth: depth + 1)
                    }
                }
            }
        case .number(let x):
            Row(key ?? "value", help: help) {
                TextField(key ?? "value", value: Binding(get: { x }, set: { value = .number($0) }), format: .number.precision(.fractionLength(0...6)))
                    .labelsHidden().multilineTextAlignment(.trailing)
            }.font(.caption)
        case .string(let s):
            Row(key ?? "text", help: help) { TextField(key ?? "text", text: Binding(get: { s }, set: { value = .string($0) })).labelsHidden() }.font(.caption)
        case .bool(let b):
            Toggle(key ?? "", isOn: Binding(get: { b }, set: { value = .bool($0) })).font(.caption).helpButton(help)
        case .null:
            HStack { Text(key ?? "").foregroundStyle(.secondary); Text("null").foregroundStyle(.tertiary) }.font(.caption)
        }
    }

    @ViewBuilder func group<C: View>(title: String?, count: Int, @ViewBuilder _ c: () -> C) -> some View {
        let content = c()
        if let title {
            DisclosureGroup { VStack(alignment: .leading, spacing: 3) { content }.padding(.leading, 4) } label: {
                HStack(spacing: 4) {
                    Text("\(title)").font(.caption.weight(.medium)) + Text("  \(count)").font(.caption2).foregroundColor(.secondary)
                    HelpButton(text: help)
                }
            }
        } else {
            VStack(alignment: .leading, spacing: 3) { content }
        }
    }
}

// MARK: Project

struct ProjectPanel: View {
    @EnvironmentObject var app: AppState
    var body: some View {
        Placeholder(task: "A1", title: "Project schema and I/O", text: "")
        Card(title: "File", subtitle: app.projectURL?.path ?? "Unsaved project. A Project holds geometry, fields, schedule, genome, plan, plugins, neuron model and metadata (docs/PROJECT_FORMAT.md).") {
            Flow {
                Button("New") { app.newProject() }
                Button("Open…") { app.openProject() }
                Button("Save") { app.saveProject() }
                Button("Save As…") { app.saveProject(as: true) }
                Button("Validate") { app.validateProject() }.helpButton("Checks the project against the toolbox's schema (neurogenesis.project.schema) and reports the first problem.")
            }
        }
        Card(title: "Settings") {
            Row("Neuron model", help: "The model the project is simulated with: lif_int (integer, fast, exact everywhere), two_compartment (soma + dendrite) or hh (Hodgkin–Huxley). See docs/NEURON_MODELS.md.") {
                Picker("Neuron model", selection: Binding(get: { app.project["neuron_model"]?.stringValue ?? "lif_int" },
                                                          set: { app.project["neuron_model"] = .string($0); app.simModel = $0 })) {
                    ForEach(app.models.compactMap { $0["name"] as? String }.isEmpty ? ["lif_int"] : app.models.compactMap { $0["name"] as? String }, id: \.self) { Text($0) }
                }.labelsHidden()
            }
            Row("Plugins", help: "Python modules, separated by commas, imported when the project loads: they register extra rules, stages or neuron models.") {
                TextField("module.name, other.module", text: Binding(
                    get: { (app.project["plugins"]?.arrayValue.compactMap { $0.stringValue } ?? []).joined(separator: ", ") },
                    set: { app.project["plugins"] = .array($0.split(separator: ",").map { .string($0.trimmingCharacters(in: .whitespaces)) }.filter { $0 != .string("") }) }))
                    .labelsHidden()
            }
        }
        ForEach(["metadata", "fields", "schedule", "geometry", "genome", "plan"], id: \.self) { key in
            DisclosureGroup {
                JSONEditor(value: Binding(get: { app.projectValue(key) }, set: { v in
                    app.project[key] = v
                    if key == "plan" { app.plan = PlanSpec(v) }
                    if key == "genome" { app.genome = v }
                    if key == "geometry" { app.adoptProject(app.project) }
                }))
            } label: {
                HStack(spacing: 4) { Text(key); HelpButton(text: projectKeyHelp[key] ?? "") }
            }
        }
    }
    let projectKeyHelp = [
        "metadata": "Free information about the project (author, description, notes).",
        "fields": "Hand-made or generated data on the geometry (gradients, layers, point sets, orientation maps). Edited in Fields.",
        "schedule": "The ordered developmental stages. Edited in Schedule.",
        "geometry": "Named shapes. Edited in Geometry.",
        "genome": "The genes. Edited in Genome and Body plan.",
        "plan": "The body plan (regions and projections). Edited in Body plan.",
    ]
}

// MARK: Geometry

struct GeometryPanel: View {
    @EnvironmentObject var app: AppState
    @State private var cells = 300.0
    @State private var inh = 0.2
    @State private var role = 0
    @State private var replace = true
    @State private var seed = 0.0

    var body: some View {
        Placeholder(task: "B1", title: "Geometry primitives", text: "")
        Card(title: "Add a shape", subtitle: "Shapes from the toolbox registry (neurogenesis.geometry). Sample clouds are drawn in the 3D view.") {
            Flow {
                ForEach(app.geometryTypes) { t in Button(t.type) { app.addGeometry(t) } }
            }.controlSize(.small)
            if app.geometryTypes.isEmpty { Text("Waiting for Python…").font(.caption).foregroundStyle(.secondary) }
        }
        ForEach($app.geometries) { $g in GeometryEditor(item: $g) }
        if !app.geometries.isEmpty {
            Card(title: "Seed cells in a shape", subtitle: "Unconnected LIF neurons sampled uniformly in the shape (stage C1 seed_cells will add densities from fields). Then wire them in the Network panel.") {
                Row("Cells", help: "How many neurons to sample uniformly inside the shape.") { TextField("Cells", value: $cells, format: .number).labelsHidden() }
                Row("Inhibitory fraction", help: "Fraction of the sampled neurons made inhibitory (negative base weight), drawn at random.") {
                    HStack { Slider(value: $inh, in: 0...1).labelsHidden(); Text(String(format: "%.2f", inh)).monospacedDigit() }
                }
                Row("Role", help: "Role of the new neurons: inputs receive the external drive, outputs are read out.") {
                    Picker("Role", selection: $role) { Text("internal").tag(0); Text("input").tag(1); Text("output").tag(2) }.labelsHidden()
                }
                Toggle("Replace the network", isOn: $replace).helpButton("On: the sampled cells become the whole network. Off: they are appended as a new region.")
                Row("Seed", help: "Random seed of the sampling: the same seed gives the same positions.") { TextField("Seed", value: $seed, format: .number).labelsHidden() }
                Flow {
                    ForEach(app.geometries.indices, id: \.self) { k in
                        Button("Sample in \(app.geometries[k].name)") { app.sampleCells(in: k, n: Int(cells), inhFraction: inh, role: role, replace: replace, seed: Int(seed)) }
                    }
                }
            }
        }
        Placeholder(task: "B2", title: "Meshes and voxel masks", text: "Import OBJ / STL meshes and .npz voxel masks as shapes.")
    }
}

struct GeometryEditor: View {
    @EnvironmentObject var app: AppState
    @Binding var item: GeometryItem
    var body: some View {
        let type = item.spec["type"]?.stringValue ?? "?"
        let params = app.geometryTypes.first { $0.type.lowercased() == type.lowercased() }?.params ?? []
        Card(title: "\(item.name) · \(type)") {
            Row("Name", help: "Name of the shape in the project (stages and fields refer to it by name).") { TextField("Name", text: $item.name).labelsHidden() }
            HStack {
                Toggle("Visible", isOn: $item.visible).helpButton("Show the shape's sample cloud and bounding box in the 3D view.")
                Spacer()
                Button(role: .destructive) { app.geometries.removeAll { $0.id == item.id } } label: { Label("Remove", systemImage: "trash") }.buttonStyle(.borderless)
            }
            ForEach(params) { p in
                switch p.kind {
                case "vec3":
                    Vec3Field(label: p.name, help: keyHelp[p.name] ?? "\(p.name): a 3D vector (x, y, z) in space units.",
                              value: Binding(get: {
                        let a = item.spec[p.name]?.arrayValue.compactMap { $0.number } ?? [0, 0, 0]
                        return a.count == 3 ? SIMD3(a[0], a[1], a[2]) : .zero
                    }, set: { v in item.spec[p.name] = .array([.number(v.x), .number(v.y), .number(v.z)]); app.previewGeometry(index) }))
                case "float":
                    DoubleField(p.name, Binding(get: { item.spec[p.name]?.number ?? 0 }, set: { item.spec[p.name] = .number($0); app.previewGeometry(index) }),
                                help: keyHelp[p.name] ?? "\(p.name), in space units.")
                case "string":
                    Row(p.name, help: p.name.hasSuffix("_expr") ? "Formula of the surface coordinate in u and v (each in [0, 1]), e.g. 40*u or 10*sin(3*u). Press Return to update." : "\(p.name) (text).") {
                        TextField(p.name, text: Binding(get: { item.spec[p.name]?.stringValue ?? "" }, set: { item.spec[p.name] = .string($0) }))
                            .labelsHidden().onSubmit { app.previewGeometry(index) }
                    }
                default:
                    DisclosureGroup {
                        JSONEditor(value: Binding(get: { item.spec[p.name] ?? .null }, set: { item.spec[p.name] = $0; app.previewGeometry(index) }))
                    } label: { HStack(spacing: 4) { Text(p.name); HelpButton(text: "\(p.name): a nested shape (union and difference combine two shapes a and b).") } }
                }
            }
            if let e = item.error { Text(e).font(.caption).foregroundStyle(.red).fixedSize(horizontal: false, vertical: true) }
            else if !item.preview.isEmpty {
                Text(String(format: "bounds (%.1f, %.1f, %.1f) – (%.1f, %.1f, %.1f)", item.lo.x, item.lo.y, item.lo.z, item.hi.x, item.hi.y, item.hi.z))
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }
    var index: Int { app.geometries.firstIndex { $0.id == item.id } ?? 0 }
}

// MARK: Fields

struct FieldsPanel: View {
    @EnvironmentObject var app: AppState
    var body: some View {
        Placeholder(task: "B3", title: "Scalar, vector and label fields", text: "Grid and analytic fields, layer stacks by depth, sampled at any position and usable as Param sources.")
        Placeholder(task: "B4", title: "Point patterns and orientation maps", text: "Poisson-disc point sets, pinwheel maps from hand-placed singularities (±1/2).")
        Placeholder(task: "B5", title: "Field operations", text: "Arithmetic, thresholds, smoothing, distance transforms, gradients.")
        Card(title: "Project fields", subtitle: "Fields are stored in the Project. Until B3–B5 define their formats, templates below write provisional entries you can edit; the toolbox will validate them once merged.") {
            Flow {
                Button("Gradient") { add("gradient", ["kind": .string("analytic"), "expr": .string("x / 100"), "type": .string("scalar")]) }
                Button("Layers") { add("layers", ["kind": .string("layer_stack"), "axis": .string("y"), "boundaries": .array([0.1, 0.3, 0.5, 0.8].map { .number($0) }),
                                                  "labels": .array(["L1", "L2/3", "L4", "L5", "L6"].map { .string($0) })]) }
                Button("Point set") { add("points", ["kind": .string("points"), "points": .array([]), "pattern": .string("poisson_disc"), "min_distance": .number(10)]) }
                Button("Pinwheels") { add("orientation", ["kind": .string("pinwheel_map"), "singularities": .array([.array([.number(0), .number(0), .number(0.5)])])]) }
            }.controlSize(.small)
            JSONEditor(value: Binding(get: { app.project["fields"] ?? .object([:]) }, set: { app.project["fields"] = $0 }))
        }
    }
    func add(_ base: String, _ v: [String: JSONValue]) {
        var f = app.project["fields"]?.objectValue ?? [:]
        var name = base, k = 1
        while f[name] != nil { k += 1; name = "\(base)\(k)" }
        f[name] = .object(v)
        app.project["fields"] = .object(f)
    }
}

// MARK: Body plan

struct PlanPanel: View {
    @EnvironmentObject var app: AppState
    var body: some View {
        Card(title: "Plan", subtitle: "Regions (where neurons are born) and the projections that may grow between them; genes in the Genome panel. Boxes are drawn in 3D.") {
            Row("Name", help: "Name of the body plan (shown as the network's morphology).") { TextField("Name", text: $app.plan.name).labelsHidden() }
            DoubleField("Conduction velocity", $app.plan.conductionVelocity, help: "Axonal conduction velocity, in space units per tick: delay = distance / velocity (clipped to Max delay).")
            Row("Max delay (ticks)", help: "Longest axonal delay, in ticks of 1 ms (at most 31: the kernel's spike register).") {
                TextField("Max delay", value: $app.plan.maxDelay, format: .number).labelsHidden()
            }
            DoubleField("Development seed", $app.devSeed, help: "Seed of development: the same plan, genome and seed always grow the same network.")
            Flow {
                Button("Grow") { app.grow() }.keyboardShortcut("g", modifiers: [.command])
                Button("Develop step by step") { app.growSteps() }.helpButton("Grows the plan and keeps a checkpoint after placement and after each projection, to step through in Development.")
                Menu("More") {
                    Button("Open plan…") { app.openProject() }
                    Button("Save plan…") { app.savePlan() }
                    Button("Reset to example") { app.plan = PlanSpec.example(); app.genome = .object([:]) }
                    Button("Empty plan") { app.plan = PlanSpec(); app.genome = .object([:]) }
                    Toggle("Show region boxes", isOn: $app.showRegionBoxes)
                }.fixedSize()
            }
        }
        Card(title: "Resources", subtitle: "Cells, expected synapses and peak memory of growing this plan, checked against what is free now. Growing refuses plans that do not fit.") {
            Flow {
                Button("Check") { app.checkGrowResources() }
                if let n = app.growEstimate["neurons"] as? Int, let e = app.growEstimate["synapses"] as? Int, let b = app.growEstimate["bytes"] as? Int {
                    Text("\(n) cells · ~\(e) synapses · \(humanBytes(UInt64(b)))")
                        .font(.caption).foregroundStyle((app.growEstimate["fits"] as? Bool ?? true) ? Color.secondary : Color.red)
                }
            }
        }
        Card(title: "Regions") {
            ForEach($app.plan.regions) { $r in RegionEditor(region: $r) }
            Button("Add region") {
                let k = app.plan.regions.count
                app.plan.regions.append(RegionSpec(name: "region\(k + 1)", origin: SIMD3(Double(k) * 50, 0, 0)))
            }
        }
        Card(title: "Projections", subtitle: "Grown in this order. Each arrow is a projection from a source region to a target region.") {
            ForEach($app.plan.projections) { $p in ProjectionEditor(projection: $p) }
            Button("Add projection") {
                let names = app.plan.regions.map(\.name)
                if let a = names.first { app.plan.projections.append(ProjectionSpec(src: a, dst: names.last ?? a)) }
            }
        }
        if !app.rules.isEmpty {
            Card(title: "Development rules", subtitle: "Registered rules per phase (neurogenesis.development.rules); each stays inactive without its genes.") {
                ForEach(app.rules.keys.sorted(), id: \.self) { phase in
                    let active = Set((app.plan.rules[phase]?.arrayValue.compactMap { $0.stringValue }) ?? defaultRules[phase] ?? [])
                    VStack(alignment: .leading) {
                        HStack(spacing: 4) { Text(phase).font(.caption.weight(.semibold)); HelpButton(text: phaseHelp[phase] ?? "Rules of the \(phase) phase.") }
                        Flow { ForEach(app.rules[phase] ?? [], id: \.self) { r in
                            Toggle(r, isOn: Binding(get: { active.contains(r) }, set: { on in
                                var all = defaultRules
                                for (k, v) in app.plan.rules.objectValue { all[k] = v.arrayValue.compactMap { $0.stringValue } }
                                var s = all[phase] ?? []
                                if on { if !s.contains(r) { s.append(r) } } else { s.removeAll { $0 == r } }
                                all[phase] = s
                                app.plan.rules = .object(all.mapValues { .array($0.map { .string($0) }) })
                            })).toggleStyle(.checkbox).font(.caption)
                        } }
                    }
                }
            }
        }
    }
    let defaultRules: [String: [String]] = ["placement": ["mosaic"], "shift": ["identity_offset"], "target": ["topographic", "lamina"],
                                             "probability": ["identity_expression", "no_autapse", "source_sign"], "weight": ["receptor_sign"]]
    let phaseHelp = ["placement": "Rules that move cells after placement (e.g. mosaic spacing).",
                     "shift": "Rules that shift where axons aim (e.g. by molecular identity).",
                     "target": "Rules that set target points (topography, laminae).",
                     "probability": "Rules that change connection probabilities (no autapses, source sign, identity).",
                     "weight": "Rules that change synaptic weights (receptor sign)."]
}

struct RegionEditor: View {
    @EnvironmentObject var app: AppState
    @Binding var region: RegionSpec
    @State private var nx = 4.0
    @State private var ny = 4.0
    @State private var nz = 1.0

    var body: some View {
        let k = app.plan.regions.firstIndex { $0.id == region.id } ?? 0
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 6) {
                Row("Name", help: "Region name (unique). Projections and genes refer to it.") { TextField("Name", text: $region.name).labelsHidden() }
                Vec3Field(label: "Origin", help: "Corner of the region's box in space units. Local positions (u, v, w) in [0, 1] map to origin + size × local.", value: $region.origin)
                Vec3Field(label: "Size", help: "Edge lengths of the region's box (space units).", value: $region.size)
                Row("Placement", help: "Grown: genes set the number of cells and where they migrate. Fixed: cells at the listed local positions (labels), e.g. a sensor grid.") {
                    Picker("Placement", selection: $region.fixed) { Text("grown").tag(false); Text("fixed").tag(true) }.pickerStyle(.segmented).labelsHidden()
                }
                if region.fixed {
                    HStack(spacing: 6) {
                        Text("\(region.labels.count) labels").font(.caption)
                        HelpButton(text: "Fixed positions of the region's cells, in local units. Grid fills them regularly: nx × ny × nz cells.")
                    }
                    Flow {
                        NumBox("nx", $nx); NumBox("ny", $ny); NumBox("nz", $nz)
                        Button("Make grid") { region.labels = RegionSpec.grid(max(1, Int(nx)), max(1, Int(ny)), max(1, Int(nz))) }
                    }.font(.caption)
                } else {
                    DoubleField("Count (gene)", gene(["count", region.name], 60), help: "Number of neurons grown in this region (genome count[region]); clipped to the count bounds.")
                    DoubleField("Spread (gene)", gene(["migration", region.name, "spread"], 0.3), help: "Scatter of the cells around the region's centre, in local units (genome migration[region].spread).")
                    DoubleField("Inhibitory bias a0 (gene)", gene(["inhibitory", region.name, "a0"], -1.4), help: "Probability of being inhibitory = sigmoid(a0): −1.4 ≈ 20 %, 0 = 50 %, +2 ≈ 88 %.")
                    HStack(spacing: 6) {
                        Text("Count bounds").font(.caption); HelpButton(text: "Smallest and largest allowed cell count, whatever the gene says.")
                        Spacer()
                        Text("min").foregroundStyle(.secondary).font(.caption)
                        TextField("min", value: $region.countLo, format: .number).labelsHidden().frame(minWidth: 40)
                        Text("max").foregroundStyle(.secondary).font(.caption)
                        TextField("max", value: $region.countHi, format: .number).labelsHidden().frame(minWidth: 50)
                    }
                }
                Row("Role", help: "Input regions receive the external drive; outputs are read out (modules expose them).") {
                    Picker("Role", selection: $region.role) { Text("internal").tag(0); Text("input").tag(1); Text("output").tag(2) }.labelsHidden()
                }
                Row("Sign", help: "Genetic: each cell is excitatory or inhibitory by its inhibitory gene. Excitatory / inhibitory: imposed on every cell (Dale's principle).") {
                    Picker("Sign", selection: $region.sign) { Text("genetic").tag("genetic"); Text("excitatory").tag("exc"); Text("inhibitory").tag("inh") }.labelsHidden()
                }
                Row("Refractory (ticks)", help: "Absolute refractory period of the region's neurons, in ticks of 1 ms.") {
                    Stepper("\(region.refractory)", value: $region.refractory, in: 0...50)
                }
                Button("Remove region", role: .destructive) {
                    let name = region.name
                    app.plan.projections.removeAll { $0.src == name || $0.dst == name }
                    app.plan.regions.removeAll { $0.id == region.id }
                }.controlSize(.small)
            }.padding(.vertical, 4)
        } label: {
            HStack { Circle().fill(paletteColor(k).swiftUI).frame(width: 8, height: 8); Text(region.name)
                Text(region.fixed ? "fixed" : "grown").font(.caption).foregroundStyle(.secondary) }
        }
    }

    /// A number at a genome path (created when edited).
    func gene(_ path: [String], _ def: Double) -> Binding<Double> {
        Binding(get: {
            var v: JSONValue? = app.genome
            for k in path { v = v?[k] }
            return v?.number ?? def
        }, set: { x in app.genome = setPath(app.genome, path[...], .number(x)) })
    }
}

func setPath(_ root: JSONValue, _ path: ArraySlice<String>, _ v: JSONValue) -> JSONValue {
    guard let k = path.first else { return v }
    var d = root.objectValue
    d[k] = setPath(d[k] ?? .object([:]), path.dropFirst(), v)
    return .object(d)
}

struct ProjectionEditor: View {
    @EnvironmentObject var app: AppState
    @Binding var projection: ProjectionSpec
    var body: some View {
        let names = app.plan.regions.map(\.name)
        let key = "\(projection.src)->\(projection.dst)"
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("from").font(.caption).foregroundStyle(.secondary)
                Picker("from", selection: $projection.src) { ForEach(names, id: \.self) { Text($0) } }.labelsHidden()
                Text("to").font(.caption).foregroundStyle(.secondary)
                Picker("to", selection: $projection.dst) { ForEach(names, id: \.self) { Text($0) } }.labelsHidden()
                HelpButton(text: "Axons grow from every cell of the source region to cells of the target region.")
                Button { app.plan.projections.removeAll { $0.id == projection.id } } label: { Image(systemName: "minus.circle") }.buttonStyle(.borderless).help("Remove this projection")
            }
            Flow {
                ForEach([("sigma", 0.3), ("p0", 0.5), ("w", 100.0)], id: \.0) { g, def in
                    HStack(spacing: 2) {
                        NumBox(g, Binding(get: { app.genome["guidance"]?[key]?[g]?.number ?? def },
                                          set: { app.genome = setPath(app.genome, ["guidance", key, g][...], .number($0)) }))
                        HelpButton(text: keyHelp[g] ?? g)
                    }
                }
            }.font(.caption)
        }
        .padding(.vertical, 2)
    }
}

// MARK: Genome

struct GenomePanel: View {
    @EnvironmentObject var app: AppState
    var body: some View {
        Card(title: "Genome", subtitle: "Nested genes (neurogenesis.genome). Projection keys are \"src->dst\". Missing genes of the plan are filled with neutral defaults.") {
            Flow {
                Button("Fill defaults for the plan") { app.action("Completing genome") { try await app.completeGenome() } }
                Button("Grow") { app.grow() }
                Button("Clear") { app.genome = .object([:]) }
                Button("Load genome JSON…") {
                    let p = NSOpenPanel(); p.allowedContentTypes = [.json]
                    if p.runModal() == .OK, let u = p.url, let d = try? Data(contentsOf: u), let v = try? JSONValue.parse(String(decoding: d, as: UTF8.self)) {
                        app.genome = v["genome"] ?? v
                    }
                }
                Button("Save genome JSON…") {
                    let p = NSSavePanel(); p.allowedContentTypes = [.json]; p.nameFieldStringValue = "genome.json"
                    if p.runModal() == .OK, let u = p.url { try? app.genome.pretty().write(to: u, atomically: true, encoding: .utf8) }
                }
            }
            JSONEditor(value: $app.genome)
        }
        Placeholder(task: "A3", title: "Param sources", text: "Every stage parameter as const, gene(path, lo, hi), field, fit or expr; genes of a schedule collected automatically for evolution.")
    }
}

// MARK: Schedule

struct SchedulePanel: View {
    @EnvironmentObject var app: AppState
    var schedule: [JSONValue] { app.project["schedule"]?.arrayValue ?? [] }

    var body: some View {
        Placeholder(task: "A4", title: "Stages and scheduler", text: "run_schedule(project, genome, seed) with one random stream per stage and a checkpoint after each stage.")
        Card(title: "Stage catalogue", subtitle: app.stagesAvailable ? "Green: registered. Orange: planned (C1–C13), can be scheduled now and runs once merged." : "Stages planned in the roadmap (C1–C13). You can already compose a schedule; it runs once A4 and the stages are merged.") {
            Flow {
                ForEach(app.stages) { s in
                    Button { add(s) } label: {
                        HStack(spacing: 4) {
                            Circle().fill(s.available ? Color.green : Color.orange.opacity(0.6)).frame(width: 6, height: 6)
                            Text(s.name).font(.caption)
                            Text(s.task).font(.caption2).foregroundStyle(.secondary)
                        }
                    }.buttonStyle(.bordered).controlSize(.small).help(s.doc.isEmpty ? "Add \(s.name) (\(s.task)) to the schedule" : s.doc)
                }
            }
        }
        Card(title: "Schedule (\(schedule.count) stages)", subtitle: "Ordered stages (A4: name, operator, params, repeat); each parameter is an A3 Param: Const, Gene (toolbox gene path, lo, hi), Field, Fit or Expr.") {
            if schedule.isEmpty { Text("Empty: add stages from the catalogue.").font(.caption).foregroundStyle(.secondary) }
            ForEach(schedule.indices, id: \.self) { k in
                StageEditor(index: k, stage: Binding(get: { schedule.indices.contains(k) ? schedule[k] : .null }, set: { v in
                    var s = schedule; s[k] = v; app.project["schedule"] = .array(s)
                }), move: { d in
                    var s = schedule; let j = k + d
                    guard s.indices.contains(j) else { return }
                    s.swapAt(k, j); app.project["schedule"] = .array(s)
                }, remove: { var s = schedule; s.remove(at: k); app.project["schedule"] = .array(s) })
            }
            Flow {
                Button("Run schedule") { app.runSchedule() }.disabled(!app.stagesAvailable || schedule.isEmpty)
                Button("Genes and cost") { app.scheduleInfo() }.disabled(schedule.isEmpty)
                    .helpButton("Lists the genes the schedule uses (A3 collect_genes) and its declared memory and operations (A4 schedule_cost).")
                Button("Body plan step by step") { app.growSteps() }
            }
            if !app.scheduleReport.isEmpty { Text(app.scheduleReport).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true) }
        }
    }

    func add(_ s: StageInfo) {
        var params: [String: JSONValue] = [:]
        for (n, d) in s.params { params[n] = .object(["type": .string("Const"), "value": d]) }
        var sch = schedule
        sch.append(.object(["name": .string("\(sch.count + 1)_\(s.name)"), "operator": .string(s.name), "params": .object(params), "repeat": .number(1)]))
        app.project["schedule"] = .array(sch)
    }
}

struct StageEditor: View {
    let index: Int
    @Binding var stage: JSONValue
    let move: (Int) -> Void
    let remove: () -> Void
    @State private var newParam = ""

    var body: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 6) {
                Row("Name", help: "Name of this step of the schedule (unique; checkpoints are labelled with it).") {
                    TextField("Name", text: Binding(get: { stage["name"]?.stringValue ?? "" }, set: { stage["name"] = .string($0) })).labelsHidden()
                }
                Row("Repeat", help: "How many times the stage runs in a row (each repetition draws from its own random stream).") {
                    Stepper("\(Int(stage["repeat"]?.number ?? 1))", value: Binding(get: { Int(stage["repeat"]?.number ?? 1) },
                                                                                  set: { stage["repeat"] = .number(Double(max(1, $0))) }), in: 1...1000)
                }
                ForEach((stage["params"]?.objectValue ?? [:]).keys.sorted(), id: \.self) { p in
                    ParamEditor(name: p, param: Binding(get: { stage["params"]?[p] ?? .null }, set: { v in
                        var ps = stage["params"]?.objectValue ?? [:]; ps[p] = v; stage["params"] = .object(ps)
                    }), remove: { var ps = stage["params"]?.objectValue ?? [:]; ps.removeValue(forKey: p); stage["params"] = .object(ps) })
                }
                Row("New parameter", help: "Name of a parameter the stage reads; it starts as a Const you can switch to Gene, Field, Fit or Expr.") {
                    HStack {
                        TextField("parameter name", text: $newParam).labelsHidden()
                        Button("Add") {
                            guard !newParam.isEmpty else { return }
                            var ps = stage["params"]?.objectValue ?? [:]
                            ps[newParam] = .object(["type": .string("Const"), "value": .number(0)])
                            stage["params"] = .object(ps); newParam = ""
                        }
                    }
                }.controlSize(.small)
            }
        } label: {
            HStack {
                Text("\(index + 1).").monospacedDigit().foregroundStyle(.secondary)
                Text(stage["operator"]?.stringValue ?? stage["stage"]?.stringValue ?? "?").font(.callout.weight(.medium))
                Spacer()
                Button { move(-1) } label: { Image(systemName: "chevron.up") }.buttonStyle(.borderless).help("Move up")
                Button { move(1) } label: { Image(systemName: "chevron.down") }.buttonStyle(.borderless).help("Move down")
                Button(action: remove) { Image(systemName: "trash") }.buttonStyle(.borderless).help("Remove this stage")
            }
        }
    }
}

/// One stage parameter as an A3 Param: Const(value), Gene(path, lo, hi, integer), Field(name, transform),
/// Fit(target, init, lo, hi) or Expr(formula).
struct ParamEditor: View {
    let name: String
    @Binding var param: JSONValue
    let remove: () -> Void
    var body: some View {
        let src = param["type"]?.stringValue ?? "Const"
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(name).font(.caption.weight(.semibold))
                HelpButton(text: "Where \(name) comes from. Const: a value by hand. Gene: read from the genome at a path (evolved within lo–hi). Field: sampled from a project field at each cell. Fit: fitted to data from init within lo–hi. Expr: a formula.")
                Spacer()
                Button(action: remove) { Image(systemName: "xmark") }.buttonStyle(.borderless).help("Remove this parameter")
            }
            Picker("Source", selection: Binding(get: { src }, set: { param["type"] = .string($0) })) {
                ForEach(["Const", "Gene", "Field", "Fit", "Expr"], id: \.self) { Text($0) }
            }.pickerStyle(.segmented).labelsHidden()
            Flow {
                switch src {
                case "Gene":
                    path(); num("lo"); num("hi")
                    Toggle("integer", isOn: Binding(get: { param["integer"] == .bool(true) }, set: { param["integer"] = .bool($0) })).toggleStyle(.checkbox)
                case "Field":
                    text("field", "name", "field name"); text("transform", "transform", "e.g. 2*x")
                case "Fit":
                    text("target", "target", "e.g. density"); num("init"); num("lo"); num("hi")
                case "Expr":
                    text("formula", "formula", "e.g. 0.5 * depth")
                default:
                    if case .string = param["value"] ?? .null { text("value", "value", "") } else { num("value") }
                }
            }.font(.caption)
        }
        .padding(6)
        .background(RoundedRectangle(cornerRadius: 5).fill(Color.primary.opacity(0.04)))
    }
    func num(_ k: String) -> some View {
        NumBox(k, Binding(get: { param[k]?.number ?? 0 }, set: { param[k] = .number($0) }))
    }
    /// A toolbox gene path, typed as keys separated by "/" (e.g. count/map, guidance/a->b/sigma, migration/map/mean/0).
    func path() -> some View {
        HStack(spacing: 3) {
            Text("path").foregroundStyle(.secondary)
            TextField("e.g. count/map", text: Binding(get: {
                if let a = param["path"]?.arrayValue { return a.map { $0.stringValue ?? ($0.number.map { String(Int($0)) } ?? "") }.joined(separator: "/") }
                return (param["path"]?.stringValue ?? "").replacingOccurrences(of: ".", with: "/")
            }, set: { v in
                param["path"] = .array(v.split(separator: "/").map { Int($0).map { .number(Double($0)) } ?? .string(String($0)) })
            })).labelsHidden().frame(minWidth: 110)
        }
    }
    func text(_ label: String, _ k: String, _ prompt: String) -> some View {
        HStack(spacing: 3) {
            Text(label).foregroundStyle(.secondary)
            TextField(prompt, text: Binding(get: { param[k]?.stringValue ?? "" }, set: { param[k] = .string($0) })).labelsHidden().frame(minWidth: 90)
        }
    }
}

// MARK: Development

struct DevelopmentPanel: View {
    @EnvironmentObject var app: AppState
    @State private var playing = false
    @State private var timer: Timer?

    var body: some View {
        Card(title: "Develop", subtitle: "Checkpoints after each developmental step, for stepping through development in 3D.") {
            DoubleField("Development seed", $app.devSeed, help: "Seed of development: the same plan, genome and seed always grow the same network.")
            Flow {
                Button("Body plan, step by step") { app.growSteps() }
                Button("Run schedule") { app.runSchedule() }.disabled(!app.stagesAvailable)
            }
        }
        Placeholder(task: "A4", title: "Stage checkpoints", text: "The tissue after every scheduled stage (proliferation, migration, differentiation, axon growth, pruning…).")
        if !app.checkpoints.isEmpty {
            Card(title: "Checkpoints", subtitle: "Source: \(app.checkpointSource)") {
                HStack {
                    Button { toggle() } label: { Image(systemName: playing ? "pause.fill" : "play.fill") }.help("Play through the checkpoints")
                    Slider(value: Binding(get: { Double(app.checkpointIndex) }, set: { app.showCheckpoint(Int($0.rounded())) }),
                           in: 0...Double(max(app.checkpoints.count - 1, 1)), step: 1) { Text("Step") }
                    Text("\(app.checkpointIndex + 1)/\(app.checkpoints.count)").monospacedDigit()
                    HelpButton(text: "Drag to step through development; each checkpoint is the network grown so far.")
                }
                ForEach(Array(app.checkpoints.enumerated()), id: \.offset) { k, c in
                    Button { app.showCheckpoint(k) } label: {
                        HStack {
                            Image(systemName: k == app.checkpointIndex ? "largecircle.fill.circle" : "circle").foregroundStyle(.tint)
                            VStack(alignment: .leading) {
                                Text(c.label).font(.callout)
                                Text("\(c.neurons) cells · \(c.synapses) synapses").font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }.buttonStyle(.plain)
                }
            }
        }
    }

    func toggle() {
        playing.toggle()
        timer?.invalidate()
        guard playing else { return }
        timer = Timer.scheduledTimer(withTimeInterval: 0.8, repeats: true) { _ in
            MainActor.assumeIsolated {
                let next = app.checkpointIndex + 1
                if next >= app.checkpoints.count { playing = false; timer?.invalidate() } else { app.showCheckpoint(next) }
            }
        }
    }
}

// MARK: Network

struct NetworkPanel: View {
    @EnvironmentObject var app: AppState
    @State private var morph = "column"
    @State private var n = 500.0
    @State private var seed = 42.0
    @State private var weightScale = 0.2
    @State private var refractory = 3.0
    @State private var wireSeed = 0.0
    @State private var velocity = 4.0

    var body: some View {
        Card(title: "Build", subtitle: "Generate a preset, grow a body plan, sample cells in a shape, or start empty and draw neurons by hand.") {
            Row("Preset", help: "Ready-made networks of the toolbox (MorphogeneticEngine): a cortical column (six layers), stacked sheets, or a small microcircuit.") {
                Picker("Preset", selection: $morph) { Text("Cortical column").tag("column"); Text("Layered sheets").tag("layered"); Text("Microcircuit").tag("microcircuit") }.labelsHidden()
            }
            DoubleField("Neurons", $n, help: "Number of neurons of the preset. Large values are checked against free memory before generating.")
            DoubleField("Seed", $seed, help: "Random seed: the same seed gives the same network.")
            if morph == "column" {
                Row("Weight scale", help: "Multiplies every weight of the column; 0.2 gives an unsaturated regime, 1 the original (strongly bursting) one.") {
                    HStack { Slider(value: $weightScale, in: 0.05...1.5).labelsHidden(); Text(String(format: "%.2f", weightScale)).monospacedDigit() }
                }
                Row("Refractory (ticks)", help: "Absolute refractory period of the column's neurons, in ticks of 1 ms.") { Stepper("\(Int(refractory))", value: $refractory, in: 0...20) }
            }
            Flow {
                Button("Generate") { app.generate(morph, neurons: Int(n), seed: Int(seed), extra: ["weight_scale": weightScale, "refractory": Int(refractory)]) }
                Button("Grow body plan") { app.grow() }
                Button("Empty") { app.clearNetwork() }.helpButton("Start from an empty network and add neurons by hand with the Add tool.")
                Button("Open network…") { app.openNetwork() }
                Button("Save network…") { app.saveNetwork() }.helpButton("Saves the network JSON (SNNNetwork format); it opens in the browser viewer (viz/) too.")
            }
        }
        Card(title: "Draw by hand", subtitle: "Tools: ⌘1 select, ⌘2 add, ⌘3 connect, ⌘4 stimulate. New cells are placed on the placement plane, so there is no depth ambiguity.") {
            Row("Tool", help: "Select: click neurons. Add: click on the placement plane to add a neuron there. Connect: click a target to connect the selection to it. Stimulate: click a neuron to inject a current pulse.") {
                Picker("Tool", selection: $app.tool) { ForEach(Tool.allCases) { Text($0.rawValue).tag($0) } }.labelsHidden()
            }
            Text("Placement plane").font(.caption.weight(.semibold))
            Row("Plane perpendicular to", help: "New neurons are placed where you click on this plane. Choose the axis it is perpendicular to (z: a horizontal plane at a given z level when z is your height axis; the 3D view's up axis is y).") {
                Picker("Axis", selection: $app.placeAxis) { Text("x").tag(0); Text("y").tag(1); Text("z").tag(2) }.pickerStyle(.segmented).labelsHidden()
            }
            Row("Level (\(["x", "y", "z"][app.placeAxis]) =)", help: "Coordinate of the placement plane along its axis, in space units. Also: [ and ] in the 3D view move it, and 'Plane here' in the inspector puts it at a selected neuron.") {
                let (lo, hi) = app.sceneBounds()
                let a = Double(lo[app.placeAxis]), b = Double(hi[app.placeAxis])
                let pad = max((b - a) * 0.25, 10)
                HStack {
                    Slider(value: $app.placeLevel, in: min(a - pad, app.placeLevel)...max(b + pad, app.placeLevel)).labelsHidden()
                    TextField("level", value: $app.placeLevel, format: .number.precision(.fractionLength(0...2))).labelsHidden().frame(minWidth: 52)
                }
            }
            Text("New neurons").font(.caption.weight(.semibold))
            Row("Sign", help: "Excitatory (red): its synapses add current. Inhibitory (blue): its synapses subtract current. The preview under the pointer and the new cell take this colour.") {
                Picker("Sign", selection: Binding(get: { app.newNeuron.baseWeight < 0 }, set: { app.newNeuron.baseWeight = $0 ? -abs(app.newNeuron.baseWeight) : abs(app.newNeuron.baseWeight) })) {
                    Text("excitatory").tag(false); Text("inhibitory").tag(true)
                }.pickerStyle(.segmented).labelsHidden()
            }
            Row("Driver", help: "LIF: integrates its inputs. Poisson: fires at random (a driver). Burster: fires bursts on a fixed period.") {
                Picker("Driver", selection: $app.newNeuron.mode) { Text("LIF").tag(Int32(0)); Text("Poisson").tag(Int32(1)); Text("Burster").tag(Int32(2)) }.labelsHidden()
            }
            Row("Role", help: "Input neurons receive the external drive; outputs are read out.") {
                Picker("Role", selection: $app.newNeuron.role) { Text("internal").tag(Int32(0)); Text("input").tag(Int32(1)); Text("output").tag(Int32(2)) }.labelsHidden()
            }
            IntField("Threshold", $app.newNeuron.threshold, help: "Firing threshold of new neurons (integer units, default 1024).")
            IntField("Refractory (ticks)", $app.newNeuron.refractory, help: "Absolute refractory period of new neurons, in ticks of 1 ms.")
            IntField("Compartment (region)", $app.newNeuron.compartment, help: "Region index given to new neurons; −1 = none (they are then coloured by sign).")
            Text("New synapses").font(.caption.weight(.semibold))
            DoubleField("Weight", $app.newWeight, help: "Weight of synapses made with the Connect tool (made negative automatically from inhibitory neurons). Rheobase of a lone neuron ≈ 8.5 units of steady current.")
            Row("Delay (ticks)", help: "Axonal delay of new synapses, 0–31 ticks of 1 ms.") { Stepper("\(Int(app.newDelay))", value: $app.newDelay, in: 0...31) }
        }
        Card(title: "Selection (\(app.selection.count))") {
            Flow {
                Button("All") { app.selectAll() }
                Button("None") { app.selection = [] }
                Menu("Region") { ForEach(Array(app.network.regionNames.enumerated()), id: \.offset) { k, name in Button(name) { app.selectRegion(Int32(k)) } } }
                    .disabled(app.network.regionNames.isEmpty).fixedSize()
                Button("Delete", role: .destructive) { app.deleteSelection() }.disabled(app.selection.isEmpty)
                Button("Connect all-to-all") {
                    let s = app.selection
                    app.modifyNetwork { net in
                        for a in s { for b in s where a != b { net.synapses.append(Synapse(pre: Int32(a), post: Int32(b), weight: net.neurons[a].baseWeight < 0 ? -Int32(abs(app.newWeight)) : Int32(app.newWeight), delay: Int32(app.newDelay))) } }
                    }
                }.disabled(app.selection.count < 2)
                Button("Remove their synapses") { app.removeSynapses(of: Set(app.selection), incoming: true, outgoing: true) }.disabled(app.selection.isEmpty)
            }
        }
        Card(title: "Wire by distance", subtitle: "Every neuron connects to neighbours within its wiring radius with its probability and base weight (MorphogeneticEngine.wire_network); delays from distance / velocity. Replaces the synapses.") {
            DoubleField("Seed", $wireSeed, help: "Random seed of the wiring.")
            DoubleField("Conduction velocity", $velocity, help: "Space units per tick: delay = distance / velocity.")
            Flow {
                Button("Wire") { app.wireByDistance(seed: Int(wireSeed), velocity: velocity) }
                Button("Radius 28, probability 0.3 on selection") { app.updateSelected { $0.connRadius = 28; $0.connProb = 0.3 } }.disabled(app.selection.isEmpty)
            }
        }
        Card(title: "Statistics") {
            Button("Compute") { app.computeStats() }.helpButton("Degree and topology statistics of the network (SNNNetwork.compute_statistics).")
            if let s = app.stats { JSONNodeView(key: nil, value: .constant(s), depth: 0).disabled(true) }
        }
        Card(title: "View") {
            Row("Neuron size", help: "Size of the neuron discs on screen.") { Slider(value: $app.pointSize, in: 1...14).labelsHidden() }
            Toggle("Perspective size", isOn: $app.perspectiveSize).helpButton("On: nearer neurons look bigger. Off: every neuron has the same size on screen.")
            Row("Flash decay (ms)", help: "How long a neuron and its outgoing synapses stay lit after a spike, in simulated ms.") { Slider(value: $app.flashTau, in: 3...120).labelsHidden() }
            Row("Max synapses drawn", help: "Above this number, synapses are subsampled for drawing (the simulation always uses all of them).") {
                HStack { Slider(value: $app.synapseCap, in: 1000...400000).labelsHidden(); Text("\(Int(app.synapseCap / 1000))k").monospacedDigit() }
            }
            Toggle("Grid", isOn: $app.showGrid).helpButton("Ground grid and x (red), y (green), z (blue) axes.")
            Toggle("Region boxes", isOn: $app.showRegionBoxes).helpButton("Boxes of the body plan's regions.")
        }
    }
}

// MARK: Simulation

struct SimulationPanel: View {
    @EnvironmentObject var app: AppState
    @State private var offlineTicks = 500.0
    var body: some View {
        Card(title: "Live (native lif_int)", subtitle: "The integer kernel runs natively, bit-identical to the Python, JAX and browser kernels (tests/test_desktop_kernel.py). Neurons flash and synapse arrows light up when spikes travel.") {
            Flow {
                Button { app.running.toggle() } label: { Label(app.running ? "Pause" : "Run", systemImage: app.running ? "pause.fill" : "play.fill") }
                Button("Step 1 ms") { app.engine.step(1) }
                Button("Step 100 ms") { app.engine.step(100) }
                Button("Reset") { app.resetSimulation() }.helpButton("Back to t = 0: membrane potentials, currents and the random generator are reset; the network is kept.")
            }
            Row("Speed", help: "Simulated milliseconds per real second (1000 = real time). At the right end: as fast as this Mac can.") {
                HStack {
                    Slider(value: Binding(get: { app.speed == 0 ? 5 : log10(max(app.speed, 10)) }, set: { app.speed = $0 >= 4.95 ? 0 : pow(10, $0) }), in: 1...5).labelsHidden()
                    Text(app.speed == 0 ? "max" : "\(Int(app.speed)) ms/s").monospacedDigit()
                }
            }
            DoubleField("Kernel seed", $app.kernelSeed, help: "Seed of the xorshift32 generator of Poisson drivers (12345 = the toolbox default). Applied at Reset.")
            LiveLine(live: app.live)
        }
        Card(title: "Stimulation", subtitle: "Currents in toolbox units, added to the synaptic current every tick (as jax_backend.tick ext_current). Rheobase ≈ 8.5.") {
            Toggle("Drive input neurons (role 1)", isOn: $app.driveInputs).helpButton("Applies the input current below to every input neuron, every tick (⌘I).")
            Row("Input current", help: "Current applied to input neurons each tick while driving is on.") {
                HStack { Slider(value: $app.inputCurrent, in: 0...400).labelsHidden(); Text("\(Int(app.inputCurrent))").monospacedDigit() }
            }
            Row("Current on selection", help: "Constant current applied to the selected neurons every tick (negative inhibits).") {
                HStack { Slider(value: $app.selectionCurrent, in: -200...400).labelsHidden(); Text("\(Int(app.selectionCurrent))").monospacedDigit() }
            }
            Row("Pulse", help: "Current injected once by the Stimulate tool or by ⌥-clicking a neuron.") {
                HStack { Slider(value: $app.pulseCurrent, in: 10...4000).labelsHidden(); Text("\(Int(app.pulseCurrent))").monospacedDigit() }
            }
        }
        Card(title: "Other neuron models", subtitle: "Runs any registered model (JAX, in Python) on the current network and stimulation, after checking its cost.") {
            Row("Model", help: "two_compartment: soma and dendrite. hh: Hodgkin–Huxley. lif_int: the integer kernel (same as live).") {
                Picker("Model", selection: $app.simModel) { ForEach(app.models.compactMap { $0["name"] as? String }, id: \.self) { Text($0) } }.labelsHidden()
            }
            if let d = app.models.first(where: { $0["name"] as? String == app.simModel })?["description"] as? String {
                Text(d).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            DoubleField("Duration (ms)", $offlineTicks, help: "Simulated time, in ticks of 1 ms.")
            Button("Simulate") { app.simulateOffline(model: app.simModel, ticks: Int(offlineTicks)) }
            if let r = app.offlineResult {
                Text(String(format: "%@: %d spikes in %d ms, %.2f Hz mean", r.model, r.t.count, r.ticks, r.rateHz)).font(.caption)
                OfflineRaster(run: r, n: app.network.neurons.count).frame(height: 120)
            }
        }
    }
}

struct OfflineRaster: View {
    let run: AppState.OfflineRun
    let n: Int
    var body: some View {
        Canvas { ctx, size in
            ctx.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black.opacity(0.85)))
            let step = max(1, run.t.count / 40000)
            var p = Path()
            for k in stride(from: 0, to: run.t.count, by: step) {
                let x = CGFloat(run.t[k]) / CGFloat(max(run.ticks, 1)) * size.width
                let y = CGFloat(run.i[k]) / CGFloat(max(n, 1)) * size.height
                p.addRect(CGRect(x: x, y: y, width: 1.2, height: max(1, size.height / CGFloat(max(n, 1)))))
            }
            ctx.fill(p, with: .color(.teal))
        }.clipShape(RoundedRectangle(cornerRadius: 4))
    }
}

// MARK: Plasticity

struct PlasticityPanel: View {
    @EnvironmentObject var app: AppState
    @State private var rule = "STDPRule"
    @State private var values: [String: JSONValue] = [:]
    @State private var ticks = 500.0
    let paramHelp = ["A_plus": "Amplitude of potentiation (pre before post).", "A_minus": "Amplitude of depression (post before pre).",
                     "tau_plus": "Time constant of the potentiation window (ms).", "tau_minus": "Time constant of the depression window (ms).",
                     "w_min": "Lowest allowed weight.", "w_max": "Highest allowed weight.", "soft_bounds": "Changes shrink near the bounds.",
                     "integer_traces": "Integer, bit-shift traces (for lif_int).", "eta": "Learning rate.", "norm_target": "Target total weight per neuron.",
                     "norm_type": "How weights are normalised.", "tau_e": "Time constant of the eligibility trace (ms)."]
    var body: some View {
        Placeholder(task: "E1", title: "Plasticity rules", text: "STDP, Hebbian with normalisation, three-factor rules.")
        Card(title: "Learn from live activity", subtitle: "Records the live simulation, applies the rule to every synapse (neurogenesis.spiking.plasticity) and writes the new weights back into the network (undoable).") {
            if app.plasticityRules.isEmpty { Text("No rules registered yet.").font(.caption).foregroundStyle(.secondary) }
            else {
                Row("Rule", help: "STDPRule: timing-dependent. HebbianRule: correlation with normalisation. ThreeFactorRule: eligibility × modulator.") {
                    Picker("Rule", selection: $rule) { ForEach(app.plasticityRules, id: \.0) { Text($0.0).tag($0.0) } }.labelsHidden()
                }
                ForEach(app.plasticityRules.first { $0.0 == rule }?.1 ?? [], id: \.0) { name, def in
                    Row(name, help: paramHelp[name] ?? "Parameter \(name) of \(rule).") {
                        switch values[name] ?? def {
                        case .bool: Toggle(name, isOn: Binding(get: { values[name]?.any as? Bool ?? (def.any as? Bool ?? false) }, set: { values[name] = .bool($0) })).labelsHidden()
                        case .string: TextField(name, text: Binding(get: { (values[name] ?? def).stringValue ?? "" }, set: { values[name] = .string($0) })).labelsHidden()
                        default: TextField(name, value: Binding(get: { (values[name] ?? def).number ?? 0 }, set: { values[name] = .number($0) }), format: .number).labelsHidden()
                        }
                    }
                }
                DoubleField("Record (ms)", $ticks, help: "Length of live activity recorded before the rule is applied.")
                Button(app.recordingPlasticity ? "Recording…" : "Record and apply") {
                    var p: [String: Any] = [:]
                    for (k, v) in values { p[k] = v.any }
                    app.recordForPlasticity(ticks: Int(ticks), rule: rule, params: p)
                }.disabled(app.recordingPlasticity)
                if !app.plasticityReport.isEmpty { Text(app.plasticityReport).font(.caption) }
            }
        }
        Placeholder(task: "C11", title: "refine_by_activity stage", text: "Spontaneous waves or twitches with plasticity, inside development.")
    }
}

// MARK: Evolution

struct EvolutionPanel: View {
    @EnvironmentObject var app: AppState
    @State private var genes: [[String: Any]] = []
    @State private var chosen: Set<String> = []
    @State private var bounds: [String: (Double, Double)] = [:]
    @State private var target = 10.0
    @State private var gens = 8.0
    @State private var pop = 10.0
    @State private var seeds = 2.0
    @State private var current = 60.0
    @State private var filter = ""

    func key(_ g: [String: Any]) -> String { (g["path"] as? [Any] ?? []).map { "\($0)" }.joined(separator: "/") }

    var body: some View {
        Card(title: "Evolve the genome", subtitle: "Island evolution (neurogenesis.evolution) of the chosen genes, every genome grown on fresh development seeds. Toy objective: a target mean firing rate with inputs driven; projects define their own.") {
            Flow {
                Button("List genes") {
                    app.action("Listing genes") {
                        try await app.completeGenome()
                        genes = (try await app.bridge.dict("genes", ["genome": app.genome.any]))["genes"] as? [[String: Any]] ?? []
                    }
                }.helpButton("Lists every number of the genome; tick the ones to evolve and give each a range (lo–hi).")
                HStack(spacing: 3) { Text("filter").foregroundStyle(.secondary); TextField("e.g. guidance", text: $filter).labelsHidden().frame(minWidth: 100) }
            }
            if !genes.isEmpty {
                ScrollView {
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(genes.indices.filter { filter.isEmpty || key(genes[$0]).localizedCaseInsensitiveContains(filter) }, id: \.self) { k in
                            let g = genes[k], kk = key(g), v = (g["value"] as? Double) ?? 0
                            HStack {
                                Toggle(kk, isOn: Binding(get: { chosen.contains(kk) }, set: { if $0 { chosen.insert(kk); bounds[kk] = bounds[kk] ?? (v == 0 ? (-1, 1) : (min(v * 0.25, v * 4), max(v * 0.25, v * 4))) } else { chosen.remove(kk) } }))
                                    .toggleStyle(.checkbox).font(.caption)
                                Spacer()
                                if chosen.contains(kk) {
                                    NumBox("lo", Binding(get: { bounds[kk]?.0 ?? 0 }, set: { bounds[kk] = ($0, bounds[kk]?.1 ?? 1) }))
                                    NumBox("hi", Binding(get: { bounds[kk]?.1 ?? 1 }, set: { bounds[kk] = (bounds[kk]?.0 ?? 0, $0) }))
                                } else { Text(String(format: "%g", v)).font(.caption).foregroundStyle(.secondary) }
                            }.font(.caption)
                        }
                    }
                }.frame(maxHeight: 220)
            }
            DoubleField("Target rate (Hz)", $target, help: "Mean firing rate the toy objective rewards (fitness = −(worst error + 0.25 × mean error) across seeds).")
            DoubleField("Input current", $current, help: "Current applied to input neurons during each evaluation.")
            DoubleField("Generations", $gens, help: "Number of generations of the island.")
            DoubleField("Population", $pop, help: "Genomes per generation.")
            DoubleField("Seeds per genome", $seeds, help: "Development seeds each genome is grown with (robustness: the worst seed counts most).")
            Button("Evolve \(chosen.count) genes") {
                let sel = genes.filter { chosen.contains(key($0)) }.map { g -> [String: Any] in
                    let b = bounds[key(g)] ?? (0, 1)
                    return ["path": g["path"] ?? [], "lo": b.0, "hi": b.1]
                }
                app.evolve(genes: sel, target: target, gens: Int(gens), pop: Int(pop), seeds: Int(seeds), current: Int(current))
            }.disabled(chosen.isEmpty || app.busy != nil)
            if !app.evolution.isEmpty {
                Chart {
                    ForEach(Array(app.evolution.enumerated()), id: \.offset) { _, h in
                        LineMark(x: .value("generation", h["generation"] as? Int ?? 0), y: .value("fitness", h["best"] as? Double ?? 0))
                            .foregroundStyle(by: .value("", "best"))
                        LineMark(x: .value("generation", h["generation"] as? Int ?? 0), y: .value("fitness", h["median"] as? Double ?? 0))
                            .foregroundStyle(by: .value("", "median"))
                    }
                }.frame(height: 140)
            }
            if let g = app.evolvedGenome {
                Flow {
                    Button("Use evolved genome and grow") { app.genome = g; app.grow() }
                    Button("Discard") { app.evolvedGenome = nil }
                }
            }
        }
        Placeholder(task: "E2", title: "Supervised fitting", text: "Fit `fit` params to densities, layer thickness, connection statistics or rates (CMA-ES).")
        Placeholder(task: "E3", title: "Semi-supervised and multi-objective", text: "Genes evolved with fitted params refitted in an inner loop; Pareto fronts.")
    }
}

// MARK: Modules

struct ModulesPanel: View {
    @EnvironmentObject var app: AppState
    @State private var name = "my module"
    @State private var desc = ""
    @State private var inputs: Set<String> = []
    @State private var outputs: Set<String> = []
    @State private var composeURLs: [URL] = []
    @State private var links = ""
    var body: some View {
        Card(title: "Open a module", subtitle: "A module = plan + genome + inputs / outputs + validation + provenance; it grows into the 3D view.") {
            Button("Open module…") { app.loadModule() }
        }
        Card(title: "Save the current plan and genome as a module") {
            Row("Name", help: "Module name (also its file name).") { TextField("Name", text: $name).labelsHidden() }
            Row("Description", help: "What the module does, for whoever reuses it.") { TextField("Description", text: $desc).labelsHidden() }
            HStack(spacing: 4) {
                Text("Inputs / outputs").font(.caption.weight(.semibold))
                HelpButton(text: "Regions other modules connect to (inputs) or read from (outputs) when composed.")
            }
            ForEach(app.plan.regions.map(\.name), id: \.self) { r in
                HStack {
                    Text(r).font(.caption); Spacer()
                    Toggle("in", isOn: Binding(get: { inputs.contains(r) }, set: { if $0 { inputs.insert(r) } else { inputs.remove(r) } })).toggleStyle(.checkbox)
                    Toggle("out", isOn: Binding(get: { outputs.contains(r) }, set: { if $0 { outputs.insert(r) } else { outputs.remove(r) } })).toggleStyle(.checkbox)
                }
            }
            Button("Save module…") { app.saveModule(name: name, inputs: Array(inputs), outputs: Array(outputs), description: desc) }
        }
        Card(title: "Compose modules", subtitle: "Each module keeps its genes (names prefixed); links are projections between them.") {
            Button("Choose modules…") {
                let p = NSOpenPanel(); p.allowsMultipleSelection = true; p.allowedContentTypes = [.json]
                if p.runModal() == .OK { composeURLs = p.urls }
            }
            ForEach(composeURLs, id: \.self) { Text($0.lastPathComponent).font(.caption) }
            HStack(spacing: 4) { Text("Links").font(.caption.weight(.semibold)); HelpButton(text: "One projection per line, as source -> target with prefixed region names, e.g. retina.ganglion -> thalamus.relay") }
            TextEditor(text: $links).font(.system(size: 11, design: .monospaced)).frame(height: 60)
            Button("Compose and grow") {
                let l = links.split(separator: "\n").compactMap { line -> [String]? in
                    let p = line.components(separatedBy: "->").map { $0.trimmingCharacters(in: .whitespaces) }
                    return p.count == 2 ? p : nil
                }
                app.composeModules(composeURLs, links: l, name: name)
            }.disabled(composeURLs.count < 1)
        }
        Placeholder(task: "G1", title: "Module registry", text: "Versioned modules, a local catalogue, install and compatibility checks.")
        Placeholder(task: "E4", title: "Validation harness", text: "Declarative assays stored in modules and rerun on demand.")
    }
}

// MARK: Cost

struct CostPanel: View {
    @EnvironmentObject var app: AppState
    @State private var neurons = 100000.0
    @State private var spn = 1000.0
    @State private var seconds = 1.0
    var body: some View {
        Card(title: "Simulation cost", subtitle: "Memory and time per neuron model before running (neurogenesis.cost); calibration runs a short benchmark once per model on this Mac.") {
            Flow {
                Button("Current network") { neurons = Double(app.network.neurons.count); spn = Double(app.network.synapses.count) / Double(max(app.network.neurons.count, 1)) }
                Button("10⁶ neurons × 5000") { neurons = 1e6; spn = 5000 }
            }
            DoubleField("Neurons", $neurons, help: "Number of neurons to estimate for.")
            DoubleField("Synapses per neuron", $spn, help: "Mean number of synapses per neuron.")
            DoubleField("Simulated seconds", $seconds, help: "Simulated time (1 s = 1000 ticks).")
            Flow {
                Button("Estimate") { app.estimate(neurons: Int(neurons), synapses: Int(neurons * spn), ticks: Int(seconds * 1000), calibrate: false) }
                Button("Calibrate + estimate") { app.estimate(neurons: Int(neurons), synapses: Int(neurons * spn), ticks: Int(seconds * 1000), calibrate: true) }
                    .helpButton("Measures this Mac's speed per model once (a few seconds), so that time estimates are available.")
            }
            ForEach(Array(app.estimates.enumerated()), id: \.offset) { _, e in
                VStack(alignment: .leading, spacing: 2) {
                    Text(e["model"] as? String ?? "").font(.callout.weight(.semibold))
                    Text(e["verdict"] as? String ?? "").font(.caption).foregroundStyle((e["fits"] as? Bool ?? true) ? Color.primary : Color.red)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        Placeholder(task: "D3", title: "Development cost model", text: "Per-stage cost declarations summed before a schedule runs (estimate --project).")
        Card(title: "Schedule cost", subtitle: "Declared bytes and operations of the Project's schedule (A4 schedule_cost; stages declare their own).") {
            Button("Compute for the current network size") { app.scheduleInfo() }
            if !app.scheduleReport.isEmpty { Text(app.scheduleReport).font(.caption) }
        }
        Placeholder(task: "D4", title: "Chunked growth", text: "Tissues larger than memory grown in spatial chunks.")
    }
}

// MARK: Analysis

struct AnalysisPanel: View {
    @EnvironmentObject var app: AppState
    @State private var shiftV = 5.0
    @State private var shiftS = 4.0
    @State private var threshold = 1024.0
    @State private var refractory = 3.0
    @State private var hi = 60.0
    @State private var model = "lif_int"
    var body: some View {
        Card(title: "Frequency–current curve", subtitle: "Firing rate of one isolated neuron per constant current (neurogenesis.analysis.fi_curve).") {
            Flow {
                Button("From selection") {
                    if let i = app.selection.first { let n = app.network.neurons[i]; shiftV = Double(n.shiftV); shiftS = Double(n.shiftS); threshold = Double(n.threshold); refractory = Double(n.refractory) }
                }.disabled(app.selection.isEmpty).helpButton("Copies the parameters of the selected neuron.")
            }
            Row("Model", help: "Neuron model the curve is computed with.") {
                Picker("Model", selection: $model) { ForEach(app.models.compactMap { $0["name"] as? String }, id: \.self) { Text($0) } }.labelsHidden()
            }
            DoubleField("Leak shift (shift_v)", $shiftV, help: "Membrane leak: v loses v >> shift_v per tick.")
            DoubleField("Synaptic shift (shift_s)", $shiftS, help: "Synaptic decay: I loses I >> shift_s per tick.")
            DoubleField("Threshold", $threshold, help: "Firing threshold (default 1024).")
            DoubleField("Refractory (ticks)", $refractory, help: "Absolute refractory period.")
            DoubleField("Largest current", $hi, help: "The curve spans currents from 0 to this value (toolbox units).")
            Button("Compute") { app.runFI(shiftV: Int(shiftV), shiftS: Int(shiftS), threshold: Int(threshold), refractory: Int(refractory), hi: Int(hi), model: model) }
            if let (x, y) = app.fiCurve, x.count == y.count {
                Chart { ForEach(x.indices, id: \.self) { k in LineMark(x: .value("current", x[k]), y: .value("Hz", y[k])) } }
                    .chartXAxisLabel("current (toolbox units)").chartYAxisLabel("rate (Hz)").frame(height: 160)
            }
        }
        Card(title: "Mosaic regularity", subtitle: "Nearest-neighbour regularity index of the selection (or all cells), in x–y.") {
            Button("Compute") { app.regularity() }.helpButton("Mean / s.d. of each cell's distance to its nearest neighbour: about 1.9 for random positions, larger for regular mosaics.")
        }
        Card(title: "Firing rates (live, last second)") {
            RegionRates(live: app.live, names: app.network.regionNames)
            Text("Colour neurons by firing rate from the toolbar.").font(.caption).foregroundStyle(.secondary)
        }
    }
}

// MARK: Roadmap

struct RoadmapPanel: View {
    @EnvironmentObject var app: AppState
    @State private var python = AppConfig.load().python
    @State private var repo = AppConfig.load().repo
    var body: some View {
        Card(title: "This Mac", subtitle: "Heavy actions check these first and are refused, with an explanation, when they would not fit (at most \(Int(ResourceGuard.fraction * 100)) % of free memory, and half the RAM).") {
            let m = app.machine
            LabeledContent("Memory free / installed") { Text("\(humanBytes(m.available)) / \(humanBytes(m.physical))").monospacedDigit() }
            LabeledContent("CPU cores") { Text("\(m.cores)") }
            LabeledContent("GPU") { Text("\(m.gpuName) · \(humanBytes(m.gpuWorkingSet))") }
            LabeledContent("Current network in the app") {
                Text(humanBytes(ResourceGuard.networkBytes(neurons: app.network.neurons.count, synapses: app.network.synapses.count, drawnSynapses: Int(app.synapseCap)))).monospacedDigit()
            }
            Button("Refresh") { app.machine = MachineResources.current() }
        }
        Card(title: "Toolbox", subtitle: app.pythonInfo) {
            Button("Refresh (re-scan merged tasks)") { app.bridge.restart() }
                .helpButton("Restarts the Python bridge, which re-imports the toolbox: newly merged tasks appear without restarting the app.")
        }
        Card(title: "Tasks (\(app.capabilities.filter(\.available).count) of \(app.capabilities.count) present)") {
            ForEach(app.capabilities) { c in
                HStack {
                    Image(systemName: c.available ? "checkmark.circle.fill" : "circle.dashed").foregroundStyle(c.available ? .green : .secondary)
                    Text(c.task).font(.caption.monospaced()).frame(width: 38, alignment: .leading)
                    Text(c.name).font(.caption)
                }
            }
        }
        if AppConfig.load().isRelease {
            Card(title: "Python", subtitle: "This release build always uses the Python embedded in the app, with the toolbox installed in it; it does not use any Python on this Mac.") {
                LabeledContent("Runtime") { Text(AppConfig.runtimeDescription).textSelection(.enabled) }
                LabeledContent("Interpreter") { Text(AppConfig.bundledPython ?? "missing: reinstall the app").font(.caption).textSelection(.enabled) }
            }
        } else {
            Card(title: "Python", subtitle: "Development build: the interpreter (with numpy, jax, matplotlib) and the neurogenesis-sim checkout the app drives.") {
                Row("Python", help: "Full path of a Python that has numpy, jax and matplotlib (e.g. /opt/anaconda3/bin/python).") { TextField("Python", text: $python).labelsHidden() }
                Row("Toolbox checkout", help: "Folder of the neurogenesis-sim repository whose code the app uses (where merged work lands).") { TextField("Toolbox checkout", text: $repo).labelsHidden() }
                Button("Apply and restart Python") { app.restartBridge(python: python, repo: repo) }
            }
        }
        Card(title: "Console") {
            ScrollView {
                VStack(alignment: .leading, spacing: 1) {
                    ForEach(app.log.suffix(200)) { l in
                        Text(l.text).font(.system(size: 10, design: .monospaced)).foregroundStyle(l.error ? .red : .secondary).textSelection(.enabled)
                    }
                }
            }.frame(height: 220)
        }
    }
}
