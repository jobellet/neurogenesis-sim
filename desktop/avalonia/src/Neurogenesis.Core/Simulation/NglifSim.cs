using System.Runtime.InteropServices;
using Neurogenesis.Core.Ngb;

namespace Neurogenesis.Core.Simulation;

/// <summary>
/// Managed wrapper around native nglif_sim, managing simulation lifecycle and state access.
/// </summary>
public sealed unsafe class NglifSim : IDisposable
{
    private IntPtr _sim;
    public int NumNeurons { get; }

    public long Tick => _sim != IntPtr.Zero ? NglifNative.Tick(_sim) : 0;
    public uint RngState => _sim != IntPtr.Zero ? NglifNative.RngState(_sim) : 0;

    public NglifSim(NgbNetwork net, uint seed = 12345)
    {
        NumNeurons = net.NeuronCount;
        var p = NglifNative.FromNgbNetwork(net);
        try
        {
            _sim = NglifNative.Create(p, seed);
            if (_sim == IntPtr.Zero) throw new InvalidOperationException("Failed to create nglif simulation instance");
        }
        finally
        {
            NglifNative.NetworkFree(p);
        }
    }

    public void SetExternal(int[]? ext)
    {
        ObjectDisposedException.ThrowIf(_sim == IntPtr.Zero, this);
        if (ext == null)
        {
            NglifNative.SetExternal(_sim, null);
        }
        else
        {
            fixed (int* p = ext)
            {
                NglifNative.SetExternal(_sim, p);
            }
        }
    }

    public void Inject(int neuronIndex, int current)
    {
        ObjectDisposedException.ThrowIf(_sim == IntPtr.Zero, this);
        NglifNative.Inject(_sim, neuronIndex, current);
    }

    public int Step(Span<int> spikes)
    {
        ObjectDisposedException.ThrowIf(_sim == IntPtr.Zero, this);
        fixed (int* p = spikes)
        {
            return NglifNative.Step(_sim, p, spikes.Length);
        }
    }

    public long Run(int ticks, Span<int> t, Span<int> i)
    {
        ObjectDisposedException.ThrowIf(_sim == IntPtr.Zero, this);
        int cap = Math.Min(t.Length, i.Length);
        fixed (int* pt = t, pi = i)
        {
            return NglifNative.Run(_sim, ticks, pt, pi, cap);
        }
    }

    public ReadOnlySpan<int> Potential =>
        _sim != IntPtr.Zero ? new ReadOnlySpan<int>(NglifNative.Potential(_sim), NumNeurons) : ReadOnlySpan<int>.Empty;

    public ReadOnlySpan<int> Current =>
        _sim != IntPtr.Zero ? new ReadOnlySpan<int>(NglifNative.Current(_sim), NumNeurons) : ReadOnlySpan<int>.Empty;

    public ReadOnlySpan<int> LastSpike =>
        _sim != IntPtr.Zero ? new ReadOnlySpan<int>(NglifNative.LastSpike(_sim), NumNeurons) : ReadOnlySpan<int>.Empty;

    public void Dispose()
    {
        if (_sim != IntPtr.Zero)
        {
            NglifNative.Free(_sim);
            _sim = IntPtr.Zero;
        }
    }
}
