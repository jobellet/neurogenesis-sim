import Foundation

struct BridgeError: LocalizedError {
    let message: String
    var trace: String = ""
    var isResource = false
    var errorDescription: String? { message }
}

/// The Python toolbox, as a child process speaking JSON lines: `python -m neurogenesis.bridge`
/// (desktop/common/PROTOCOL.md). Calls are async; long jobs send progress events. Started lazily, restarted if it dies.
final class Bridge {
    private var process: Process?
    private var stdin: FileHandle?
    private var buffer = Data()
    private var nextId = 1
    private var pending: [Int: (Result<Any, Error>) -> Void] = [:]
    private let q = DispatchQueue(label: "bridge")
    private var readyWaiters: [() -> Void] = []
    private(set) var ready = false

    var onProgress: ((Int, [String: Any]) -> Void)?
    var onLog: ((String) -> Void)?
    var onStatus: ((String) -> Void)?

    var python: String
    var repo: String
    static let protocolVersion = "1.0"

    init(python: String, repo: String) {
        self.python = python; self.repo = repo
    }

    func start() {
        q.async { self.launch() }
    }

    func restart(python: String? = nil, repo: String? = nil) {
        q.async {
            if let p = python { self.python = p }
            if let r = repo { self.repo = r }
            self.process?.terminate()
            self.process = nil
            self.launch()
        }
    }

    private func launch() {
        guard process == nil else { return }
        ready = false
        let p = Process()
        p.executableURL = URL(fileURLWithPath: python)
        p.arguments = ["-u", "-m", "neurogenesis.bridge"]
        var env = ProcessInfo.processInfo.environment
        if !repo.isEmpty {                      // a source checkout takes precedence over an installed toolbox
            env["PYTHONPATH"] = repo + (env["PYTHONPATH"].map { ":" + $0 } ?? "")
        }
        env["JAX_PLATFORMS"] = "cpu"
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        p.environment = env
        p.currentDirectoryURL = URL(fileURLWithPath: repo.isEmpty ? NSTemporaryDirectory() : repo)
        let inPipe = Pipe(), outPipe = Pipe(), errPipe = Pipe()
        p.standardInput = inPipe; p.standardOutput = outPipe; p.standardError = errPipe
        outPipe.fileHandleForReading.readabilityHandler = { [weak self] h in
            let d = h.availableData
            self?.q.async { self?.consume(d) }
        }
        errPipe.fileHandleForReading.readabilityHandler = { [weak self] h in
            let d = h.availableData
            if !d.isEmpty, let s = String(data: d, encoding: .utf8) { DispatchQueue.main.async { self?.onLog?(s) } }
        }
        p.terminationHandler = { [weak self] proc in
            self?.q.async {
                guard let self, self.process === proc else { return }
                self.process = nil; self.ready = false
                let waiting = self.pending; self.pending.removeAll()
                for (_, cb) in waiting { cb(.failure(BridgeError(message: "the Python bridge stopped (exit \(proc.terminationStatus))"))) }
                DispatchQueue.main.async { self.onStatus?("Python stopped (exit \(proc.terminationStatus))") }
            }
        }
        do {
            try p.run()
            process = p; stdin = inPipe.fileHandleForWriting
            DispatchQueue.main.async { self.onStatus?("starting Python…") }
        } catch {
            DispatchQueue.main.async { self.onStatus?("cannot start \(self.python): \(error.localizedDescription)") }
        }
    }

    private func consume(_ d: Data) {
        if d.isEmpty { return }
        buffer.append(d)
        while let nl = buffer.firstIndex(of: 0x0A) {
            let line = buffer.subdata(in: buffer.startIndex..<nl)
            buffer.removeSubrange(buffer.startIndex...nl)
            guard let obj = try? JSONSerialization.jsonObject(with: line) as? [String: Any] else { continue }
            if let ev = obj["event"] as? String {
                if ev == "ready" {
                    ready = true
                    let proto = (obj["data"] as? [String: Any])?["protocol"] as? String ?? "?"
                    if proto.split(separator: ".").first != Bridge.protocolVersion.split(separator: ".").first {
                        DispatchQueue.main.async { self.onLog?("bridge protocol \(proto), app expects \(Bridge.protocolVersion): some features may fail") }
                    }
                    let w = readyWaiters; readyWaiters.removeAll(); w.forEach { $0() }
                    DispatchQueue.main.async { self.onStatus?("Python ready") }
                } else if ev == "progress", let job = obj["job"] as? Int {
                    let data = obj["data"] as? [String: Any] ?? [:]
                    DispatchQueue.main.async { self.onProgress?(job, data) }
                }
                continue
            }
            guard let id = obj["id"] as? Int, let cb = pending.removeValue(forKey: id) else { continue }
            if let err = obj["error"] as? String {
                cb(.failure(BridgeError(message: err.replacingOccurrences(of: "ResourceError: ", with: ""),
                                        trace: obj["trace"] as? String ?? "", isResource: obj["kind"] as? String == "resource")))
            } else {
                cb(.success(obj["result"] ?? NSNull()))
            }
        }
    }

    /// Calls a bridge method; returns its JSON result. jobId receives the request id (for progress events).
    func call(_ method: String, _ params: [String: Any] = [:], jobId: ((Int) -> Void)? = nil) async throws -> Any {
        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Any, Error>) in
            q.async {
                if self.process == nil { self.launch() }
                let send = {
                    let id = self.nextId; self.nextId += 1
                    self.pending[id] = { cont.resume(with: $0) }
                    jobId?(id)
                    do {
                        var line = try JSONSerialization.data(withJSONObject: ["id": id, "method": method, "params": params])
                        line.append(0x0A)
                        try self.stdin?.write(contentsOf: line)
                    } catch {
                        self.pending.removeValue(forKey: id)
                        cont.resume(throwing: error)
                    }
                }
                if self.ready { send() } else { self.readyWaiters.append(send) }
            }
        }
    }

    func dict(_ method: String, _ params: [String: Any] = [:], jobId: ((Int) -> Void)? = nil) async throws -> [String: Any] {
        let r = try await call(method, params, jobId: jobId)
        guard let d = r as? [String: Any] else { throw BridgeError(message: "\(method): unexpected reply") }
        return d
    }

    func stop() {
        q.sync { process?.terminate(); process = nil }
    }
}
