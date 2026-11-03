using System.Runtime.InteropServices;
using System.Text;

namespace Neurogenesis.Core.Ngb;

/// <summary>Reads and writes NGB1 files (desktop/common/PROTOCOL.md §6; Python twin: neurogenesis/bridge/ngb.py).
/// Columns are read straight from the stream into typed arrays, so memory is O(N + E) with no per-element objects.</summary>
public static class NgbFile
{
    public const int Version = 1;
    public const int FlagExtensions = 1;
    private static readonly byte[] Magic = "NGB1"u8.ToArray();

    /// <summary>Size of the mandatory part: 16 + 112 N + 16 E bytes.</summary>
    public static long MandatoryBytes(long neurons, long synapses) => 16 + 112 * neurons + 16 * synapses;

    /// <summary>The (neurons, synapses) counts of an NGB1 file, from its 16-byte header only.</summary>
    public static (int Neurons, int Synapses) ReadCounts(string path)
    {
        using var f = File.OpenRead(path);
        Span<byte> h = stackalloc byte[16];
        f.ReadExactly(h);
        CheckHeader(h, path);
        return (BitConverter.ToInt32(h[4..]), BitConverter.ToInt32(h[8..]));
    }

    public static NgbNetwork Read(string path)
    {
        using var f = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 1 << 20);
        return Read(f, f.Length, path);
    }

    /// <summary>Reads a network from <paramref name="s"/>, which holds exactly <paramref name="length"/> bytes of it.</summary>
    public static NgbNetwork Read(Stream s, long length, string name = "stream")
    {
        if (!BitConverter.IsLittleEndian) throw new PlatformNotSupportedException("NGB1 I/O needs a little-endian machine");
        if (length < 16) throw new InvalidDataException($"{name}: {length} bytes, too short for an NGB1 header");
        Span<byte> h = stackalloc byte[16];
        s.ReadExactly(h);
        CheckHeader(h, name);
        int n = BitConverter.ToInt32(h[4..]), e = BitConverter.ToInt32(h[8..]), flags = BitConverter.ToInt32(h[12..]);
        if (n < 0 || e < 0) throw new InvalidDataException($"{name}: negative counts ({n} neurons, {e} synapses)");
        if ((flags & ~FlagExtensions) != 0)
            throw new InvalidDataException($"{name}: unknown NGB1 flags 0x{flags:x} (written by a newer version)");
        long mandatory = MandatoryBytes(n, e);
        bool ext = (flags & FlagExtensions) != 0;
        if (ext ? length < mandatory + 4 : length != mandatory)
            throw new InvalidDataException($"{name}: {length} bytes, expected {(ext ? "more than " : "")}{mandatory} for {n} neurons and {e} synapses");

        var net = new NgbNetwork(n, e);
        Fill(s, net.Positions);
        Fill(s, net.Directions);
        foreach (var c in net.NeuronInt32) Fill(s, c);
        foreach (var c in net.NeuronFloat64) Fill(s, c);
        Fill(s, net.Pre);
        Fill(s, net.Post);
        Fill(s, net.Weight);
        Fill(s, net.Delay);
        if (ext) ReadExtensions(s, length - mandatory, net, name);
        return net;
    }

    private static void ReadExtensions(Stream s, long remaining, NgbNetwork net, string name)
    {
        Span<byte> b = stackalloc byte[32];
        s.ReadExactly(b[..4]);
        int count = BitConverter.ToInt32(b);
        remaining -= 4;
        if (count < 0) throw new InvalidDataException($"{name}: negative extension count {count}");
        for (int k = 0; k < count; k++)
        {
            if (remaining < 32) throw new InvalidDataException($"{name}: truncated extension header {k}");
            s.ReadExactly(b);
            remaining -= 32;
            string col = Encoding.ASCII.GetString(b[..16]).TrimEnd('\0');
            int axis = BitConverter.ToInt32(b[16..]), dtype = BitConverter.ToInt32(b[20..]), comps = BitConverter.ToInt32(b[24..]);
            int size = NgbExtension.DTypeSize(dtype);
            if (axis is not (0 or 1) || size == 0 || comps < 1)
                throw new InvalidDataException($"{name}: extension '{col}' has axis {axis}, dtype {dtype}, components {comps}");
            long rows = axis == 0 ? net.NeuronCount : net.SynapseCount;
            long bytes = rows * comps * size;
            if (bytes > remaining || bytes > Array.MaxLength)
                throw new InvalidDataException($"{name}: extension '{col}' needs {bytes} bytes, {remaining} left");
            var data = new byte[bytes];
            s.ReadExactly(data);
            remaining -= bytes;
            net.Extensions.Add(new NgbExtension(col, (NgbAxis)axis, dtype, comps, data));
        }
        if (remaining != 0) throw new InvalidDataException($"{name}: {remaining} bytes after the extension columns");
    }

    public static void Write(NgbNetwork net, string path)
    {
        using var f = new FileStream(path, FileMode.Create, FileAccess.Write, FileShare.None, 1 << 20);
        Write(net, f);
    }

    /// <summary>Writes <paramref name="net"/> as NGB1; flags bit 0 is set exactly when it has extension columns.</summary>
    public static void Write(NgbNetwork net, Stream s)
    {
        if (!BitConverter.IsLittleEndian) throw new PlatformNotSupportedException("NGB1 I/O needs a little-endian machine");
        s.Write(Magic);
        Int(s, net.NeuronCount);
        Int(s, net.SynapseCount);
        Int(s, net.Extensions.Count > 0 ? FlagExtensions : 0);
        Put<double>(s, net.Positions);
        Put<double>(s, net.Directions);
        foreach (var c in net.NeuronInt32) Put<int>(s, c);
        foreach (var c in net.NeuronFloat64) Put<double>(s, c);
        Put<int>(s, net.Pre);
        Put<int>(s, net.Post);
        Put<int>(s, net.Weight);
        Put<int>(s, net.Delay);
        if (net.Extensions.Count == 0) return;
        Int(s, net.Extensions.Count);
        foreach (var x in net.Extensions)
        {
            var name = Encoding.ASCII.GetBytes(x.Name);
            long rows = x.Axis == NgbAxis.Neuron ? net.NeuronCount : net.SynapseCount;
            if (name.Length > 16 || x.Data.LongLength != rows * x.Components * NgbExtension.DTypeSize(x.DType))
                throw new ArgumentException($"extension '{x.Name}': needs a name of at most 16 bytes and {rows} rows");
            var head = new byte[16];
            name.CopyTo(head, 0);
            s.Write(head);
            Int(s, (int)x.Axis);
            Int(s, x.DType);
            Int(s, x.Components);
            Int(s, 0);
            s.Write(x.Data);
        }
    }

    private static void CheckHeader(ReadOnlySpan<byte> h, string name)
    {
        if (!h[..4].SequenceEqual(Magic)) throw new InvalidDataException($"{name}: not an NGB1 network file");
    }

    private static void Fill<T>(Stream s, T[] a) where T : unmanaged => s.ReadExactly(MemoryMarshal.AsBytes(a.AsSpan()));

    private static void Put<T>(Stream s, T[] a) where T : unmanaged => s.Write(MemoryMarshal.AsBytes(a.AsSpan()));

    private static void Int(Stream s, int v)
    {
        Span<byte> b = stackalloc byte[4];
        BitConverter.TryWriteBytes(b, v);
        s.Write(b);
    }
}
