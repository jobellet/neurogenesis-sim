using System.Text.Json.Nodes;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Neurogenesis.Core.Schema;

namespace Neurogenesis.App.Controls;

/// <summary>
/// Dynamically generates editor controls for stages, schedules and parameters
/// conforming strictly to UI_SCHEMA.md 1.0 (task Step 4).
/// All edits update the underlying Project JSON directly without hidden state.
/// </summary>
public static class DynamicPanelGenerator
{
    private static readonly string[] AllSources = { "Const", "Gene", "Field", "Fit", "Expr" };

    public static Control CreateStageEditor(
        StageSpec stage,
        int stageIndex,
        JsonObject currentStageObj,
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
            Background = new SolidColorBrush(Color.FromArgb(50, 100, 150, 255)),
            CornerRadius = new CornerRadius(3),
            Padding = new Thickness(4, 1),
            Child = new TextBlock
            {
                Text = stage.Task,
                FontSize = 10,
                Foreground = new SolidColorBrush(Color.FromRgb(150, 200, 255))
            }
        });

        // Availability badge
        var availBrush = stage.Available
            ? new SolidColorBrush(Color.FromArgb(60, 40, 180, 80))
            : new SolidColorBrush(Color.FromArgb(60, 220, 120, 30));
        var availFg = stage.Available
            ? new SolidColorBrush(Color.FromRgb(90, 220, 130))
            : new SolidColorBrush(Color.FromRgb(255, 170, 70));
        titlePanel.Children.Add(new Border
        {
            Background = availBrush,
            CornerRadius = new CornerRadius(3),
            Padding = new Thickness(4, 1),
            Child = new TextBlock
            {
                Text = stage.Available ? "Registered" : "Planned",
                FontSize = 10,
                Foreground = availFg
            }
        });

        DockPanel.SetDock(titlePanel, Dock.Left);
        header.Children.Add(titlePanel);
        panel.Children.Add(header);

        // Description
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

        // Cost scaling badge if declared
        if (stage.Cost is { Declared: true, Samples: { Count: > 0 } })
        {
            var firstSample = stage.Cost.Samples[0];
            int n = firstSample?["N"]?.GetValue<int>() ?? 0;
            int ops = firstSample?["ops"]?.GetValue<int>() ?? 0;
            long bytes = firstSample?["bytes"]?.GetValue<long>() ?? 0;

            var costText = new TextBlock
            {
                Text = $"Cost (N={n:N0}): ~{ops:N0} ops, {bytes / 1024:N0} KB",
                FontSize = 10,
                Opacity = 0.55
            };
            panel.Children.Add(costText);
        }

        // Stage execution properties: Name, Repeat, Condition (When)
        var metaGrid = new Grid
        {
            ColumnDefinitions = new ColumnDefinitions("60,*,70,60"),
            RowDefinitions = new RowDefinitions("Auto,Auto"),
            Margin = new Thickness(0, 4)
        };

        // Name
        var nameLabel = new TextBlock { Text = "Name:", VerticalAlignment = VerticalAlignment.Center, FontSize = 11, Opacity = 0.8 };
        Grid.SetRow(nameLabel, 0);
        Grid.SetColumn(nameLabel, 0);
        metaGrid.Children.Add(nameLabel);

        string currentName = currentStageObj["name"]?.GetValue<string>() ?? $"{stageIndex + 1}_{stage.Operator}";
        var nameBox = new TextBox { Text = currentName, FontSize = 11, Margin = new Thickness(0, 2, 8, 2) };
        nameBox.TextChanged += (s, e) => onNameChanged(nameBox.Text ?? "");
        Grid.SetRow(nameBox, 0);
        Grid.SetColumn(nameBox, 1);
        metaGrid.Children.Add(nameBox);

        // Repeat
        var repLabel = new TextBlock { Text = "Repeat:", VerticalAlignment = VerticalAlignment.Center, FontSize = 11, Opacity = 0.8 };
        Grid.SetRow(repLabel, 0);
        Grid.SetColumn(repLabel, 2);
        metaGrid.Children.Add(repLabel);

        int currentRepeat = currentStageObj["repeat"]?.GetValue<int>() ?? 1;
        var repNum = new NumericUpDown
        {
            Minimum = 1,
            Maximum = 10000,
            Increment = 1,
            FormatString = "0",
            Value = currentRepeat,
            FontSize = 11,
            IsEnabled = stage.Repeatable,
            Margin = new Thickness(0, 2, 0, 2)
        };
        repNum.ValueChanged += (s, e) =>
        {
            if (repNum.Value.HasValue) onRepeatChanged((int)repNum.Value.Value);
        };
        Grid.SetRow(repNum, 0);
        Grid.SetColumn(repNum, 3);
        metaGrid.Children.Add(repNum);

        // When (condition) if conditional
        if (stage.Conditional)
        {
            var whenLabel = new TextBlock { Text = "When:", VerticalAlignment = VerticalAlignment.Center, FontSize = 11, Opacity = 0.8 };
            Grid.SetRow(whenLabel, 1);
            Grid.SetColumn(whenLabel, 0);
            metaGrid.Children.Add(whenLabel);

            string currentWhen = currentStageObj["when"]?.GetValue<string>() ?? "";
            var whenBox = new TextBox
            {
                Text = currentWhen,
                FontSize = 11,
                Watermark = "e.g. rep < 5 (optional condition)",
                Margin = new Thickness(0, 2, 0, 2)
            };
            whenBox.TextChanged += (s, e) => onWhenChanged(string.IsNullOrWhiteSpace(whenBox.Text) ? null : whenBox.Text);
            Grid.SetRow(whenBox, 1);
            Grid.SetColumn(whenBox, 1);
            Grid.SetColumnSpan(whenBox, 3);
            metaGrid.Children.Add(whenBox);
        }

        panel.Children.Add(metaGrid);

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
                var row = CreateParamControl(p, paramsObj, onParamChanged);
                panel.Children.Add(row);
            }
        }

        return panel;
    }

    public static Control CreateParamControl(ParamSpec param, JsonObject currentParams, Action<string, JsonNode?> onParamChanged)
    {
        var card = new Border
        {
            Background = new SolidColorBrush(Color.FromArgb(25, 255, 255, 255)),
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
                Foreground = new SolidColorBrush(Color.FromRgb(120, 170, 240)),
                Cursor = new Avalonia.Input.Cursor(Avalonia.Input.StandardCursorType.Help),
                FontSize = 11,
                VerticalAlignment = VerticalAlignment.Center
            };
            ToolTip.SetTip(helpBtn, $"{param.Doc}\nType: {param.Type}" + (param.Min.HasValue || param.Max.HasValue ? $"\nBounds: [{param.Min} .. {param.Max}]" : ""));
            titleBlock.Children.Add(helpBtn);
        }

        DockPanel.SetDock(titleBlock, Dock.Left);
        header.Children.Add(titleBlock);

        // Source Switcher (Const / Gene / Field / Fit / Expr)
        var allowedSources = param.Sources != null && param.Sources.Count > 0 ? param.Sources.ToArray() : AllSources;
        var sourcePicker = new ComboBox
        {
            ItemsSource = allowedSources,
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
        if (!allowedSources.Contains(currentSource))
            currentSource = allowedSources.FirstOrDefault() ?? "Const";
        sourcePicker.SelectedItem = currentSource;

        var inputContainer = new ContentControl();
        root.Children.Add(inputContainer);

        void RenderInputs(string sourceKind)
        {
            inputContainer.Content = CreateInputsForSource(sourceKind, param, paramObj, updatedObj =>
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
                var newObj = CreateDefaultParamForSource(newSource, param);
                paramObj = newObj;
                onParamChanged(param.Name, paramObj);
                RenderInputs(newSource);
            }
        };

        card.Child = root;
        return card;
    }

    private static JsonObject CreateDefaultParamForSource(string source, ParamSpec param)
    {
        var obj = new JsonObject { ["type"] = source };
        switch (source)
        {
            case "Gene":
                obj["path"] = $"genes/{param.Name}";
                obj["lo"] = param.Min ?? 0.0;
                obj["hi"] = param.Max ?? 10.0;
                obj["integer"] = param.Type == "int";
                break;
            case "Field":
                obj["name"] = "default_field";
                obj["transform"] = "x";
                break;
            case "Fit":
                obj["target"] = param.Name;
                obj["init"] = param.Min ?? 1.0;
                obj["lo"] = param.Min ?? 0.0;
                obj["hi"] = param.Max ?? 10.0;
                break;
            case "Expr":
                obj["formula"] = "1.0";
                break;
            case "Const":
            default:
                if (param.Default != null && param.Default is JsonObject defObj && defObj["value"] != null)
                {
                    obj["value"] = defObj["value"]!.DeepClone();
                }
                else
                {
                    obj["value"] = param.Type switch
                    {
                        "int" => 0,
                        "float" => 0.0,
                        "bool" => false,
                        "choice" => param.Choices?.FirstOrDefault()?.Value ?? "",
                        _ => ""
                    };
                }
                break;
        }
        return obj;
    }

    private static Control CreateInputsForSource(
        string source,
        ParamSpec param,
        JsonObject? currentObj,
        Action<JsonObject> onUpdated)
    {
        var workingObj = currentObj?.DeepClone() as JsonObject ?? CreateDefaultParamForSource(source, param);

        switch (source)
        {
            case "Gene":
            {
                var grid = new Grid
                {
                    ColumnDefinitions = new ColumnDefinitions("Auto,*,Auto,60,Auto,60,Auto"),
                    Margin = new Thickness(0, 2)
                };

                // Path
                var lblPath = new TextBlock { Text = "Path:", VerticalAlignment = VerticalAlignment.Center, FontSize = 11, Margin = new Thickness(0, 0, 4, 0) };
                Grid.SetColumn(lblPath, 0);
                grid.Children.Add(lblPath);

                var txtPath = new TextBox { Text = workingObj["path"]?.GetValue<string>() ?? "", FontSize = 11, Margin = new Thickness(0, 0, 6, 0) };
                txtPath.TextChanged += (s, e) =>
                {
                    workingObj["path"] = txtPath.Text ?? "";
                    onUpdated(workingObj);
                };
                Grid.SetColumn(txtPath, 1);
                grid.Children.Add(txtPath);

                // Lo
                var lblLo = new TextBlock { Text = "Lo:", VerticalAlignment = VerticalAlignment.Center, FontSize = 11, Margin = new Thickness(0, 0, 4, 0) };
                Grid.SetColumn(lblLo, 2);
                grid.Children.Add(lblLo);

                var numLo = new NumericUpDown
                {
                    Value = ToDecimal(workingObj["lo"]?.GetValue<double>() ?? (param.Min ?? 0.0), 0m),
                    FontSize = 11,
                    Increment = ToDecimal(param.Step, 0.1m),
                    FormatString = "0.##",
                    Margin = new Thickness(0, 0, 6, 0)
                };
                numLo.ValueChanged += (s, e) =>
                {
                    if (numLo.Value.HasValue)
                    {
                        workingObj["lo"] = (double)numLo.Value.Value;
                        onUpdated(workingObj);
                    }
                };
                Grid.SetColumn(numLo, 3);
                grid.Children.Add(numLo);

                // Hi
                var lblHi = new TextBlock { Text = "Hi:", VerticalAlignment = VerticalAlignment.Center, FontSize = 11, Margin = new Thickness(0, 0, 4, 0) };
                Grid.SetColumn(lblHi, 4);
                grid.Children.Add(lblHi);

                var numHi = new NumericUpDown
                {
                    Value = ToDecimal(workingObj["hi"]?.GetValue<double>() ?? (param.Max ?? 10.0), 10m),
                    FontSize = 11,
                    Increment = ToDecimal(param.Step, 0.1m),
                    FormatString = "0.##",
                    Margin = new Thickness(0, 0, 6, 0)
                };
                numHi.ValueChanged += (s, e) =>
                {
                    if (numHi.Value.HasValue)
                    {
                        workingObj["hi"] = (double)numHi.Value.Value;
                        onUpdated(workingObj);
                    }
                };
                Grid.SetColumn(numHi, 5);
                grid.Children.Add(numHi);

                // Integer toggle
                var chkInt = new CheckBox
                {
                    Content = "int",
                    IsChecked = workingObj["integer"]?.GetValue<bool>() ?? (param.Type == "int"),
                    FontSize = 11
                };
                chkInt.IsCheckedChanged += (s, e) =>
                {
                    workingObj["integer"] = chkInt.IsChecked ?? false;
                    onUpdated(workingObj);
                };
                Grid.SetColumn(chkInt, 6);
                grid.Children.Add(chkInt);

                return grid;
            }

            case "Field":
            {
                var grid = new Grid
                {
                    ColumnDefinitions = new ColumnDefinitions("Auto,*,Auto,*"),
                    Margin = new Thickness(0, 2)
                };

                var lblField = new TextBlock { Text = "Field:", VerticalAlignment = VerticalAlignment.Center, FontSize = 11, Margin = new Thickness(0, 0, 4, 0) };
                Grid.SetColumn(lblField, 0);
                grid.Children.Add(lblField);

                var txtField = new TextBox { Text = workingObj["name"]?.GetValue<string>() ?? "", FontSize = 11, Margin = new Thickness(0, 0, 6, 0) };
                txtField.TextChanged += (s, e) =>
                {
                    workingObj["name"] = txtField.Text ?? "";
                    onUpdated(workingObj);
                };
                Grid.SetColumn(txtField, 1);
                grid.Children.Add(txtField);

                var lblTrans = new TextBlock { Text = "Transform:", VerticalAlignment = VerticalAlignment.Center, FontSize = 11, Margin = new Thickness(0, 0, 4, 0) };
                Grid.SetColumn(lblTrans, 2);
                grid.Children.Add(lblTrans);

                var txtTrans = new TextBox { Text = workingObj["transform"]?.GetValue<string>() ?? "x", FontSize = 11 };
                txtTrans.TextChanged += (s, e) =>
                {
                    workingObj["transform"] = txtTrans.Text ?? "";
                    onUpdated(workingObj);
                };
                Grid.SetColumn(txtTrans, 3);
                grid.Children.Add(txtTrans);

                return grid;
            }

            case "Fit":
            {
                var grid = new Grid
                {
                    ColumnDefinitions = new ColumnDefinitions("Auto,*,Auto,55,Auto,55,Auto,55"),
                    Margin = new Thickness(0, 2)
                };

                var lblTarget = new TextBlock { Text = "Target:", VerticalAlignment = VerticalAlignment.Center, FontSize = 11, Margin = new Thickness(0, 0, 4, 0) };
                Grid.SetColumn(lblTarget, 0);
                grid.Children.Add(lblTarget);

                var txtTarget = new TextBox { Text = workingObj["target"]?.GetValue<string>() ?? "", FontSize = 11, Margin = new Thickness(0, 0, 4, 0) };
                txtTarget.TextChanged += (s, e) =>
                {
                    workingObj["target"] = txtTarget.Text ?? "";
                    onUpdated(workingObj);
                };
                Grid.SetColumn(txtTarget, 1);
                grid.Children.Add(txtTarget);

                var lblInit = new TextBlock { Text = "Init:", VerticalAlignment = VerticalAlignment.Center, FontSize = 11, Margin = new Thickness(0, 0, 2, 0) };
                Grid.SetColumn(lblInit, 2);
                grid.Children.Add(lblInit);

                var numInit = new NumericUpDown
                {
                    Value = ToDecimal(workingObj["init"]?.GetValue<double>() ?? (param.Min ?? 1.0), 1m),
                    FontSize = 10,
                    FormatString = "0.##",
                    Margin = new Thickness(0, 0, 4, 0)
                };
                numInit.ValueChanged += (s, e) =>
                {
                    if (numInit.Value.HasValue)
                    {
                        workingObj["init"] = (double)numInit.Value.Value;
                        onUpdated(workingObj);
                    }
                };
                Grid.SetColumn(numInit, 3);
                grid.Children.Add(numInit);

                var lblLo = new TextBlock { Text = "Lo:", VerticalAlignment = VerticalAlignment.Center, FontSize = 11, Margin = new Thickness(0, 0, 2, 0) };
                Grid.SetColumn(lblLo, 4);
                grid.Children.Add(lblLo);

                var numLo = new NumericUpDown
                {
                    Value = ToDecimal(workingObj["lo"]?.GetValue<double>() ?? (param.Min ?? 0.0), 0m),
                    FontSize = 10,
                    FormatString = "0.##",
                    Margin = new Thickness(0, 0, 4, 0)
                };
                numLo.ValueChanged += (s, e) =>
                {
                    if (numLo.Value.HasValue)
                    {
                        workingObj["lo"] = (double)numLo.Value.Value;
                        onUpdated(workingObj);
                    }
                };
                Grid.SetColumn(numLo, 5);
                grid.Children.Add(numLo);

                var lblHi = new TextBlock { Text = "Hi:", VerticalAlignment = VerticalAlignment.Center, FontSize = 11, Margin = new Thickness(0, 0, 2, 0) };
                Grid.SetColumn(lblHi, 6);
                grid.Children.Add(lblHi);

                var numHi = new NumericUpDown
                {
                    Value = ToDecimal(workingObj["hi"]?.GetValue<double>() ?? (param.Max ?? 10.0), 10m),
                    FontSize = 10,
                    FormatString = "0.##"
                };
                numHi.ValueChanged += (s, e) =>
                {
                    if (numHi.Value.HasValue)
                    {
                        workingObj["hi"] = (double)numHi.Value.Value;
                        onUpdated(workingObj);
                    }
                };
                Grid.SetColumn(numHi, 7);
                grid.Children.Add(numHi);

                return grid;
            }

            case "Expr":
            {
                var grid = new Grid
                {
                    ColumnDefinitions = new ColumnDefinitions("Auto,*"),
                    Margin = new Thickness(0, 2)
                };

                var lblFormula = new TextBlock { Text = "Formula:", VerticalAlignment = VerticalAlignment.Center, FontSize = 11, Margin = new Thickness(0, 0, 4, 0) };
                Grid.SetColumn(lblFormula, 0);
                grid.Children.Add(lblFormula);

                var txtFormula = new TextBox { Text = workingObj["formula"]?.GetValue<string>() ?? "", FontSize = 11 };
                txtFormula.TextChanged += (s, e) =>
                {
                    workingObj["formula"] = txtFormula.Text ?? "";
                    onUpdated(workingObj);
                };
                Grid.SetColumn(txtFormula, 1);
                grid.Children.Add(txtFormula);

                return grid;
            }

            case "Const":
            default:
            {
                return CreateConstWidget(param, workingObj, onUpdated);
            }
        }
    }

    private static decimal ToDecimal(double? val, decimal fallback)
    {
        if (!val.HasValue || double.IsNaN(val.Value) || double.IsInfinity(val.Value)) return fallback;
        if (val.Value <= (double)decimal.MinValue) return decimal.MinValue;
        if (val.Value >= (double)decimal.MaxValue) return decimal.MaxValue;
        return (decimal)val.Value;
    }

    private static Control CreateConstWidget(ParamSpec param, JsonObject workingObj, Action<JsonObject> onUpdated)
    {
        JsonNode? val = null;
        workingObj.TryGetPropertyValue("value", out val);

        switch (param.Type)
        {
            case "bool":
            {
                var toggle = new CheckBox
                {
                    Content = param.Title,
                    IsChecked = val?.GetValue<bool>() ?? false,
                    FontSize = 11
                };
                toggle.IsCheckedChanged += (s, e) =>
                {
                    workingObj["value"] = toggle.IsChecked ?? false;
                    onUpdated(workingObj);
                };
                return toggle;
            }

            case "int":
            {
                var num = new NumericUpDown
                {
                    Minimum = ToDecimal(param.Min, -1000000m),
                    Maximum = ToDecimal(param.Max, 1000000m),
                    Increment = ToDecimal(param.Step, 1m),
                    FormatString = "0",
                    Value = (decimal)(val?.GetValue<long>() ?? (long)(param.Min ?? 0)),
                    FontSize = 11
                };
                num.ValueChanged += (s, e) =>
                {
                    if (num.Value.HasValue)
                    {
                        workingObj["value"] = (long)num.Value.Value;
                        onUpdated(workingObj);
                    }
                };
                return num;
            }

            case "float":
            {
                var num = new NumericUpDown
                {
                    Minimum = ToDecimal(param.Min, -1000000m),
                    Maximum = ToDecimal(param.Max, 1000000m),
                    Increment = ToDecimal(param.Step, 0.01m),
                    FormatString = "0.###",
                    Value = ToDecimal(val?.GetValue<double>() ?? (param.Min ?? 0.0), 0m),
                    FontSize = 11
                };
                num.ValueChanged += (s, e) =>
                {
                    if (num.Value.HasValue)
                    {
                        workingObj["value"] = (double)num.Value.Value;
                        onUpdated(workingObj);
                    }
                };
                return num;
            }

            case "choice":
            {
                var combo = new ComboBox { FontSize = 11 };
                if (param.Choices != null)
                {
                    combo.ItemsSource = param.Choices;
                    combo.SelectedItem = param.Choices.FirstOrDefault(c => c.Value == val?.GetValue<string>());
                }
                combo.SelectionChanged += (s, e) =>
                {
                    if (combo.SelectedItem is ParamChoice sel)
                    {
                        workingObj["value"] = sel.Value;
                        onUpdated(workingObj);
                    }
                };
                return combo;
            }

            case "vec3":
            {
                var grid = new Grid { ColumnDefinitions = new ColumnDefinitions("*,*,*") };
                double vx = 0, vy = 0, vz = 0;
                if (val is JsonArray arr && arr.Count >= 3)
                {
                    vx = arr[0]?.GetValue<double>() ?? 0;
                    vy = arr[1]?.GetValue<double>() ?? 0;
                    vz = arr[2]?.GetValue<double>() ?? 0;
                }

                var numX = new NumericUpDown { Value = ToDecimal(vx, 0m), Watermark = "X", FontSize = 10, Margin = new Thickness(0, 0, 2, 0) };
                var numY = new NumericUpDown { Value = ToDecimal(vy, 0m), Watermark = "Y", FontSize = 10, Margin = new Thickness(0, 0, 2, 0) };
                var numZ = new NumericUpDown { Value = ToDecimal(vz, 0m), Watermark = "Z", FontSize = 10 };

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
            default:
            {
                var txt = new TextBox
                {
                    Text = val?.GetValue<string>() ?? "",
                    FontSize = 11
                };
                txt.TextChanged += (s, e) =>
                {
                    workingObj["value"] = txt.Text ?? "";
                    onUpdated(workingObj);
                };
                return txt;
            }
        }
    }
}
