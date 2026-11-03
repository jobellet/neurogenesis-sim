using System.Text.Json;
using Neurogenesis.Core.Ngb;
using Xunit;

namespace Neurogenesis.Tests;

public class NgbTests
{
    [Theory]
    [InlineData("empty")]
    [InlineData("extreme")]
    [InlineData("column")]
    [InlineData("extensions")]
    public void ReadMatchesExpected(string fixture)
    {
        string path = PythonFixtures.File(fixture);
        var expected = PythonFixtures.Expected(fixture);

        var net = NgbFile.Read(path);
        Assert.Equal(expected.GetProperty("neurons").GetInt32(), net.NeuronCount);
        Assert.Equal(expected.GetProperty("synapses").GetInt32(), net.SynapseCount);

        // Header counts fast path
        var (nCounts, sCounts) = NgbFile.ReadCounts(path);
        Assert.Equal(net.NeuronCount, nCounts);
        Assert.Equal(net.SynapseCount, sCounts);

        // Positions
        var expPos = expected.GetProperty("positions").EnumerateArray().Select(x => x.GetDouble()).ToArray();
        Assert.Equal(expPos.Length, net.Positions.Length);
        for (int i = 0; i < expPos.Length; i++)
        {
            Assert.Equal(expPos[i], net.Positions[i]);
        }

        // Directions
        var expDirs = expected.GetProperty("directions").EnumerateArray().Select(x => x.GetDouble()).ToArray();
        Assert.Equal(expDirs.Length, net.Directions.Length);
        for (int i = 0; i < expDirs.Length; i++)
        {
            Assert.Equal(expDirs[i], net.Directions[i]);
        }

        // Int32 columns
        var expI32 = expected.GetProperty("int32");
        foreach (var colName in NgbNetwork.NeuronInt32Names)
        {
            var expCol = expI32.GetProperty(colName).EnumerateArray().Select(x => x.GetInt32()).ToArray();
            var actualCol = net.Int32Column(colName);
            Assert.Equal(expCol, actualCol);
        }

        // Float64 columns
        var expF64 = expected.GetProperty("float64");
        foreach (var colName in NgbNetwork.NeuronFloat64Names)
        {
            var expCol = expF64.GetProperty(colName).EnumerateArray().Select(x => x.GetDouble()).ToArray();
            int idx = Array.IndexOf(NgbNetwork.NeuronFloat64Names, colName);
            var actualCol = net.NeuronFloat64[idx];
            for (int i = 0; i < expCol.Length; i++)
            {
                Assert.Equal(expCol[i], actualCol[i]);
            }
        }

        // Synapses
        var expSyn = expected.GetProperty("synapse");
        var expPre = expSyn.GetProperty("pre").EnumerateArray().Select(x => x.GetInt32()).ToArray();
        var expPost = expSyn.GetProperty("post").EnumerateArray().Select(x => x.GetInt32()).ToArray();
        var expW = expSyn.GetProperty("weight").EnumerateArray().Select(x => x.GetInt32()).ToArray();
        var expD = expSyn.GetProperty("delay").EnumerateArray().Select(x => x.GetInt32()).ToArray();

        Assert.Equal(expPre, net.Pre);
        Assert.Equal(expPost, net.Post);
        Assert.Equal(expW, net.Weight);
        Assert.Equal(expD, net.Delay);

        // Extensions
        var expExts = expected.GetProperty("extensions");
        foreach (var prop in expExts.EnumerateObject())
        {
            var ext = net.Extensions.FirstOrDefault(e => e.Name == prop.Name);
            Assert.NotNull(ext);
            var axisStr = prop.Value.GetProperty("axis").GetString();
            Assert.Equal(axisStr == "neuron" ? NgbAxis.Neuron : NgbAxis.Synapse, ext.Axis);
            int comps = prop.Value.GetProperty("components").GetInt32();
            Assert.Equal(comps, ext.Components);

            var expVals = prop.Value.GetProperty("values").EnumerateArray().Select(x => x.GetDouble()).ToArray();
            long rows = ext.Axis == NgbAxis.Neuron ? net.NeuronCount : net.SynapseCount;
            Assert.Equal(rows * comps, expVals.Length);
            for (int r = 0; r < rows; r++)
            {
                for (int c = 0; c < comps; c++)
                {
                    double expV = expVals[r * comps + c];
                    double actV = ext.Value(r, c);
                    // Compare within floating tolerance for single/double precision
                    Assert.True(Math.Abs(expV - actV) <= 1e-4 * Math.Max(1.0, Math.Abs(expV)),
                        $"Mismatch on ext {prop.Name} row {r} comp {c}: expected {expV}, got {actV}");
                }
            }
        }
    }

    [Theory]
    [InlineData("empty")]
    [InlineData("extreme")]
    [InlineData("column")]
    [InlineData("extensions")]
    public void RoundTripMatchesOriginalBytes(string fixture)
    {
        string origPath = PythonFixtures.File(fixture);
        byte[] origBytes = File.ReadAllBytes(origPath);

        var net = NgbFile.Read(origPath);
        using var ms = new MemoryStream();
        NgbFile.Write(net, ms);
        byte[] writtenBytes = ms.ToArray();

        Assert.Equal(origBytes.Length, writtenBytes.Length);
        Assert.True(origBytes.SequenceEqual(writtenBytes), $"Bytes mismatch for fixture {fixture}");
    }

    [Fact]
    public void CorruptedFilesThrowInvalidDataException()
    {
        // Bad magic
        var badMagic = new byte[16];
        Assert.Throws<InvalidDataException>(() => NgbFile.Read(new MemoryStream(badMagic), badMagic.Length));

        // Short stream
        var shortStream = "NGB1"u8.ToArray();
        Assert.Throws<InvalidDataException>(() => NgbFile.Read(new MemoryStream(shortStream), shortStream.Length));

        // Unknown flags
        var badFlags = new byte[16];
        "NGB1"u8.CopyTo(badFlags.AsSpan(0, 4));
        BitConverter.TryWriteBytes(badFlags.AsSpan(12, 4), 0x02); // flag bit 1 is reserved
        Assert.Throws<InvalidDataException>(() => NgbFile.Read(new MemoryStream(badFlags), badFlags.Length));
    }
}
