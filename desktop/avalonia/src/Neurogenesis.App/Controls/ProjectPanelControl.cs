using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Neurogenesis.App.ViewModels;
using Neurogenesis.Core.Schema;

namespace Neurogenesis.App.Controls;

/// <summary>
/// Project settings panel: neuron model selector, schema metadata, and live JSON inspector.
/// Guarantees that edits are written to Project JSON only with no hidden state.
/// </summary>
public sealed class ProjectPanelControl : UserControl
{
    private MainViewModel? _vm;
    private bool _isUpdating;
    private readonly ComboBox _modelCombo = new() { HorizontalAlignment = HorizontalAlignment.Stretch, FontSize = 11 };
    private readonly TextBlock _modelDoc = new() { FontSize = 11, Opacity = 0.7, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 4) };
    private readonly TextBlock _modelStats = new() { FontSize = 10, Opacity = 0.55, Margin = new Thickness(0, 2) };
    private readonly TextBox _jsonViewer = new()
    {
        AcceptsReturn = true,
        FontFamily = new FontFamily("Consolas, Menlo, Monospace"),
        FontSize = 10,
        IsReadOnly = true,
        TextWrapping = TextWrapping.NoWrap
    };

    public ProjectPanelControl()
    {
        var root = new DockPanel { Margin = new Thickness(6) };

        var topStack = new StackPanel { Spacing = 8, Margin = new Thickness(0, 0, 0, 8) };

        // Neuron model group
        var modelHeader = new TextBlock { Text = "Neuron Model", FontWeight = FontWeight.Bold, FontSize = 12 };
        topStack.Children.Add(modelHeader);
        topStack.Children.Add(_modelCombo);
        topStack.Children.Add(_modelDoc);
        topStack.Children.Add(_modelStats);

        _modelCombo.SelectionChanged += (s, e) =>
        {
            if (!_isUpdating && _modelCombo.SelectedItem is ModelSpec model && _vm != null)
            {
                if (model.Name != _vm.Project.NeuronModel)
                {
                    _vm.SetNeuronModel(model.Name);
                    UpdateModelInfo(model);
                }
            }
        };

        // Project JSON Header
        var jsonHeader = new DockPanel();
        var jsonTitle = new TextBlock { Text = "Project JSON (Source of Truth)", FontWeight = FontWeight.Bold, FontSize = 12, VerticalAlignment = VerticalAlignment.Center };
        DockPanel.SetDock(jsonTitle, Dock.Left);
        jsonHeader.Children.Add(jsonTitle);
        topStack.Children.Add(jsonHeader);

        DockPanel.SetDock(topStack, Dock.Top);
        root.Children.Add(topStack);

        var jsonScroll = new ScrollViewer { Content = _jsonViewer };
        root.Children.Add(jsonScroll);

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
                    _isUpdating = true;
                    try
                    {
                        _modelCombo.ItemsSource = _vm.UiSchema.Models;
                        var curModel = _vm.UiSchema.Models.FirstOrDefault(m => m.Name == _vm.Project.NeuronModel)
                                       ?? _vm.UiSchema.Models.FirstOrDefault();
                        _modelCombo.SelectedItem = curModel;
                        if (curModel != null) UpdateModelInfo(curModel);
                    }
                    finally
                    {
                        _isUpdating = false;
                    }
                }
                UpdateJsonView();
            }
        };
    }

    private void OnDocumentChanged(object? sender, EventArgs e)
    {
        if (_isUpdating) return;
        Avalonia.Threading.Dispatcher.UIThread.Post(UpdateJsonView);
    }

    private void UpdateModelInfo(ModelSpec model)
    {
        _modelDoc.Text = model.Description ?? "";
        string nativeNote = model.Native ? "[Native C kernel nglif]" : "[Bridge simulation]";
        _modelStats.Text = $"{nativeNote}  Substeps: {model.Substeps}  State: {model.StateBytes} B/neuron  Flops: {model.Flops}";
    }

    private void UpdateJsonView()
    {
        if (_vm == null || _isUpdating) return;
        _isUpdating = true;
        try
        {
            _jsonViewer.Text = _vm.Project.ToJsonString(indented: true);
        }
        finally
        {
            _isUpdating = false;
        }
    }
}
