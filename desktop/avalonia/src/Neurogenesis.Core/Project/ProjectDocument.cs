using System.Text.Json;
using System.Text.Json.Nodes;
using Neurogenesis.Core.Schema;

namespace Neurogenesis.Core.Project;

/// <summary>
/// Represents a neurogenesis Project (version 1.0.0) conforming to the Project schema.
/// All state mutations go through undo/redo snapshots, ensuring no hidden state exists.
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
        Root = CreateDefaultProject();
    }

    public ProjectDocument(string json)
    {
        var node = JsonNode.Parse(json);
        Root = node as JsonObject ?? throw new ArgumentException("JSON root must be an object", nameof(json));
    }

    public static JsonObject CreateDefaultProject()
    {
        return new JsonObject
        {
            ["version"] = "1.0.0",
            ["geometry"] = new JsonObject(),
            ["fields"] = new JsonObject(),
            ["schedule"] = new JsonArray(),
            ["genome"] = new JsonObject(),
            ["plugins"] = new JsonArray(),
            ["neuron_model"] = "lif_int",
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
        get => Root["neuron_model"]?.GetValue<string>() ?? "lif_int";
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

    public void Mutate(Action<JsonObject> mutateAction)
    {
        string before = Root.ToJsonString();
        _undoStack.Push(before);
        if (_undoStack.Count > MaxHistory)
        {
            var list = _undoStack.ToList();
            list.RemoveAt(list.Count - 1);
            _undoStack.Clear();
            for (int i = list.Count - 1; i >= 0; i--) _undoStack.Push(list[i]);
        }
        _redoStack.Clear();

        mutateAction(Root);
        DocumentChanged?.Invoke(this, EventArgs.Empty);
    }

    public bool Undo()
    {
        if (_undoStack.Count == 0) return false;
        string current = Root.ToJsonString();
        _redoStack.Push(current);

        string prev = _undoStack.Pop();
        Root = (JsonObject)JsonNode.Parse(prev)!;
        DocumentChanged?.Invoke(this, EventArgs.Empty);
        return true;
    }

    public bool Redo()
    {
        if (_redoStack.Count == 0) return false;
        string current = Root.ToJsonString();
        _undoStack.Push(current);

        string next = _redoStack.Pop();
        Root = (JsonObject)JsonNode.Parse(next)!;
        DocumentChanged?.Invoke(this, EventArgs.Empty);
        return true;
    }

    public void AddStage(StageSpec spec)
    {
        Mutate(root =>
        {
            var schedule = GetSchedule(root);
            var paramsObj = new JsonObject();
            if (spec.Params != null)
            {
                foreach (var p in spec.Params)
                {
                    if (p.Default != null)
                        paramsObj[p.Name] = p.Default.DeepClone();
                    else
                        paramsObj[p.Name] = new JsonObject { ["type"] = "Const", ["value"] = 0 };
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
            var schedule = GetSchedule(root);
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
            var schedule = GetSchedule(root);
            if (fromIndex >= 0 && fromIndex < schedule.Count && toIndex >= 0 && toIndex < schedule.Count && fromIndex != toIndex)
            {
                var item = schedule[fromIndex];
                schedule.RemoveAt(fromIndex);
                schedule.Insert(toIndex, item);
            }
        });
    }

    public void UpdateStageName(int index, string name)
    {
        Mutate(root =>
        {
            var schedule = GetSchedule(root);
            if (index >= 0 && index < schedule.Count && schedule[index] is JsonObject st)
            {
                st["name"] = name;
            }
        });
    }

    public void UpdateStageRepeat(int index, int repeat)
    {
        Mutate(root =>
        {
            var schedule = GetSchedule(root);
            if (index >= 0 && index < schedule.Count && schedule[index] is JsonObject st)
            {
                st["repeat"] = Math.Max(1, repeat);
            }
        });
    }

    public void UpdateStageWhen(int index, string? when)
    {
        Mutate(root =>
        {
            var schedule = GetSchedule(root);
            if (index >= 0 && index < schedule.Count && schedule[index] is JsonObject st)
            {
                if (string.IsNullOrWhiteSpace(when))
                    st.Remove("when");
                else
                    st["when"] = when;
            }
        });
    }

    public void UpdateParam(int stageIndex, string paramName, JsonNode? paramValue)
    {
        Mutate(root =>
        {
            var schedule = GetSchedule(root);
            if (stageIndex >= 0 && stageIndex < schedule.Count && schedule[stageIndex] is JsonObject st)
            {
                if (st["params"] is not JsonObject ps)
                {
                    ps = new JsonObject();
                    st["params"] = ps;
                }
                ps[paramName] = paramValue?.DeepClone();
            }
        });
    }

    private static JsonArray GetSchedule(JsonObject root)
    {
        if (root["schedule"] is not JsonArray arr)
        {
            arr = new JsonArray();
            root["schedule"] = arr;
        }
        return arr;
    }

    public string ToJsonString(bool indented = true)
    {
        return JsonSerializer.Serialize(Root, new JsonSerializerOptions { WriteIndented = indented });
    }
}
