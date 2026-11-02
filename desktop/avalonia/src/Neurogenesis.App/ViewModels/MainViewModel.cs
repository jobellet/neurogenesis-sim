using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using Neurogenesis.Core.Bridge;
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
    public BridgeClient? Bridge { get; }

    public ProjectDocument Project { get; }
    [ObservableProperty] private UiSchemaDocument? _uiSchema;

    [ObservableProperty] private string _status = "Open a network file (.ngb) or configure schedule.";
    [ObservableProperty] private string _sceneNote = "";
    [ObservableProperty] private string _title = "Neurogenesis";
    [ObservableProperty] private ColorMode _colorMode;
    [ObservableProperty] private SceneData? _scene;
    [ObservableProperty] private float[] _instances = Array.Empty<float>();
    [ObservableProperty, NotifyPropertyChangedFor(nameof(HasSelection))] private int _selected = -1;

    [ObservableProperty] private bool _canUndo;
    [ObservableProperty] private bool _canRedo;

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
        Project = new ProjectDocument();
        Project.DocumentChanged += (s, e) =>
        {
            CanUndo = Project.CanUndo;
            CanRedo = Project.CanRedo;
            UpdateModelNative();
        };

        // Load bundled / fallback UI schema
        var (success, error, doc, isExample) = UiSchemaLoader.LoadDefault();
        if (success && doc != null)
        {
            UiSchema = doc;
            if (string.IsNullOrEmpty(Project.NeuronModel) && doc.Models.Count > 0)
            {
                Project.NeuronModel = doc.Models[0].Name;
            }
            if (Project.Schedule.Count == 0 && doc.Stages.Count > 0)
            {
                var firstAvailable = doc.Stages.FirstOrDefault(st => st.Available) ?? doc.Stages[0];
                Project.AddStage(firstAvailable);
            }
            if (isExample)
            {
                SceneNote = "Using bundled example UI schema";
            }
        }
        else if (!string.IsNullOrEmpty(error))
        {
            Status = $"UI Schema warning: {error}";
        }

        UpdateModelNative();

        // Connect bridge if python runtime is found
        try
        {
            string? py = PythonLocator.FindPython();
            if (!string.IsNullOrEmpty(py))
            {
                Bridge = new BridgeClient(py);
                Bridge.StatusChanged += status =>
                {
                    Dispatcher.UIThread.Post(() => Status = status);
                };
                Bridge.ReadyReceived += async _ =>
                {
                    await RefreshSchemaFromBridgeAsync();
                };

                _ = Task.Run(async () =>
                {
                    try
                    {
                        await Bridge.StartAsync();
                    }
                    catch (Exception ex)
                    {
                        Dispatcher.UIThread.Post(() => Status = $"Bridge error: {ex.Message}");
                    }
                });
            }
        }
        catch (Exception ex)
        {
            Status = $"Python runtime error: {ex.Message}";
        }
    }

    public async Task RefreshSchemaFromBridgeAsync()
    {
        if (Bridge == null || !Bridge.IsReady) return;
        try
        {
            // Query bridge for ui_schema if supported
            var schemaJson = await Bridge.CallAsync("ui_schema", null);
            if (schemaJson.ValueKind == JsonValueKind.Object)
            {
                string raw = schemaJson.GetRawText();
                var (valid, validationErr, dynamicDoc) = UiSchemaLoader.ValidateDynamic(raw);
                if (valid && dynamicDoc != null)
                {
                    Dispatcher.UIThread.Post(() =>
                    {
                        UiSchema = dynamicDoc;
                        SceneNote = "";
                        Status = "Live UI schema loaded from bridge.";
                        UpdateModelNative();
                    });
                }
                else
                {
                    Dispatcher.UIThread.Post(() => Status = $"Bridge schema invalid: {validationErr}");
                }
            }
        }
        catch (Exception ex)
        {
            // Bridge does not implement ui_schema or call failed; keep current schema
            Dispatcher.UIThread.Post(() =>
            {
                if (ex is not BridgeException be || !be.Message.Contains("no_such_method", StringComparison.OrdinalIgnoreCase))
                {
                    Status = $"Bridge ui_schema note: {ex.Message}";
                }
            });
        }
    }

    private void UpdateModelNative()
    {
        if (UiSchema != null)
        {
            string targetModel = !string.IsNullOrEmpty(Project.NeuronModel)
                ? Project.NeuronModel
                : (UiSchema.Models.FirstOrDefault()?.Name ?? "");
            var model = UiSchema.Models.FirstOrDefault(m => string.Equals(m.Name, targetModel, StringComparison.OrdinalIgnoreCase));
            IsModelNative = model?.Native ?? false;
        }
        else
        {
            IsModelNative = false;
        }
    }

    partial void OnUiSchemaChanged(UiSchemaDocument? value) => UpdateModelNative();

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
        UpdateModelNative();
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

        Dispatcher.UIThread.Post(UpdateSimUi);
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
