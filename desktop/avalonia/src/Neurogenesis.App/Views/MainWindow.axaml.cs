using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Platform.Storage;
using Neurogenesis.App.ViewModels;

namespace Neurogenesis.App.Views;

public partial class MainWindow : Window
{
    private static readonly FilePickerFileType NgbType = new("Network (NGB1)") { Patterns = new[] { "*.ngb" } };

    public MainWindow()
    {
        InitializeComponent();
        View.NeuronClicked += i => (DataContext as MainViewModel)?.Select(i);
        View.GlError += msg => { if (DataContext is MainViewModel vm) vm.Status = "3D view unavailable: " + msg; };
        AddHandler(DragDrop.DropEvent, OnDrop);
    }

    private async void OnOpen(object? sender, RoutedEventArgs e)
    {
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = "Open a network",
            FileTypeFilter = new[] { NgbType, FilePickerFileTypes.All },
        });
        if (files.Count > 0 && files[0].TryGetLocalPath() is { } path && DataContext is MainViewModel vm)
            await vm.OpenAsync(path);
    }

    private void OnFrame(object? sender, RoutedEventArgs e) => View.Frame();

    private async void OnDrop(object? sender, DragEventArgs e)
    {
#pragma warning disable CS0618
        if (e.Data.GetFiles()?.FirstOrDefault()?.TryGetLocalPath() is { } path && DataContext is MainViewModel vm)
            await vm.OpenAsync(path);
#pragma warning restore CS0618
    }
}
