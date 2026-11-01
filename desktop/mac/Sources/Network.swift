import Foundation
import simd

/// One neuron, with the fields of neurogenesis.spiking.network.NeuronData.
struct Neuron {
    var pos: SIMD3<Double>
    var dir: SIMD3<Double> = SIMD3(0, 1, 0)
    var mode: Int32 = 0            // 0 LIF, 1 Poisson, 2 burster
    var shiftV: Int32 = 5
    var shiftS: Int32 = 4
    var baseWeight: Int32 = 180
    var burstPeriod: Int32 = 200
    var burstDuty: Int32 = 24
    var refractory: Int32 = 0
    var role: Int32 = 0            // 0 internal, 1 input, 2 output
    var compartment: Int32 = -1
    var threshold: Int32 = 1024
    var poissonHz: Double = 25.0
    var connRadius: Double = 28.0
    var connProb: Double = 0.38
}

struct Synapse: Hashable {
    var pre: Int32
    var post: Int32
    var weight: Int32
    var delay: Int32
}

/// A network as the toolbox's SNNNetwork, plus the region names of a grown body plan (compartment -> name).
struct Network {
    var morphology: String = "Empty"
    var neurons: [Neuron] = []
    var synapses: [Synapse] = []
    var regionNames: [String] = []

    var isEmpty: Bool { neurons.isEmpty }

    /// Excitatory unless its base weight or its outgoing weights are negative.
    func inhibitoryMask() -> [Bool] {
        var outSum = [Int64](repeating: 0, count: neurons.count)
        for s in synapses where Int(s.pre) < neurons.count { outSum[Int(s.pre)] += Int64(s.weight) }
        return neurons.indices.map { neurons[$0].baseWeight < 0 || outSum[$0] < 0 }
    }

    func bounds() -> (SIMD3<Float>, SIMD3<Float>) {
        guard let f = neurons.first else { return (SIMD3(-50, -50, -50), SIMD3(50, 50, 50)) }
        var lo = SIMD3<Float>(f.pos), hi = lo
        for n in neurons {
            let p = SIMD3<Float>(n.pos)
            lo = simd_min(lo, p); hi = simd_max(hi, p)
        }
        return (lo, hi)
    }

    func regionName(_ c: Int32) -> String {
        if c >= 0, Int(c) < regionNames.count { return regionNames[Int(c)] }
        return c < 0 ? "–" : "#\(c)"
    }

    // MARK: NGB1 binary exchange with the Python bridge (layout: desktop/common/PROTOCOL.md, section 6)

    static func readNGB(_ url: URL) throws -> Network {
        let data = try Data(contentsOf: url, options: .mappedIfSafe)
        return try data.withUnsafeBytes { (raw: UnsafeRawBufferPointer) -> Network in
            guard raw.count >= 16, String(bytes: raw[0..<4], encoding: .ascii) == "NGB1" else {
                throw NSError(domain: "NGB", code: 1, userInfo: [NSLocalizedDescriptionKey: "not an NGB1 file"])
            }
            let n = Int(raw.loadUnaligned(fromByteOffset: 4, as: Int32.self))
            let e = Int(raw.loadUnaligned(fromByteOffset: 8, as: Int32.self))
            var o = 16
            func f64(_ count: Int) -> [Double] {
                var a = [Double](repeating: 0, count: count)
                for k in 0..<count { a[k] = raw.loadUnaligned(fromByteOffset: o + 8 * k, as: Double.self) }
                o += 8 * count; return a
            }
            func i32(_ count: Int) -> [Int32] {
                var a = [Int32](repeating: 0, count: count)
                for k in 0..<count { a[k] = raw.loadUnaligned(fromByteOffset: o + 4 * k, as: Int32.self) }
                o += 4 * count; return a
            }
            let pos = f64(3 * n), dir = f64(3 * n)
            let mode = i32(n), sv = i32(n), ss = i32(n), bw = i32(n), bp = i32(n), bd = i32(n), rf = i32(n),
                role = i32(n), comp = i32(n), th = i32(n)
            let hz = f64(n), cr = f64(n), cp = f64(n)
            let pre = i32(e), post = i32(e), w = i32(e), d = i32(e)
            var net = Network()
            net.neurons.reserveCapacity(n)
            for i in 0..<n {
                net.neurons.append(Neuron(pos: SIMD3(pos[3 * i], pos[3 * i + 1], pos[3 * i + 2]),
                                          dir: SIMD3(dir[3 * i], dir[3 * i + 1], dir[3 * i + 2]),
                                          mode: mode[i], shiftV: sv[i], shiftS: ss[i], baseWeight: bw[i], burstPeriod: bp[i],
                                          burstDuty: bd[i], refractory: rf[i], role: role[i], compartment: comp[i],
                                          threshold: th[i], poissonHz: hz[i], connRadius: cr[i], connProb: cp[i]))
            }
            net.synapses = (0..<e).map { Synapse(pre: pre[$0], post: post[$0], weight: w[$0], delay: d[$0]) }
            return net
        }
    }

    func writeNGB(_ url: URL) throws {
        var d = Data()
        d.reserveCapacity(16 + neurons.count * 88 + synapses.count * 16)
        func put<T>(_ v: T) { withUnsafeBytes(of: v) { d.append(contentsOf: $0) } }
        d.append(contentsOf: Array("NGB1".utf8))
        put(Int32(neurons.count)); put(Int32(synapses.count)); put(Int32(0))
        for n in neurons { put(n.pos.x); put(n.pos.y); put(n.pos.z) }
        for n in neurons { put(n.dir.x); put(n.dir.y); put(n.dir.z) }
        let ints: [KeyPath<Neuron, Int32>] = [\.mode, \.shiftV, \.shiftS, \.baseWeight, \.burstPeriod, \.burstDuty,
                                              \.refractory, \.role, \.compartment, \.threshold]
        for k in ints { for n in neurons { put(n[keyPath: k]) } }
        let dbls: [KeyPath<Neuron, Double>] = [\.poissonHz, \.connRadius, \.connProb]
        for k in dbls { for n in neurons { put(n[keyPath: k]) } }
        for s in synapses { put(s.pre) }
        for s in synapses { put(s.post) }
        for s in synapses { put(s.weight) }
        for s in synapses { put(s.delay) }
        try d.write(to: url)
    }

    // MARK: Network JSON (the format of SNNNetwork.save_json and of the browser viewer)

    static func readJSON(_ url: URL) throws -> Network {
        let obj = try JSONSerialization.jsonObject(with: Data(contentsOf: url))
        guard let d = obj as? [String: Any] else { throw NSError(domain: "JSON", code: 1) }
        var net = Network()
        net.morphology = d["morphology"] as? String ?? "Custom"
        func dbl(_ x: Any?, _ def: Double) -> Double { (x as? NSNumber)?.doubleValue ?? def }
        func int(_ x: Any?, _ def: Int32) -> Int32 { (x as? NSNumber).map { Int32(truncatingIfNeeded: $0.intValue) } ?? def }
        for case let n as [String: Any] in d["neurons"] as? [Any] ?? [] {
            net.neurons.append(Neuron(pos: SIMD3(dbl(n["x"], 0), dbl(n["y"], 0), dbl(n["z"], 0)),
                                      dir: SIMD3(dbl(n["dirX"], 0), dbl(n["dirY"], 1), dbl(n["dirZ"], 0)),
                                      mode: int(n["mode"], 0), shiftV: int(n["shiftV"], 5), shiftS: int(n["shiftS"], 4),
                                      baseWeight: int(n["baseWeight"], 180), burstPeriod: int(n["burstPeriod"], 200),
                                      burstDuty: int(n["burstDuty"], 24), refractory: int(n["refractory"], 0),
                                      role: int(n["role"], 0), compartment: int(n["compartment"], -1),
                                      threshold: int(n["threshold"], 1024), poissonHz: dbl(n["poissonHz"], 25),
                                      connRadius: dbl(n["connRadius"], 28), connProb: dbl(n["connProb"], 0.38)))
        }
        for case let s as [String: Any] in d["synapses"] as? [Any] ?? [] {
            net.synapses.append(Synapse(pre: int(s["pre"], 0), post: int(s["post"], 0), weight: int(s["weight"], 0),
                                        delay: int(s["delay"], 1)))
        }
        if let names = (d["desktop"] as? [String: Any])?["regions"] as? [String] { net.regionNames = names }
        return net
    }

    func writeJSON(_ url: URL) throws {
        func r(_ x: Double, _ k: Double) -> Double { (x * k).rounded() / k }
        let ns: [[String: Any]] = neurons.enumerated().map { i, n in
            ["id": i, "x": r(n.pos.x, 100), "y": r(n.pos.y, 100), "z": r(n.pos.z, 100),
             "dirX": r(n.dir.x, 1000), "dirY": r(n.dir.y, 1000), "dirZ": r(n.dir.z, 1000), "mode": n.mode,
             "shiftV": n.shiftV, "shiftS": n.shiftS, "baseWeight": n.baseWeight, "connRadius": r(n.connRadius, 10),
             "connProb": r(n.connProb, 100), "burstPeriod": n.burstPeriod, "burstDuty": n.burstDuty,
             "poissonHz": r(n.poissonHz, 1e6), "refractory": n.refractory, "role": n.role, "compartment": n.compartment,
             "threshold": n.threshold]
        }
        let ss: [[String: Any]] = synapses.map { ["pre": $0.pre, "post": $0.post, "weight": $0.weight, "delay": $0.delay] }
        var d: [String: Any] = ["version": "1.0.0", "morphology": morphology, "numNeurons": neurons.count,
                                "numSynapses": synapses.count, "neurons": ns, "synapses": ss]
        if !regionNames.isEmpty { d["desktop"] = ["regions": regionNames] }
        try JSONSerialization.data(withJSONObject: d, options: [.prettyPrinted]).write(to: url)
    }
}
