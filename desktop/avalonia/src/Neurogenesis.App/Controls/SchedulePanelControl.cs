using System.Text.Json.Nodes;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Neurogenesis.App.Style;
using Neurogenesis.App.ViewModels;
using Neurogenesis.Core.Schema;

namespace Neurogenesis.App.Controls;

/// <summary>
/// Dynamic Schedule editor generated directly from UI_SCHEMA.md 1.0 specifications.
/// Displays the stage catalogue, stage list with reordering/removal, and parameter editors.
/// </summary>
public sealed class SchedulePanelControl : UserControl
{
    private MainViewModel? _vm;
    private bool _isRebuilding;
    private readonly StackPanel _stageListPanel = new() { Spacing = 6 };
    private readonly ComboBox _stageCataloguePicker = new() { HorizontalAlignment = HorizontalAlignment.Stretch, FontSize = 11 };
    private readonly Button _addStageBtn = new() { Content = "+ Add Stage", FontSize = 11 };
    private readonly TextBlock _costSummaryText = new() { FontSize = 11, Opacity = 0.7, Margin = new Thickness(0, 4) };

    public SchedulePanelControl()
    {
        var root = new DockPanel { Margin = new Thickness(6) };

        // Top toolbar: Add stage from catalogue
        var addBar = new DockPanel { Margin = new Thickness(0, 0, 0, 8) };
        DockPanel.SetDock(_addStageBtn, Dock.Right);
        _addStageBtn.Click += (s, e) =>
        {
            if (_stageCataloguePicker.SelectedItem is StageSpec sel && _vm != null)
            {
                _vm.AddStage(sel);
            }
        };
        addBar.Children.Add(_addStageBtn);
        addBar.Children.Add(_stageCataloguePicker);
        DockPanel.SetDock(addBar, Dock.Top);
        root.Children.Add(addBar);

        // Cost summary
        DockPanel.SetDock(_costSummaryText, Dock.Bottom);
        root.Children.Add(_costSummaryText);

        // Scrollable stage list
        var scroll = new ScrollViewer { Content = _stageListPanel };
        root.Children.Add(scroll);

        Content = root;

        DataContextChanged += (s, e) =>
        {
            if (_vm != null)
            {
                _vm.Project.DocumentChanged -= OnDocumentChanged;
            }

            _vm = DataContext as MainViewModel;
            if (_vm != null)
            {
                _vm.Project.DocumentChanged += OnDocumentChanged;
                if (_vm.UiSchema != null)
                {
                    _stageCataloguePicker.ItemsSource = _vm.UiSchema.Stages;
                    _stageCataloguePicker.SelectedItem = _vm.UiSchema.Stages.FirstOrDefault();
                }
                RebuildList();
            }
        };
    }

    private void OnDocumentChanged(object? sender, EventArgs e)
    {
        if (_isRebuilding) return;
        Avalonia.Threading.Dispatcher.UIThread.Post(RebuildList);
    }

    public void RebuildList()
    {
        if (_isRebuilding) return;
        _isRebuilding = true;

        try
        {
            _stageListPanel.Children.Clear();
            if (_vm == null) return;

            var schedule = _vm.Project.Schedule;
            int count = schedule.Count;
            _costSummaryText.Text = $"Total stages: {count}";

            for (int i = 0; i < count; i++)
            {
                int index = i;
                if (schedule[index] is not JsonObject stageObj) continue;

                string opName = stageObj["operator"]?.GetValue<string>() ?? "";
                var stageSpec = _vm.UiSchema?.Stages.FirstOrDefault(s => s.Operator == opName);

                var stageCard = new Border
                {
                    Background = ThemeBrushes.CardBackground,
                    BorderBrush = ThemeBrushes.CardBorder,
                    BorderThickness = new Thickness(1),
                    CornerRadius = new CornerRadius(5),
                    Padding = new Thickness(8),
                    Margin = new Thickness(0, 2)
                };

                var cardStack = new StackPanel { Spacing = 6 };

                // Stage header bar: Index + Operator Title + Reorder buttons + Remove button
                var headerDock = new DockPanel();

                var actionButtons = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 4 };
                DockPanel.SetDock(actionButtons, Dock.Right);

                var btnUp = new Button
                {
                    Content = "▲",
                    FontSize = 10,
                    Padding = new Thickness(4, 2),
                    IsEnabled = index > 0
                };
                btnUp.Click += (s, e) => _vm.MoveStage(index, index - 1);
                actionButtons.Children.Add(btnUp);

                var btnDown = new Button
                {
                    Content = "▼",
                    FontSize = 10,
                    Padding = new Thickness(4, 2),
                    IsEnabled = index < count - 1
                };
                btnDown.Click += (s, e) => _vm.MoveStage(index, index + 1);
                actionButtons.Children.Add(btnDown);

                var btnRemove = new Button
                {
                    Content = "✕",
                    FontSize = 10,
                    Foreground = ThemeBrushes.WarningText,
                    Padding = new Thickness(5, 2)
                };
                btnRemove.Click += (s, e) => _vm.RemoveStage(index);
                actionButtons.Children.Add(btnRemove);

                headerDock.Children.Add(actionButtons);

                var labelTitle = new TextBlock
                {
                    Text = $"{index + 1}. {(stageSpec?.Title ?? opName)}",
                    FontWeight = FontWeight.Bold,
                    FontSize = 12,
                    VerticalAlignment = VerticalAlignment.Center
                };
                headerDock.Children.Add(labelTitle);

                cardStack.Children.Add(headerDock);

                // Dynamic parameter and metadata editor
                if (stageSpec != null)
                {
                    var editor = DynamicPanelGenerator.CreateStageEditor(
                        stageSpec,
                        index,
                        stageObj,
                        _vm.UiSchema?.ParamSources,
                        (pName, pVal) => { if (!_isRebuilding) _vm.UpdateParam(index, pName, pVal); },
                        newName => { if (!_isRebuilding) _vm.UpdateStageName(index, newName); },
                        newRepeat => { if (!_isRebuilding) _vm.UpdateStageRepeat(index, newRepeat); },
                        newWhen => { if (!_isRebuilding) _vm.UpdateStageWhen(index, newWhen); });

                    cardStack.Children.Add(editor);
                }
                else
                {
                    // Fallback for unknown operator
                    var fallback = new TextBlock
                    {
                        Text = $"Unknown stage operator '{opName}'",
                        Foreground = ThemeBrushes.WarningText,
                        FontSize = 11
                    };
                    cardStack.Children.Add(fallback);
                }

                stageCard.Child = cardStack;
                _stageListPanel.Children.Add(stageCard);
            }
        }
        finally
        {
            _isRebuilding = false;
        }
    }
}
