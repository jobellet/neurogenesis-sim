using System.Runtime.InteropServices;
using Neurogenesis.Core.Ngb;
using Neurogenesis.Core.Simulation;
using Xunit;

namespace Neurogenesis.Tests;

public class NglifFixtureTests
{
    private static string FixturesDir()
    {
        string root = PythonFixtures.RepoRoot();
        string fixtures = Path.Combine(root, "desktop", "common", "fixtures");
        if (!Directory.Exists(fixtures))
            throw new DirectoryNotFoundException("Fixtures dir not found: " + fixtures);
        return fixtures;
    }

    private static int[] ReadI32File(string path)
    {
        byte[] bytes = File.ReadAllBytes(path);
        int count = bytes.Length / sizeof(int);
        var result = new int[count];
        Buffer.BlockCopy(bytes, 0, result, 0, bytes.Length);
        return result;
    }

    [Theory]
    [InlineData("column_saturated", 300, 12345u, "-")]
    [InlineData("column_unsaturated", 300, 12345u, "-")]
    [InlineData("column_external", 300, 12345u, "column_external.ext.i32")]
    [InlineData("column_extensions", 300, 12345u, "-")]
    [InlineData("microcircuit", 300, 12345u, "-")]
    [InlineData("layered", 300, 12345u, "-")]
    [InlineData("drivers_delays", 400, 12345u, "-")]
    [InlineData("drivers_delays_seed", 400, 999u, "-")]
    [InlineData("drivers_delays_external", 400, 4242u, "drivers_delays_external.ext.i32")]
    public void TestGoldenFixtureRunsIdentically(string name, int ticks, uint seed, string extFile)
    {
        string dir = FixturesDir();
        string ngbPath = Path.Combine(dir, $"{name}.ngb");
        string spikesPath = Path.Combine(dir, $"{name}.spikes.i32");

        int[] expectedPairs = ReadI32File(spikesPath);
        int expectedSpikeCount = expectedPairs.Length / 2;

        int[]? ext = null;
        if (extFile != "-")
        {
            string extPath = Path.Combine(dir, extFile);
            ext = ReadI32File(extPath);
        }

        var net = NgbFile.Read(ngbPath);

        // 1. Run via nglif_run
        using (var sim = new NglifSim(net, seed))
        {
            if (ext != null)
            {
                sim.SetExternal(ext);
            }

            var t = new int[expectedSpikeCount + 10];
            var i = new int[expectedSpikeCount + 10];
            long got = sim.Run(ticks, t, i);

            Assert.Equal(expectedSpikeCount, got);

            for (int k = 0; k < expectedSpikeCount; k++)
            {
                Assert.True(t[k] == expectedPairs[2 * k] && i[k] == expectedPairs[2 * k + 1],
                    $"Fixture {name} mismatch at spike {k}: expected ({expectedPairs[2 * k]}, {expectedPairs[2 * k + 1]}), got ({t[k]}, {i[k]})");
            }
        }

        // 2. Step-by-step live API
        using (var sim = new NglifSim(net, seed))
        {
            if (ext != null)
            {
                sim.SetExternal(ext);
            }

            var stepSpikes = new int[net.NeuronCount];
            int spikeIdx = 0;

            for (int tick = 0; tick < ticks; tick++)
            {
                int count = sim.Step(stepSpikes);
                for (int s = 0; s < count; s++)
                {
                    Assert.True(spikeIdx < expectedSpikeCount, $"Fixture {name}: step produced more spikes than expected ({spikeIdx} >= {expectedSpikeCount})");
                    int expTick = expectedPairs[2 * spikeIdx];
                    int expNeuron = expectedPairs[2 * spikeIdx + 1];

                    Assert.Equal(expTick, tick);
                    Assert.Equal(expNeuron, stepSpikes[s]);
                    spikeIdx++;
                }
            }

            Assert.Equal(expectedSpikeCount, spikeIdx);
        }
    }
}
