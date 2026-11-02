using Avalonia.Media;
using Neurogenesis.Core.Style;

namespace Neurogenesis.App.Style;

public static class ThemeBrushes
{
    private static IBrush Brush(string hex, string fallback) =>
        new SolidColorBrush(Color.Parse(string.IsNullOrEmpty(hex) ? fallback : hex));

    public static IBrush WindowBackground => Brush(VisualStyle.Default.UiWindowBackground, "#0E1014");
    public static IBrush WindowForeground => Brush(VisualStyle.Default.UiWindowForeground, "#E0E6ED");
    public static IBrush PanelBackground => Brush(VisualStyle.Default.UiPanelBackground, "#16191E");
    public static IBrush PanelBorder => Brush(VisualStyle.Default.UiPanelBorder, "#252A32");
    public static IBrush StatusBackground => Brush(VisualStyle.Default.UiStatusBackground, "#1A1D23");
    public static IBrush NoteBackground => Brush(VisualStyle.Default.UiNoteBackground, "#B0101318");
    public static IBrush NoteForeground => Brush(VisualStyle.Default.UiNoteForeground, "#FFD27F");
    public static IBrush CardBackground => Brush(VisualStyle.Default.UiCardBackground, "#1C2027");
    public static IBrush CardBorder => Brush(VisualStyle.Default.UiCardBorder, "#282E38");
    public static IBrush TaskBadgeBg => Brush(VisualStyle.Default.UiTaskBadgeBg, "#193264");
    public static IBrush TaskBadgeFg => Brush(VisualStyle.Default.UiTaskBadgeFg, "#96C8FF");
    public static IBrush AvailableBadgeBg => Brush(VisualStyle.Default.UiAvailableBadgeBg, "#144620");
    public static IBrush AvailableBadgeFg => Brush(VisualStyle.Default.UiAvailableBadgeFg, "#5ADC82");
    public static IBrush PlannedBadgeBg => Brush(VisualStyle.Default.UiPlannedBadgeBg, "#46280A");
    public static IBrush PlannedBadgeFg => Brush(VisualStyle.Default.UiPlannedBadgeFg, "#FFAA46");
    public static IBrush HelpAccent => Brush(VisualStyle.Default.UiHelpAccent, "#78AAF0");
    public static IBrush WarningText => Brush(VisualStyle.Default.UiWarningText, "#FFAA46");
    public static IBrush ErrorText => Brush(VisualStyle.Default.UiErrorText, "#FF6464");
}
