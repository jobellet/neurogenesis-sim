using System.Diagnostics;
using System.Runtime.InteropServices;

namespace Neurogenesis.Core.Bridge;

/// <summary>
/// Locates the Python executable to run the bridge child process.
/// Resolution priority:
/// 1. NEUROGENESIS_PYTHON environment variable
/// 2. Bundled embedded Python (python-build-standalone in AppDir or runtime/)
/// 3. Path in settings / PATH python3 or python.
/// </summary>
public static class PythonLocator
{
    public static string FindPython()
    {
        // 1. NEUROGENESIS_PYTHON environment variable
        string? envPath = Environment.GetEnvironmentVariable("NEUROGENESIS_PYTHON");
        if (!string.IsNullOrWhiteSpace(envPath) && File.Exists(envPath))
        {
            return envPath;
        }

        string baseDir = AppContext.BaseDirectory;

        // 2. Bundled embedded Python
        string[] candidates;
        if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
        {
            candidates = new[]
            {
                Path.Combine(baseDir, "runtime", "python", "python.exe"),
                Path.Combine(baseDir, "python", "python.exe"),
                Path.Combine(baseDir, "..", "runtime", "python", "python.exe"),
                Path.Combine(baseDir, "..", "..", "runtime", "python", "python.exe")
            };
        }
        else
        {
            candidates = new[]
            {
                Path.Combine(baseDir, "runtime", "python", "bin", "python3"),
                Path.Combine(baseDir, "python", "bin", "python3"),
                Path.Combine(baseDir, "runtime", "python", "bin", "python"),
                Path.Combine(baseDir, "python", "bin", "python"),
                Path.Combine(baseDir, "..", "runtime", "python", "bin", "python3"),
                Path.Combine(baseDir, "..", "..", "runtime", "python", "bin", "python3")
            };
        }

        foreach (var c in candidates)
        {
            string full = Path.GetFullPath(c);
            if (File.Exists(full)) return full;
        }

        // 3. Fallback to system Python
        string sys = RuntimeInformation.IsOSPlatform(OSPlatform.Windows) ? "python.exe" : "python3";
        return sys;
    }
}
