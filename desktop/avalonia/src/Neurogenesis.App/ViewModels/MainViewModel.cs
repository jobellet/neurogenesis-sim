using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Text.Json.Nodes;
using CommunityToolkit.Mvvm.ComponentModel;
using Neurogenesis.Core.Ngb;
using Neurogenesis.Core.Project;
using Neurogenesis.Core.Scene;
using Neurogenesis.Core.Schema;
using Neurogenesis.Core.Simulation;
using Neurogenesis.Core.Style;

namespace Neurogenesis.App.ViewModels;

public sealed record FieldRow(string Name, string Value);

/// <summary>State of the main window: the open network, its scene, the colour mode, the inspector, and the project/schedule.</summary>
public sealed partial class MainViewModel : ObservableObject
{
    public VisualStyle Style { get; } = VisualStyle.Default;
    public IReadOnlyList<ColorMode> ColorModes => Style.ColorModes;
    public ObservableCollection<FieldRow> Inspector { get; } = new();

    public ProjectDocument Project { get; }
    public UiSchemaDocument? UiSchema { get; }

    [ObservableProperty] private string _status = "Open a network file (.ngb) or configure schedule.";
    [ObservableProperty] private string _sceneNote = "";
    [ObservableProperty] private string _title = "Neurogenesis";
    [ObservableProperty] private ColorMode _colorMode;
    [ObservableProperty] private SceneData? _scene;
    [ObservableProperty] private float[] _instances = Array.Empty<float>();
    [ObservableProperty, NotifyPropertyChangedFor(nameof(HasSelection))] private int _selected = -1;

    [ObservableProperty] private bool _canUndo;
    [ObservableProperty] private bool _canRedo;

    public bool HasSelection => Selected >= 0;
    public string SimButtonText => IsSimulating ? "Pause" : "Simulate";

    public MainViewModel()
    {
        _colorMode = Style.ColorModes[0];
        Project = new ProjectDocument();
        Project.DocumentChanged += (s, e) =>
        {
            CanUndo = Project.CanUndo;
            CanRedo = Project.CanRedo;
        };

        var (success, _, doc) = UiSchemaLoader.LoadDefault();
        if (success && doc != null)
        {
            UiSchema = doc;
            // Populate project with default stage if empty
            if (Project.Schedule.Count == 0 && doc.Stages.Count > 0)
            {
                var seedStage = doc.Stages.FirstOrDefault(st => st.Operator == "seed_cells") ?? doc.Stages[0];
                Project.AddStage(seedStage);
            }
        }
    }

    public void Undo()
    {
        if (Project.Undo())
        {
            CanUndo = Project.CanUndo;
            CanRedo = Project.CanRedo;
            Status = "Undo applied.";
        }
    }

    public void Redo()
    {
        if (Project.Redo())
        {
            CanUndo = Project.CanUndo;
            CanRedo = Project.CanRedo;
            Status = "Redo applied.";
        }
    }

    public void AddStage(StageSpec spec)
    {
        Project.AddStage(spec);
        Status = $"Added stage '{spec.Title}'.";
    }

    public void RemoveStage(int index)
    {
        Project.RemoveStage(index);
        Status = $"Removed stage #{index + 1}.";
    }

    public void MoveStage(int fromIndex, int toIndex)
    {
        Project.MoveStage(fromIndex, toIndex);
    }

    public void UpdateParam(int stageIndex, string paramName, JsonNode? value)
    {
        Project.UpdateParam(stageIndex, paramName, value);
    }

    public void UpdateStageName(int index, string name)
    {
        Project.UpdateStageName(index, name);
    }

    public void UpdateStageRepeat(int index, int repeat)
    {
        Project.UpdateStageRepeat(index, repeat);
    }

    public void UpdateStageWhen(int index, string? when)
    {
        Project.UpdateStageWhen(index, when);
    }

    public void SetNeuronModel(string modelName)
    {
        Project.NeuronModel = modelName;
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

    [ObservableProperty] private float _currentTick = 0f;
    [ObservableProperty, NotifyPropertyChangedFor(nameof(SimButtonText))] private bool _isSimulating = false;
    private SimulationEngine? _simEngine;

    public void StartSimulation()
    {
        if (Scene == null) return;
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
    }

    public void StepSimulation()
    {
        if (Scene == null) return;
        if (_simEngine == null)
        {
            _simEngine = new SimulationEngine(Scene.Network);
            _simEngine.FrameStepped += OnSimStep;
        }
        _simEngine.StepOnce();
    }

    private void OnSimStep()
    {
        if (_simEngine == null || Scene == null) return;
        CurrentTick = (float)_simEngine.CurrentTick;
        Instances = Scene.Instances(ColorMode, Selected, _simEngine.LastSpikeSnapshot);
        Status = $"Tick {_simEngine.CurrentTick:N0} — Spikes {_simEngine.TotalSpikes:N0}";
    }

    private void Refresh() => Instances = Scene?.Instances(ColorMode, Selected, _simEngine?.LastSpikeSnapshot) ?? Array.Empty<float>();
}
