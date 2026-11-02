namespace Neurogenesis.Core.Schema;

/// <summary>
/// Locates, loads, and validates the UI schema document (embedded or from desktop/common/ui_schema.example.json)
/// against ui_schema.schema.json, or validates dynamic schema returned by the Python bridge.
/// </summary>
public static class UiSchemaLoader
{
    public static (bool Success, string? Error, UiSchemaDocument? Document, bool IsExample) LoadDefault()
    {
        string? schemaJson = ReadEmbeddedOrFile("ui_schema.schema.json");
        string? exampleJson = ReadEmbeddedOrFile("ui_schema.example.json");

        if (string.IsNullOrEmpty(schemaJson) || string.IsNullOrEmpty(exampleJson))
        {
            return (false, "Could not find ui_schema.schema.json or ui_schema.example.json (embedded or on disk)", null, false);
        }

        var (success, error, doc) = UiSchemaDocument.LoadAndValidate(exampleJson, schemaJson);
        return (success, error, doc, true);
    }

    public static (bool Success, string? Error, UiSchemaDocument? Document) ValidateDynamic(string dynamicSchemaJson)
    {
        string? schemaJson = ReadEmbeddedOrFile("ui_schema.schema.json");
        if (string.IsNullOrEmpty(schemaJson))
        {
            return (false, "Could not find ui_schema.schema.json validator", null);
        }

        return UiSchemaDocument.LoadAndValidate(dynamicSchemaJson, schemaJson);
    }

    private static string? ReadEmbeddedOrFile(string filename)
    {
        // 1. Try embedded resource
        var asm = typeof(UiSchemaLoader).Assembly;
        using (var s = asm.GetManifestResourceStream(filename))
        {
            if (s != null)
            {
                using var reader = new StreamReader(s);
                return reader.ReadToEnd();
            }
        }

        // 2. Try walking up directory tree on disk
        string? filePath = FindFile(filename);
        if (filePath != null && File.Exists(filePath))
        {
            return File.ReadAllText(filePath);
        }

        return null;
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

        string rel = Path.Combine("desktop", "common", filename);
        if (File.Exists(rel)) return Path.GetFullPath(rel);

        return null;
    }
}
