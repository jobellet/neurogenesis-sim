using System.Diagnostics;
using System.Text.Json;

namespace Neurogenesis.Tests;

/// <summary>NGB1 files written by the Python toolbox (neurogenesis/bridge/ngb.py) through make_ngb_fixtures.py.
/// NG_NGB_FIXTURES names a directory that already holds them (CI); otherwise they are generated once per run with
/// NG_PYTHON (default "python"), which needs numpy and the toolbox (pip install -e .). A missing Python fails the
/// tests: they are never skipped.</summary>
public static class PythonFixtures
{
    private static readonly Lazy<string> Directory_ = new(Make);

    public static string Dir => Directory_.Value;
    public static string File(string name) => Path.Combine(Dir, name + ".ngb");

    public static JsonElement Expected(string name)
    {
        using var doc = JsonDocument.Parse(System.IO.File.ReadAllText(Path.Combine(Dir, "expected.json")));
        return doc.RootElement.GetProperty(name).Clone();
    }

    /// <summary>The repository root (the folder holding neurogenesis/bridge), found upwards from the test binaries.</summary>
    public static string RepoRoot()
    {
        for (var d = new DirectoryInfo(AppContext.BaseDirectory); d is not null; d = d.Parent)
            if (Directory.Exists(Path.Combine(d.FullName, "neurogenesis", "bridge"))) return d.FullName;
        throw new DirectoryNotFoundException("repository root (neurogenesis/bridge) not found above " + AppContext.BaseDirectory);
    }

    public static string Python => Environment.GetEnvironmentVariable("NG_PYTHON") is { Length: > 0 } p ? p : "python";

    private static string Make()
    {
        if (Environment.GetEnvironmentVariable("NG_NGB_FIXTURES") is { Length: > 0 } given) return given;
        string dir = Path.Combine(Path.GetTempPath(), $"ng-ngb-fixtures-{Environment.ProcessId}");
        var psi = new ProcessStartInfo(Python)
        {
            RedirectStandardError = true,
            RedirectStandardOutput = true,
            UseShellExecute = false,
        };
        psi.ArgumentList.Add(Path.Combine(AppContext.BaseDirectory, "make_ngb_fixtures.py"));
        psi.ArgumentList.Add(dir);
        psi.Environment["PYTHONPATH"] = RepoRoot();
        psi.Environment["JAX_PLATFORMS"] = "cpu";
        using var p = Process.Start(psi) ?? throw new InvalidOperationException($"cannot start {Python}");
        string err = p.StandardError.ReadToEnd();
        p.WaitForExit();
        if (p.ExitCode != 0)
            throw new InvalidOperationException(
                $"make_ngb_fixtures.py failed with {Python} (set NG_PYTHON to a Python with numpy and the toolbox): {err}");
        return dir;
    }
}
