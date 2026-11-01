using Neurogenesis.Core.Schema;
using Xunit;

namespace Neurogenesis.Tests;

public class UiSchemaTests
{
    [Fact]
    public void ValidateAndParseExampleSchemaDocument()
    {
        string root = PythonFixtures.RepoRoot();
        string schemaPath = Path.Combine(root, "desktop", "common", "ui_schema.schema.json");
        string examplePath = Path.Combine(root, "desktop", "common", "ui_schema.example.json");

        string schemaJson = File.ReadAllText(schemaPath);
        string exampleJson = File.ReadAllText(examplePath);

        var (isValid, error, doc) = UiSchemaDocument.LoadAndValidate(exampleJson, schemaJson);

        Assert.True(isValid, $"ui_schema.example.json failed validation: {error}");
        Assert.NotNull(doc);
        Assert.Equal("neurogenesis-ui-schema", doc.Format);
        Assert.Equal("1.0", doc.Version);

        // Stages present
        Assert.NotEmpty(doc.Stages);
        var seedStage = doc.Stages.FirstOrDefault(s => s.Operator == "seed_cells");
        Assert.NotNull(seedStage);
        Assert.True(seedStage.Available);
        Assert.NotNull(seedStage.Params);
        Assert.Contains(seedStage.Params, p => p.Name == "count" && p.Type == "int");

        // Models present
        Assert.NotEmpty(doc.Models);
        var lifModel = doc.Models.FirstOrDefault(m => m.Name == "lif_int");
        Assert.NotNull(lifModel);
        Assert.True(lifModel.Native);
    }

    [Fact]
    public void LoadDefault_Succeeds()
    {
        var (ok, err, doc) = UiSchemaLoader.LoadDefault();
        Assert.True(ok, err);
        Assert.NotNull(doc);
        Assert.Equal("neurogenesis-ui-schema", doc.Format);
    }
}
