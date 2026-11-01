import Darwin
import Foundation
import Metal

/// What this Mac can hold, measured when asked (memory changes as other apps run).
struct MachineResources {
    let physical: UInt64          // installed RAM
    let available: UInt64         // free + inactive + purgeable + speculative pages: what can be used without swapping
    let cores: Int
    let gpuName: String
    let gpuWorkingSet: UInt64     // Metal's recommended maximum working set

    static func current() -> MachineResources {
        let dev = MTLCreateSystemDefaultDevice()
        return MachineResources(physical: ProcessInfo.processInfo.physicalMemory, available: availableMemory(),
                                cores: ProcessInfo.processInfo.activeProcessorCount, gpuName: dev?.name ?? "none",
                                gpuWorkingSet: dev?.recommendedMaxWorkingSetSize ?? 0)
    }

    static func availableMemory() -> UInt64 {
        var stats = vm_statistics64()
        var count = mach_msg_type_number_t(MemoryLayout<vm_statistics64>.size / MemoryLayout<integer_t>.size)
        let ok = withUnsafeMutablePointer(to: &stats) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) { host_statistics64(mach_host_self(), HOST_VM_INFO64, $0, &count) }
        }
        guard ok == KERN_SUCCESS else { return ProcessInfo.processInfo.physicalMemory / 2 }
        let pages = UInt64(stats.free_count) + UInt64(stats.inactive_count) + UInt64(stats.purgeable_count) + UInt64(stats.speculative_count)
        return pages * UInt64(vm_kernel_page_size)
    }
}

func humanBytes(_ b: UInt64) -> String {
    ByteCountFormatter.string(fromByteCount: Int64(clamping: b), countStyle: .memory)
}

/// An action that cannot run on this machine; shown to the user in an alert.
struct ResourceError: LocalizedError {
    let action: String
    let message: String
    var errorDescription: String? { message }
}

/// Memory checks before heavy actions. An action may use at most `fraction` of the memory available right now (the
/// rest is left to macOS and the other apps), and never more than half the installed RAM.
enum ResourceGuard {
    static let fraction = 0.6

    /// Bytes the app needs to hold a network: model arrays, kernel state and CSR, GPU instances, drawn synapse lines
    /// (at most `drawnSynapses`), undo copies, and a copy during edits.
    static func networkBytes(neurons n: Int, synapses e: Int, drawnSynapses: Int) -> UInt64 {
        let perNeuron = 144 + 64 + 32 + 48         // Neuron struct, kernel arrays, instance, raster and colour maps
        let perSynapse = 16 + 12                   // Synapse struct, CSR entry
        let held = UInt64(n * perNeuron + e * perSynapse) * 3     // current, undo copy, copy while editing
        return held + UInt64(min(e, drawnSynapses) * 64)
    }

    static func check(_ bytes: UInt64, for action: String) throws {
        let m = MachineResources.current()
        let limit = min(UInt64(Double(m.available) * fraction), m.physical / 2)
        if bytes > limit {
            throw ResourceError(action: action, message: """
                \(action) needs about \(humanBytes(bytes)) of memory, but only \(humanBytes(m.available)) is free on this Mac \
                (\(humanBytes(m.physical)) installed; the app uses at most \(Int(fraction * 100)) % of free memory, so the \
                computer stays responsive). Make it smaller (fewer cells or synapses), or quit other apps and try again.
                """)
        }
    }

    static func checkNetwork(neurons: Int, synapses: Int, drawn: Int, action: String) throws {
        if neurons > 2_000_000 {
            throw ResourceError(action: action, message: "\(action): \(neurons) neurons is beyond what the interactive view and live kernel handle (2 million). Simulate it in Python instead, after checking its cost in the Cost panel.")
        }
        try check(networkBytes(neurons: neurons, synapses: synapses, drawnSynapses: drawn), for: action)
    }

    /// Neuron and synapse counts from an NGB1 header, without reading the file.
    static func ngbHeader(_ path: String) -> (Int, Int)? {
        guard let h = FileHandle(forReadingAtPath: path) else { return nil }
        defer { try? h.close() }
        guard let d = try? h.read(upToCount: 16), d.count == 16, String(data: d.prefix(4), encoding: .ascii) == "NGB1" else { return nil }
        let n = d.withUnsafeBytes { $0.loadUnaligned(fromByteOffset: 4, as: Int32.self) }
        let e = d.withUnsafeBytes { $0.loadUnaligned(fromByteOffset: 8, as: Int32.self) }
        return (Int(n), Int(e))
    }

    /// Parsing JSON takes about 12 times the file size (Foundation objects), plus the network itself.
    static func checkJSONFile(_ url: URL, action: String) throws {
        var bytes = (try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? UInt64) ?? 0
        let npz = url.deletingPathExtension().appendingPathExtension("npz")
        bytes += ((try? FileManager.default.attributesOfItem(atPath: npz.path)[.size] as? UInt64) ?? 0) * 4
        try check(bytes * 12, for: action)
    }
}
