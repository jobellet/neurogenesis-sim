using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using Json.Schema;

namespace Neurogenesis.Core.Schema;

public sealed record ParamSourceInput(
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("type")] string Type,
    [property: JsonPropertyName("doc")] string? Doc
);

public sealed record ParamSourceSpec(
    [property: JsonPropertyName("type")] string Type,
    [property: JsonPropertyName("title")] string Title,
    [property: JsonPropertyName("doc")] string? Doc,
    [property: JsonPropertyName("inputs")] IReadOnlyList<ParamSourceInput>? Inputs
);

public sealed record ParamChoice(
    [property: JsonPropertyName("value")] string Value,
    [property: JsonPropertyName("title")] string Title
);

public sealed record ParamSpec(
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("title")] string Title,
    [property: JsonPropertyName("doc")] string? Doc,
    [property: JsonPropertyName("type")] string Type,
    [property: JsonPropertyName("default")] JsonNode? Default,
    [property: JsonPropertyName("sources")] IReadOnlyList<string>? Sources,
    [property: JsonPropertyName("units")] string? Units,
    [property: JsonPropertyName("min")] double? Min,
    [property: JsonPropertyName("max")] double? Max,
    [property: JsonPropertyName("step")] double? Step,
    [property: JsonPropertyName("choices")] IReadOnlyList<ParamChoice>? Choices,
    [property: JsonPropertyName("per_cell")] bool PerCell = false,
    [property: JsonPropertyName("advanced")] bool Advanced = false
);

public sealed record StageCost(
    [property: JsonPropertyName("declared")] bool Declared,
    [property: JsonPropertyName("samples")] IReadOnlyList<JsonNode>? Samples
);

public sealed record StageSpec(
    [property: JsonPropertyName("operator")] string Operator,
    [property: JsonPropertyName("title")] string Title,
    [property: JsonPropertyName("task")] string Task,
    [property: JsonPropertyName("available")] bool Available,
    [property: JsonPropertyName("description")] string? Description,
    [property: JsonPropertyName("repeatable")] bool Repeatable,
    [property: JsonPropertyName("conditional")] bool Conditional,
    [property: JsonPropertyName("cost")] StageCost? Cost,
    [property: JsonPropertyName("params")] IReadOnlyList<ParamSpec>? Params
);

public sealed record ModelSpec(
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("title")] string Title,
    [property: JsonPropertyName("description")] string? Description,
    [property: JsonPropertyName("substeps")] int Substeps,
    [property: JsonPropertyName("state_bytes")] int StateBytes,
    [property: JsonPropertyName("flops")] int Flops,
    [property: JsonPropertyName("cost")] JsonNode? Cost,
    [property: JsonPropertyName("native")] bool Native
);

public sealed record UiSchemaDocument(
    [property: JsonPropertyName("format")] string Format,
    [property: JsonPropertyName("version")] string Version,
    [property: JsonPropertyName("project_schema_version")] string ProjectSchemaVersion,
    [property: JsonPropertyName("param_sources")] IReadOnlyList<ParamSourceSpec> ParamSources,
    [property: JsonPropertyName("stages")] IReadOnlyList<StageSpec> Stages,
    [property: JsonPropertyName("models")] IReadOnlyList<ModelSpec> Models,
    [property: JsonPropertyName("rule_phases")] IReadOnlyList<JsonNode>? RulePhases,
    [property: JsonPropertyName("rules")] IReadOnlyList<JsonNode>? Rules,
    [property: JsonPropertyName("schedule_genes")] IReadOnlyList<JsonNode>? ScheduleGenes
)
{
    public static readonly string ExpectedFormat = "neurogenesis-ui-schema";
    public static readonly string ExpectedMajorVersion = "1";
    private static readonly object _schemaLock = new();
    private static JsonSchema? _cachedSchema;

    public static (bool IsValid, string? Error, UiSchemaDocument? Document) LoadAndValidate(string json, string schemaJson)
    {
        JsonSchema schema;
        lock (_schemaLock)
        {
            schema = _cachedSchema ??= JsonSchema.FromText(schemaJson);
        }
        using var doc = JsonDocument.Parse(json);
        var res = schema.Evaluate(doc.RootElement, new EvaluationOptions { OutputFormat = OutputFormat.List });

        if (!res.IsValid)
        {
            var firstErr = res.Details?.FirstOrDefault(d => d.Errors != null && d.Errors.Count > 0);
            string msg = firstErr?.Errors?.Values.FirstOrDefault() ?? "Schema validation failed";
            return (false, msg, null);
        }

        var parsed = JsonSerializer.Deserialize<UiSchemaDocument>(json);
        if (parsed == null) return (false, "Deserialization returned null", null);

        if (parsed.Format != ExpectedFormat)
            return (false, $"Unexpected format '{parsed.Format}', expected '{ExpectedFormat}'", null);

        string major = parsed.Version.Split('.')[0];
        if (major != ExpectedMajorVersion)
            return (false, $"Major version mismatch '{parsed.Version}', expected '{ExpectedMajorVersion}.x'", null);

        return (true, null, parsed);
    }
}
