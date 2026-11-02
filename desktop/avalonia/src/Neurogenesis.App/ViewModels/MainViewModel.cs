using System.Collections.ObjectModel;
using System.Diagnostics;
using CommunityToolkit.Mvvm.ComponentModel;
using Neurogenesis.Core.Bridge;
using Neurogenesis.Core.Ngb;
using Neurogenesis.Core.Scene;
using Neurogenesis.Core.Style;

namespace Neurogenesis.App.ViewModels;

public sealed record FieldRow(string Name, string Value);

/// <summary>State of the main window in Step 1/2: open network, scene, colour mode, inspector, and bridge.</summary>
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

    public bool HasSelection => Selected >= 0;

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

    private void Refresh() => Instances = Scene?.Instances(ColorMode, Selected) ?? Array.Empty<float>();
}
