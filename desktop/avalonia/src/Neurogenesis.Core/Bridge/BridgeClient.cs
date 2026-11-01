using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Neurogenesis.Core.Bridge;

public sealed class BridgeException : Exception
{
    public string? Trace { get; }
    public bool IsResource { get; }

    public BridgeException(string message, string? trace = null, bool isResource = false)
        : base(message)
    {
        Trace = trace;
        IsResource = isResource;
    }
}

/// <summary>
/// Child process speaking JSON-lines stdio protocol with `python -m neurogenesis.bridge` (desktop/common/PROTOCOL.md).
/// </summary>
public sealed class BridgeClient : IAsyncDisposable
{
    public const string ExpectedProtocolMajor = "1";

    public string PythonPath { get; set; }
    public string RepoRoot { get; set; }

    public event Action<string>? LogReceived;
    public event Action<string>? StatusChanged;
    public event Action<int, JsonElement>? ProgressReceived;
    public event Action<JsonElement>? ReadyReceived;

    private Process? _process;
    private StreamWriter? _stdin;
    private int _nextId = 1;
    private readonly Dictionary<int, TaskCompletionSource<JsonElement>> _pending = new();
    private readonly TaskCompletionSource<bool> _readyTcs = new();
    private readonly object _lock = new();

    public bool IsReady => _readyTcs.Task.IsCompletedSuccessfully;

    public BridgeClient(string pythonPath, string repoRoot)
    {
        PythonPath = pythonPath;
        RepoRoot = repoRoot;
    }

    public async Task StartAsync(CancellationToken ct = default)
    {
        lock (_lock)
        {
            if (_process != null) return;

            StatusChanged?.Invoke("Starting Python bridge…");

            var psi = new ProcessStartInfo(PythonPath)
            {
                Arguments = "-u -m neurogenesis.bridge",
                RedirectStandardInput = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true,
                WorkingDirectory = string.IsNullOrEmpty(RepoRoot) ? Path.GetTempPath() : RepoRoot
            };

            psi.Environment["JAX_PLATFORMS"] = "cpu";
            psi.Environment["PYTHONUNBUFFERED"] = "1";
            psi.Environment["PYTHONDONTWRITEBYTECODE"] = "1";
            if (!string.IsNullOrEmpty(RepoRoot))
            {
                string existing = Environment.GetEnvironmentVariable("PYTHONPATH") ?? "";
                psi.Environment["PYTHONPATH"] = string.IsNullOrEmpty(existing)
                    ? RepoRoot
                    : $"{RepoRoot}{Path.PathSeparator}{existing}";
            }

            _process = new Process { StartInfo = psi, EnableRaisingEvents = true };

            _process.OutputDataReceived += OnOutputData;
            _process.ErrorDataReceived += (s, e) =>
            {
                if (!string.IsNullOrEmpty(e.Data))
                {
                    LogReceived?.Invoke(e.Data);
                }
            };
            _process.Exited += (s, e) =>
            {
                int exitCode = _process?.ExitCode ?? -1;
                StatusChanged?.Invoke($"Python bridge exited (code {exitCode})");
                lock (_lock)
                {
                    foreach (var kv in _pending)
                    {
                        kv.Value.TrySetException(new BridgeException($"Python bridge exited unexpectedly (code {exitCode})"));
                    }
                    _pending.Clear();
                    _readyTcs.TrySetException(new BridgeException($"Python bridge exited before ready (code {exitCode})"));
                }
            };

            _process.Start();
            _process.BeginOutputReadLine();
            _process.BeginErrorReadLine();
            _stdin = _process.StandardInput;
        }

        using var reg = ct.Register(() => _readyTcs.TrySetCanceled(ct));
        await _readyTcs.Task.ConfigureAwait(false);
    }

    private void OnOutputData(object sender, DataReceivedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(e.Data)) return;

        try
        {
            using var doc = JsonDocument.Parse(e.Data);
            var root = doc.RootElement.Clone();

            if (root.TryGetProperty("event", out var evProp))
            {
                string ev = evProp.GetString()!;
                if (ev == "ready")
                {
                    var data = root.GetProperty("data");
                    string proto = data.TryGetProperty("protocol", out var p) ? p.GetString() ?? "?" : "?";
                    string major = proto.Split('.')[0];
                    if (major != ExpectedProtocolMajor)
                    {
                        LogReceived?.Invoke($"Warning: Bridge protocol {proto}, app expects major version {ExpectedProtocolMajor}");
                    }
                    StatusChanged?.Invoke("Python bridge ready");
                    ReadyReceived?.Invoke(data);
                    _readyTcs.TrySetResult(true);
                }
                else if (ev == "progress")
                {
                    int job = root.GetProperty("job").GetInt32();
                    var data = root.GetProperty("data");
                    ProgressReceived?.Invoke(job, data);
                }
                return;
            }

            if (root.TryGetProperty("id", out var idProp))
            {
                int id = idProp.GetInt32();
                TaskCompletionSource<JsonElement>? tcs;
                lock (_lock)
                {
                    _pending.Remove(id, out tcs);
                }

                if (tcs != null)
                {
                    if (root.TryGetProperty("error", out var errProp))
                    {
                        string err = errProp.GetString()!;
                        string? trace = root.TryGetProperty("trace", out var t) ? t.GetString() : null;
                        bool isResource = root.TryGetProperty("kind", out var k) && k.GetString() == "resource";
                        tcs.TrySetException(new BridgeException(err, trace, isResource));
                    }
                    else
                    {
                        var res = root.GetProperty("result");
                        tcs.TrySetResult(res);
                    }
                }
            }
        }
        catch (Exception ex)
        {
            LogReceived?.Invoke($"Failed to parse bridge line: {ex.Message}");
        }
    }

    public async Task<JsonElement> CallAsync(string method, JsonObject? parameters = null, CancellationToken ct = default)
    {
        if (!_readyTcs.Task.IsCompletedSuccessfully)
        {
            await _readyTcs.Task.ConfigureAwait(false);
        }

        int id;
        var tcs = new TaskCompletionSource<JsonElement>(TaskCreationOptions.RunContinuationsAsynchronously);

        lock (_lock)
        {
            id = _nextId++;
            _pending[id] = tcs;

            var req = new JsonObject
            {
                ["id"] = id,
                ["method"] = method
            };
            if (parameters != null)
            {
                req["params"] = parameters;
            }

            string line = req.ToJsonString();
            _stdin?.WriteLine(line);
        }

        using var reg = ct.Register(() =>
        {
            lock (_lock)
            {
                if (_pending.Remove(id))
                {
                    tcs.TrySetCanceled(ct);
                }
            }
        });

        return await tcs.Task.ConfigureAwait(false);
    }

    public ValueTask DisposeAsync()
    {
        Process? proc;
        lock (_lock)
        {
            proc = _process;
            _process = null;
        }

        if (proc != null)
        {
            try
            {
                if (!proc.HasExited)
                {
                    try { _stdin?.Close(); } catch { }
                    if (!proc.WaitForExit(1000))
                    {
                        proc.Kill(entireProcessTree: true);
                    }
                }
            }
            catch { }
            finally
            {
                proc.Dispose();
            }
        }
        return ValueTask.CompletedTask;
    }
}
