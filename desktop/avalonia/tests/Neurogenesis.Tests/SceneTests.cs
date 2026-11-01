using System.Diagnostics;
using System.Numerics;
using Neurogenesis.Core.Ngb;
using Neurogenesis.Core.Scene;
using Neurogenesis.Core.Style;
using Xunit;

namespace Neurogenesis.Tests;

public class SceneTests
{
    [Fact]
    public void LargeNetworkSubsamplingAndPerformance()
    {
        // Test responsiveness with 10^5 neurons and 10^7 synapses
        int n = 100_000;
        int e = 10_000_000;
        var net = new NgbNetwork(n, e);

        // Fill with dummy positions
        for (int i = 0; i < n; i++)
        {
            net.Positions[3 * i] = (i % 100) * 1.5;
            net.Positions[3 * i + 1] = ((i / 100) % 100) * 1.5;
            net.Positions[3 * i + 2] = (i / 10000) * 1.5;
        }

        // Fill synapses (cyclic)
        for (int s = 0; s < e; s++)
        {
            net.Pre[s] = s % n;
            net.Post[s] = (s + 1) % n;
            net.Weight[s] = 100;
        }

        var sw = Stopwatch.StartNew();
        var scene = new SceneData(net, VisualStyle.Default);
        sw.Stop();

        // 10^5 neurons should all be retained since neuron budget is 2,000,000
        Assert.Equal(n, scene.InstanceNeuron.Length);

        // 10^7 synapses must be subsampled down to synapse budget (200,000)
        Assert.True(scene.DrawnSynapses <= VisualStyle.Default.SynapseBudget);
        Assert.Contains("synapses", scene.Note);

        // Building the scene must complete in a few seconds (linear time)
        Assert.True(sw.ElapsedMilliseconds < 5000, $"Scene construction took {sw.ElapsedMilliseconds} ms, expected < 5000 ms");

        // Instances color/scale generation
        sw.Restart();
        var instances = scene.Instances(scene.Style.ColorModes[0], selected: 42);
        sw.Stop();
        Assert.Equal(n * SceneData.InstanceStride, instances.Length);
        Assert.True(sw.ElapsedMilliseconds < 1000, $"Instances generation took {sw.ElapsedMilliseconds} ms, expected < 1000 ms");

        // Selected neuron check
        int offset = 42 * SceneData.InstanceStride;
        Assert.Equal(scene.Style.SelectedScale, instances[offset + 3]);
        Assert.Equal(scene.Style.SelectedColor.X, instances[offset + 4]);
        Assert.Equal(scene.Style.SelectedColor.Y, instances[offset + 5]);
        Assert.Equal(scene.Style.SelectedColor.Z, instances[offset + 6]);
    }

    [Fact]
    public void CameraPickingFindsCorrectNeuron()
    {
        var cam = new Camera();
        cam.Frame(Vector3.Zero, 10f);

        var instances = new float[]
        {
            0f, 0f, 0f, 1f, 1f, 1f, 1f, 1f, -1f,    // instance 0 at (0, 0, 0)
            50f, 50f, 0f, 1f, 1f, 1f, 1f, 1f, -1f  // instance 1 at (50, 50, 0)
        };

        // Center of viewport (500, 500) on a 1000x1000 screen
        int hit = cam.Pick(instances, SceneData.InstanceStride, 1000f, 1000f, 500f, 500f, 4f, 1f, minPx: 10f);
        Assert.Equal(0, hit);

        // Far away point
        int miss = cam.Pick(instances, SceneData.InstanceStride, 1000f, 1000f, 10f, 10f, 4f, 1f, minPx: 10f);
        Assert.Equal(-1, miss);
    }
}
