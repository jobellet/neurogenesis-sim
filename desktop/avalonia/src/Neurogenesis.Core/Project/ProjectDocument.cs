using System.Text.Json.Nodes;
using Neurogenesis.Core.Schema;

namespace Neurogenesis.Core.Project;

/// <summary>
/// Manages the in-memory Project JSON document conforming to the Project schema (task A1).
/// Supports full undo/redo history for non-destructive stage and parameter editing.
/// </summary>
public sealed class ProjectDocument
{
    private readonly Stack<string> _undoStack = new();
    private readonly Stack<string> _redoStack = new();
    private const int MaxHistory = 50;

    public JsonObject Root { get; private set; }

    public event EventHandler? DocumentChanged;

    public bool CanUndo => _undoStack.Count > 0;
    public bool CanRedo => _redoStack.Count > 0;

    public ProjectDocument()
    {
        Root = CreateDefaultProject("");
    }

    public ProjectDocument(JsonObject root)
    {
        Root = root ?? throw new ArgumentNullException(nameof(root));
    }

    public ProjectDocument(string json)
    {
        var node = JsonNode.Parse(json);
        Root = node as JsonObject ?? throw new ArgumentException("JSON root must be an object", nameof(json));
    }

    public static ProjectDocument FromJson(string json, string? defaultModel = null)
    {
        var doc = new ProjectDocument(json);
        if (defaultModel != null && string.IsNullOrEmpty(doc.NeuronModel))
        {
            doc.NeuronModel = defaultModel;
        }
        return doc;
    }

    public static JsonObject CreateDefaultProject(string defaultModel = "")
    {
        return new JsonObject
        {
            ["version"] = "1.0.0",
            ["geometry"] = new JsonObject(),
            ["fields"] = new JsonObject(),
            ["schedule"] = new JsonArray(),
            ["genome"] = new JsonObject(),
            ["plugins"] = new JsonArray(),
            ["neuron_model"] = defaultModel,
            ["metadata"] = new JsonObject
            {
                ["created"] = DateTime.UtcNow.ToString("o")
            }
        };
    }

    public string Version
    {
        get => Root["version"]?.GetValue<string>() ?? "1.0.0";
        set => Mutate(root => root["version"] = value);
    }

    public string NeuronModel
    {
        get => Root["neuron_model"]?.GetValue<string>() ?? "";
        set => Mutate(root => root["neuron_model"] = value);
    }

    public JsonArray Schedule
    {
        get
        {
            if (Root["schedule"] is not JsonArray arr)
            {
                arr = new JsonArray();
                Root["schedule"] = arr;
            }
            return arr;
        }
    }

    public IReadOnlyList<JsonObject> Stages
    {
        get
        {
            var list = new List<JsonObject>();
            foreach (var node in Schedule)
            {
                if (node is JsonObject obj) list.Add(obj);
            }
            return list;
        }
    }

    public void AddStage(StageSpec spec)
    {
        Mutate(root =>
        {
            var schedule = Schedule;
            var paramsObj = new JsonObject();
            if (spec.Params != null)
            {
                foreach (var p in spec.Params)
                {
                    if (p.Default != null)
                    {
                        paramsObj[p.Name] = p.Default.DeepClone();
                    }
                    else
                    {
                        JsonNode? defaultValue = p.Type switch
                        {
                            "bool" => false,
                            "string" => "",
                            "choice" => p.Choices != null && p.Choices.Count > 0 ? p.Choices[0].Value : "",
                            "vec3" => new JsonArray { 0, 0, 0 },
                            "float" => 0.0,
                            "int" => 0,
                            _ => null
                        };
                        if (defaultValue != null)
                            paramsObj[p.Name] = new JsonObject { ["type"] = "Const", ["value"] = defaultValue };
                        else
                            paramsObj[p.Name] = null;
                    }
                }
            }

            int index = schedule.Count + 1;
            var stageObj = new JsonObject
            {
                ["name"] = $"{index}_{spec.Operator}",
                ["operator"] = spec.Operator,
                ["repeat"] = 1,
                ["params"] = paramsObj
            };
            schedule.Add(stageObj);
        });
    }

    public void RemoveStage(int index)
    {
        Mutate(root =>
        {
            var schedule = Schedule;
            if (index >= 0 && index < schedule.Count)
            {
                schedule.RemoveAt(index);
            }
        });
    }

    public void MoveStage(int fromIndex, int toIndex)
    {
        Mutate(root =>
        {
            var schedule = Schedule;
            if (fromIndex >= 0 && fromIndex < schedule.Count && toIndex >= 0 && toIndex < schedule.Count)
            {
                var item = schedule[fromIndex];
                schedule.RemoveAt(fromIndex);
                schedule.Insert(toIndex, item);
            }
        });
    }

    public void UpdateParam(int stageIndex, string paramName, JsonNode? value)
    {
        Mutate(root =>
        {
            var schedule = Schedule;
            if (stageIndex >= 0 && stageIndex < schedule.Count && schedule[stageIndex] is JsonObject stageObj)
            {
                if (stageObj["params"] is not JsonObject paramsObj)
                {
                    paramsObj = new JsonObject();
                    stageObj["params"] = paramsObj;
                }
                paramsObj[paramName] = value?.DeepClone();
            }
        });
    }

    public void UpdateStageName(int stageIndex, string name)
    {
        Mutate(root =>
        {
            var schedule = Schedule;
            if (stageIndex >= 0 && stageIndex < schedule.Count && schedule[stageIndex] is JsonObject stageObj)
            {
                stageObj["name"] = name;
            }
        });
    }

    public void UpdateStageRepeat(int stageIndex, int repeat)
    {
        Mutate(root =>
        {
            var schedule = Schedule;
            if (stageIndex >= 0 && stageIndex < schedule.Count && schedule[stageIndex] is JsonObject stageObj)
            {
                stageObj["repeat"] = Math.Max(1, repeat);
            }
        });
    }

    public void UpdateStageWhen(int stageIndex, string? when)
    {
        Mutate(root =>
        {
            var schedule = Schedule;
            if (stageIndex >= 0 && stageIndex < schedule.Count && schedule[stageIndex] is JsonObject stageObj)
            {
                if (string.IsNullOrWhiteSpace(when))
                    stageObj.Remove("when");
                else
                    stageObj["when"] = when;
            }
        });
    }

    public bool Undo()
    {
        if (_undoStack.Count == 0) return false;
        _redoStack.Push(Root.ToJsonString());
        string previous = _undoStack.Pop();
        Root = (JsonObject)JsonNode.Parse(previous)!;
        DocumentChanged?.Invoke(this, EventArgs.Empty);
        return true;
    }

    public bool Redo()
    {
        if (_redoStack.Count == 0) return false;
        _undoStack.Push(Root.ToJsonString());
        string next = _redoStack.Pop();
        Root = (JsonObject)JsonNode.Parse(next)!;
        DocumentChanged?.Invoke(this, EventArgs.Empty);
        return true;
    }

    private void Mutate(Action<JsonObject> action)
    {
        string before = Root.ToJsonString();
        action(Root);
        string after = Root.ToJsonString();

        if (before != after)
        {
            _undoStack.Push(before);
            if (_undoStack.Count > MaxHistory)
            {
                var list = _undoStack.ToList();
                list.RemoveAt(list.Count - 1);
                _undoStack.Clear();
                for (int i = list.Count - 1; i >= 0; i--) _undoStack.Push(list[i]);
            }
            _redoStack.Clear();
            DocumentChanged?.Invoke(this, EventArgs.Empty);
        }
    }

    public string ToJsonString(bool indented = true)
    {
        return Root.ToJsonString(new System.Text.Json.JsonSerializerOptions { WriteIndented = indented });
    }
}
