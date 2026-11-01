namespace Neurogenesis.Core.Schema;

/// <summary>
/// Locates, loads, and validates the UI schema document (desktop/common/ui_schema.example.json)
/// against ui_schema.schema.json until the Python bridge serves it dynamically.
/// </summary>
public static class UiSchemaLoader
{
    public static (bool Success, string? Error, UiSchemaDocument? Document) LoadDefault()
    {
        string? schemaPath = FindFile("ui_schema.schema.json");
        string? examplePath = FindFile("ui_schema.example.json");

        if (schemaPath == null || examplePath == null)
        {
            return (false, "Could not find desktop/common/ui_schema.* files", null);
        }

        string schemaJson = File.ReadAllText(schemaPath);
        string exampleJson = File.ReadAllText(examplePath);

        return UiSchemaDocument.LoadAndValidate(exampleJson, schemaJson);
    }

    private static string? FindFile(string filename)
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir != null)
        {
            string candidate = Path.Combine(dir.FullName, "desktop", "common", filename);
            if (File.Exists(candidate)) return candidate;

            candidate = Path.Combine(dir.FullName, filename);
            if (File.Exists(candidate)) return candidate;

            dir = dir.Parent;
        }

        // Also check current directory
        string rel = Path.Combine("desktop", "common", filename);
        if (File.Exists(rel)) return Path.GetFullPath(rel);

        return null;
    }
}
