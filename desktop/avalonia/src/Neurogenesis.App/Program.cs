using Avalonia;

namespace Neurogenesis.App;

internal static class Program
{
    [STAThread]
    public static void Main(string[] args) => BuildAvaloniaApp().StartWithClassicDesktopLifetime(args);

    /// <summary>NG_GL=desktop makes Windows use WGL (desktop OpenGL, GLSL 3.30) instead of the default ANGLE
    /// (OpenGL ES 3.0, GLSL ES 3.00), to test both shader dialects on one machine.</summary>
    public static AppBuilder BuildAvaloniaApp()
    {
        var b = AppBuilder.Configure<App>().UsePlatformDetect().WithInterFont().LogToTrace();
        if (Environment.GetEnvironmentVariable("NG_GL") == "desktop")
            b = b.With(new Win32PlatformOptions { RenderingMode = new[] { Win32RenderingMode.Wgl } });
        return b;
    }
}
