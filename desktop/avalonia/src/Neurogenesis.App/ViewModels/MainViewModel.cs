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
    [ObservableProperty, NotifyPropertyChangedFor(nameof(CanSimulateRemote))] private bool _isBridgeReady = false;
    [ObservableProperty] private string _currentNetworkPath = "";

    // Preset Generation Fields
    [ObservableProperty] private string _generateMorphology = "column";
    [ObservableProperty] private decimal _generateNeurons = 500m;
    [ObservableProperty] private decimal _generateSeed = 42m;
    [ObservableProperty] private string? _lastError;
    public IReadOnlyList<string> Morphologies { get; } = new[] { "column", "layered", "microcircuit" };

    // Remote Simulation Fields
    [ObservableProperty] private string _remoteModel = "lif_int";
    [ObservableProperty] private decimal _remoteTicks = 500m;
    [ObservableProperty] private decimal _remoteSeed = 12345m;
    [ObservableProperty] private int _remoteTotalSpikes = 0;
    public List<(int Tick, int Neuron)> RemoteSpikes { get; } = new();
    private int[]? _remoteLastSpikes;
    public IReadOnlyList<string> AvailableModels =>
        UiSchema?.Models.Select(m => m.Name).ToList() ?? new List<string> { "lif_int", "lif_curr", "izhikevich" };

    public bool HasSelection => Selected >= 0;
    public string SimButtonText => IsSimulating ? "Pause" : "Simulate";
    public bool CanSimulateNative => Scene != null && IsModelNative;
    public bool CanSimulateRemote => Scene != null && IsBridgeReady;

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
                    IsBridgeReady = true;
                    await RefreshSchemaFromBridgeAsync();
                };
                Bridge.ProgressReceived += (job, data) =>
                {
                    string label = FormatProgress(job, data);
                    Dispatcher.UIThread.Post(() =>
                    {
                        Status = label;
                    });
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
            if (PythonLocator.IsPackagedBuild())
            {
                SceneNote = "Bundled Python runtime missing";
            }
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
            _remoteLastSpikes = null;
            RemoteSpikes.Clear();
            RemoteTotalSpikes = 0;
            IsSimulating = false;
            CurrentTick = 0f;
            CurrentNetworkPath = path;
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


    /// <summary>Formats bridge progress events into human-readable status labels.</summary>
    public static string FormatProgress(int job, JsonElement data)
    {
        if (data.ValueKind != JsonValueKind.Object)
        {
            return $"Job #{job} — In progress";
        }

        // Percentage
        if (data.TryGetProperty("percent", out var pctProp) && pctProp.TryGetDouble(out var pct))
        {
            return $"Job #{job} — {pct:F0}%";
        }
        if (data.TryGetProperty("percentage", out var pctProp2) && pctProp2.TryGetDouble(out var pct2))
        {
            return $"Job #{job} — {pct2:F0}%";
        }

        // Step / Total
        if (data.TryGetProperty("step", out var stepProp) && stepProp.TryGetInt32(out var step))
        {
            if (data.TryGetProperty("total", out var totProp) && totProp.TryGetInt32(out var total) && total > 0)
            {
                int p = (int)Math.Round((double)step / total * 100);
                return $"Job #{job} — Step {step}/{total} ({p}%)";
            }
            return $"Job #{job} — Step {step}";
        }

        // Evolution generation
        if (data.TryGetProperty("generation", out var genProp) && genProp.TryGetInt32(out var gen))
        {
            string bestStr = "";
            if (data.TryGetProperty("best", out var bestProp) && bestProp.TryGetDouble(out var bestVal))
            {
                bestStr = $" (best: {bestVal:F2})";
            }
            if (data.TryGetProperty("gens", out var gensProp) && gensProp.TryGetInt32(out var totalGens) && totalGens > 0)
            {
                int p = (int)Math.Round((double)(gen + 1) / totalGens * 100);
                return $"Job #{job} — Gen {gen + 1}/{totalGens} ({p}%){bestStr}";
            }
            return $"Job #{job} — Generation {gen + 1}{bestStr}";
        }

        // Descriptive message
        if (data.TryGetProperty("message", out var msgProp) && msgProp.GetString() is { } msg && !string.IsNullOrWhiteSpace(msg))
        {
            return $"Job #{job} — {msg}";
        }
        if (data.TryGetProperty("status", out var statProp) && statProp.GetString() is { } stat && !string.IsNullOrWhiteSpace(stat))
        {
            return $"Job #{job} — {stat}";
        }

        return $"Job #{job} — In progress";
    }

    /// <summary>Calls Python bridge `generate` using current ViewModel properties.</summary>
    public async Task GeneratePresetAsync()
    {
        await GeneratePresetAsync(GenerateMorphology, (int)GenerateNeurons, (int)GenerateSeed);
    }

    /// <summary>Calls Python bridge `generate` method from presets and opens the resulting network.</summary>
    public async Task GeneratePresetAsync(string morphology, int neurons, int seed)
    {
        if (neurons < 1)
        {
            Status = "Neuron count must be at least 1.";
            LastError = Status;
            return;
        }
        if (neurons > 1000000)
        {
            Status = "Neuron count cannot exceed 1,000,000.";
            LastError = Status;
            return;
        }

        if (Bridge == null || !Bridge.IsReady)
        {
            Status = "Bridge not ready for network generation.";
            LastError = Status;
            return;
        }

        Status = $"Generating {neurons} neuron {morphology} preset via bridge…";
        try
        {
            var p = new JsonObject
            {
                ["morphology"] = morphology,
                ["neurons"] = neurons,
                ["seed"] = seed
            };
            var res = await Bridge.CallAsync("generate", p);
            if (res.TryGetProperty("path", out var pathProp) && pathProp.GetString() is { } ngbPath && File.Exists(ngbPath))
            {
                await OpenAsync(ngbPath);
                Status = $"Generated {neurons} neuron {morphology} (seed {seed}) via bridge.";
                LastError = null;
            }
            else
            {
                Status = "Bridge generate returned invalid response.";
                LastError = Status;
            }
        }
        catch (BridgeException ex)
        {
            // Surfaces memory refusal or backend errors cleanly
            Status = ex.Message;
            LastError = ex.Message;
        }
        catch (Exception ex)
        {
            Status = $"Bridge generate error: {ex.Message}";
            LastError = ex.Message;
        }
    }

    /// <summary>Runs remote simulation using current ViewModel properties.</summary>
    public async Task SimulateRemoteAsync()
    {
        await SimulateRemoteAsync(RemoteModel, (int)RemoteTicks, (uint)RemoteSeed);
    }

    /// <summary>Runs remote simulation via Python bridge `simulate` method (JAX / non-native models).</summary>
    public async Task SimulateRemoteAsync(string model, int ticks, uint seed)
    {
        if (ticks < 1)
        {
            Status = "Ticks must be at least 1.";
            LastError = Status;
            return;
        }

        if (Scene == null || string.IsNullOrEmpty(CurrentNetworkPath))
        {
            Status = "No network file open for remote simulation.";
            LastError = Status;
            return;
        }
        if (Bridge == null || !Bridge.IsReady)
        {
            Status = "Bridge not ready for remote simulation.";
            LastError = Status;
            return;
        }

        string modelName = !string.IsNullOrEmpty(model) ? model : (RemoteModel ?? "lif_int");

        Status = $"Simulating {ticks} ticks remotely via bridge with {modelName}…";
        try
        {
            var p = new JsonObject
            {
                ["ngb"] = CurrentNetworkPath,
                ["model"] = modelName,
                ["ticks"] = ticks,
                ["seed"] = (int)seed
            };
            var res = await Bridge.CallAsync("simulate", p);
            int returnedTicks = res.TryGetProperty("ticks", out var tp) ? tp.GetInt32() : ticks;

            int spikeCount = 0;
            _remoteLastSpikes = new int[Scene.Network.NeuronCount];
            Array.Fill(_remoteLastSpikes, int.MinValue);
            RemoteSpikes.Clear();

            if (res.TryGetProperty("t", out var tProp) && res.TryGetProperty("i", out var iProp) &&
                tProp.ValueKind == JsonValueKind.Array && iProp.ValueKind == JsonValueKind.Array)
            {
                spikeCount = tProp.GetArrayLength();
                int nLen = Math.Min(tProp.GetArrayLength(), iProp.GetArrayLength());
                for (int k = 0; k < nLen; k++)
                {
                    int spikeTick = tProp[k].GetInt32();
                    int neuronIdx = iProp[k].GetInt32();
                    RemoteSpikes.Add((spikeTick, neuronIdx));
                    if (neuronIdx >= 0 && neuronIdx < _remoteLastSpikes.Length)
                    {
                        if (spikeTick > _remoteLastSpikes[neuronIdx])
                        {
                            _remoteLastSpikes[neuronIdx] = spikeTick;
                        }
                    }
                }
            }

            RemoteTotalSpikes = spikeCount;
            CurrentTick = (float)returnedTicks;
            Refresh();

            Status = $"Remote sim complete: {returnedTicks} ticks, {spikeCount} spikes using {modelName}.";
            LastError = null;
        }
        catch (BridgeException ex)
        {
            Status = ex.Message;
            LastError = ex.Message;
        }
        catch (Exception ex)
        {
            Status = $"Remote sim error: {ex.Message}";
            LastError = ex.Message;
        }
    }

    private void Refresh()
    {
        int[]? lastSpikes = _simEngine?.LastSpikeSnapshot ?? _remoteLastSpikes;
        Instances = Scene?.Instances(ColorMode, Selected, lastSpikes) ?? Array.Empty<float>();
    }
}
