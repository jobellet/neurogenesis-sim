using System.Text.Json.Nodes;
using Neurogenesis.Core.Project;
using Neurogenesis.Core.Schema;
using Xunit;

namespace Neurogenesis.Tests;

public class ProjectDocumentTests
{
    [Fact]
    public void DefaultProject_HasCorrectStructure()
    {
        var doc = new ProjectDocument();
        Assert.Equal("1.0.0", doc.Version);
        Assert.Equal("", doc.NeuronModel);
        Assert.Empty(doc.Schedule);
        Assert.False(doc.CanUndo);
        Assert.False(doc.CanRedo);

        doc.NeuronModel = "lif_int";
        Assert.Equal("lif_int", doc.NeuronModel);
        Assert.True(doc.CanUndo);
    }

    [Fact]
    public void AddStage_And_UndoRedo_Works()
    {
        var (ok, err, schema, _) = UiSchemaLoader.LoadDefault();
        Assert.True(ok, err);
        Assert.NotNull(schema);

        var doc = new ProjectDocument();
        var seedStage = schema.Stages.First(s => s.Operator == "seed_cells");

        doc.AddStage(seedStage);
        Assert.Single(doc.Schedule);
        Assert.True(doc.CanUndo);
        Assert.False(doc.CanRedo);

        var stageObj = doc.Schedule[0] as JsonObject;
        Assert.NotNull(stageObj);
        Assert.Equal("seed_cells", stageObj["operator"]?.GetValue<string>());
        Assert.Equal(1, stageObj["repeat"]?.GetValue<int>());

        // Undo
        Assert.True(doc.Undo());
        Assert.Empty(doc.Schedule);
        Assert.False(doc.CanUndo);
        Assert.True(doc.CanRedo);

        // Redo
        Assert.True(doc.Redo());
        Assert.Single(doc.Schedule);
    }

    [Fact]
    public void ParamUpdate_AllSources_RecordToProjectJson()
    {
        var (ok, _, schema, _) = UiSchemaLoader.LoadDefault();
        Assert.True(ok);
        var doc = new ProjectDocument();
        var seedStage = schema!.Stages.First(s => s.Operator == "seed_cells");
        doc.AddStage(seedStage);

        // 1. Const
        doc.UpdateParam(0, "count", new JsonObject { ["type"] = "Const", ["value"] = 500 });
        var pConst = (doc.Schedule[0] as JsonObject)?["params"]?["count"] as JsonObject;
        Assert.Equal("Const", pConst?["type"]?.GetValue<string>());
        Assert.Equal(500, pConst?["value"]?.GetValue<int>());

        // 2. Gene
        doc.UpdateParam(0, "count", new JsonObject
        {
            ["type"] = "Gene",
            ["path"] = "progenitors/seed_count",
            ["lo"] = 10.0,
            ["hi"] = 1000.0,
            ["integer"] = true
        });
        var pGene = (doc.Schedule[0] as JsonObject)?["params"]?["count"] as JsonObject;
        Assert.Equal("Gene", pGene?["type"]?.GetValue<string>());
        Assert.Equal("progenitors/seed_count", pGene?["path"]?.GetValue<string>());
        Assert.Equal(10.0, pGene?["lo"]?.GetValue<double>());
        Assert.True(pGene?["integer"]?.GetValue<bool>());

        // 3. Field
        doc.UpdateParam(0, "density", new JsonObject
        {
            ["type"] = "Field",
            ["name"] = "gradient_y",
            ["transform"] = "2*x + 1"
        });
        var pField = (doc.Schedule[0] as JsonObject)?["params"]?["density"] as JsonObject;
        Assert.Equal("Field", pField?["type"]?.GetValue<string>());
        Assert.Equal("gradient_y", pField?["name"]?.GetValue<string>());
        Assert.Equal("2*x + 1", pField?["transform"]?.GetValue<string>());

        // 4. Fit
        doc.UpdateParam(0, "count", new JsonObject
        {
            ["type"] = "Fit",
            ["target"] = "density_target",
            ["init"] = 100.0,
            ["lo"] = 10.0,
            ["hi"] = 500.0
        });
        var pFit = (doc.Schedule[0] as JsonObject)?["params"]?["count"] as JsonObject;
        Assert.Equal("Fit", pFit?["type"]?.GetValue<string>());
        Assert.Equal("density_target", pFit?["target"]?.GetValue<string>());

        // 5. Expr
        doc.UpdateParam(0, "density", new JsonObject
        {
            ["type"] = "Expr",
            ["formula"] = "0.5 * morphogen_a + 0.1"
        });
        var pExpr = (doc.Schedule[0] as JsonObject)?["params"]?["density"] as JsonObject;
        Assert.Equal("Expr", pExpr?["type"]?.GetValue<string>());
        Assert.Equal("0.5 * morphogen_a + 0.1", pExpr?["formula"]?.GetValue<string>());

        // Verify JSON round trip
        string json = doc.ToJsonString();
        var reloaded = new ProjectDocument(json);
        Assert.Equal(doc.NeuronModel, reloaded.NeuronModel);
        Assert.Equal(doc.Schedule.Count, reloaded.Schedule.Count);
    }

    [Fact]
    public void StageReorder_And_Remove_Works()
    {
        var (ok, _, schema, _) = UiSchemaLoader.LoadDefault();
        Assert.True(ok);
        var doc = new ProjectDocument();

        var stage1 = schema!.Stages[0];
        var stage2 = schema.Stages[1];
        doc.AddStage(stage1);
        doc.AddStage(stage2);

        Assert.Equal(2, doc.Schedule.Count);
        Assert.Equal(stage1.Operator, (doc.Schedule[0] as JsonObject)?["operator"]?.GetValue<string>());
        Assert.Equal(stage2.Operator, (doc.Schedule[1] as JsonObject)?["operator"]?.GetValue<string>());

        // Move stage 1 to 0
        doc.MoveStage(1, 0);
        Assert.Equal(stage2.Operator, (doc.Schedule[0] as JsonObject)?["operator"]?.GetValue<string>());
        Assert.Equal(stage1.Operator, (doc.Schedule[1] as JsonObject)?["operator"]?.GetValue<string>());

        // Remove stage 0
        doc.RemoveStage(0);
        Assert.Single(doc.Schedule);
        Assert.Equal(stage1.Operator, (doc.Schedule[0] as JsonObject)?["operator"]?.GetValue<string>());

        // Undo remove
        doc.Undo();
        Assert.Equal(2, doc.Schedule.Count);
        Assert.Equal(stage2.Operator, (doc.Schedule[0] as JsonObject)?["operator"]?.GetValue<string>());
    }
}
