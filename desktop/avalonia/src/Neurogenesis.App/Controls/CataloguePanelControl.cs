using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Neurogenesis.App.ViewModels;
using Neurogenesis.Core.Schema;

namespace Neurogenesis.App.Controls;

/// <summary>
/// Stage catalogue panel displaying all registered and planned stages defined in the UI schema.
/// Allows inspecting stage metadata, scaling cost, and adding stages to the schedule.
/// </summary>
public sealed class CataloguePanelControl : UserControl
{
    private MainViewModel? _vm;
    private readonly StackPanel _list = new() { Spacing = 6 };

    public CataloguePanelControl()
    {
        var root = new ScrollViewer
        {
            Content = _list,
            Margin = new Thickness(6)
        };
        Content = root;

        DataContextChanged += (s, e) =>
        {
            _vm = DataContext as MainViewModel;
            RebuildCatalogue();
        };
    }

    private void RebuildCatalogue()
    {
        _list.Children.Clear();
        if (_vm?.UiSchema?.Stages == null) return;

        foreach (var stage in _vm.UiSchema.Stages)
        {
            var card = new Border
            {
                Background = new SolidColorBrush(Color.FromArgb(25, 255, 255, 255)),
                CornerRadius = new CornerRadius(5),
                Padding = new Thickness(8),
                Margin = new Thickness(0, 2)
            };

            var stack = new StackPanel { Spacing = 4 };

            // Title + badges + Add button
            var headerDock = new DockPanel();

            var addBtn = new Button
            {
                Content = "+ Add",
                FontSize = 10,
                Padding = new Thickness(6, 2)
            };
            addBtn.Click += (s, e) => _vm?.AddStage(stage);
            DockPanel.SetDock(addBtn, Dock.Right);
            headerDock.Children.Add(addBtn);

            var titleStack = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6 };
            titleStack.Children.Add(new TextBlock
            {
                Text = stage.Title,
                FontWeight = FontWeight.Bold,
                FontSize = 12,
                VerticalAlignment = VerticalAlignment.Center
            });

            titleStack.Children.Add(new Border
            {
                Background = new SolidColorBrush(Color.FromArgb(50, 100, 150, 255)),
                CornerRadius = new CornerRadius(3),
                Padding = new Thickness(4, 1),
                Child = new TextBlock
                {
                    Text = stage.Task,
                    FontSize = 9,
                    Foreground = new SolidColorBrush(Color.FromRgb(150, 200, 255))
                }
            });

            var availBrush = stage.Available
                ? new SolidColorBrush(Color.FromArgb(60, 40, 180, 80))
                : new SolidColorBrush(Color.FromArgb(60, 220, 120, 30));
            var availFg = stage.Available
                ? new SolidColorBrush(Color.FromRgb(90, 220, 130))
                : new SolidColorBrush(Color.FromRgb(255, 170, 70));
            titleStack.Children.Add(new Border
            {
                Background = availBrush,
                CornerRadius = new CornerRadius(3),
                Padding = new Thickness(4, 1),
                Child = new TextBlock
                {
                    Text = stage.Available ? "Registered" : "Planned",
                    FontSize = 9,
                    Foreground = availFg
                }
            });

            headerDock.Children.Add(titleStack);
            stack.Children.Add(headerDock);

            if (!string.IsNullOrEmpty(stage.Description))
            {
                stack.Children.Add(new TextBlock
                {
                    Text = stage.Description,
                    Opacity = 0.7,
                    FontSize = 10,
                    TextWrapping = TextWrapping.Wrap
                });
            }

            if (stage.Cost is { Declared: true, Samples: { Count: > 0 } })
            {
                var s0 = stage.Cost.Samples[0];
                int n = s0?["N"]?.GetValue<int>() ?? 0;
                int ops = s0?["ops"]?.GetValue<int>() ?? 0;
                long bytes = s0?["bytes"]?.GetValue<long>() ?? 0;
                stack.Children.Add(new TextBlock
                {
                    Text = $"Cost (N={n:N0}): ~{ops:N0} ops, {bytes / 1024:N0} KB",
                    FontSize = 9,
                    Opacity = 0.5
                });
            }

            card.Child = stack;
            _list.Children.Add(card);
        }
    }
}
