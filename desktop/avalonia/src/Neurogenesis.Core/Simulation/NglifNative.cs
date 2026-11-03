using System.Reflection;
using System.Runtime.InteropServices;
using Neurogenesis.Core.Ngb;

namespace Neurogenesis.Core.Simulation;

[StructLayout(LayoutKind.Sequential)]
public unsafe struct NglifNetworkNative
{
    public int n, e;
    public double* pos, dir;
    public int* mode, shift_v, shift_s, base_weight, burst_period, burst_duty, refractory, role, compartment, threshold;
    public double* poisson_hz, conn_radius, conn_prob;
    public int* pre, post, weight, delay;
}

/// <summary>
/// P/Invoke bindings for portable C kernel nglif (desktop/common/native/nglif).
/// </summary>
public static unsafe partial class NglifNative
{
    public const string LibName = "nglif";

    static NglifNative()
    {
        NativeLibrary.SetDllImportResolver(typeof(NglifNative).Assembly, ResolveDll);
    }

    private static IntPtr ResolveDll(string libraryName, Assembly assembly, DllImportSearchPath? searchPath)
    {
        if (libraryName != LibName) return IntPtr.Zero;

        string baseDir = AppContext.BaseDirectory;
        string ext = RuntimeInformation.IsOSPlatform(OSPlatform.Windows) ? ".dll"
                   : RuntimeInformation.IsOSPlatform(OSPlatform.OSX) ? ".dylib" : ".so";
        string prefix = RuntimeInformation.IsOSPlatform(OSPlatform.Windows) ? "" : "lib";

        // Potential search locations
        string[] candidates =
        {
            Path.Combine(baseDir, $"{prefix}{LibName}{ext}"),
            Path.Combine(baseDir, "runtimes", RuntimeInformation.RuntimeIdentifier, "native", $"{prefix}{LibName}{ext}"),
            Path.Combine(baseDir, "..", "..", "..", "..", "..", "..", "..", "build", "nglif", $"{prefix}{LibName}{ext}"),
            Path.Combine(baseDir, "..", "..", "..", "..", "..", "..", "..", "build", "nglif", "Release", $"{prefix}{LibName}{ext}")
        };

        foreach (var candidate in candidates)
        {
            string full = Path.GetFullPath(candidate);
            if (File.Exists(full))
            {
                if (NativeLibrary.TryLoad(full, out var handle))
                {
                    return handle;
                }
            }
        }

        if (NativeLibrary.TryLoad(libraryName, assembly, searchPath, out var defHandle))
        {
            return defHandle;
        }

        return IntPtr.Zero;
    }

    [LibraryImport(LibName, EntryPoint = "nglif_network_new")]
    public static partial NglifNetworkNative* NetworkNew(int n, int e);

    [LibraryImport(LibName, EntryPoint = "nglif_network_free")]
    public static partial void NetworkFree(NglifNetworkNative* net);

    [LibraryImport(LibName, EntryPoint = "nglif_network_read", StringMarshalling = StringMarshalling.Utf8)]
    public static partial NglifNetworkNative* NetworkRead(string path, byte* err, nuint err_len);

    [LibraryImport(LibName, EntryPoint = "nglif_network_write", StringMarshalling = StringMarshalling.Utf8)]
    public static partial int NetworkWrite(NglifNetworkNative* net, string path);

    [LibraryImport(LibName, EntryPoint = "nglif_create")]
    public static partial IntPtr Create(NglifNetworkNative* net, uint seed);

    [LibraryImport(LibName, EntryPoint = "nglif_free")]
    public static partial void Free(IntPtr sim);

    [LibraryImport(LibName, EntryPoint = "nglif_num_neurons")]
    public static partial int NumNeurons(IntPtr sim);

    [LibraryImport(LibName, EntryPoint = "nglif_tick")]
    public static partial long Tick(IntPtr sim);

    [LibraryImport(LibName, EntryPoint = "nglif_rng_state")]
    public static partial uint RngState(IntPtr sim);

    [LibraryImport(LibName, EntryPoint = "nglif_set_external")]
    public static partial void SetExternal(IntPtr sim, int* ext);

    [LibraryImport(LibName, EntryPoint = "nglif_inject")]
    public static partial void Inject(IntPtr sim, int i, int current);

    [LibraryImport(LibName, EntryPoint = "nglif_step")]
    public static partial int Step(IntPtr sim, int* spikes, int cap);

    [LibraryImport(LibName, EntryPoint = "nglif_run")]
    public static partial long Run(IntPtr sim, int ticks, int* t, int* i, long cap);

    [LibraryImport(LibName, EntryPoint = "nglif_potential")]
    public static partial int* Potential(IntPtr sim);

    [LibraryImport(LibName, EntryPoint = "nglif_current")]
    public static partial int* Current(IntPtr sim);

    [LibraryImport(LibName, EntryPoint = "nglif_last_spike")]
    public static partial int* LastSpike(IntPtr sim);

    /// <summary>
    /// Creates an nglif native network structure populated from an NgbNetwork.
    /// Caller is responsible for calling NetworkFree on the returned pointer.
    /// </summary>
    public static NglifNetworkNative* FromNgbNetwork(NgbNetwork net)
    {
        int n = net.NeuronCount;
        int e = net.SynapseCount;
        var p = NetworkNew(n, e);
        if (p == null) throw new OutOfMemoryException("Failed to allocate nglif native network");

        fixed (double* pos = net.Positions, dir = net.Directions, hz = net.NeuronFloat64[0], cr = net.NeuronFloat64[1], cp = net.NeuronFloat64[2])
        fixed (int* mode = net.Int32Column("mode"),
                    sv = net.Int32Column("shift_v"),
                    ss = net.Int32Column("shift_s"),
                    bw = net.Int32Column("base_weight"),
                    bp = net.Int32Column("burst_period"),
                    bd = net.Int32Column("burst_duty"),
                    rf = net.Int32Column("refractory"),
                    role = net.Int32Column("role"),
                    comp = net.Int32Column("compartment"),
                    th = net.Int32Column("threshold"))
        fixed (int* pre = net.Pre, post = net.Post, w = net.Weight, d = net.Delay)
        {
            Buffer.MemoryCopy(pos, p->pos, (long)n * 3 * sizeof(double), (long)n * 3 * sizeof(double));
            Buffer.MemoryCopy(dir, p->dir, (long)n * 3 * sizeof(double), (long)n * 3 * sizeof(double));
            Buffer.MemoryCopy(hz, p->poisson_hz, (long)n * sizeof(double), (long)n * sizeof(double));
            Buffer.MemoryCopy(cr, p->conn_radius, (long)n * sizeof(double), (long)n * sizeof(double));
            Buffer.MemoryCopy(cp, p->conn_prob, (long)n * sizeof(double), (long)n * sizeof(double));

            Buffer.MemoryCopy(mode, p->mode, (long)n * sizeof(int), (long)n * sizeof(int));
            Buffer.MemoryCopy(sv, p->shift_v, (long)n * sizeof(int), (long)n * sizeof(int));
            Buffer.MemoryCopy(ss, p->shift_s, (long)n * sizeof(int), (long)n * sizeof(int));
            Buffer.MemoryCopy(bw, p->base_weight, (long)n * sizeof(int), (long)n * sizeof(int));
            Buffer.MemoryCopy(bp, p->burst_period, (long)n * sizeof(int), (long)n * sizeof(int));
            Buffer.MemoryCopy(bd, p->burst_duty, (long)n * sizeof(int), (long)n * sizeof(int));
            Buffer.MemoryCopy(rf, p->refractory, (long)n * sizeof(int), (long)n * sizeof(int));
            Buffer.MemoryCopy(role, p->role, (long)n * sizeof(int), (long)n * sizeof(int));
            Buffer.MemoryCopy(comp, p->compartment, (long)n * sizeof(int), (long)n * sizeof(int));
            Buffer.MemoryCopy(th, p->threshold, (long)n * sizeof(int), (long)n * sizeof(int));

            Buffer.MemoryCopy(pre, p->pre, (long)e * sizeof(int), (long)e * sizeof(int));
            Buffer.MemoryCopy(post, p->post, (long)e * sizeof(int), (long)e * sizeof(int));
            Buffer.MemoryCopy(w, p->weight, (long)e * sizeof(int), (long)e * sizeof(int));
            Buffer.MemoryCopy(d, p->delay, (long)e * sizeof(int), (long)e * sizeof(int));
        }

        return p;
    }
}
