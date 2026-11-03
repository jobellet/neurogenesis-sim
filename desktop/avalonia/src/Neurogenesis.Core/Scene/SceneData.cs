using System.Numerics;
using Neurogenesis.Core.Ngb;
using Neurogenesis.Core.Style;

namespace Neurogenesis.Core.Scene;

/// <summary>What the 3D view draws for one network, built off the UI thread: neuron instances up to the style's neuron
/// budget and synapse lines subsampled to its synapse budget. Positions are relative to <see cref="Center"/> and in
/// float32, so large coordinates keep their precision on the GPU.</summary>
public sealed class SceneData
{
    /// <summary>Floats per neuron instance: x, y, z, size scale, r, g, b, a, lastSpike.</summary>
    public const int InstanceStride = 9;
    /// <summary>Floats per line vertex: x, y, z, r, g, b, a.</summary>
    public const int LineStride = 7;

    public NgbNetwork Network { get; }
    public VisualStyle Style { get; }
    public Vector3 Center { get; }
    public float Radius { get; }
    /// <summary>Excitatory unless its base_weight or the sum of its outgoing weights is negative (as the Mac app).</summary>
    public bool[] InhibitoryMask { get; }
    /// <summary>Neuron index of each drawn instance (all neurons, or every k-th above the budget).</summary>
    public int[] InstanceNeuron { get; }
    public float[] LineVertices { get; }
    public int DrawnSynapses { get; }
    /// <summary>On-screen note when not everything is drawn; empty otherwise.</summary>
    public string Note { get; }

    public SceneData(NgbNetwork net, VisualStyle style)
    {
        Network = net;
        Style = style;
        int n = net.NeuronCount;
        InhibitoryMask = Inhibitory(net);

        int nStride = Stride(n, style.NeuronBudget);
        InstanceNeuron = new int[(n + nStride - 1) / nStride];
        for (int k = 0; k < InstanceNeuron.Length; k++) InstanceNeuron[k] = k * nStride;

        var lo = new Vector3(float.MaxValue);
        var hi = new Vector3(float.MinValue);
        for (int i = 0; i < n; i++)
        {
            var p = Pos(net, i);
            lo = Vector3.Min(lo, p);
            hi = Vector3.Max(hi, p);
        }
        Center = n > 0 ? (lo + hi) / 2 : Vector3.Zero;
        Radius = n > 0 ? MathF.Max((hi - lo).Length() / 2, 1f) : 50f;

        int e = net.SynapseCount, sStride = Stride(e, style.SynapseBudget);
        var verts = new List<float>(Math.Min(e, style.SynapseBudget) * 2 * LineStride);
        for (long s = 0; s < e; s += sStride)
        {
            int a = net.Pre[s], b = net.Post[s];
            if ((uint)a >= (uint)n || (uint)b >= (uint)n) continue;
            var c = net.Weight[s] < 0 ? style.Inhibitory : style.Excitatory;
            Vertex(verts, Pos(net, a) - Center, c);
            Vertex(verts, Pos(net, b) - Center, c);
        }
        LineVertices = verts.ToArray();
        DrawnSynapses = LineVertices.Length / (2 * LineStride);

        var notes = new List<string>();
        if (nStride > 1) notes.Add($"Showing {InstanceNeuron.Length:N0} of {n:N0} neurons (every {nStride}th).");
        if (sStride > 1) notes.Add($"Showing {DrawnSynapses:N0} of {e:N0} synapses (every {sStride}th).");
        Note = string.Join(" ", notes);
    }

    /// <summary>Instance data (<see cref="InstanceStride"/> floats each) in <paramref name="mode"/>, with
    /// <paramref name="selected"/> (a neuron index, or -1) highlighted and optional <paramref name="lastSpikes"/> per neuron.</summary>
    public float[] Instances(ColorMode mode, int selected, int[]? lastSpikes = null)
    {
        var color = Style.Colorizer(mode, Network, InhibitoryMask);
        var a = new float[InstanceNeuron.Length * InstanceStride];
        for (int k = 0; k < InstanceNeuron.Length; k++)
        {
            int i = InstanceNeuron[k];
            var p = Pos(Network, i) - Center;
            bool sel = i == selected;
            var c = sel ? Style.SelectedColor : color(i);
            float ls = lastSpikes != null && i < lastSpikes.Length ? lastSpikes[i] : float.NegativeInfinity;
            int o = k * InstanceStride;
            a[o] = p.X; a[o + 1] = p.Y; a[o + 2] = p.Z;
            a[o + 3] = sel ? Style.SelectedScale : 1f;
            a[o + 4] = c.X; a[o + 5] = c.Y; a[o + 6] = c.Z; a[o + 7] = c.W;
            a[o + 8] = ls;
        }
        return a;
    }

    private static bool[] Inhibitory(NgbNetwork net)
    {
        var outSum = new long[net.NeuronCount];
        for (int s = 0; s < net.SynapseCount; s++)
            if ((uint)net.Pre[s] < (uint)net.NeuronCount) outSum[net.Pre[s]] += net.Weight[s];
        var bw = net.Int32Column("base_weight");
        var mask = new bool[net.NeuronCount];
        for (int i = 0; i < mask.Length; i++) mask[i] = bw[i] < 0 || outSum[i] < 0;
        return mask;
    }

    private static int Stride(int count, int budget) => count <= budget || budget <= 0 ? 1 : (count + budget - 1) / budget;

    private static Vector3 Pos(NgbNetwork net, long i) =>
        new((float)net.Positions[3 * i], (float)net.Positions[3 * i + 1], (float)net.Positions[3 * i + 2]);

    private static void Vertex(List<float> v, Vector3 p, Vector4 c)
    {
        v.Add(p.X); v.Add(p.Y); v.Add(p.Z);
        v.Add(c.X); v.Add(c.Y); v.Add(c.Z); v.Add(c.W);
    }
}
