using System.Numerics;
using System.Text.Json;
using Neurogenesis.Core.Ngb;

namespace Neurogenesis.Core.Style;

/// <summary>One way of colouring neurons, from the style's <c>color_modes</c>. Kinds: <c>palette</c> (categorical
/// field indexing the palette; negative values use the <c>fallback</c> mode), <c>categorical</c> (field value indexes
/// <c>colors</c>, clamped), <c>ramp</c> (field mapped linearly from <c>lo</c>..<c>hi</c> onto <c>colors</c>) and
/// <c>sign</c> (excitatory / inhibitory, from the mask given to <see cref="VisualStyle.Colorizer"/>).</summary>
public sealed record ColorMode(string Name, string Kind, string? Field, string? Fallback, Vector4[] Colors, double Lo, double Hi)
{
    public override string ToString() => Name;
}

/// <summary>The app's whole visual look (colours, sizes, budgets). Loaded from <c>default_visual_style.json</c>, the
/// single place where it is defined until <c>desktop/common/visual_spec.json</c> exists.</summary>
public sealed class VisualStyle
{
    public Vector4 Background { get; private init; }
    public float PointSizePx { get; private init; }
    public float Attenuation { get; private init; }
    public Vector4 SelectedColor { get; private init; }
    public float SelectedScale { get; private init; }
    public int NeuronBudget { get; private init; }
    public Vector4 Excitatory { get; private init; }
    public Vector4 Inhibitory { get; private init; }
    public int SynapseBudget { get; private init; }
    public Vector4[] Palette { get; private init; } = Array.Empty<Vector4>();
    public IReadOnlyList<ColorMode> ColorModes { get; private init; } = Array.Empty<ColorMode>();

    public string UiWindowBackground { get; private init; } = "";
    public string UiWindowForeground { get; private init; } = "";
    public string UiPanelBackground { get; private init; } = "";
    public string UiPanelBorder { get; private init; } = "";
    public string UiStatusBackground { get; private init; } = "";
    public string UiNoteBackground { get; private init; } = "";
    public string UiNoteForeground { get; private init; } = "";
    public string UiCardBackground { get; private init; } = "";
    public string UiCardBorder { get; private init; } = "";
    public string UiTaskBadgeBg { get; private init; } = "";
    public string UiTaskBadgeFg { get; private init; } = "";
    public string UiAvailableBadgeBg { get; private init; } = "";
    public string UiAvailableBadgeFg { get; private init; } = "";
    public string UiPlannedBadgeBg { get; private init; } = "";
    public string UiPlannedBadgeFg { get; private init; } = "";
    public string UiHelpAccent { get; private init; } = "";
    public string UiWarningText { get; private init; } = "";
    public string UiErrorText { get; private init; } = "";

    public static VisualStyle Default { get; } = LoadDefault();

    private static VisualStyle LoadDefault()
    {
        using var s = typeof(VisualStyle).Assembly.GetManifestResourceStream("default_visual_style.json")
            ?? throw new InvalidOperationException("default_visual_style.json is not embedded");
        using var doc = JsonDocument.Parse(s);
        return Parse(doc.RootElement);
    }

    public static VisualStyle Parse(JsonElement r)
    {
        var n = r.GetProperty("neuron");
        var syn = r.GetProperty("synapse");
        var modes = r.GetProperty("color_modes").EnumerateArray().Select(m =>
        {
            string kind = m.GetProperty("kind").GetString()!;
            var colors = kind == "sign"
                ? new[] { Color(m.GetProperty("excitatory")), Color(m.GetProperty("inhibitory")) }
                : m.TryGetProperty("colors", out var c) ? c.EnumerateArray().Select(Color).ToArray() : Array.Empty<Vector4>();
            return new ColorMode(m.GetProperty("name").GetString()!, kind, Str(m, "field"), Str(m, "fallback"), colors,
                m.TryGetProperty("lo", out var lo) ? lo.GetDouble() : 0, m.TryGetProperty("hi", out var hi) ? hi.GetDouble() : 1);
        }).ToArray();

        var ui = r.TryGetProperty("ui", out var u) ? u : default;
        static string UiStr(JsonElement u, string prop) =>
            u.ValueKind == JsonValueKind.Object && u.TryGetProperty(prop, out var p) ? p.GetString() ?? "" : "";

        return new VisualStyle
        {
            Background = Color(r.GetProperty("background")),
            PointSizePx = n.GetProperty("point_size_px").GetSingle(),
            Attenuation = n.GetProperty("attenuation").GetSingle(),
            SelectedColor = Color(n.GetProperty("selected_color")),
            SelectedScale = n.GetProperty("selected_scale").GetSingle(),
            NeuronBudget = n.GetProperty("budget").GetInt32(),
            Excitatory = Color(syn.GetProperty("excitatory")),
            Inhibitory = Color(syn.GetProperty("inhibitory")),
            SynapseBudget = syn.GetProperty("budget").GetInt32(),
            Palette = r.GetProperty("palette").EnumerateArray().Select(Color).ToArray(),
            ColorModes = modes,
            UiWindowBackground = UiStr(ui, "window_background"),
            UiWindowForeground = UiStr(ui, "window_foreground"),
            UiPanelBackground = UiStr(ui, "panel_background"),
            UiPanelBorder = UiStr(ui, "panel_border"),
            UiStatusBackground = UiStr(ui, "status_background"),
            UiNoteBackground = UiStr(ui, "note_background"),
            UiNoteForeground = UiStr(ui, "note_foreground"),
            UiCardBackground = UiStr(ui, "card_background"),
            UiCardBorder = UiStr(ui, "card_border"),
            UiTaskBadgeBg = UiStr(ui, "task_badge_bg"),
            UiTaskBadgeFg = UiStr(ui, "task_badge_fg"),
            UiAvailableBadgeBg = UiStr(ui, "available_badge_bg"),
            UiAvailableBadgeFg = UiStr(ui, "available_badge_fg"),
            UiPlannedBadgeBg = UiStr(ui, "planned_badge_bg"),
            UiPlannedBadgeFg = UiStr(ui, "planned_badge_fg"),
            UiHelpAccent = UiStr(ui, "help_accent"),
            UiWarningText = UiStr(ui, "warning_text"),
            UiErrorText = UiStr(ui, "error_text"),
        };
    }

    /// <summary>The colour of each neuron index in <paramref name="mode"/>. A field the network lacks, or an unknown
    /// kind, gives one neutral colour.</summary>
    public Func<int, Vector4> Colorizer(ColorMode mode, NgbNetwork net, bool[] inhibitory, int depth = 0)
    {
        var neutral = Palette.Length > 0 ? Palette[^1] : Vector4.One;
        if (mode.Kind == "sign") return i => inhibitory[i] ? mode.Colors[1] : mode.Colors[0];
        var field = mode.Field is null ? null : net.NeuronField(mode.Field);
        if (field is null || mode.Colors.Length == 0 && mode.Kind != "palette") return _ => neutral;
        switch (mode.Kind)
        {
            case "palette":
                var fb = ColorModes.FirstOrDefault(m => m.Name == mode.Fallback);
                var fallback = fb is not null && depth < 4 ? Colorizer(fb, net, inhibitory, depth + 1) : _ => neutral;
                return i =>
                {
                    double v = field(i);
                    return v >= 0 && Palette.Length > 0 ? Palette[(int)((long)v % Palette.Length)] : fallback(i);
                };
            case "categorical":
                return i => mode.Colors[(int)Math.Clamp(field(i), 0, mode.Colors.Length - 1)];
            case "ramp":
                return i =>
                {
                    double t = Math.Clamp((field(i) - mode.Lo) / (mode.Hi - mode.Lo), 0, 1) * (mode.Colors.Length - 1);
                    int k = Math.Min((int)t, mode.Colors.Length - 2);
                    return k < 0 ? mode.Colors[0] : Vector4.Lerp(mode.Colors[k], mode.Colors[k + 1], (float)(t - k));
                };
            default:
                return _ => neutral;
        }
    }

    private static string? Str(JsonElement e, string name) => e.TryGetProperty(name, out var v) ? v.GetString() : null;

    private static Vector4 Color(JsonElement e)
    {
        var a = e.EnumerateArray().Select(x => x.GetSingle()).ToArray();
        return new Vector4(a[0], a[1], a[2], a.Length > 3 ? a[3] : 1f);
    }
}
