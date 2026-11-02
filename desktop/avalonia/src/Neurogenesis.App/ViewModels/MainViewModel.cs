using System.Collections.ObjectModel;
using System.Diagnostics;
using CommunityToolkit.Mvvm.ComponentModel;
using Neurogenesis.Core.Bridge;
using Neurogenesis.Core.Ngb;
using Neurogenesis.Core.Scene;
using Neurogenesis.Core.Simulation;
using Neurogenesis.Core.Style;

namespace Neurogenesis.App.ViewModels;

public sealed record FieldRow(string Name, string Value);

/// <summary>State of the main window in Step 3: includes in-app simulation with nglif and bridge integration.</summary>
public sealed partial class MainViewModel : ObservableObject
{
    public VisualStyle Style { get; } = VisualStyle.Default;
    public IReadOnlyList<ColorMode> ColorModes => Style.ColorModes;
    public ObservableCollection<FieldRow> Inspector { get; } = new();
    public BridgeClient? Bridge { get; }

    [ObservableProperty] private string _status = "Open a network file (.ngb).";
    [ObservableProperty] private string _sceneNote = "";
    [ObservableProperty] private string _title = "Neurogenesis";
    [ObservableProperty] private ColorMode _colorMode;
    [ObservableProperty] private SceneData? _scene;
    [ObservableProperty] private float[] _instances = Array.Empty<float>();
    [ObservableProperty, NotifyPropertyChangedFor(nameof(HasSelection))] private int _selected = -1;
    [ObservableProperty] private float _currentTick = 0f;
    [ObservableProperty, NotifyPropertyChangedFor(nameof(SimButtonText))] private bool _isSimulating = false;
    [ObservableProperty, NotifyPropertyChangedFor(nameof(CanSimulateNative))] private bool _isModelNative = true;

    public bool HasSelection => Selected >= 0;
    public string SimButtonText => IsSimulating ? "Pause" : "Simulate";
    public bool CanSimulateNative => Scene != null && IsModelNative;

    private SimulationEngine? _simEngine;
    private long _lastUiUpdateTimestamp;

    public MainViewModel()
    {
        _colorMode = Style.ColorModes[0];
        try
        {
            string? py = PythonLocator.FindPython();
            if (!string.IsNullOrEmpty(py))
            {
                Bridge = new BridgeClient(py);
                _ = Task.Run(async () =>
                {
                    try
                    {
                        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
                        await Bridge.StartAsync(cts.Token);
                    }
                    catch
                    {
                        // Bridge startup is optional during initial launch
                    }
                });
            }
        }
        catch
        {
            // Python runtime not configured yet
        }
    }

    /// <summary>Reads an NGB1 file and builds its scene off the UI thread.</summary>
    public async Task OpenAsync(string path)
    {
        Status = $"Opening {Path.GetFileName(path)}…";
        try
        {
            var sw = Stopwatch.StartNew();
            var scene = await Task.Run(() => new SceneData(NgbFile.Read(path), Style));
            Selected = -1;
            _simEngine?.Dispose();
            _simEngine = null;
            IsSimulating = false;
            CurrentTick = 0f;
            Scene = scene;
            Title = $"Neurogenesis — {Path.GetFileName(path)}";
            Status = $"{scene.Network.NeuronCount:N0} neurons, {scene.Network.SynapseCount:N0} synapses " +
                     $"({sw.ElapsedMilliseconds} ms)";
        }
        catch (Exception e) when (e is IOException or InvalidDataException or UnauthorizedAccessException or OutOfMemoryException)
        {
            Status = $"Cannot open {Path.GetFileName(path)}: {e.Message}";
        }
    }

    /// <summary>Selects neuron <paramref name="neuron"/> (-1 for none) and shows its fields.</summary>
    public void Select(int neuron) => Selected = Scene is { } s && neuron < s.Network.NeuronCount ? neuron : -1;

    partial void OnSceneChanged(SceneData? value)
    {
        SceneNote = value?.Note ?? "";
        Refresh();
    }

    partial void OnColorModeChanged(ColorMode value) => Refresh();

    partial void OnSelectedChanged(int value)
    {
        Inspector.Clear();
        if (Scene is { } s && value >= 0)
            foreach (var (name, text) in s.Network.NeuronFields(value)) Inspector.Add(new FieldRow(name, text));
        Refresh();
    }

    public void StartSimulation()
    {
        if (Scene == null) return;
        if (!IsModelNative)
        {
            Status = "Live in-app simulation requires a native model (schema native: true).";
            return;
        }

        if (_simEngine == null)
        {
            _simEngine = new SimulationEngine(Scene.Network);
            _simEngine.FrameStepped += OnSimStep;
        }
        _simEngine.Start();
        IsSimulating = true;
    }

    public void StopSimulation()
    {
        _simEngine?.Stop();
        IsSimulating = false;
        UpdateSimUi();
    }

    public void StepSimulation()
    {
        if (Scene == null) return;
        if (!IsModelNative)
        {
            Status = "Live in-app simulation requires a native model (schema native: true).";
            return;
        }

        if (_simEngine == null)
        {
            _simEngine = new SimulationEngine(Scene.Network);
            _simEngine.FrameStepped += OnSimStep;
        }
        _simEngine.StepOnce();
        UpdateSimUi();
    }

    private void OnSimStep()
    {
        if (_simEngine == null || Scene == null) return;

        // Throttle UI rendering and instance array allocations to ~60 Hz
        long now = Stopwatch.GetTimestamp();
        if (Stopwatch.GetElapsedTime(_lastUiUpdateTimestamp, now).TotalMilliseconds < 16.0) return;
        _lastUiUpdateTimestamp = now;

        Avalonia.Threading.Dispatcher.UIThread.Post(UpdateSimUi);
    }

    private void UpdateSimUi()
    {
        if (_simEngine == null || Scene == null) return;
        CurrentTick = (float)_simEngine.CurrentTick;
        Instances = Scene.Instances(ColorMode, Selected, _simEngine.LastSpikeSnapshot);
        Status = $"Tick {_simEngine.CurrentTick:N0} — Spikes {_simEngine.TotalSpikes:N0}";
    }

    private void Refresh() => Instances = Scene?.Instances(ColorMode, Selected, _simEngine?.LastSpikeSnapshot) ?? Array.Empty<float>();
}
