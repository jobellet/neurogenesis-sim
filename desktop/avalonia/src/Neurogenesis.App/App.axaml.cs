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
            desktop.MainWindow = new MainWindow { DataContext = vm };
            if (desktop.Args is { Length: > 0 } args) _ = vm.OpenAsync(args[0]);
        }
        base.OnFrameworkInitializationCompleted();
    }
}
