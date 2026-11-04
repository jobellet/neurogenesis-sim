using Neurogenesis.Core.Bridge;
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
    public async Task HeadlessAction_GeneratePreset_TransmitsValuesAndLoadsNetwork()
    {
        var vm = new MainViewModel();
        if (vm.Bridge != null)
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(20));
            while (!vm.Bridge.IsReady && !cts.IsCancellationRequested)
            {
                await Task.Delay(50);
            }
        }

        Assert.True(vm.Bridge?.IsReady == true, "Bridge must be ready for generation test");
        vm.GenerateMorphology = "column";
        vm.GenerateNeurons = 60m;
        vm.GenerateSeed = 84m;

        await vm.GeneratePresetAsync();

        Assert.NotNull(vm.Scene);
        Assert.Equal(60, vm.Scene.Network.NeuronCount);
        Assert.True(vm.Scene.Network.SynapseCount > 0);
        Assert.True(File.Exists(vm.CurrentNetworkPath));
        Assert.Null(vm.LastError);
    }

    [Fact]
    public async Task HeadlessAction_GeneratePreset_ValidatesNeuronBounds()
    {
        var vm = new MainViewModel();

        // Bound min test: 0
        vm.GenerateNeurons = 0m;
        await vm.GeneratePresetAsync();
        Assert.Contains("at least 1", vm.Status);
        Assert.Equal(vm.Status, vm.LastError);

        // Bound max test: > 1,000,000
        vm.GenerateNeurons = 1500000m;
        await vm.GeneratePresetAsync();
        Assert.Contains("cannot exceed 1,000,000", vm.Status);
        Assert.Equal(vm.Status, vm.LastError);
    }

    [Fact]
    public async Task HeadlessAction_GeneratePreset_SurfacesBridgeRefusalOrError()
    {
        var vm = new MainViewModel();
        if (vm.Bridge != null)
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(20));
            while (!vm.Bridge.IsReady && !cts.IsCancellationRequested)
            {
                await Task.Delay(50);
            }
        }
        Assert.True(vm.Bridge?.IsReady == true, "Bridge must be ready");

        // Request 500,000 neurons to trigger bridge memory ResourceError
        await vm.GeneratePresetAsync("column", 500000, 42);
        Assert.NotNull(vm.LastError);
        Assert.True(vm.LastError.Contains("ResourceError") || vm.LastError.Contains("memory"), $"Expected memory refusal message, got: {vm.LastError}");
        Assert.Contains(vm.LastError, vm.Status);
    }

    [Fact]
    public async Task HeadlessAction_SimulateRemote_ValidatesTicksBound()
    {
        var vm = new MainViewModel();
        vm.RemoteTicks = 0m;
        await vm.SimulateRemoteAsync();
        Assert.Contains("at least 1", vm.Status);
        Assert.Equal(vm.Status, vm.LastError);
    }

    [Fact]
    public async Task HeadlessAction_SimulateRemote_TransmitsValuesAndVisualizesSpikesInScene()
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

        Assert.True(vm.Bridge?.IsReady == true, $"Bridge readiness failed. Status: {vm.Status}");
        Assert.True(vm.CanSimulateRemote, $"CanSimulateRemote failed. Status: {vm.Status}");

        vm.RemoteModel = "lif_int";
        vm.RemoteTicks = 120m;
        vm.RemoteSeed = 9999m;

        await vm.SimulateRemoteAsync();

        Assert.Equal(120f, vm.CurrentTick);
        Assert.Contains("Remote sim complete: 120 ticks", vm.Status);
        Assert.True(vm.RemoteTotalSpikes > 0, "Spikes should be produced by simulation");
        Assert.Equal(vm.RemoteTotalSpikes, vm.RemoteSpikes.Count);

        // Verify scene instances buffer has 9 floats per neuron and contains spike timestamps
        Assert.NotNull(vm.Instances);
        Assert.Equal(vm.Scene!.Network.NeuronCount * 9, vm.Instances.Length);

        // Stride 9, offset 8 is lastSpike. At least one spiking neuron must have lastSpike >= 0
        bool foundSpikeInInstances = false;
        for (int i = 0; i < vm.Scene.Network.NeuronCount; i++)
        {
            float ls = vm.Instances[i * 9 + 8];
            if (ls >= 0f)
            {
                foundSpikeInInstances = true;
                break;
            }
        }
        Assert.True(foundSpikeInInstances, "Instances buffer must contain spike timestamps for 3D flash visualization");
    }

    [Fact]
    public async Task HeadlessAction_SimulateRemote_SurfacesBridgeErrorMessageOnInvalidModel()
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
        Assert.True(vm.Bridge?.IsReady == true, "Bridge must be ready");

        await vm.SimulateRemoteAsync("non_existent_model_abc", 50, 1);
        Assert.NotNull(vm.LastError);
        Assert.Contains("non_existent_model_abc", vm.LastError);
        Assert.Equal(vm.LastError, vm.Status);
    }

    [Fact]
    public void FormatProgress_FormatsReadableLabelsAndHandlesAbsentFields()
    {
        // 1. Percentage
        using var docPct = System.Text.Json.JsonDocument.Parse("{\"percent\": 45.2}");
        Assert.Equal("Job #1 — 45%", MainViewModel.FormatProgress(1, docPct.RootElement));

        // 2. Step and Total
        using var docStep = System.Text.Json.JsonDocument.Parse("{\"step\": 3, \"total\": 10}");
        Assert.Equal("Job #1 — Step 3/10 (30%)", MainViewModel.FormatProgress(1, docStep.RootElement));

        // 3. Generation with best
        using var docGen = System.Text.Json.JsonDocument.Parse("{\"generation\": 4, \"best\": -0.85, \"gens\": 10}");
        Assert.Equal("Job #2 — Gen 5/10 (50%) (best: -0.85)", MainViewModel.FormatProgress(2, docGen.RootElement));

        // 4. Message / status
        using var docMsg = System.Text.Json.JsonDocument.Parse("{\"status\": \"Growing axons\"}");
        Assert.Equal("Job #3 — Growing axons", MainViewModel.FormatProgress(3, docMsg.RootElement));

        // 5. Empty object (fields absent)
        using var docEmpty = System.Text.Json.JsonDocument.Parse("{}");
        Assert.Equal("Job #4 — In progress", MainViewModel.FormatProgress(4, docEmpty.RootElement));

        // 6. Primitive / null (fields absent)
        using var docNull = System.Text.Json.JsonDocument.Parse("null");
        Assert.Equal("Job #5 — In progress", MainViewModel.FormatProgress(5, docNull.RootElement));
    }
    [Fact]
    public void FormatProgress_UsesFallbackTotalWhenGensAbsentFromProgressPayload()
    {
        // Bridge evolve progress event: {"generation": 2, "best": -0.42} without "gens"
        using var doc = System.Text.Json.JsonDocument.Parse("{\"generation\": 2, \"best\": -0.42}");

        // When fallbackTotal is passed (from active request parameters "gens")
        string formattedWithFallback = MainViewModel.FormatProgress(1, doc.RootElement, fallbackTotal: 10);
        Assert.Equal("Job #1 — Gen 3/10 (30%) (best: -0.42)", formattedWithFallback);

        // When fallbackTotal is not available
        string formattedWithoutFallback = MainViewModel.FormatProgress(1, doc.RootElement);
        Assert.Equal("Job #1 — Generation 3 (best: -0.42)", formattedWithoutFallback);
    }

    [Fact]
    public async Task BridgeClient_TracksRequestParametersAndSurfacesGetRequestParameters()
    {
        string python = PythonFixtures.Python;
        string repo = PythonFixtures.RepoRoot();

        await using var client = new BridgeClient(python, repo);
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        await client.StartAsync(cts.Token);

        Assert.Null(client.GetRequestParameters(99999));
    }
}
