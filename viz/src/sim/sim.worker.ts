/**
 * Dedicated SNN Simulation Web Worker
 * Executes integer-only SNN kernel, bitwise delay engine, and lock-free commands.
 */

import {
  ControlIndex,
  CommandType,
  SharedSimulationMemory,
} from './types';
import { createSharedSimulationMemory, popCommand, safeLoad, safeStore, safeAdd, safeSub } from './memory';
import { SpatialHashManager } from './spatialHash';
import { DEFAULT_SEED, stepKernel } from './kernel';
import { PopulationRhythm } from './rhythm';

console.log('[Worker] Script executing...');
let mem: SharedSimulationMemory | null = null;
const spatialHash = new SpatialHashManager();

let prngState = DEFAULT_SEED;
let lastTickTime = performance.now();
let tickAccumulator = 0;
let lastFpsTime = performance.now();
let tickCounterForFps = 0;
const rhythm = new PopulationRhythm();

function resetRhythm(): void {
  rhythm.reset();
  if (!mem) return;
  safeStore(mem.control, ControlIndex.RHYTHM_PEAK_MHZ, 0);
  safeStore(mem.control, ControlIndex.RHYTHM_CV_MILLI, 0);
}

function executeCommand(cmdType: number, arg1: number, arg2: number, arg3: number): void {
  if (!mem) return;

  switch (cmdType) {
    case CommandType.ADD_NEURON:
    case CommandType.DELETE_NEURON:
    case CommandType.SET_SYNAPSE:
    case CommandType.REMOVE_SYNAPSE:
    case CommandType.REWIRE_NEURON:
    case CommandType.REWIRE_ALL:
      // Graph topology mutations are managed synchronously by SpatialHashManager on the main thread
      // and written directly into the shared CSR buffers (rowPtr, colIdx, weights, delays).
      // Worker reads them immediately on the next tick with zero lock overhead.
      break;

    case CommandType.INJECT_CURRENT: {
      const neuronId = arg1;
      const current = arg2;
      const numNeurons = safeLoad(mem.control, ControlIndex.NUM_NEURONS);
      if (neuronId >= 0 && neuronId < numNeurons) {
        mem.iSyn[neuronId] += current;
      }
      break;
    }

    case CommandType.SET_HZ: {
      const hz = Math.max(100, Math.min(5000, arg1));
      safeStore(mem.control, ControlIndex.SIM_HZ, hz);
      break;
    }

    case CommandType.SET_RUNNING: {
      safeStore(mem.control, ControlIndex.IS_RUNNING, arg1 ? 1 : 0);
      break;
    }

    case CommandType.STEP: {
      const count = Math.max(1, arg1);
      safeAdd(mem.control, ControlIndex.STEP_COUNT, count);
      break;
    }

    case CommandType.RESET_VOLTAGES: {
      const numNeurons = safeLoad(mem.control, ControlIndex.NUM_NEURONS);
      for (let i = 0; i < numNeurons; i++) {
        mem.vMem[i] = 0;
        mem.iSyn[i] = 0;
        mem.spikeBitfield[i] = 0;
        mem.visualFlash[i] = 0;
        mem.burstPhase[i] = 0;
        mem.refrCount[i] = 0;
      }
      break;
    }
  }
}

function processAllCommands(): void {
  if (!mem) return;
  let cmd = popCommand(mem);
  while (cmd !== null) {
    executeCommand(cmd.cmdType, cmd.arg1, cmd.arg2, cmd.arg3);
    cmd = popCommand(mem);
  }
}

function stepSimulation(): void {
  if (!mem) return;
  const numNeurons = safeLoad(mem.control, ControlIndex.NUM_NEURONS);
  const [tickSpikeCount, nextPrng] = stepKernel(mem, numNeurons, prngState);
  prngState = nextPrng;

  safeAdd(mem.control, ControlIndex.SIM_TICK, 1);
  safeStore(mem.control, ControlIndex.SPIKE_COUNT, tickSpikeCount);
  safeAdd(mem.control, ControlIndex.TOTAL_SPIKES, tickSpikeCount);
  if (rhythm.push(tickSpikeCount)) {
    safeStore(mem.control, ControlIndex.RHYTHM_PEAK_MHZ, Math.round(rhythm.peakHz * 1000));
    safeStore(mem.control, ControlIndex.RHYTHM_CV_MILLI, Math.round(rhythm.variability * 1000));
  }

  tickCounterForFps++;
}

let loopRunning = false;

function simulationLoop(): void {
  if (!mem) return;

  const now = performance.now();
  const dt = Math.min((now - lastTickTime) / 1000.0, 0.1);
  lastTickTime = now;

  processAllCommands();

  const numNeurons = safeLoad(mem.control, ControlIndex.NUM_NEURONS);
  const isRunning = safeLoad(mem.control, ControlIndex.IS_RUNNING) === 1;
  const targetHz = safeLoad(mem.control, ControlIndex.SIM_HZ) || 1000;
  const stepCount = safeLoad(mem.control, ControlIndex.STEP_COUNT);

  if (numNeurons > 0) {
    if (stepCount > 0) {
      const toStep = Math.min(stepCount, 50);
      for (let s = 0; s < toStep; s++) {
        stepSimulation();
      }
      safeSub(mem.control, ControlIndex.STEP_COUNT, toStep);
    } else if (isRunning) {
      tickAccumulator += dt * targetHz;
      if (tickAccumulator > targetHz * 0.2) {
        tickAccumulator = targetHz * 0.2;
      }

      const ticksToRun = Math.floor(tickAccumulator);
      if (ticksToRun > 0) {
        for (let k = 0; k < ticksToRun; k++) {
          stepSimulation();
        }
        tickAccumulator -= ticksToRun;
      }
    }
  } else {
    tickAccumulator = 0;
    safeStore(mem.control, ControlIndex.SPIKE_COUNT, 0);
  }

  if (now - lastFpsTime >= 500) {
    const elapsedSec = (now - lastFpsTime) / 1000.0;
    const actualFps = Math.round(tickCounterForFps / elapsedSec);
    safeStore(mem.control, ControlIndex.WORKER_FPS, actualFps);
    tickCounterForFps = 0;
    lastFpsTime = now;
  }

  setTimeout(simulationLoop, 1);
}

self.onmessage = (e: MessageEvent) => {
  console.log('[Worker] onmessage received type:', e.data?.type);
  const data = e.data;
  if (!data) return;

  if (data.type === 'INIT') {
    mem = createSharedSimulationMemory(data.buffer);
    const initialNeurons = typeof data.numNeurons === 'number' ? data.numNeurons : 0;
    safeStore(mem.control, ControlIndex.NUM_NEURONS, initialNeurons);
    safeStore(mem.control, ControlIndex.SIM_HZ, 1000);
    safeStore(mem.control, ControlIndex.IS_RUNNING, 1);

    if (initialNeurons > 0) {
      // The main thread has already built the CSR (rowPtr, colIdx, weights, delays) in shared memory, either by
      // rewiring or by importing a network. Rewiring here again would replace it with a different random graph,
      // so that the simulated synapses would differ from the displayed (or imported) ones.
      const synCount = mem.rowPtr[initialNeurons];
      safeStore(mem.control, ControlIndex.NUM_SYNAPSES, synCount);
      safeStore(mem.control, ControlIndex.SIM_TICK, 0);
      safeStore(mem.control, ControlIndex.TOTAL_SPIKES, 0);
      prngState = DEFAULT_SEED;
      resetRhythm();
      self.postMessage({ type: 'INIT_DONE', numSynapses: synCount });
    } else {
      spatialHash.clearAll(mem);
      safeStore(mem.control, ControlIndex.NUM_SYNAPSES, 0);
      self.postMessage({ type: 'INIT_DONE', numSynapses: 0 });
    }

    lastTickTime = performance.now();
    lastFpsTime = performance.now();
    tickAccumulator = 0;
    tickCounterForFps = 0;

    if (!loopRunning) {
      loopRunning = true;
      simulationLoop();
    }
  } else if (data.type === 'CLEAR') {
    if (mem) {
      spatialHash.clearAll(mem);
      safeStore(mem.control, ControlIndex.NUM_NEURONS, 0);
      safeStore(mem.control, ControlIndex.NUM_SYNAPSES, 0);
      safeStore(mem.control, ControlIndex.SELECTED_NEURON, -1);
      safeStore(mem.control, ControlIndex.SIM_TICK, 0);
      safeStore(mem.control, ControlIndex.SPIKE_COUNT, 0);
      safeStore(mem.control, ControlIndex.TOTAL_SPIKES, 0);
      resetRhythm();
      self.postMessage({ type: 'CLEAR_DONE' });
    }
  } else if (data.type === 'SYNC_ALL_SYNAPSES') {
    if (mem) {
      const numNeurons = safeLoad(mem.control, ControlIndex.NUM_NEURONS);
      // The CSR is owned by the main thread; the worker's own adjacency lists are empty, so it only reports the count.
      const total = numNeurons > 0 ? mem.rowPtr[numNeurons] : 0;
      safeStore(mem.control, ControlIndex.NUM_SYNAPSES, total);
      self.postMessage({ type: 'SYNC_DONE', numSynapses: total });
    }
  }
};
