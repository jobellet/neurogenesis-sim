using System.Diagnostics;
using Neurogenesis.Core.Ngb;

namespace Neurogenesis.Core.Simulation;

public readonly record struct SpikeEvent(int Tick, int Neuron);

/// <summary>
/// Background simulation engine running nglif on a dedicated worker thread,
/// with support for pause/play, speed stepping, external stimulation, and spike ring buffer for live raster display.
/// </summary>
public sealed class SimulationEngine : IDisposable
{
    private readonly object _lock = new();
    private NglifSim? _sim;
    private Thread? _thread;
    private volatile bool _running;
    private volatile bool _disposed;

    public int NumNeurons { get; }
    public uint Seed { get; set; } = 12345;
    public double TicksPerSecond { get; set; } = 1000.0; // 0 = as fast as possible

    public long CurrentTick { get; private set; }
    public long TotalSpikes { get; private set; }
    public bool IsRunning => _running;

    // Spike ring buffer for raster (stores last N ticks of spikes)
    private readonly int _ringCapacityTicks = 1000;
    private readonly List<int>[] _spikeRing;

    // Snapshot of last spike tick per neuron for 3D flashes
    public int[] LastSpikeSnapshot { get; }

    public event Action? FrameStepped;

    public SimulationEngine(NgbNetwork net, uint seed = 12345)
    {
        NumNeurons = net.NeuronCount;
        Seed = seed;
        LastSpikeSnapshot = new int[NumNeurons];
        Array.Fill(LastSpikeSnapshot, int.MinValue);

        _spikeRing = new List<int>[_ringCapacityTicks];
        for (int k = 0; k < _ringCapacityTicks; k++)
        {
            _spikeRing[k] = new List<int>();
        }

        _sim = new NglifSim(net, seed);
    }

    public void Start()
    {
        lock (_lock)
        {
            if (_running || _disposed) return;
            _running = true;
            _thread = new Thread(RunLoop)
            {
                IsBackground = true,
                Name = "nglif-simulation-thread"
            };
            _thread.Start();
        }
    }

    public void Stop()
    {
        lock (_lock)
        {
            _running = false;
        }
        _thread?.Join(500);
        _thread = null;
    }

    public void Inject(int neuron, int current)
    {
        lock (_lock)
        {
            _sim?.Inject(neuron, current);
        }
    }

    public void SetExternal(int[]? ext)
    {
        lock (_lock)
        {
            _sim?.SetExternal(ext);
        }
    }

    public void StepOnce()
    {
        lock (_lock)
        {
            DoStep();
        }
        FrameStepped?.Invoke();
    }

    private void RunLoop()
    {
        var sw = Stopwatch.StartNew();
        long lastTick = 0;

        var buffer = new int[NumNeurons];

        while (_running && !_disposed)
        {
            bool step = false;
            double tps = TicksPerSecond;

            if (tps <= 0)
            {
                step = true;
            }
            else
            {
                double targetTicks = sw.Elapsed.TotalSeconds * tps;
                if (targetTicks > lastTick)
                {
                    step = true;
                    lastTick++;
                }
            }

            if (step)
            {
                lock (_lock)
                {
                    if (!_running || _disposed) break;
                    DoStep();
                }
                FrameStepped?.Invoke();
            }
            else
            {
                Thread.Sleep(1);
            }
        }
    }

    private void DoStep()
    {
        if (_sim == null) return;

        var stepSpikes = new int[NumNeurons];
        int count = _sim.Step(stepSpikes);

        CurrentTick = _sim.Tick;
        TotalSpikes += count;

        // Copy last spike states
        _sim.LastSpike.CopyTo(LastSpikeSnapshot);

        // Store into ring
        int ringIdx = (int)(CurrentTick % _ringCapacityTicks);
        var list = _spikeRing[ringIdx];
        list.Clear();
        for (int k = 0; k < count; k++)
        {
            list.Add(stepSpikes[k]);
        }
    }

    public List<SpikeEvent> GetRecentSpikes(int maxTicks)
    {
        var result = new List<SpikeEvent>();
        lock (_lock)
        {
            long cur = CurrentTick;
            long start = Math.Max(0, cur - maxTicks);
            for (long t = start; t <= cur; t++)
            {
                int idx = (int)(t % _ringCapacityTicks);
                var list = _spikeRing[idx];
                foreach (int n in list)
                {
                    result.Add(new SpikeEvent((int)t, n));
                }
            }
        }
        return result;
    }

    public void Dispose()
    {
        Stop();
        lock (_lock)
        {
            _disposed = true;
            _sim?.Dispose();
            _sim = null;
        }
    }
}
