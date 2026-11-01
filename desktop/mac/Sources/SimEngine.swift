import Foundation

/// Runs the native kernel on its own thread, at a chosen speed, and keeps what the views need: the last spike tick of
/// every neuron (3D flashes), a ring of recent spikes (raster), spikes per tick (rate trace) and an optional recording.
final class SimEngine {
    private let lock = NSLock()
    private var kernel: LIFKernel
    private var thread: Thread?

    private(set) var n: Int
    private(set) var lastSpike: UnsafeMutablePointer<Int32>
    private var ext: [Int32]
    private var pulse: [Int32]
    private var pulsePending = false
    private var extActive = false

    let ringTicks = 4096
    private var ring: [[Int32]]
    private var counts: [Int32]

    // controls (read by the sim thread)
    var running = false
    var ticksPerSecond: Double = 1000          // simulated ms per wall second; 0 = as fast as possible
    var seed: UInt32 = 12345

    // statistics (read by the UI)
    private(set) var tick = 0
    private(set) var totalSpikes = 0
    private(set) var measuredTPS: Double = 0

    // recording, for plasticity and export
    private(set) var recording = false
    private var recStart = 0
    private var recorded: [(Int32, Int32)] = []

    init(_ net: Network) {
        kernel = LIFKernel(net, seed: seed)
        n = net.neurons.count
        lastSpike = .allocate(capacity: max(n, 1))
        lastSpike.initialize(repeating: -100000, count: max(n, 1))
        ext = .init(repeating: 0, count: n); pulse = ext
        ring = .init(repeating: [], count: ringTicks)
        counts = .init(repeating: 0, count: ringTicks)
        let t = Thread { [weak self] in self?.loop() }
        t.name = "lif_int"
        t.qualityOfService = .userInteractive
        thread = t
        t.start()
    }

    deinit { thread?.cancel() }

    /// Replace the network (state reset).
    func load(_ net: Network) {
        lock.lock(); defer { lock.unlock() }
        kernel = LIFKernel(net, seed: seed)
        let old = lastSpike
        n = net.neurons.count
        lastSpike = .allocate(capacity: max(n, 1))
        lastSpike.initialize(repeating: -100000, count: max(n, 1))
        old.deallocate()
        ext = .init(repeating: 0, count: n); pulse = ext
        extActive = false; pulsePending = false
        ring = .init(repeating: [], count: ringTicks)
        counts = .init(repeating: 0, count: ringTicks)
        tick = 0; totalSpikes = 0
        recorded.removeAll(); recStart = 0
    }

    func setExternal(_ e: [Int32]) {
        lock.lock(); defer { lock.unlock() }
        if e.count == n { ext = e; extActive = e.contains { $0 != 0 } }
    }

    func inject(_ i: Int, current: Int32) {
        lock.lock(); defer { lock.unlock() }
        if i >= 0 && i < n { pulse[i] &+= current; pulsePending = true }
    }

    func step(_ k: Int) {
        lock.lock(); defer { lock.unlock() }
        for _ in 0..<k { advance() }
    }

    func startRecording() {
        lock.lock(); defer { lock.unlock() }
        recording = true; recStart = tick; recorded.removeAll()
    }

    /// Stops recording; returns (ticks, spike ticks relative to the start, neuron ids).
    func stopRecording() -> (Int, [Int32], [Int32]) {
        lock.lock(); defer { lock.unlock() }
        recording = false
        return (tick - recStart, recorded.map { $0.0 }, recorded.map { $0.1 })
    }

    private func advance() {
        let t = tick
        var spikes: [Int32] = []
        let ls = lastSpike
        let mark: (Int) -> Void = { i in
            ls[i] = Int32(truncatingIfNeeded: t)
            spikes.append(Int32(i))
        }
        if pulsePending {
            var cur = ext
            for i in 0..<n { cur[i] &+= pulse[i]; pulse[i] = 0 }
            pulsePending = false
            cur.withUnsafeBufferPointer { kernel.step(ext: $0.baseAddress, spiked: mark) }
        } else if extActive {
            ext.withUnsafeBufferPointer { kernel.step(ext: $0.baseAddress, spiked: mark) }
        } else {
            kernel.step(spiked: mark)
        }
        if recording, recorded.count < 5_000_000 {
            for i in spikes { recorded.append((Int32(t - recStart), i)) }
        }
        ring[t % ringTicks] = spikes
        counts[t % ringTicks] = Int32(spikes.count)
        totalSpikes += spikes.count
        tick += 1
    }

    private func loop() {
        var last = Date.timeIntervalSinceReferenceDate
        var budget = 0.0
        var measureT = last, measureTick = 0
        while !Thread.current.isCancelled {
            let now = Date.timeIntervalSinceReferenceDate
            let dt = now - last; last = now
            if running {
                lock.lock()
                if ticksPerSecond <= 0 {
                    let until = now + 0.003
                    while Date.timeIntervalSinceReferenceDate < until { for _ in 0..<8 { advance() } }
                } else {
                    budget = min(budget + dt * ticksPerSecond, ticksPerSecond * 0.1 + 1)
                    let k = Int(budget)
                    budget -= Double(k)
                    let until = now + 0.004
                    var done = 0
                    while done < k && Date.timeIntervalSinceReferenceDate < until { advance(); done += 1 }
                    if done < k { budget = 0 }
                }
                lock.unlock()
            } else {
                budget = 0
            }
            if now - measureT > 0.5 {
                measuredTPS = Double(tick - measureTick) / (now - measureT)
                measureT = now; measureTick = tick
            }
            usleep(running && ticksPerSecond <= 0 ? 200 : 2000)
        }
    }

    /// Copies the last-spike ticks into dst (count n) and returns the current tick.
    func snapshotLastSpike(into dst: UnsafeMutableRawPointer, capacity: Int) -> Int {
        lock.lock(); defer { lock.unlock() }
        memcpy(dst, lastSpike, 4 * min(n, capacity))
        return tick
    }

    /// Spikes of the last `window` ticks: (first tick, per-tick lists), and spike counts per tick.
    func recent(_ window: Int) -> (Int, [[Int32]], [Int32]) {
        lock.lock(); defer { lock.unlock() }
        let w = min(window, ringTicks, tick)
        let first = tick - w
        var lists: [[Int32]] = [], c: [Int32] = []
        lists.reserveCapacity(w); c.reserveCapacity(w)
        for t in first..<tick { lists.append(ring[t % ringTicks]); c.append(counts[t % ringTicks]) }
        return (first, lists, c)
    }

    /// Spike count per neuron over the last `window` ticks.
    func rates(_ window: Int) -> [Float] {
        let (_, lists, c) = recent(window)
        var r = [Float](repeating: 0, count: n)
        for l in lists { for i in l where Int(i) < n { r[Int(i)] += 1 } }
        let s = Float(max(c.count, 1)) / 1000
        return r.map { $0 / s }
    }
}
