import Foundation
import simd
import SwiftUI

/// A JSON value, editable in SwiftUI (genomes, project sections, stage parameters).
enum JSONValue: Equatable {
    case null
    case bool(Bool)
    case number(Double)
    case string(String)
    case array([JSONValue])
    case object([String: JSONValue])

    init(_ any: Any?) {
        switch any {
        case nil, is NSNull: self = .null
        case let n as NSNumber:
            if CFGetTypeID(n) == CFBooleanGetTypeID() { self = .bool(n.boolValue) } else { self = .number(n.doubleValue) }
        case let s as String: self = .string(s)
        case let a as [Any]: self = .array(a.map { JSONValue($0) })
        case let d as [String: Any]: self = .object(d.mapValues { JSONValue($0) })
        default: self = .string(String(describing: any!))
        }
    }

    var any: Any {
        switch self {
        case .null: return NSNull()
        case .bool(let b): return b
        case .number(let x): return x.rounded() == x && abs(x) < 1e15 ? (Int(x) as Any) : (x as Any)
        case .string(let s): return s
        case .array(let a): return a.map { $0.any }
        case .object(let d): return d.mapValues { $0.any }
        }
    }

    subscript(key: String) -> JSONValue? {
        get { if case .object(let d) = self { return d[key] }; return nil }
        set {
            guard case .object(var d) = self else { return }
            d[key] = newValue; self = .object(d)
        }
    }

    var objectValue: [String: JSONValue] { if case .object(let d) = self { return d }; return [:] }
    var arrayValue: [JSONValue] { if case .array(let a) = self { return a }; return [] }
    var number: Double? { if case .number(let x) = self { return x }; return nil }
    var stringValue: String? { if case .string(let s) = self { return s }; return nil }

    func pretty() -> String {
        guard let d = try? JSONSerialization.data(withJSONObject: any, options: [.prettyPrinted, .sortedKeys, .fragmentsAllowed]) else { return "" }
        return String(data: d, encoding: .utf8) ?? ""
    }

    static func parse(_ text: String) throws -> JSONValue {
        JSONValue(try JSONSerialization.jsonObject(with: Data(text.utf8), options: [.fragmentsAllowed]))
    }
}

// MARK: Body plan (neurogenesis.development.BodyPlan), edited in the Plan panel

struct RegionSpec: Identifiable, Equatable {
    var id = UUID()
    var name: String
    var origin: SIMD3<Double> = .zero
    var size: SIMD3<Double> = SIMD3(30, 30, 10)
    var fixed = false
    var labels: [[Double]] = []
    var placementExtra: [String: JSONValue] = [:]     // counts, jitter: kept as they are
    var role = 0
    var sign = "genetic"                              // genetic, exc, inh
    var refractory = 3
    var countLo = 4, countHi = 1024

    static func grid(_ nx: Int, _ ny: Int, _ nz: Int) -> [[Double]] {
        var out: [[Double]] = []
        for i in 0..<nx { for j in 0..<ny { for k in 0..<nz {
            out.append([(Double(i) + 0.5) / Double(nx), (Double(j) + 0.5) / Double(ny), (Double(k) + 0.5) / Double(nz)])
        }}}
        return out
    }
}

struct ProjectionSpec: Identifiable, Equatable {
    var id = UUID()
    var src: String
    var dst: String
}

struct PlanSpec: Equatable {
    var name = "untitled"
    var regions: [RegionSpec] = []
    var projections: [ProjectionSpec] = []
    var conductionVelocity = 20.0
    var maxDelay = 31
    var rules: JSONValue = .null
    var plugins: [String] = []

    var dict: [String: Any] {
        var d: [String: Any] = [
            "name": name, "conduction_velocity": conductionVelocity, "max_delay": maxDelay, "plugins": plugins,
            "projections": projections.map { [$0.src, $0.dst] },
            "regions": regions.map { r -> [String: Any] in
                var placement: Any = NSNull()
                if r.fixed {
                    var p = r.placementExtra.mapValues { $0.any }
                    p["labels"] = r.labels
                    placement = p
                }
                return ["name": r.name, "origin": [r.origin.x, r.origin.y, r.origin.z], "size": [r.size.x, r.size.y, r.size.z],
                        "placement": placement, "role": r.role, "sign": r.sign == "genetic" ? NSNull() : r.sign as Any,
                        "refractory": r.refractory, "count_bounds": [r.countLo, r.countHi]]
            },
        ]
        if case .object = rules { d["rules"] = rules.any }
        return d
    }

    init() {}

    init(_ j: JSONValue) {
        let d = j.objectValue
        name = d["name"]?.stringValue ?? "plan"
        conductionVelocity = d["conduction_velocity"]?.number ?? 20
        maxDelay = Int(d["max_delay"]?.number ?? 31)
        rules = d["rules"] ?? .null
        plugins = d["plugins"]?.arrayValue.compactMap { $0.stringValue } ?? []
        func v3(_ x: JSONValue?) -> SIMD3<Double> {
            let a = x?.arrayValue.compactMap { $0.number } ?? []
            return a.count == 3 ? SIMD3(a[0], a[1], a[2]) : .zero
        }
        regions = d["regions"]?.arrayValue.map { r in
            let o = r.objectValue
            var spec = RegionSpec(name: o["name"]?.stringValue ?? "region", origin: v3(o["origin"]), size: v3(o["size"]))
            if case .object(var pl) = o["placement"] ?? .null {
                spec.fixed = true
                spec.labels = pl["labels"]?.arrayValue.map { $0.arrayValue.compactMap { $0.number } } ?? []
                pl.removeValue(forKey: "labels")
                spec.placementExtra = pl.filter { $0.value != .null }
            }
            spec.role = Int(o["role"]?.number ?? 0)
            spec.sign = o["sign"]?.stringValue ?? "genetic"
            spec.refractory = Int(o["refractory"]?.number ?? 3)
            let cb = o["count_bounds"]?.arrayValue.compactMap { $0.number } ?? [4, 1024]
            if cb.count == 2 { spec.countLo = Int(cb[0]); spec.countHi = Int(cb[1]) }
            return spec
        } ?? []
        projections = d["projections"]?.arrayValue.compactMap { p in
            let a = p.arrayValue.compactMap { $0.stringValue }
            return a.count == 2 ? ProjectionSpec(src: a[0], dst: a[1]) : nil
        } ?? []
    }

    /// A small working example: a sensor sheet projecting topographically onto a grown map with recurrent inhibition.
    static func example() -> PlanSpec {
        var p = PlanSpec()
        p.name = "sensor → map"
        p.regions = [
            RegionSpec(name: "sensor", origin: SIMD3(0, 0, 0), size: SIMD3(30, 30, 5), fixed: true, labels: RegionSpec.grid(6, 6, 1), role: 1),
            RegionSpec(name: "map", origin: SIMD3(50, 0, 0), size: SIMD3(30, 30, 10), countLo: 4, countHi: 4096),
            RegionSpec(name: "inter", origin: SIMD3(50, 40, 0), size: SIMD3(30, 10, 10), sign: "inh"),
            RegionSpec(name: "out", origin: SIMD3(100, 0, 0), size: SIMD3(5, 30, 10), fixed: true,
                       labels: [[0.5, 0.25, 0.5], [0.5, 0.75, 0.5]], role: 2),
        ]
        p.projections = [ProjectionSpec(src: "sensor", dst: "map"), ProjectionSpec(src: "map", dst: "map"),
                         ProjectionSpec(src: "map", dst: "inter"), ProjectionSpec(src: "inter", dst: "map"),
                         ProjectionSpec(src: "map", dst: "out")]
        return p
    }
}

// MARK: Geometry, stages, checkpoints, roadmap

struct GeometryParam: Identifiable { var id: String { name }; let name: String; let kind: String; let def: JSONValue }
struct GeometryType: Identifiable { var id: String { type }; let type: String; let params: [GeometryParam] }

struct GeometryItem: Identifiable, Equatable {
    var id = UUID()
    var name: String
    var spec: JSONValue
    var visible = true
    var preview: [SIMD3<Float>] = []
    var lo: SIMD3<Float> = .zero, hi: SIMD3<Float> = .zero
    var error: String?
}

struct StageInfo: Identifiable { var id: String { name }; let name: String; let task: String; let available: Bool; let doc: String; let params: [(String, JSONValue)] }

struct Checkpoint: Identifiable { let id = UUID(); let label: String; let path: String; let neurons: Int; let synapses: Int; let regions: [String] }

struct TaskCap: Identifiable { var id: String { task + name }; let task: String; let name: String; let available: Bool }

struct LogLine: Identifiable { let id = UUID(); let date = Date(); let text: String; let error: Bool }

enum Section: String, CaseIterable, Identifiable {
    case project = "Project", geometry = "Geometry", fields = "Fields", plan = "Body plan", genome = "Genome",
         schedule = "Schedule", development = "Development", network = "Network", simulation = "Simulation",
         plasticity = "Plasticity", evolution = "Evolution", modules = "Modules", cost = "Cost", analysis = "Analysis",
         roadmap = "Roadmap status"
    var id: String { rawValue }
    var icon: String {
        switch self {
        case .project: return "doc.text"
        case .geometry: return "cube.transparent"
        case .fields: return "paintbrush.pointed"
        case .plan: return "square.grid.3x3.square"
        case .genome: return "allergens"
        case .schedule: return "list.number"
        case .development: return "leaf"
        case .network: return "point.3.connected.trianglepath.dotted"
        case .simulation: return "waveform.path.ecg"
        case .plasticity: return "arrow.triangle.2.circlepath"
        case .evolution: return "tortoise"
        case .modules: return "shippingbox"
        case .cost: return "gauge.with.dots.needle.33percent"
        case .analysis: return "chart.xyaxis.line"
        case .roadmap: return "checklist"
        }
    }
    /// Roadmap tasks this panel depends on (shown as badges / placeholders).
    var tasks: [String] {
        switch self {
        case .project: return ["A1"]
        case .geometry: return ["B1", "B2"]
        case .fields: return ["B3", "B4", "B5"]
        case .schedule: return ["A3", "A4"]
        case .development: return ["A4", "A5"]
        case .plasticity: return ["E1"]
        case .evolution: return ["E2", "E3"]
        case .modules: return ["G1"]
        case .cost: return ["D3"]
        case .analysis: return ["E4"]
        default: return []
        }
    }
}

enum ColorMode: String, CaseIterable, Identifiable {
    case region = "Region", sign = "Exc / Inh", role = "Role", mode = "Driver", threshold = "Threshold", activity = "Firing rate"
    var id: String { rawValue }
}

enum SynapseDisplay: String, CaseIterable, Identifiable {
    case none = "None", selected = "Selected", all = "All"
    var id: String { rawValue }
}

enum Tool: String, CaseIterable, Identifiable {
    case select = "Select", add = "Add neuron", connect = "Connect", stimulate = "Stimulate"
    var id: String { rawValue }
    var icon: String {
        switch self {
        case .select: return "cursorarrow"
        case .add: return "plus.circle"
        case .connect: return "arrow.right.circle"
        case .stimulate: return "bolt.circle"
        }
    }
    var help: String {
        switch self {
        case .select: return "Click a neuron to select it (shift-click: add to selection). Drag to orbit."
        case .add: return "Click on the cyan placement plane to add a neuron there (set the plane in Network → Draw by hand)."
        case .connect: return "Click a target: synapses from every selected neuron to it (weight and delay from the Network panel)."
        case .stimulate: return "Click a neuron to inject a current pulse (option-click works with every tool)."
        }
    }
}

/// Categorical colours (validated for contrast on the dark background).
let palette: [SIMD4<Float>] = [
    SIMD4(0.33, 0.62, 0.98, 1), SIMD4(0.98, 0.55, 0.24, 1), SIMD4(0.35, 0.80, 0.45, 1), SIMD4(0.89, 0.36, 0.50, 1),
    SIMD4(0.70, 0.52, 0.96, 1), SIMD4(0.95, 0.80, 0.30, 1), SIMD4(0.30, 0.80, 0.82, 1), SIMD4(0.80, 0.62, 0.48, 1),
    SIMD4(0.62, 0.68, 0.75, 1), SIMD4(0.55, 0.85, 0.20, 1),
]

func paletteColor(_ i: Int) -> SIMD4<Float> { i < 0 ? SIMD4(0.62, 0.66, 0.72, 1) : palette[i % palette.count] }

extension SIMD4 where Scalar == Float {
    var swiftUI: Color { Color(red: Double(x), green: Double(y), blue: Double(z)) }
}

/// Colour map for scalars in [0, 1] (dark blue → teal → yellow).
func heat(_ t: Float) -> SIMD4<Float> {
    let x = max(0, min(1, t))
    let a = SIMD3<Float>(0.18, 0.20, 0.55), b = SIMD3<Float>(0.15, 0.70, 0.70), c = SIMD3<Float>(0.99, 0.88, 0.25)
    let rgb = x < 0.5 ? a + (b - a) * (x * 2) : b + (c - b) * ((x - 0.5) * 2)
    return SIMD4(rgb, 1)
}
