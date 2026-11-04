using Neurogenesis.App.ViewModels;
using Neurogenesis.Core.Ngb;
using Neurogenesis.Core.Simulation;
using Xunit;

namespace Neurogenesis.Tests;

public class SimulationEngineTests
{
    [Fact]
    public void StartStopRestart_IsSafeAndJoinsCleanly()
    {
        string path = Path.Combine(PythonFixtures.RepoRoot(), "desktop", "common", "fixtures", "column_saturated.ngb");
        var net = NgbFile.Read(path);
        using var engine = new SimulationEngine(net) { TicksPerSecond = 0 };

        engine.Start();
        Assert.True(engine.IsRunning);
        Thread.Sleep(50);

        engine.Stop();
        Assert.False(engine.IsRunning);
        long tickAfterFirstStop = engine.CurrentTick;
        Assert.True(tickAfterFirstStop > 0);

        // Immediate restart must not create duplicate worker loops
        engine.Start();
        Assert.True(engine.IsRunning);
        Thread.Sleep(50);

        engine.Stop();
        Assert.False(engine.IsRunning);
        Assert.True(engine.CurrentTick > tickAfterFirstStop);
    }

    [Fact]
    public void RecentSpikesRingWrap_ClampsAndDoesNotReturnStaleTicks()
    {
        string path = Path.Combine(PythonFixtures.RepoRoot(), "desktop", "common", "fixtures", "column_saturated.ngb");
        var net = NgbFile.Read(path);
        using var engine = new SimulationEngine(net);

        // Step past ring capacity (1000 ticks)
        for (int i = 0; i < 1200; i++)
        {
            engine.StepOnce();
        }

        Assert.Equal(1200, engine.CurrentTick);

        // Requesting 1500 ticks should clamp to ring capacity (1000)
        var spikes = engine.GetRecentSpikes(1500);
        Assert.NotEmpty(spikes);

        // Every spike event must be in range [1200 - 1000 + 1, 1200] = [201, 1200]
        foreach (var ev in spikes)
        {
            Assert.InRange(ev.Tick, 201, 1200);
        }

        // Requesting 100 ticks
        var recent100 = engine.GetRecentSpikes(100);
        foreach (var ev in recent100)
        {
            Assert.InRange(ev.Tick, 1101, 1200);
        }
    }

    [Fact]
    public async Task NonNativeModel_CannotSimulateInApp()
    {
        string path = Path.Combine(PythonFixtures.RepoRoot(), "desktop", "common", "fixtures", "column_saturated.ngb");
        var vm = new MainViewModel();
        await vm.OpenAsync(path);

        Assert.True(vm.CanSimulateNative);

        // Mark model as non-native (e.g. from schema native: false)
        vm.IsModelNative = false;
        Assert.False(vm.CanSimulateNative);

        vm.StartSimulation();
        Assert.False(vm.IsSimulating);
        Assert.Contains("requires a native model", vm.Status);

        vm.StepSimulation();
        Assert.Contains("requires a native model", vm.Status);
    }
    [Fact]
    public async Task HeadlessAction_GeneratePreset_CallsBridgeAndLoadsNetwork()
    {
        var vm = new MainViewModel();
        // Wait briefly if bridge is starting
        if (vm.Bridge != null)
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(20));
            while (!vm.Bridge.IsReady && !cts.IsCancellationRequested)
            {
                await Task.Delay(50);
            }
        }

        Assert.True(vm.Bridge?.IsReady == true, "Bridge must be ready for generation test");
        await vm.GeneratePresetAsync("column", 60, 42);

        Assert.NotNull(vm.Scene);
        Assert.Equal(60, vm.Scene.Network.NeuronCount);
        Assert.True(vm.Scene.Network.SynapseCount > 0);
        Assert.True(File.Exists(vm.CurrentNetworkPath));
    }

    [Fact]
    public async Task HeadlessAction_SimulateRemote_CallsBridgeSimulate()
    {
        string path = Path.Combine(PythonFixtures.RepoRoot(), "desktop", "common", "fixtures", "microcircuit.ngb");
        var vm = new MainViewModel();
        await vm.OpenAsync(path);

        if (vm.Bridge != null)
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(20));
            while ((!vm.Bridge.IsReady || !vm.CanSimulateRemote) && !cts.IsCancellationRequested)
            {
                await Task.Delay(50);
            }
        }

        Assert.True(vm.Bridge?.IsReady == true, $"Bridge readiness failed. Status: {vm.Status}, Note: {vm.SceneNote}");
        Assert.True(vm.CanSimulateRemote, $"CanSimulateRemote false. Scene: {vm.Scene != null}, IsBridgeReady: {vm.IsBridgeReady}, Status: {vm.Status}");

        await vm.SimulateRemoteAsync(ticks: 100, seed: 12345);

        Assert.Equal(100f, vm.CurrentTick);
        Assert.Contains("Remote sim complete: 100 ticks", vm.Status);
    }
}

