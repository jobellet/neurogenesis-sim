using Avalonia;
using Avalonia.Headless;
using Neurogenesis.Tests;

[assembly: AvaloniaTestApplication(typeof(TestAppBuilder))]

namespace Neurogenesis.Tests;

public static class TestAppBuilder
{
    public static AppBuilder BuildAvaloniaApp() =>
        AppBuilder.Configure<Neurogenesis.App.App>()
            .UseHeadless(new AvaloniaHeadlessPlatformOptions());
}
