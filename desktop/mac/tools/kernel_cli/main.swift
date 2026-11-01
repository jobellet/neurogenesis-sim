import Foundation

// Equivalence harness: kernel_cli <network.ngb> <ticks> [ext.bin] prints "tick neuron" for every spike.
// ext.bin: int32 per neuron, added every tick (as jax_backend.tick(ext_current)).
let args = CommandLine.arguments
let net = try Network.readNGB(URL(fileURLWithPath: args[1]))
let ticks = Int(args[2])!
var ext: [Int32]? = nil
if args.count > 3 {
    let d = try Data(contentsOf: URL(fileURLWithPath: args[3]))
    ext = d.withUnsafeBytes { raw in (0..<net.neurons.count).map { raw.loadUnaligned(fromByteOffset: 4 * $0, as: Int32.self) } }
}
let k = LIFKernel(net)
var out = ""
for t in 0..<ticks {
    if let e = ext {
        e.withUnsafeBufferPointer { p in k.step(ext: p.baseAddress!) { out += "\(t) \($0)\n" } }
    } else {
        k.step { out += "\(t) \($0)\n" }
    }
}
FileHandle.standardOutput.write(out.data(using: .utf8)!)
