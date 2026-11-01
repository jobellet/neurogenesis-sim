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
        .disabled(false)
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

/// Edits any JSON value as a tree (numbers, strings, booleans; objects and arrays fold), with a raw-text mode.
struct JSONEditor: View {
    @Binding var value: JSONValue
    @State private var raw = false
    @State private var text = ""
    @State private var error: String?
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Picker("", selection: $raw) { Text("Tree").tag(false); Text("JSON").tag(true) }.pickerStyle(.segmented).labelsHidden().frame(width: 140)
            if raw {
                TextEditor(text: $text).font(.system(size: 11, design: .monospaced)).frame(minHeight: 160, maxHeight: 360)
                    .onAppear { text = value.pretty() }
                HStack {
                    Button("Apply") {
                        do { value = try JSONValue.parse(text); error = nil } catch { self.error = error.localizedDescription }
                    }
                    Button("Revert") { text = value.pretty() }
                    if let e = error { Text(e).font(.caption).foregroundStyle(.red).lineLimit(2) }
                }
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
                HStack {
                    if let key { Text(key).foregroundStyle(.secondary) }
                    ForEach(a.indices, id: \.self) { j in
                        TextField("", value: Binding(get: { a.indices.contains(j) ? (value.arrayValue[j].number ?? 0) : 0 },
                                                     set: { v in var arr = value.arrayValue; arr[j] = .number(v); value = .array(arr) }),
                                  format: .number.precision(.fractionLength(0...4))).frame(minWidth: 44)
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
            HStack { Text(key ?? "").foregroundStyle(.secondary); Spacer()
                TextField("", value: Binding(get: { x }, set: { value = .number($0) }), format: .number.precision(.fractionLength(0...6))).frame(width: 90)
            }.font(.caption)
        case .string(let s):
            HStack { Text(key ?? "").foregroundStyle(.secondary); TextField("", text: Binding(get: { s }, set: { value = .string($0) })) }.font(.caption)
        case .bool(let b):
            Toggle(key ?? "", isOn: Binding(get: { b }, set: { value = .bool($0) })).font(.caption)
        case .null:
            HStack { Text(key ?? "").foregroundStyle(.secondary); Text("null").foregroundStyle(.tertiary) }.font(.caption)
        }
    }

    @ViewBuilder func group<C: View>(title: String?, count: Int, @ViewBuilder _ c: () -> C) -> some View {
        let content = c()
        if let title {
            DisclosureGroup { VStack(alignment: .leading, spacing: 3) { content }.padding(.leading, 4) } label: {
                Text("\(title)").font(.caption.weight(.medium)) + Text("  \(count)").font(.caption2).foregroundColor(.secondary)
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
            HStack {
                Button("New") { app.newProject() }
                Button("Open…") { app.openProject() }
                Button("Save") { app.saveProject() }
                Button("Save As…") { app.saveProject(as: true) }
                Button("Validate") { app.validateProject() }
            }
        }
        Card(title: "Settings") {
            Picker("Neuron model", selection: Binding(get: { app.project["neuron_model"]?.stringValue ?? "lif_int" },
                                                      set: { app.project["neuron_model"] = .string($0); app.simModel = $0 })) {
                ForEach(app.models.compactMap { $0["name"] as? String }.isEmpty ? ["lif_int"] : app.models.compactMap { $0["name"] as? String }, id: \.self) { Text($0) }
            }
            TextField("Plugins (Python modules, comma separated)", text: Binding(
                get: { (app.project["plugins"]?.arrayValue.compactMap { $0.stringValue } ?? []).joined(separator: ", ") },
                set: { app.project["plugins"] = .array($0.split(separator: ",").map { .string($0.trimmingCharacters(in: .whitespaces)) }.filter { $0 != .string("") }) }))
        }
        ForEach(["metadata", "fields", "schedule", "geometry", "genome", "plan"], id: \.self) { key in
            DisclosureGroup("\(key)") {
                JSONEditor(value: Binding(get: {
                    app.syncProject(); return app.project[key] ?? .null
                }, set: { v in
                    app.project[key] = v
                    if key == "plan" { app.plan = PlanSpec(v) }
                    if key == "genome" { app.genome = v }
                    if key == "geometry" { app.adoptProject(app.project) }
                }))
            }
        }
    }
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
            HStack {
                ForEach(app.geometryTypes) { t in Button(t.type) { app.addGeometry(t) } }
            }.controlSize(.small).fixedSize()
            if app.geometryTypes.isEmpty { Text("Waiting for Python…").font(.caption).foregroundStyle(.secondary) }
        }
        ForEach($app.geometries) { $g in
            GeometryEditor(item: $g)
        }
        if !app.geometries.isEmpty {
            Card(title: "Seed cells in a shape", subtitle: "Unconnected LIF neurons sampled uniformly in the shape (stage C1 seed_cells will add densities from fields). Then wire them in the Network panel.") {
                ForEach(app.geometries.indices, id: \.self) { k in
                    Button("Sample in \(app.geometries[k].name)") { app.sampleCells(in: k, n: Int(cells), inhFraction: inh, role: role, replace: replace, seed: Int(seed)) }
                }
                LabeledContent("Cells") { TextField("", value: $cells, format: .number).frame(width: 80) }
                LabeledContent("Inhibitory fraction") { Slider(value: $inh, in: 0...1); Text(String(format: "%.2f", inh)).monospacedDigit() }
                Picker("Role", selection: $role) { Text("internal").tag(0); Text("input").tag(1); Text("output").tag(2) }
                Toggle("Replace the network (otherwise append as a new region)", isOn: $replace)
                LabeledContent("Seed") { TextField("", value: $seed, format: .number).frame(width: 80) }
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
            HStack {
                TextField("Name", text: $item.name)
                Toggle("Visible", isOn: $item.visible)
                Button { app.geometries.removeAll { $0.id == item.id } } label: { Image(systemName: "trash") }.buttonStyle(.borderless)
            }
            ForEach(params) { p in
                switch p.kind {
                case "vec3":
                    Vec3Field(label: p.name, value: Binding(get: {
                        let a = item.spec[p.name]?.arrayValue.compactMap { $0.number } ?? [0, 0, 0]
                        return a.count == 3 ? SIMD3(a[0], a[1], a[2]) : .zero
                    }, set: { v in item.spec[p.name] = .array([.number(v.x), .number(v.y), .number(v.z)]); app.previewGeometry(index) }))
                case "float":
                    LabeledContent(p.name) {
                        TextField("", value: Binding(get: { item.spec[p.name]?.number ?? 0 },
                                                     set: { item.spec[p.name] = .number($0); app.previewGeometry(index) }), format: .number)
                    }
                case "string":
                    LabeledContent(p.name) {
                        TextField("", text: Binding(get: { item.spec[p.name]?.stringValue ?? "" }, set: { item.spec[p.name] = .string($0) }))
                            .onSubmit { app.previewGeometry(index) }
                    }
                default:
                    DisclosureGroup(p.name) {
                        JSONEditor(value: Binding(get: { item.spec[p.name] ?? .null }, set: { item.spec[p.name] = $0; app.previewGeometry(index) }))
                    }
                }
            }
            if let e = item.error { Text(e).font(.caption).foregroundStyle(.red) }
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
            HStack {
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
            TextField("Name", text: $app.plan.name)
            LabeledContent("Conduction velocity") { TextField("", value: $app.plan.conductionVelocity, format: .number) }
            LabeledContent("Max delay (ticks)") { TextField("", value: $app.plan.maxDelay, format: .number) }
            LabeledContent("Development seed") { TextField("", value: $app.devSeed, format: .number) }
            HStack {
                Button("Grow") { app.grow() }.keyboardShortcut("g", modifiers: [.command])
                Button("Develop step by step") { app.growSteps() }
                Menu("More") {
                    Button("Open plan…") { app.openProject() }
                    Button("Save plan…") { app.savePlan() }
                    Button("Reset to example") { app.plan = PlanSpec.example(); app.genome = .object([:]) }
                    Button("Empty plan") { app.plan = PlanSpec(); app.genome = .object([:]) }
                    Toggle("Show region boxes", isOn: $app.showRegionBoxes)
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
        Card(title: "Projections", subtitle: "Grown in this order. Guidance genes: sigma (spread of targets), p0 (peak probability), w (weight).") {
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
                        Text(phase).font(.caption.weight(.semibold))
                        HStack { ForEach(app.rules[phase] ?? [], id: \.self) { r in
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
                TextField("Name", text: $region.name)
                Vec3Field(label: "Origin", value: $region.origin)
                Vec3Field(label: "Size", value: $region.size)
                Picker("Placement", selection: $region.fixed) { Text("grown (genes)").tag(false); Text("fixed labels").tag(true) }.pickerStyle(.segmented)
                if region.fixed {
                    HStack {
                        Text("\(region.labels.count) labels")
                        Spacer()
                        TextField("nx", value: $nx, format: .number).frame(width: 36)
                        TextField("ny", value: $ny, format: .number).frame(width: 36)
                        TextField("nz", value: $nz, format: .number).frame(width: 36)
                        Button("Grid") { region.labels = RegionSpec.grid(max(1, Int(nx)), max(1, Int(ny)), max(1, Int(nz))) }
                    }.font(.caption)
                } else {
                    LabeledContent("Count (gene)") {
                        TextField("", value: gene(["count", region.name], 60), format: .number).frame(width: 70)
                    }
                    LabeledContent("Spread (gene)") {
                        TextField("", value: gene(["migration", region.name, "spread"], 0.3), format: .number).frame(width: 70)
                    }
                    LabeledContent("Inhibitory bias a0 (gene)") {
                        TextField("", value: gene(["inhibitory", region.name, "a0"], -1.4), format: .number).frame(width: 70)
                    }
                    HStack {
                        Text("Count bounds").font(.caption)
                        TextField("", value: $region.countLo, format: .number).frame(width: 50)
                        TextField("", value: $region.countHi, format: .number).frame(width: 60)
                    }
                }
                Picker("Role", selection: $region.role) { Text("internal").tag(0); Text("input").tag(1); Text("output").tag(2) }
                Picker("Sign", selection: $region.sign) { Text("genetic").tag("genetic"); Text("excitatory").tag("exc"); Text("inhibitory").tag("inh") }
                Stepper("Refractory: \(region.refractory) ticks", value: $region.refractory, in: 0...50)
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
                Picker("", selection: $projection.src) { ForEach(names, id: \.self) { Text($0) } }.labelsHidden()
                Image(systemName: "arrow.right")
                Picker("", selection: $projection.dst) { ForEach(names, id: \.self) { Text($0) } }.labelsHidden()
                Button { app.plan.projections.removeAll { $0.id == projection.id } } label: { Image(systemName: "minus.circle") }.buttonStyle(.borderless)
            }
            HStack {
                ForEach([("sigma", 0.3), ("p0", 0.5), ("w", 100.0)], id: \.0) { g, def in
                    Text(g).font(.caption).foregroundStyle(.secondary)
                    TextField(g, value: Binding(get: { app.genome["guidance"]?[key]?[g]?.number ?? def },
                                                set: { app.genome = setPath(app.genome, ["guidance", key, g][...], .number($0)) }), format: .number)
                        .frame(width: 54)
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
            HStack {
                Button("Fill defaults for the plan") { app.action("Completing genome") { try await app.completeGenome() } }
                Button("Grow") { app.grow() }
                Button("Clear") { app.genome = .object([:]) }
            }
            HStack {
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
        Card(title: "Stage catalogue", subtitle: app.stagesAvailable ? "Registered stages." : "Stages planned in the roadmap (C1–C13). You can already compose a schedule; it runs once A4 and the stages are merged.") {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 130), alignment: .leading)], alignment: .leading, spacing: 4) {
                ForEach(app.stages) { s in
                    Button { add(s) } label: {
                        HStack(spacing: 4) {
                            Circle().fill(s.available ? Color.green : Color.orange.opacity(0.6)).frame(width: 6, height: 6)
                            Text(s.name).font(.caption)
                            Text(s.task).font(.caption2).foregroundStyle(.secondary)
                        }
                    }.buttonStyle(.bordered).controlSize(.small).help(s.doc.isEmpty ? "\(s.task): \(s.name)" : s.doc)
                }
            }
        }
        Card(title: "Schedule (\(schedule.count) stages)", subtitle: "Ordered stages (A4: name, operator, params, repeat); each parameter is an A3 Param: Const, Gene (dotted path, lo, hi), Field, Fit or Expr.") {
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
            HStack {
                Button("Run schedule") { app.runSchedule() }.disabled(!app.stagesAvailable || schedule.isEmpty)
                Button("Genes and cost") { app.scheduleInfo() }.disabled(schedule.isEmpty)
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
                TextField("Name", text: Binding(get: { stage["name"]?.stringValue ?? "" }, set: { stage["name"] = .string($0) }))
                Stepper("Repeat: \(Int(stage["repeat"]?.number ?? 1))", value: Binding(get: { Int(stage["repeat"]?.number ?? 1) },
                                                                                        set: { stage["repeat"] = .number(Double(max(1, $0))) }), in: 1...1000)
                ForEach((stage["params"]?.objectValue ?? [:]).keys.sorted(), id: \.self) { p in
                    ParamEditor(name: p, param: Binding(get: { stage["params"]?[p] ?? .null }, set: { v in
                        var ps = stage["params"]?.objectValue ?? [:]; ps[p] = v; stage["params"] = .object(ps)
                    }), remove: { var ps = stage["params"]?.objectValue ?? [:]; ps.removeValue(forKey: p); stage["params"] = .object(ps) })
                }
                HStack {
                    TextField("new parameter", text: $newParam).frame(width: 140)
                    Button("Add") {
                        guard !newParam.isEmpty else { return }
                        var ps = stage["params"]?.objectValue ?? [:]
                        ps[newParam] = .object(["type": .string("Const"), "value": .number(0)])
                        stage["params"] = .object(ps); newParam = ""
                    }
                }.controlSize(.small)
            }
        } label: {
            HStack {
                Text("\(index + 1).").monospacedDigit().foregroundStyle(.secondary)
                Text(stage["operator"]?.stringValue ?? stage["stage"]?.stringValue ?? "?").font(.callout.weight(.medium))
                Spacer()
                Button { move(-1) } label: { Image(systemName: "chevron.up") }.buttonStyle(.borderless)
                Button { move(1) } label: { Image(systemName: "chevron.down") }.buttonStyle(.borderless)
                Button(action: remove) { Image(systemName: "trash") }.buttonStyle(.borderless)
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
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(name).font(.caption.weight(.semibold))
                Picker("", selection: Binding(get: { src }, set: { param["type"] = .string($0) })) {
                    ForEach(["Const", "Gene", "Field", "Fit", "Expr"], id: \.self) { Text($0) }
                }.pickerStyle(.segmented).labelsHidden()
                Button(action: remove) { Image(systemName: "xmark") }.buttonStyle(.borderless)
            }
            HStack {
                switch src {
                case "Gene":
                    text("path", "e.g. growth.rate"); num("lo"); num("hi")
                    Toggle("int", isOn: Binding(get: { param["integer"] == .bool(true) }, set: { param["integer"] = .bool($0) })).toggleStyle(.checkbox)
                case "Field":
                    text("name", "field name"); text("transform", "e.g. 2*x")
                case "Fit":
                    text("target", "e.g. density"); num("init"); num("lo"); num("hi")
                case "Expr":
                    text("formula", "e.g. 0.5 * depth")
                default:
                    if case .string = param["value"] ?? .null { text("value", "") } else { num("value") }
                }
            }.font(.caption)
        }
        .padding(6)
        .background(RoundedRectangle(cornerRadius: 5).fill(Color.primary.opacity(0.04)))
    }
    func num(_ k: String) -> some View {
        TextField(k, value: Binding(get: { param[k]?.number ?? 0 }, set: { param[k] = .number($0) }), format: .number).frame(width: 60)
    }
    func text(_ k: String, _ prompt: String) -> some View {
        TextField(prompt, text: Binding(get: { param[k]?.stringValue ?? "" }, set: { param[k] = .string($0) }))
    }
}

// MARK: Development

struct DevelopmentPanel: View {
    @EnvironmentObject var app: AppState
    @State private var playing = false
    @State private var timer: Timer?

    var body: some View {
        Card(title: "Develop", subtitle: "Checkpoints after each developmental step, for stepping through development in 3D.") {
            LabeledContent("Development seed") { TextField("", value: $app.devSeed, format: .number).frame(width: 80) }
            HStack {
                Button("Body plan, step by step") { app.growSteps() }
                Button("Run schedule") { app.runSchedule() }.disabled(!app.stagesAvailable)
            }
        }
        Placeholder(task: "A4", title: "Stage checkpoints", text: "The tissue after every scheduled stage (proliferation, migration, differentiation, axon growth, pruning…).")
        if !app.checkpoints.isEmpty {
            Card(title: "Checkpoints", subtitle: "Source: \(app.checkpointSource)") {
                HStack {
                    Button { toggle() } label: { Image(systemName: playing ? "pause.fill" : "play.fill") }
                    Slider(value: Binding(get: { Double(app.checkpointIndex) }, set: { app.showCheckpoint(Int($0.rounded())) }),
                           in: 0...Double(max(app.checkpoints.count - 1, 1)), step: 1)
                    Text("\(app.checkpointIndex + 1)/\(app.checkpoints.count)").monospacedDigit()
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
            Picker("Preset", selection: $morph) { Text("Cortical column").tag("column"); Text("Layered sheets").tag("layered"); Text("Microcircuit").tag("microcircuit") }
            LabeledContent("Neurons") { TextField("", value: $n, format: .number).frame(width: 80) }
            LabeledContent("Seed") { TextField("", value: $seed, format: .number).frame(width: 80) }
            if morph == "column" {
                LabeledContent("Weight scale") { Slider(value: $weightScale, in: 0.05...1.5); Text(String(format: "%.2f", weightScale)).monospacedDigit() }
                LabeledContent("Refractory") { Stepper("\(Int(refractory))", value: $refractory, in: 0...20) }
            }
            HStack {
                Button("Generate") { app.generate(morph, neurons: Int(n), seed: Int(seed), extra: ["weight_scale": weightScale, "refractory": Int(refractory)]) }
                Button("Grow body plan") { app.grow() }
                Button("Empty") { app.clearNetwork() }
            }
            HStack {
                Button("Open network…") { app.openNetwork() }
                Button("Save network…") { app.saveNetwork() }
            }
        }
        Card(title: "Draw by hand", subtitle: "Tools in the toolbar: ⌘1 select, ⌘2 add, ⌘3 connect, ⌘4 stimulate. Supervised entry points (C9) will read these edits from the Project.") {
            Picker("Tool", selection: $app.tool) { ForEach(Tool.allCases) { Label($0.rawValue, systemImage: $0.icon).tag($0) } }.pickerStyle(.radioGroup)
            Text("New neurons").font(.caption.weight(.semibold))
            Picker("Driver", selection: $app.newNeuron.mode) { Text("LIF").tag(Int32(0)); Text("Poisson").tag(Int32(1)); Text("Burster").tag(Int32(2)) }
            Picker("Sign", selection: Binding(get: { app.newNeuron.baseWeight < 0 }, set: { app.newNeuron.baseWeight = $0 ? -abs(app.newNeuron.baseWeight) : abs(app.newNeuron.baseWeight) })) {
                Text("excitatory").tag(false); Text("inhibitory").tag(true)
            }.pickerStyle(.segmented)
            Picker("Role", selection: $app.newNeuron.role) { Text("internal").tag(Int32(0)); Text("input").tag(Int32(1)); Text("output").tag(Int32(2)) }
            IntField("Threshold", $app.newNeuron.threshold)
            IntField("Refractory", $app.newNeuron.refractory)
            IntField("Compartment", $app.newNeuron.compartment)
            Text("New synapses").font(.caption.weight(.semibold))
            LabeledContent("Weight") { TextField("", value: $app.newWeight, format: .number).frame(width: 70) }
            LabeledContent("Delay (ticks)") { Stepper("\(Int(app.newDelay))", value: $app.newDelay, in: 0...31) }
        }
        Card(title: "Selection (\(app.selection.count))") {
            HStack {
                Button("All") { app.selectAll() }
                Button("None") { app.selection = [] }
                Menu("Region") { ForEach(Array(app.network.regionNames.enumerated()), id: \.offset) { k, name in Button(name) { app.selectRegion(Int32(k)) } } }
                    .disabled(app.network.regionNames.isEmpty)
                Button("Delete", role: .destructive) { app.deleteSelection() }.disabled(app.selection.isEmpty)
            }
            HStack {
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
            LabeledContent("Seed") { TextField("", value: $wireSeed, format: .number).frame(width: 70) }
            LabeledContent("Conduction velocity") { TextField("", value: $velocity, format: .number).frame(width: 70) }
            HStack {
                Button("Wire") { app.wireByDistance(seed: Int(wireSeed), velocity: velocity) }
                Button("Set radius 28 / p 0.3 on selection") { app.updateSelected { $0.connRadius = 28; $0.connProb = 0.3 } }.disabled(app.selection.isEmpty)
            }
        }
        Card(title: "Statistics") {
            Button("Compute") { app.computeStats() }
            if let s = app.stats { JSONNodeView(key: nil, value: .constant(s), depth: 0).disabled(true) }
        }
        Card(title: "View") {
            LabeledContent("Neuron size") { Slider(value: $app.pointSize, in: 1...14) }
            Toggle("Perspective size", isOn: $app.perspectiveSize)
            LabeledContent("Flash decay (ms)") { Slider(value: $app.flashTau, in: 3...120) }
            LabeledContent("Max synapses drawn") { Slider(value: $app.synapseCap, in: 1000...400000) ; Text("\(Int(app.synapseCap / 1000))k").monospacedDigit() }
            Toggle("Grid", isOn: $app.showGrid)
            Toggle("Region boxes", isOn: $app.showRegionBoxes)
        }
    }
}

// MARK: Simulation

struct SimulationPanel: View {
    @EnvironmentObject var app: AppState
    @State private var offlineTicks = 500.0
    var body: some View {
        Card(title: "Live (native lif_int)", subtitle: "The integer kernel runs natively, bit-identical to the Python, JAX and browser kernels (tests/test_desktop_kernel.py). Neurons flash and synapses light up when spikes travel.") {
            HStack {
                Button { app.running.toggle() } label: { Label(app.running ? "Pause" : "Run", systemImage: app.running ? "pause.fill" : "play.fill") }
                Button("Step 1 ms") { app.engine.step(1) }
                Button("Step 100 ms") { app.engine.step(100) }
                Button("Reset") { app.resetSimulation() }
            }
            LabeledContent("Speed") {
                Slider(value: Binding(get: { app.speed == 0 ? 5 : log10(max(app.speed, 10)) }, set: { app.speed = $0 >= 4.95 ? 0 : pow(10, $0) }), in: 1...5)
                Text(app.speed == 0 ? "max" : "\(Int(app.speed)) ms/s").monospacedDigit().frame(width: 80, alignment: .trailing)
            }
            LabeledContent("Kernel seed") { TextField("", value: $app.kernelSeed, format: .number).frame(width: 80) }
            Text(String(format: "t = %d ms · %.1f Hz mean · %.0f ticks/s", app.tick, app.rateHz, app.tps)).font(.caption).monospacedDigit().foregroundStyle(.secondary)
        }
        Card(title: "Stimulation", subtitle: "Currents in toolbox units, added to the synaptic current every tick (as jax_backend.tick ext_current). Rheobase ≈ 8.5.") {
            Toggle("Drive input neurons (role 1)", isOn: $app.driveInputs)
            LabeledContent("Input current") { Slider(value: $app.inputCurrent, in: 0...400); Text("\(Int(app.inputCurrent))").monospacedDigit().frame(width: 36) }
            LabeledContent("Current on selection") { Slider(value: $app.selectionCurrent, in: -200...400); Text("\(Int(app.selectionCurrent))").monospacedDigit().frame(width: 36) }
            LabeledContent("Pulse (stimulate tool, ⌥-click)") { Slider(value: $app.pulseCurrent, in: 10...4000); Text("\(Int(app.pulseCurrent))").monospacedDigit().frame(width: 40) }
        }
        Card(title: "Other neuron models", subtitle: "Runs any registered model (JAX, in Python) on the current network and stimulation, after checking its cost.") {
            Picker("Model", selection: $app.simModel) { ForEach(app.models.compactMap { $0["name"] as? String }, id: \.self) { Text($0) } }
            if let d = app.models.first(where: { $0["name"] as? String == app.simModel })?["description"] as? String {
                Text(d).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            LabeledContent("Duration (ms)") { TextField("", value: $offlineTicks, format: .number).frame(width: 80) }
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
    var body: some View {
        Placeholder(task: "E1", title: "Plasticity rules", text: "STDP, Hebbian with normalisation, three-factor rules.")
        Card(title: "Learn from live activity", subtitle: "Records the live simulation, applies the rule to every synapse (neurogenesis.spiking.plasticity) and writes the new weights back into the network (undoable).") {
            if app.plasticityRules.isEmpty { Text("No rules registered yet.").font(.caption).foregroundStyle(.secondary) }
            else {
                Picker("Rule", selection: $rule) { ForEach(app.plasticityRules, id: \.0) { Text($0.0).tag($0.0) } }
                ForEach(app.plasticityRules.first { $0.0 == rule }?.1 ?? [], id: \.0) { name, def in
                    HStack {
                        Text(name).font(.caption)
                        Spacer()
                        switch values[name] ?? def {
                        case .bool: Toggle("", isOn: Binding(get: { values[name]?.any as? Bool ?? (def.any as? Bool ?? false) }, set: { values[name] = .bool($0) })).labelsHidden()
                        case .string: TextField("", text: Binding(get: { (values[name] ?? def).stringValue ?? "" }, set: { values[name] = .string($0) })).frame(width: 120)
                        default: TextField("", value: Binding(get: { (values[name] ?? def).number ?? 0 }, set: { values[name] = .number($0) }), format: .number).frame(width: 80)
                        }
                    }
                }
                LabeledContent("Record (ms)") { TextField("", value: $ticks, format: .number).frame(width: 80) }
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
            HStack {
                Button("List genes") {
                    app.action("Listing genes") {
                        try await app.completeGenome()
                        genes = (try await app.bridge.dict("genes", ["genome": app.genome.any]))["genes"] as? [[String: Any]] ?? []
                    }
                }
                TextField("filter", text: $filter)
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
                                    TextField("lo", value: Binding(get: { bounds[kk]?.0 ?? 0 }, set: { bounds[kk] = ($0, bounds[kk]?.1 ?? 1) }), format: .number).frame(width: 50)
                                    TextField("hi", value: Binding(get: { bounds[kk]?.1 ?? 1 }, set: { bounds[kk] = (bounds[kk]?.0 ?? 0, $0) }), format: .number).frame(width: 50)
                                } else { Text(String(format: "%g", v)).font(.caption).foregroundStyle(.secondary) }
                            }
                        }
                    }
                }.frame(maxHeight: 220)
            }
            LabeledContent("Target rate (Hz)") { TextField("", value: $target, format: .number).frame(width: 60) }
            LabeledContent("Input current") { TextField("", value: $current, format: .number).frame(width: 60) }
            HStack {
                Text("gens"); TextField("", value: $gens, format: .number).frame(width: 40)
                Text("pop"); TextField("", value: $pop, format: .number).frame(width: 40)
                Text("seeds"); TextField("", value: $seeds, format: .number).frame(width: 40)
            }.font(.caption)
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
                HStack {
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
            TextField("Name", text: $name)
            TextField("Description", text: $desc)
            Text("Inputs / outputs").font(.caption.weight(.semibold))
            ForEach(app.plan.regions.map(\.name), id: \.self) { r in
                HStack {
                    Text(r).font(.caption); Spacer()
                    Toggle("in", isOn: Binding(get: { inputs.contains(r) }, set: { if $0 { inputs.insert(r) } else { inputs.remove(r) } })).toggleStyle(.checkbox)
                    Toggle("out", isOn: Binding(get: { outputs.contains(r) }, set: { if $0 { outputs.insert(r) } else { outputs.remove(r) } })).toggleStyle(.checkbox)
                }
            }
            Button("Save module…") { app.saveModule(name: name, inputs: Array(inputs), outputs: Array(outputs), description: desc) }
        }
        Card(title: "Compose modules", subtitle: "Each module keeps its genes (names prefixed); links are projections between them, as \"a.out->b.in\" per line.") {
            Button("Choose modules…") {
                let p = NSOpenPanel(); p.allowsMultipleSelection = true; p.allowedContentTypes = [.json]
                if p.runModal() == .OK { composeURLs = p.urls }
            }
            ForEach(composeURLs, id: \.self) { Text($0.lastPathComponent).font(.caption) }
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
            HStack {
                Button("Current network") { neurons = Double(app.network.neurons.count); spn = Double(app.network.synapses.count) / Double(max(app.network.neurons.count, 1)) }
                Button("Cortical column 10⁶") { neurons = 1e6; spn = 5000 }
            }
            LabeledContent("Neurons") { TextField("", value: $neurons, format: .number).frame(width: 110) }
            LabeledContent("Synapses per neuron") { TextField("", value: $spn, format: .number).frame(width: 110) }
            LabeledContent("Simulated seconds") { TextField("", value: $seconds, format: .number).frame(width: 110) }
            HStack {
                Button("Estimate") { app.estimate(neurons: Int(neurons), synapses: Int(neurons * spn), ticks: Int(seconds * 1000), calibrate: false) }
                Button("Calibrate + estimate") { app.estimate(neurons: Int(neurons), synapses: Int(neurons * spn), ticks: Int(seconds * 1000), calibrate: true) }
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
            HStack {
                Button("From selection") {
                    if let i = app.selection.first { let n = app.network.neurons[i]; shiftV = Double(n.shiftV); shiftS = Double(n.shiftS); threshold = Double(n.threshold); refractory = Double(n.refractory) }
                }.disabled(app.selection.isEmpty)
                Picker("", selection: $model) { ForEach(app.models.compactMap { $0["name"] as? String }, id: \.self) { Text($0) } }.labelsHidden()
            }
            HStack {
                Text("shift_v"); TextField("", value: $shiftV, format: .number).frame(width: 36)
                Text("shift_s"); TextField("", value: $shiftS, format: .number).frame(width: 36)
                Text("θ"); TextField("", value: $threshold, format: .number).frame(width: 50)
                Text("ref"); TextField("", value: $refractory, format: .number).frame(width: 36)
                Text("max I"); TextField("", value: $hi, format: .number).frame(width: 44)
            }.font(.caption)
            Button("Compute") { app.runFI(shiftV: Int(shiftV), shiftS: Int(shiftS), threshold: Int(threshold), refractory: Int(refractory), hi: Int(hi), model: model) }
            if let (x, y) = app.fiCurve, x.count == y.count {
                Chart { ForEach(x.indices, id: \.self) { k in LineMark(x: .value("current", x[k]), y: .value("Hz", y[k])) } }
                    .chartXAxisLabel("current (toolbox units)").chartYAxisLabel("rate (Hz)").frame(height: 160)
            }
        }
        Card(title: "Mosaic regularity", subtitle: "Nearest-neighbour regularity index of the selection (or all cells), in x–y.") {
            Button("Compute") { app.regularity() }
        }
        Card(title: "Firing rates (live)") {
            let r = app.engine.rates(1000)
            let names = app.network.regionNames
            if !names.isEmpty {
                ForEach(Array(names.enumerated()), id: \.offset) { k, name in
                    let idx = app.network.neurons.indices.filter { app.network.neurons[$0].compartment == Int32(k) }
                    let m = idx.isEmpty ? 0 : idx.map { Double(r[$0]) }.reduce(0, +) / Double(idx.count)
                    HStack { Circle().fill(paletteColor(k).swiftUI).frame(width: 8, height: 8); Text(name); Spacer(); Text(String(format: "%.1f Hz", m)).monospacedDigit() }.font(.caption)
                }
            } else { Text(String(format: "%.1f Hz mean", app.rateHz)).font(.caption) }
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
        Card(title: "Toolbox", subtitle: app.pythonInfo) {
            Button("Refresh (re-scan merged tasks)") { app.bridge.restart(); }
            Text("Restarting the Python bridge re-imports the toolbox, so newly merged tasks appear without restarting the app.").font(.caption).foregroundStyle(.secondary)
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
        Card(title: "Python", subtitle: "The interpreter (with numpy, jax, matplotlib) and the neurogenesis-sim checkout the app drives.") {
            TextField("Python", text: $python)
            TextField("Toolbox checkout", text: $repo)
            Button("Apply and restart Python") { app.restartBridge(python: python, repo: repo) }
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
