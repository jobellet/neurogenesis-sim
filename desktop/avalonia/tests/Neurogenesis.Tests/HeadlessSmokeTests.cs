using Avalonia.Headless.XUnit;
using Neurogenesis.App.ViewModels;
using Neurogenesis.App.Views;
using Xunit;

namespace Neurogenesis.Tests;

public sealed class HeadlessSmokeTests
{
    [AvaloniaFact]
    public async Task MainWindow_OpenNgbAndSelectNeuron_PopulatesInspector()
    {
        var vm = new MainViewModel();
        var window = new MainWindow { DataContext = vm };
        window.Show();

        string fixture = PythonFixtures.File("column");
        await vm.OpenAsync(fixture);

        Assert.NotNull(vm.Scene);
        Assert.True(vm.Scene.Network.NeuronCount > 0);
        Assert.False(vm.HasSelection);

        vm.Select(0);

        Assert.True(vm.HasSelection);
        Assert.NotEmpty(vm.Inspector);
        Assert.Contains(vm.Inspector, row => row.Name == "compartment");
    }
}
