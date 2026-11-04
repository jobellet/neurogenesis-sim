using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using Neurogenesis.App.ViewModels;
using Neurogenesis.App.Views;

namespace Neurogenesis.App;

public partial class App : Application
{
    public override void Initialize() => AvaloniaXamlLoader.Load(this);

    /// <summary>The first command-line argument, if any, is a network file to open.</summary>
    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            var vm = new MainViewModel();
            var win = new MainWindow { DataContext = vm };
            desktop.MainWindow = win;
            win.Closed += async (s, e) =>
            {
                if (vm.Bridge != null) await vm.Bridge.DisposeAsync();
            };
            if (desktop.Args is { Length: > 0 } args)
            {
                _ = vm.OpenAsync(args[0]);
                if (args.Contains("--open-generate"))
                {
                    Avalonia.Threading.Dispatcher.UIThread.Post(async () =>
                    {
                        await System.Threading.Tasks.Task.Delay(1200);
                        win.GeneratePresetButton.Flyout?.ShowAt(win.GeneratePresetButton);
                    });
                }
            }
        }
        base.OnFrameworkInitializationCompleted();
    }
}
