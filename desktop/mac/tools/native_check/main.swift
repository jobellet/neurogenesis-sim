import Foundation
import nglif

// Checks the Swift side of the native kernel on the golden fixtures: native_check <fixtures dir>.
// Networks are read with the app's own NGB1 reader (Network.readNGB) and run through NativeSim, as the app does.
let dir = URL(fileURLWithPath: CommandLine.arguments[1])
let manifest = try String(contentsOf: dir.appendingPathComponent("MANIFEST.txt"), encoding: .utf8)
var failures = 0, cases = 0
for line in manifest.split(separator: "\n") where !line.hasPrefix("#") {
    let f = line.split(separator: " ").map(String.init)
    guard f.count == 4, let ticks = Int(f[1]), let seed = UInt32(f[2]) else { continue }
    cases += 1
    let net = try Network.readNGB(dir.appendingPathComponent("\(f[0]).ngb"))
    let k = NativeSim(net, seed: seed)
    if f[3] != "-" {
        let d = try Data(contentsOf: dir.appendingPathComponent(f[3]))
        let ext = d.withUnsafeBytes { raw in (0..<net.neurons.count).map { raw.loadUnaligned(fromByteOffset: 4 * $0, as: Int32.self) } }
        ext.withUnsafeBufferPointer { nglif_set_external(k.sim, $0.baseAddress) }
    }
    var got: [Int32] = []
    var buf = [Int32](repeating: 0, count: max(net.neurons.count, 1))
    for t in 0..<ticks {
        let c = buf.withUnsafeMutableBufferPointer { nglif_step(k.sim, $0.baseAddress, Int32($0.count)) }
        for j in 0..<Int(c) { got.append(Int32(t)); got.append(buf[j]) }
    }
    let exp = try Data(contentsOf: dir.appendingPathComponent("\(f[0]).spikes.i32"))
    let want = exp.withUnsafeBytes { raw in (0..<exp.count / 4).map { raw.loadUnaligned(fromByteOffset: 4 * $0, as: Int32.self) } }
    if got == want { print("ok   \(f[0]): \(want.count / 2) spikes") } else { print("FAIL \(f[0]): \(got.count / 2) spikes, expected \(want.count / 2)"); failures += 1 }
}
print("\(cases) fixtures, \(failures) failures")
exit(failures == 0 && cases > 0 ? 0 : 1)
