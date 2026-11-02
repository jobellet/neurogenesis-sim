using System.Text.Json.Nodes;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Neurogenesis.App.Style;
using Neurogenesis.Core.Schema;

namespace Neurogenesis.App.Controls;

/// <summary>
/// Dynamically generates editor controls for stages, schedules and parameters
/// conforming strictly to UI_SCHEMA.md 1.0 (task Step 4).
/// All edits update the underlying Project JSON directly without hidden state.
/// All colors are derived from the visual style through ThemeBrushes.
/// </summary>
public static class DynamicPanelGenerator
{
    public static Control CreateStageEditor(
        StageSpec stage,
        int stageIndex,
        JsonObject currentStageObj,
        IReadOnlyList<ParamSourceSpec>? paramSources,
        Action<string, JsonNode?> onParamChanged,
        Action<string> onNameChanged,
        Action<int> onRepeatChanged,
        Action<string?> onWhenChanged)
    {
        var panel = new StackPanel { Spacing = 8, Margin = new Thickness(0, 4) };

        // Header with title and availability / task badges
        var header = new DockPanel();
        var titlePanel = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
        titlePanel.Children.Add(new TextBlock
        {
            Text = stage.Title,
            FontWeight = FontWeight.Bold,
            FontSize = 14,
            VerticalAlignment = VerticalAlignment.Center
        });

        // Task badge (e.g. C1, C2)
        titlePanel.Children.Add(new Border
        {
            Background = ThemeBrushes.TaskBadgeBg,
            CornerRadius = new CornerRadius(3),
            Padding = new Thickness(4, 1),
            Child = new TextBlock
            {
                Text = stage.Task,
                FontSize = 10,
                Foreground = ThemeBrushes.TaskBadgeFg
            }
        });

        // Availability badge
        var availBrush = stage.Available ? ThemeBrushes.AvailableBadgeBg : ThemeBrushes.PlannedBadgeBg;
        var availFg = stage.Available ? ThemeBrushes.AvailableBadgeFg : ThemeBrushes.PlannedBadgeFg;
        titlePanel.Children.Add(new Border
        {
            Background = availBrush,
            CornerRadius = new CornerRadius(3),
            Padding = new Thickness(4, 1),
            Child = new TextBlock
            {
                Text = stage.Available ? "Registered" : "Planned (not runnable)",
                FontSize = 10,
                Foreground = availFg
            }
        });

        DockPanel.SetDock(titlePanel, Dock.Left);
        header.Children.Add(titlePanel);
        panel.Children.Add(header);

        if (!string.IsNullOrEmpty(stage.Description))
        {
            panel.Children.Add(new TextBlock
            {
                Text = stage.Description,
                Opacity = 0.7,
                FontSize = 11,
                TextWrapping = TextWrapping.Wrap
            });
        }

        // Stage execution properties: Name, Repeat, When
        var metaGrid = new Grid
        {
            ColumnDefinitions = new ColumnDefinitions("Auto,*,Auto,80"),
            RowDefinitions = new RowDefinitions("Auto,Auto"),
            Margin = new Thickness(0, 4)
        };

        // Name
        var lblName = new TextBlock { Text = "Stage name:", VerticalAlignment = VerticalAlignment.Center, FontSize = 11 };
        Grid.SetRow(lblName, 0);
        Grid.SetColumn(lblName, 0);
        metaGrid.Children.Add(lblName);

        var txtName = new TextBox
        {
            Text = currentStageObj["name"]?.GetValue<string>() ?? $"{stageIndex + 1}_{stage.Operator}",
            Margin = new Thickness(6, 2, 8, 2),
            FontSize = 11
        };
        txtName.TextChanged += (s, e) => onNameChanged(txtName.Text ?? "");
        Grid.SetRow(txtName, 0);
        Grid.SetColumn(txtName, 1);
        metaGrid.Children.Add(txtName);

        // Repeat (if repeatable)
        if (stage.Repeatable)
        {
            var lblRep = new TextBlock { Text = "Repeat:", VerticalAlignment = VerticalAlignment.Center, FontSize = 11 };
            Grid.SetRow(lblRep, 0);
            Grid.SetColumn(lblRep, 2);
            metaGrid.Children.Add(lblRep);

            var numRep = new NumericUpDown
            {
                Minimum = 1,
                Maximum = 100000,
                Value = currentStageObj["repeat"]?.GetValue<int>() ?? 1,
                FormatString = "0",
                Margin = new Thickness(6, 2, 0, 2),
                FontSize = 11
            };
            numRep.ValueChanged += (s, e) => onRepeatChanged((int)(numRep.Value ?? 1));
            Grid.SetRow(numRep, 0);
            Grid.SetColumn(numRep, 3);
            metaGrid.Children.Add(numRep);
        }

        // When condition (if conditional)
        if (stage.Conditional)
        {
            var lblWhen = new TextBlock { Text = "When condition:", VerticalAlignment = VerticalAlignment.Center, FontSize = 11, Margin = new Thickness(0, 4, 0, 0) };
            Grid.SetRow(lblWhen, 1);
            Grid.SetColumn(lblWhen, 0);
            metaGrid.Children.Add(lblWhen);

            var txtWhen = new TextBox
            {
                Text = currentStageObj["when"]?.GetValue<string>() ?? "",
                Watermark = "e.g. epoch == 10",
                Margin = new Thickness(6, 4, 0, 2),
                FontSize = 11
            };
            txtWhen.TextChanged += (s, e) => onWhenChanged(string.IsNullOrWhiteSpace(txtWhen.Text) ? null : txtWhen.Text);
            Grid.SetRow(txtWhen, 1);
            Grid.SetColumn(txtWhen, 1);
            Grid.SetColumnSpan(txtWhen, 3);
            metaGrid.Children.Add(txtWhen);
        }

        panel.Children.Add(metaGrid);

        // Cost preview
        if (stage.Cost != null)
        {
            panel.Children.Add(new Border
            {
                Background = ThemeBrushes.CardBackground,
                BorderBrush = ThemeBrushes.CardBorder,
                BorderThickness = new Thickness(1),
                CornerRadius = new CornerRadius(3),
                Padding = new Thickness(6, 3),
                Margin = new Thickness(0, 2),
                Child = new TextBlock
                {
                    Text = $"Cost: Declared = {stage.Cost.Declared}, Samples = {stage.Cost.Samples?.Count ?? 0}",
                    FontSize = 10,
                    Opacity = 0.6
                }
            });
        }

        // Parameter list
        var paramsObj = currentStageObj["params"] as JsonObject ?? new JsonObject();
        if (stage.Params != null && stage.Params.Count > 0)
        {
            panel.Children.Add(new TextBlock
            {
                Text = "Parameters",
                FontWeight = FontWeight.SemiBold,
                FontSize = 12,
                Margin = new Thickness(0, 4, 0, 2)
            });

            foreach (var p in stage.Params)
            {
                var row = CreateParamControl(p, paramsObj, paramSources, onParamChanged);
                panel.Children.Add(row);
            }
        }

        return panel;
    }

    public static Control CreateParamControl(
        ParamSpec param,
        JsonObject currentParams,
        IReadOnlyList<ParamSourceSpec>? paramSources,
        Action<string, JsonNode?> onParamChanged)
    {
        var card = new Border
        {
            Background = ThemeBrushes.CardBackground,
            BorderBrush = ThemeBrushes.CardBorder,
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(4),
            Padding = new Thickness(6),
            Margin = new Thickness(0, 2)
        };

        var root = new StackPanel { Spacing = 4 };

        // Header: Title + (?) Help + Units + Kind (Source) picker
        var header = new DockPanel();

        var titleBlock = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6, VerticalAlignment = VerticalAlignment.Center };
        titleBlock.Children.Add(new TextBlock
        {
            Text = param.Title,
            FontWeight = FontWeight.Medium,
            FontSize = 12,
            VerticalAlignment = VerticalAlignment.Center
        });

        if (!string.IsNullOrEmpty(param.Units))
        {
            titleBlock.Children.Add(new TextBlock
            {
                Text = $"({param.Units})",
                Opacity = 0.55,
                FontSize = 10,
                VerticalAlignment = VerticalAlignment.Center
            });
        }

        if (!string.IsNullOrEmpty(param.Doc))
        {
            var helpBtn = new TextBlock
            {
                Text = "(?)",
                Foreground = ThemeBrushes.HelpAccent,
                Cursor = new Avalonia.Input.Cursor(Avalonia.Input.StandardCursorType.Help),
                FontSize = 11,
                VerticalAlignment = VerticalAlignment.Center
            };
            ToolTip.SetTip(helpBtn, $"{param.Doc}\nType: {param.Type}" + (param.Min.HasValue || param.Max.HasValue ? $"\nBounds: [{param.Min} .. {param.Max}]" : ""));
            titleBlock.Children.Add(helpBtn);
        }

        DockPanel.SetDock(titleBlock, Dock.Left);
        header.Children.Add(titleBlock);

        // Determine available source types from schema param_sources and param.Sources
        string[] availableSourceTypes = (param.Sources != null && param.Sources.Count > 0)
            ? param.Sources.ToArray()
            : (paramSources != null && paramSources.Count > 0)
                ? paramSources.Select(ps => ps.Type).ToArray()
                : new[] { "Const" };

        var sourcePicker = new ComboBox
        {
            ItemsSource = availableSourceTypes,
            FontSize = 10,
            HorizontalAlignment = HorizontalAlignment.Right,
            Margin = new Thickness(4, 0, 0, 0)
        };
        DockPanel.SetDock(sourcePicker, Dock.Right);
        header.Children.Add(sourcePicker);

        root.Children.Add(header);

        // Current param state
        var paramObj = currentParams[param.Name] as JsonObject;
        string currentSource = paramObj?["type"]?.GetValue<string>() ?? "Const";
        if (!availableSourceTypes.Contains(currentSource))
            currentSource = availableSourceTypes.FirstOrDefault() ?? "Const";
        sourcePicker.SelectedItem = currentSource;

        var inputContainer = new ContentControl();
        root.Children.Add(inputContainer);

        ParamSourceSpec? FindSourceSpec(string srcType) =>
            paramSources?.FirstOrDefault(ps => ps.Type == srcType);

        void RenderInputs(string sourceKind)
        {
            var spec = FindSourceSpec(sourceKind);
            inputContainer.Content = CreateInputsForSource(sourceKind, param, spec, paramObj, updatedObj =>
            {
                paramObj = updatedObj;
                onParamChanged(param.Name, paramObj);
            });
        }

        RenderInputs(currentSource);

        sourcePicker.SelectionChanged += (s, e) =>
        {
            if (sourcePicker.SelectedItem is string newSource && newSource != currentSource)
            {
                currentSource = newSource;
                var spec = FindSourceSpec(newSource);
                var newObj = CreateDefaultParamForSource(newSource, param, spec);
                paramObj = newObj;
                onParamChanged(param.Name, paramObj);
                RenderInputs(newSource);
            }
        };

        card.Child = root;
        return card;
    }

    private static JsonObject CreateDefaultParamForSource(string source, ParamSpec param, ParamSourceSpec? sourceSpec)
    {
        var obj = new JsonObject { ["type"] = source };

        if (sourceSpec?.Inputs != null && sourceSpec.Inputs.Count > 0)
        {
            foreach (var inp in sourceSpec.Inputs)
            {
                if (inp.Type == "value")
                {
                    if (param.Default != null && param.Default is JsonObject defObj && defObj["value"] != null)
                        obj["value"] = defObj["value"]!.DeepClone();
                    else
                        obj["value"] = GetDefaultValueNode(param);
                }
                else if (inp.Type == "bool")
                {
                    obj[inp.Name] = false;
                }
                else if (inp.Type == "float" || inp.Type == "int")
                {
                    obj[inp.Name] = 0;
                }
                else
                {
                    obj[inp.Name] = "";
                }
            }
        }
        else
        {
            if (source == "Const")
            {
                obj["value"] = GetDefaultValueNode(param);
            }
        }

        return obj;
    }

    private static JsonNode? GetDefaultValueNode(ParamSpec param) => param.Type switch
    {
        "int" => 0,
        "float" => 0.0,
        "bool" => false,
        "choice" => param.Choices?.FirstOrDefault()?.Value ?? "",
        "vec3" => new JsonArray { 0.0, 0.0, 0.0 },
        "string" => "",
        _ => null
    };

    private static Control CreateInputsForSource(
        string source,
        ParamSpec param,
        ParamSourceSpec? sourceSpec,
        JsonObject? currentObj,
        Action<JsonObject> onUpdated)
    {
        var workingObj = currentObj?.DeepClone() as JsonObject ?? CreateDefaultParamForSource(source, param, sourceSpec);

        // If no schema inputs defined, fall back to raw JSON
        if (sourceSpec?.Inputs == null || sourceSpec.Inputs.Count == 0)
        {
            if (source == "Const")
            {
                return CreateValueInput(param, workingObj, onUpdated);
            }

            var rawBox = new TextBox
            {
                Text = workingObj.ToJsonString(),
                FontSize = 11,
                AcceptsReturn = true
            };
            rawBox.TextChanged += (s, e) =>
            {
                try
                {
                    if (JsonNode.Parse(rawBox.Text ?? "{}") is JsonObject parsed)
                    {
                        workingObj = parsed;
                        onUpdated(workingObj);
                    }
                }
                catch { }
            };
            return rawBox;
        }

        // Build controls dynamically according to param_sources[].inputs
        var container = new StackPanel { Spacing = 4, Margin = new Thickness(0, 2) };

        foreach (var inp in sourceSpec.Inputs)
        {
            var row = new DockPanel { Margin = new Thickness(0, 1) };
            var label = new TextBlock
            {
                Text = inp.Name + ":",
                Width = 70,
                FontSize = 11,
                VerticalAlignment = VerticalAlignment.Center,
                Opacity = 0.8
            };
            if (!string.IsNullOrEmpty(inp.Doc)) ToolTip.SetTip(label, inp.Doc);
            DockPanel.SetDock(label, Dock.Left);
            row.Children.Add(label);

            Control inputCtrl;
            switch (inp.Type)
            {
                case "value":
                    inputCtrl = CreateValueInput(param, workingObj, onUpdated);
                    break;

                case "float":
                {
                    var num = new NumericUpDown
                    {
                        Value = (decimal)(workingObj[inp.Name]?.GetValue<double>() ?? 0.0),
                        Increment = 0.1m,
                        FormatString = "0.###",
                        FontSize = 11
                    };
                    num.ValueChanged += (s, e) =>
                    {
                        workingObj[inp.Name] = (double)(num.Value ?? 0m);
                        onUpdated(workingObj);
                    };
                    inputCtrl = num;
                    break;
                }

                case "int":
                {
                    var num = new NumericUpDown
                    {
                        Value = workingObj[inp.Name]?.GetValue<int>() ?? 0,
                        Increment = 1,
                        FormatString = "0",
                        FontSize = 11
                    };
                    num.ValueChanged += (s, e) =>
                    {
                        workingObj[inp.Name] = (int)(num.Value ?? 0);
                        onUpdated(workingObj);
                    };
                    inputCtrl = num;
                    break;
                }

                case "bool":
                {
                    var chk = new CheckBox
                    {
                        IsChecked = workingObj[inp.Name]?.GetValue<bool>() ?? false,
                        FontSize = 11
                    };
                    chk.IsCheckedChanged += (s, e) =>
                    {
                        workingObj[inp.Name] = chk.IsChecked ?? false;
                        onUpdated(workingObj);
                    };
                    inputCtrl = chk;
                    break;
                }

                case "string":
                case "gene_path":
                case "field":
                {
                    var txt = new TextBox
                    {
                        Text = workingObj[inp.Name]?.GetValue<string>() ?? "",
                        FontSize = 11
                    };
                    txt.TextChanged += (s, e) =>
                    {
                        workingObj[inp.Name] = txt.Text ?? "";
                        onUpdated(workingObj);
                    };
                    inputCtrl = txt;
                    break;
                }

                default:
                {
                    // Unknown input type: render raw JSON text box
                    var txt = new TextBox
                    {
                        Text = workingObj[inp.Name]?.ToJsonString() ?? "",
                        FontSize = 11
                    };
                    txt.TextChanged += (s, e) =>
                    {
                        try
                        {
                            workingObj[inp.Name] = JsonNode.Parse(txt.Text ?? "null");
                            onUpdated(workingObj);
                        }
                        catch { }
                    };
                    inputCtrl = txt;
                    break;
                }
            }

            row.Children.Add(inputCtrl);
            container.Children.Add(row);
        }

        return container;
    }

    private static Control CreateValueInput(
        ParamSpec param,
        JsonObject workingObj,
        Action<JsonObject> onUpdated)
    {
        var val = workingObj["value"];

        switch (param.Type)
        {
            case "int":
            {
                var num = new NumericUpDown
                {
                    Minimum = param.Min != null ? (decimal)param.Min : decimal.MinValue,
                    Maximum = param.Max != null ? (decimal)param.Max : decimal.MaxValue,
                    Increment = param.Step != null ? (decimal)param.Step : 1,
                    Value = val is JsonValue jv && jv.TryGetValue<int>(out var iVal) ? iVal : 0,
                    FormatString = "0",
                    FontSize = 11
                };
                num.ValueChanged += (s, e) =>
                {
                    workingObj["value"] = (int)(num.Value ?? 0);
                    onUpdated(workingObj);
                };
                return num;
            }

            case "float":
            {
                var num = new NumericUpDown
                {
                    Minimum = param.Min != null ? (decimal)param.Min : decimal.MinValue,
                    Maximum = param.Max != null ? (decimal)param.Max : decimal.MaxValue,
                    Increment = param.Step != null ? (decimal)param.Step : 0.01m,
                    Value = val is JsonValue jv && jv.TryGetValue<double>(out var dVal) ? (decimal)dVal : 0m,
                    FormatString = "0.####",
                    FontSize = 11
                };
                num.ValueChanged += (s, e) =>
                {
                    workingObj["value"] = (double)(num.Value ?? 0);
                    onUpdated(workingObj);
                };
                return num;
            }

            case "bool":
            {
                var chk = new CheckBox
                {
                    IsChecked = val is JsonValue jv && jv.TryGetValue<bool>(out var bVal) && bVal,
                    FontSize = 11
                };
                chk.IsCheckedChanged += (s, e) =>
                {
                    workingObj["value"] = chk.IsChecked ?? false;
                    onUpdated(workingObj);
                };
                return chk;
            }

            case "choice":
            {
                var combo = new ComboBox
                {
                    ItemsSource = param.Choices?.Select(c => c.Value).ToArray() ?? Array.Empty<string>(),
                    SelectedItem = val is JsonValue jv && jv.TryGetValue<string>(out var sVal) ? sVal : param.Choices?.FirstOrDefault()?.Value,
                    FontSize = 11
                };
                combo.SelectionChanged += (s, e) =>
                {
                    if (combo.SelectedItem is string choice)
                    {
                        workingObj["value"] = choice;
                        onUpdated(workingObj);
                    }
                };
                return combo;
            }

            case "vec3":
            {
                var grid = new Grid { ColumnDefinitions = new ColumnDefinitions("*,*,*") };
                var arr = val as JsonArray;
                double x = arr != null && arr.Count > 0 ? arr[0]?.GetValue<double>() ?? 0 : 0;
                double y = arr != null && arr.Count > 1 ? arr[1]?.GetValue<double>() ?? 0 : 0;
                double z = arr != null && arr.Count > 2 ? arr[2]?.GetValue<double>() ?? 0 : 0;

                var numX = new NumericUpDown { Value = (decimal)x, FormatString = "0.##", Margin = new Thickness(0, 0, 2, 0), FontSize = 10 };
                var numY = new NumericUpDown { Value = (decimal)y, FormatString = "0.##", Margin = new Thickness(2, 0, 2, 0), FontSize = 10 };
                var numZ = new NumericUpDown { Value = (decimal)z, FormatString = "0.##", Margin = new Thickness(2, 0, 0, 0), FontSize = 10 };

                void UpdateVec()
                {
                    var a = new JsonArray
                    {
                        (double)(numX.Value ?? 0),
                        (double)(numY.Value ?? 0),
                        (double)(numZ.Value ?? 0)
                    };
                    workingObj["value"] = a;
                    onUpdated(workingObj);
                }

                numX.ValueChanged += (s, e) => UpdateVec();
                numY.ValueChanged += (s, e) => UpdateVec();
                numZ.ValueChanged += (s, e) => UpdateVec();

                Grid.SetColumn(numX, 0);
                Grid.SetColumn(numY, 1);
                Grid.SetColumn(numZ, 2);
                grid.Children.Add(numX);
                grid.Children.Add(numY);
                grid.Children.Add(numZ);
                return grid;
            }

            case "string":
            {
                string text = val is JsonValue jv && jv.TryGetValue<string>(out var s) ? s : (val?.ToJsonString() ?? "");
                var txt = new TextBox
                {
                    Text = text,
                    FontSize = 11
                };
                txt.TextChanged += (s, e) =>
                {
                    workingObj["value"] = txt.Text ?? "";
                    onUpdated(workingObj);
                };
                return txt;
            }

            default:
            {
                // UI_SCHEMA.md §1: show unknown parameter types as read-only JSON, never crash
                var txt = new TextBox
                {
                    Text = val?.ToJsonString() ?? "{}",
                    FontSize = 11,
                    IsReadOnly = true,
                    Opacity = 0.85
                };
                return txt;
            }
        }
    }
}
