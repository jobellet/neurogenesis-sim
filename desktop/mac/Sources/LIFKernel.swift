import Foundation

/// The integer leaky integrate-and-fire kernel (lif_int), bit for bit as neurogenesis/spiking/reference.py,
/// jax_backend.py and viz/src/sim/kernel.ts: bit-shift leak and synaptic decay, clamp to ±2048, per-neuron threshold,
/// reset to -256, absolute refractory period, xorshift32 Poisson drivers drawn in neuron-index order, intrinsic
/// bursters, and a 32-tick spike shift register for axonal delays. External currents are added to the synaptic current
/// before the tick, as jax_backend.tick(ext_current). tests/test_desktop_kernel.py checks the equivalence.
final class LIFKernel {
    let n: Int
    private(set) var tick: Int = 0
    var rng: UInt32

    var v: [Int32], iSyn: [Int32], bits: [UInt32], phase: [Int32], refr: [Int32]
    let shiftV: [Int32], shiftS: [Int32], mode: [Int32], period: [Int32], duty: [Int32], refractory: [Int32],
        threshold: [Int32], poissonThresh: [UInt32]
    let rowPtr: [Int32], col: [Int32], weight: [Int32], delay: [UInt32]

    init(_ net: Network, seed: UInt32 = 12345) {
        let ns = net.neurons
        n = ns.count
        rng = seed
        v = .init(repeating: 0, count: n); iSyn = v; phase = v; refr = v
        bits = .init(repeating: 0, count: n)
        shiftV = ns.map { $0.shiftV }; shiftS = ns.map { $0.shiftS }; mode = ns.map { $0.mode }
        period = ns.map { $0.burstPeriod }; duty = ns.map { $0.burstDuty }; refractory = ns.map { $0.refractory }
        threshold = ns.map { $0.threshold }
        poissonThresh = ns.map { UInt32(min(4294967295.0, max(0, ($0.poissonHz / 1000.0 * 4294967296.0).rounded(.towardZero)))) }
        // CSR by presynaptic neuron (synapses to or from unknown neurons are dropped, as jax_backend.pack)
        let syn = net.synapses.filter { $0.pre >= 0 && Int($0.pre) < ns.count && $0.post >= 0 && Int($0.post) < ns.count }
        var counts = [Int32](repeating: 0, count: n + 1)
        for s in syn { counts[Int(s.pre) + 1] += 1 }
        for i in 0..<n { counts[i + 1] += counts[i] }
        var fill = counts
        var c = [Int32](repeating: 0, count: syn.count), w = c
        var d = [UInt32](repeating: 0, count: syn.count)
        for s in syn {
            let k = Int(fill[Int(s.pre)]); fill[Int(s.pre)] += 1
            c[k] = s.post; w[k] = s.weight; d[k] = UInt32(max(0, min(31, s.delay)))
        }
        rowPtr = counts; col = c; weight = w; delay = d
    }

    @inline(__always) private static func decay(_ x: Int32, _ k: Int32) -> Int32 {
        if x > 0 { return x - max(1, x >> k) }
        if x < 0 { return x - min(-1, x >> k) }
        return x
    }

    /// One tick of 1 ms. ext: per-neuron current added to the synaptic current first (nil: none).
    /// Calls spiked(i) for every neuron that fires. Returns the number of spikes.
    @discardableResult
    func step(ext: UnsafePointer<Int32>? = nil, spiked: (Int) -> Void = { _ in }) -> Int {
        var count = 0
        v.withUnsafeMutableBufferPointer { v in
        iSyn.withUnsafeMutableBufferPointer { isyn in
        bits.withUnsafeMutableBufferPointer { bits in
        phase.withUnsafeMutableBufferPointer { phase in
        refr.withUnsafeMutableBufferPointer { refr in
            for i in 0..<n {
                var cur = isyn[i]
                if let ext { cur = cur &+ ext[i] }
                var vi = LIFKernel.decay(v[i], shiftV[i])
                cur = LIFKernel.decay(cur, shiftS[i])
                isyn[i] = cur
                vi += cur >> 2
                if vi > 2048 { vi = 2048 } else if vi < -2048 { vi = -2048 }
                let m = mode[i]
                if m == 1 {
                    rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5
                    if rng < poissonThresh[i] { vi = threshold[i] }
                } else if m == 2 {
                    let p = period[i] == 0 ? 200 : period[i]
                    let du = duty[i] == 0 ? 24 : duty[i]
                    let ph = (phase[i] + 1) % p
                    phase[i] = ph
                    if ph < du && (ph & 3) == 0 { vi = threshold[i] }
                }
                var s: UInt32 = vi >= threshold[i] ? 1 : 0
                if refr[i] > 0 {
                    refr[i] -= 1; s = 0; vi = -256
                }
                if s == 1 {
                    refr[i] = refractory[i]
                    v[i] = -256
                    count += 1
                    spiked(i)
                } else {
                    v[i] = vi
                }
                bits[i] = (bits[i] << 1) | s
            }
            rowPtr.withUnsafeBufferPointer { rp in
            col.withUnsafeBufferPointer { col in
            weight.withUnsafeBufferPointer { w in
            delay.withUnsafeBufferPointer { d in
                for i in 0..<n {
                    let bf = bits[i]
                    if bf == 0 { continue }
                    var k = Int(rp[i]); let end = Int(rp[i + 1])
                    while k < end {
                        if (bf >> d[k]) & 1 == 1 { isyn[Int(col[k])] = isyn[Int(col[k])] &+ w[k] }
                        k += 1
                    }
                }
            }}}}
        }}}}}
        tick += 1
        return count
    }
}
