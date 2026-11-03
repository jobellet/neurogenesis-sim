using Avalonia.Media;
using Neurogenesis.Core.Style;

namespace Neurogenesis.App.Style;

public static class ThemeBrushes
{
    private static IBrush Brush(string hex) => new SolidColorBrush(Color.Parse(hex));

    public static IBrush WindowBackground => Brush(VisualStyle.Default.UiWindowBackground);
    public static IBrush WindowForeground => Brush(VisualStyle.Default.UiWindowForeground);
    public static IBrush PanelBackground => Brush(VisualStyle.Default.UiPanelBackground);
    public static IBrush PanelBorder => Brush(VisualStyle.Default.UiPanelBorder);
    public static IBrush StatusBackground => Brush(VisualStyle.Default.UiStatusBackground);
    public static IBrush NoteBackground => Brush(VisualStyle.Default.UiNoteBackground);
    public static IBrush NoteForeground => Brush(VisualStyle.Default.UiNoteForeground);
    public static IBrush CardBackground => Brush(VisualStyle.Default.UiCardBackground);
    public static IBrush CardBorder => Brush(VisualStyle.Default.UiCardBorder);
    public static IBrush TaskBadgeBg => Brush(VisualStyle.Default.UiTaskBadgeBg);
    public static IBrush TaskBadgeFg => Brush(VisualStyle.Default.UiTaskBadgeFg);
    public static IBrush AvailableBadgeBg => Brush(VisualStyle.Default.UiAvailableBadgeBg);
    public static IBrush AvailableBadgeFg => Brush(VisualStyle.Default.UiAvailableBadgeFg);
    public static IBrush PlannedBadgeBg => Brush(VisualStyle.Default.UiPlannedBadgeBg);
    public static IBrush PlannedBadgeFg => Brush(VisualStyle.Default.UiPlannedBadgeFg);
    public static IBrush HelpAccent => Brush(VisualStyle.Default.UiHelpAccent);
    public static IBrush WarningText => Brush(VisualStyle.Default.UiWarningText);
    public static IBrush ErrorText => Brush(VisualStyle.Default.UiErrorText);
}
