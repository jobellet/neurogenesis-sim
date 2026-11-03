namespace Neurogenesis.Core.Ngb;

/// <summary>Row axis of an NGB1 extension column.</summary>
public enum NgbAxis { Neuron = 0, Synapse = 1 }

/// <summary>An optional NGB1 extension column (desktop/common/PROTOCOL.md §6), kept as raw little-endian bytes so a
/// file is written back unchanged. The app interprets none of them; the inspector shows per-neuron ones.</summary>
public sealed record NgbExtension(string Name, NgbAxis Axis, int DType, int Components, byte[] Data)
{
    /// <summary>Bytes per value of an NGB1 dtype code (1 int8, 2 uint8, 3 int16, 4 int32, 5 int64, 6 float32,
    /// 7 float64); 0 for an unknown code.</summary>
    public static int DTypeSize(int dtype) => dtype switch { 1 or 2 => 1, 3 => 2, 4 or 6 => 4, 5 or 7 => 8, _ => 0 };

    /// <summary>Value <paramref name="component"/> of row <paramref name="row"/>, as a double.</summary>
    public double Value(int row, int component = 0)
    {
        int size = DTypeSize(DType);
        var b = Data.AsSpan(checked((row * Components + component) * size), size);
        return DType switch
        {
            1 => (sbyte)b[0],
            2 => b[0],
            3 => BitConverter.ToInt16(b),
            4 => BitConverter.ToInt32(b),
            5 => BitConverter.ToInt64(b),
            6 => BitConverter.ToSingle(b),
            _ => BitConverter.ToDouble(b),
        };
    }

    /// <summary>Row <paramref name="row"/> as text: one value, or "(a, b, c)" for several components.</summary>
    public string ValueText(int row)
    {
        var parts = Enumerable.Range(0, Components).Select(c => NgbNetwork.Format(Value(row, c)));
        return Components == 1 ? parts.First() : "(" + string.Join(", ", parts) + ")";
    }
}

/// <summary>A network in NGB1 layout: struct of arrays, no per-neuron or per-synapse objects. Field meanings are those
/// of neurogenesis.spiking.network.NeuronData / SynapseData.</summary>
public sealed class NgbNetwork
{
    public static readonly string[] NeuronInt32Names =
        { "mode", "shift_v", "shift_s", "base_weight", "burst_period", "burst_duty", "refractory", "role", "compartment", "threshold" };
    public static readonly string[] NeuronFloat64Names = { "poisson_hz", "conn_radius", "conn_prob" };

    public int NeuronCount { get; }
    public int SynapseCount { get; }
    /// <summary>N × 3 positions (x, y, z), row-major, in space units.</summary>
    public double[] Positions { get; }
    /// <summary>N × 3 directions, row-major.</summary>
    public double[] Directions { get; }
    /// <summary>One int32 column of N values per <see cref="NeuronInt32Names"/> entry, same order.</summary>
    public int[][] NeuronInt32 { get; }
    /// <summary>One float64 column of N values per <see cref="NeuronFloat64Names"/> entry, same order.</summary>
    public double[][] NeuronFloat64 { get; }
    public int[] Pre { get; }
    public int[] Post { get; }
    public int[] Weight { get; }
    public int[] Delay { get; }
    public List<NgbExtension> Extensions { get; } = new();

    public NgbNetwork(int neurons, int synapses)
    {
        if (neurons < 0 || synapses < 0) throw new ArgumentOutOfRangeException(nameof(neurons), "counts must be >= 0");
        NeuronCount = neurons;
        SynapseCount = synapses;
        Positions = new double[3L * neurons];
        Directions = new double[3L * neurons];
        NeuronInt32 = NeuronInt32Names.Select(_ => new int[neurons]).ToArray();
        NeuronFloat64 = NeuronFloat64Names.Select(_ => new double[neurons]).ToArray();
        Pre = new int[synapses];
        Post = new int[synapses];
        Weight = new int[synapses];
        Delay = new int[synapses];
    }

    public int[] Int32Column(string name)
    {
        int k = Array.IndexOf(NeuronInt32Names, name);
        return k >= 0 ? NeuronInt32[k] : throw new KeyNotFoundException($"no NGB1 int32 neuron column '{name}'");
    }

    /// <summary>A per-neuron numeric field by name: a mandatory column, or a one-component per-neuron extension
    /// column. Null when the network has no such field.</summary>
    public Func<int, double>? NeuronField(string name)
    {
        int k = Array.IndexOf(NeuronInt32Names, name);
        if (k >= 0) { var c = NeuronInt32[k]; return i => c[i]; }
        k = Array.IndexOf(NeuronFloat64Names, name);
        if (k >= 0) { var c = NeuronFloat64[k]; return i => c[i]; }
        var ext = Extensions.FirstOrDefault(e => e.Name == name && e.Axis == NgbAxis.Neuron && e.Components == 1);
        return ext is null ? null : i => ext.Value(i);
    }

    /// <summary>Every field of neuron <paramref name="i"/> as (name, text), in file order, then its synapse counts.</summary>
    public IEnumerable<(string Name, string Value)> NeuronFields(int i)
    {
        yield return ("index", i.ToString());
        yield return ("position", Vec(Positions, i));
        yield return ("direction", Vec(Directions, i));
        for (int k = 0; k < NeuronInt32Names.Length; k++) yield return (NeuronInt32Names[k], NeuronInt32[k][i].ToString());
        for (int k = 0; k < NeuronFloat64Names.Length; k++) yield return (NeuronFloat64Names[k], Format(NeuronFloat64[k][i]));
        foreach (var e in Extensions.Where(e => e.Axis == NgbAxis.Neuron)) yield return (e.Name, e.ValueText(i));
        int outgoing = 0, incoming = 0;
        for (int s = 0; s < SynapseCount; s++)
        {
            if (Pre[s] == i) outgoing++;
            if (Post[s] == i) incoming++;
        }
        yield return ("synapses out", outgoing.ToString());
        yield return ("synapses in", incoming.ToString());
    }

    internal static string Format(double v) => v.ToString("G6", System.Globalization.CultureInfo.InvariantCulture);

    private static string Vec(double[] a, int i) => $"({Format(a[3 * i])}, {Format(a[3 * i + 1])}, {Format(a[3 * i + 2])})";
}
