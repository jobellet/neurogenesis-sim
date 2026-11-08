/**
 * SNN 3D Simulator & neurogenesis-sim viewer
 * Main Entry Point: Initializes SharedArrayBuffer (or in-memory fallback), Web Worker,
 * SceneManager, Inspector, and Raster Plot.
 */

import './style.css';
import {
  MAX_NEURONS,
  ControlIndex,
  CommandType,
  NeuronMode,
  SharedSimulationMemory,
  SerializedNetwork,
} from './sim/types';
import { createSharedSimulationMemory, safeLoad, safeStore, safeAdd, pushCommand } from './sim/memory';
import { SpatialHashManager } from './sim/spatialHash';
import { SceneManager } from './render/SceneManager';
import { Inspector } from './ui/Inspector';
import { RasterCanvas } from './ui/RasterCanvas';
import { DEFAULT_SEED, stepKernel } from './sim/kernel';

// 1. Allocate Simulation Memory (SharedArrayBuffer when available, ArrayBuffer fallback)
const simMem: SharedSimulationMemory = createSharedSimulationMemory();
const spatialHash = new SpatialHashManager();

// 2. Initialize Initial State
// Allow URL param override (?preset=column or ?test=1 for testing)
const urlParams = new URLSearchParams(window.location.search);
const shouldStartWithColumn = urlParams.get('preset') === 'column' || urlParams.get('test') === '1';

const INITIAL_NEURONS = shouldStartWithColumn ? 1000 : 0;
if (INITIAL_NEURONS > 0) {
  initializeCorticalColumn(simMem, INITIAL_NEURONS);
  const initialSynCount = spatialHash.rewireAll(simMem, INITIAL_NEURONS);
  safeStore(simMem.control, ControlIndex.NUM_NEURONS, INITIAL_NEURONS);
  safeStore(simMem.control, ControlIndex.NUM_SYNAPSES, initialSynCount);
} else {
  spatialHash.clearAll(simMem);
  safeStore(simMem.control, ControlIndex.NUM_NEURONS, 0);
  safeStore(simMem.control, ControlIndex.NUM_SYNAPSES, 0);
}
safeStore(simMem.control, ControlIndex.SIM_HZ, 1000);
safeStore(simMem.control, ControlIndex.IS_RUNNING, 1);

// 3. Viewport & Simulation Orchestration
let isUsingWorker = false;
let worker: Worker | null = null;
let sceneManager: SceneManager;

if (simMem.isShared) {
  try {
    console.log('[Main] Spawning simulation worker...');
    worker = new Worker(new URL('./sim/sim.worker.ts', import.meta.url), {
      type: 'module',
    });

    worker.onerror = (err) => {
      console.error('[Main] WORKER ONERROR:', err);
      isUsingWorker = false;
    };

    console.log('[Main] Posting INIT to worker with buffer:', simMem.buffer);
    worker.postMessage({
      type: 'INIT',
      buffer: simMem.buffer,
      numNeurons: INITIAL_NEURONS,
    });

    worker.onmessage = (e: MessageEvent) => {
      if (sceneManager) {
        if (e.data?.type === 'INIT_DONE' || e.data?.type === 'CLEAR_DONE' || e.data?.type === 'SYNC_DONE') {
          sceneManager.syncPositionsFromMemory();
          sceneManager.updateGlobalSynapseGeometry();
        }
      }
    };

    isUsingWorker = true;
  } catch (err) {
    console.warn('Worker initialization failed, using in-process simulation loop:', err);
    isUsingWorker = false;
  }
} else {
  console.info('SharedArrayBuffer not available in this browser context. Running high-performance in-process simulation.');
}

// 4. Initialize 3D Viewport, Inspector, and Raster Plot
const appContainer = document.getElementById('app') || document.body;

sceneManager = new SceneManager(appContainer, simMem);
const inspector = new Inspector(appContainer, simMem, spatialHash);
const rasterCanvas = new RasterCanvas(appContainer, simMem);
import { PopulationFilter } from "./ui/PopulationFilter";
const popFilter = new PopulationFilter(appContainer, simMem);
rasterCanvas.popFilter = popFilter;
sceneManager.popFilter = popFilter;
popFilter.onFilterChanged = () => {
  sceneManager.syncPositionsFromMemory();
  sceneManager.updateGlobalSynapseGeometry();
};

// 5. Connect Callbacks
sceneManager.onNeuronSelected = (id: number | null) => {
  inspector.setSelectedNeuron(id);
  sceneManager.updateSelectedNeuronVisuals(id);
};

// Global debug reference for testing and scripting
(window as any).__snn = {
  simMem,
  spatialHash,
  sceneManager,
  inspector,
  rasterCanvas,
  spawnNeuronAt,
  deleteNeuron,
  generatePopulation,
  clearNetwork,
  importNetwork,
  exportNetworkToFile,
  openStartupModal: () => inspector.openStartupModal(),
  setGeneEIRatio: (val: number) => inspector.setGeneEIRatio(val),
  setGeneSigmaScale: (val: number) => inspector.setGeneSigmaScale(val),
  setDrugGabaDose: (val: number) => inspector.setDrugGabaDose(val),
  setDrugAmpaGain: (val: number) => inspector.setDrugAmpaGain(val),
  getTargetFitness: () => inspector.getTargetFitness(),
  captureBaseline: () => inspector.captureBaseline(),
};

// Support Drag & Drop of network.json files directly onto the window
window.addEventListener('dragover', (e) => {
  e.preventDefault();
  e.dataTransfer!.dropEffect = 'copy';
});

window.addEventListener('drop', (e) => {
  e.preventDefault();
  const file = e.dataTransfer?.files[0];
  if (file && file.name.endsWith('.json')) {
    const reader = new FileReader();
    reader.onload = (evt) => {
      try {
        const net = JSON.parse(evt.target?.result as string);
        importNetwork(net);
      } catch (err) {
        alert('Could not parse dropped JSON network: ' + err);
      }
    };
    reader.readAsText(file);
  }
});

sceneManager.onNeuronSpawnRequested = (x: number, y: number, z: number) => {
  spawnNeuronAt(x, y, z);
};

sceneManager.onSynapseDragComplete = (preId: number, postId: number, dist: number) => {
  inspector.showSynapseModal(preId, postId, dist);
};

sceneManager.onNeuronDeleteRequested = (id: number) => {
  deleteNeuron(id);
};

inspector.onToolModeChanged = (mode) => {
  sceneManager.toolMode = mode;
};

inspector.onNeuronParamsUpdated = () => {
  const selectedId = safeLoad(simMem.control, ControlIndex.SELECTED_NEURON);
  sceneManager.updateSelectedNeuronVisuals(selectedId >= 0 ? selectedId : null);
  sceneManager.syncPositionsFromMemory();
};

inspector.onGlobalRewireRequested = () => {
  const numNeurons = safeLoad(simMem.control, ControlIndex.NUM_NEURONS);
  const total = spatialHash.rewireAll(simMem, numNeurons);
  safeStore(simMem.control, ControlIndex.NUM_SYNAPSES, total);
  sceneManager.updateGlobalSynapseGeometry();
  const selectedId = safeLoad(simMem.control, ControlIndex.SELECTED_NEURON);
  sceneManager.updateSelectedNeuronVisuals(selectedId >= 0 ? selectedId : null);
};

inspector.onPlaneYChanged = (y: number) => {
  sceneManager.setPlaneY(y);
};

inspector.onToggleGlobalSynapses = (show: boolean) => {
  sceneManager.showGlobalSynapses = show;
  sceneManager.updateGlobalSynapseGeometry();
};

inspector.onNeuronDelete = (id: number) => {
  deleteNeuron(id);
};

inspector.onClearNetwork = () => {
  clearNetwork();
};

inspector.onStartConfiguredSimulation = (config: any) => {
  safeStore(simMem.control, ControlIndex.SIM_HZ, config.hz || 1000);
  safeStore(simMem.control, ControlIndex.IS_RUNNING, config.isRunning !== undefined ? config.isRunning : 1);
  pushCommand(simMem, CommandType.SET_HZ, config.hz || 1000);
  pushCommand(simMem, CommandType.SET_RUNNING, config.isRunning !== undefined ? config.isRunning : 1);
  generatePopulation(config);
};

inspector.onRegeneratePopulation = (config) => {
  generatePopulation(config);
};

inspector.onExportNetwork = () => {
  exportNetworkToFile();
};

inspector.onImportNetwork = (net: SerializedNetwork) => {
  importNetwork(net);
};

// 6. Spawn, Delete, and Population Management Functions
function spawnNeuronAt(x: number, y: number, z: number): void {
  const currentCount = safeLoad(simMem.control, ControlIndex.NUM_NEURONS);
  if (currentCount >= MAX_NEURONS) {
    alert('Maximum neuron capacity reached (10,000 neurons).');
    return;
  }

  const id = currentCount;
  simMem.posXYZ[id * 3] = x;
  simMem.posXYZ[id * 3 + 1] = y;
  simMem.posXYZ[id * 3 + 2] = z;

  const randTh = Math.random() * Math.PI * 2;
  simMem.axonDirXYZ[id * 3] = Math.cos(randTh) * 0.2;
  simMem.axonDirXYZ[id * 3 + 1] = 0.95;
  simMem.axonDirXYZ[id * 3 + 2] = Math.sin(randTh) * 0.2;

  simMem.vMem[id] = 0;
  simMem.refractory[id] = 0;
  simMem.refrCount[id] = 0;
  simMem.role[id] = 0;
  simMem.threshold[id] = 1024;
  simMem.iSyn[id] = 0;
  simMem.shiftV[id] = 5;
  simMem.shiftS[id] = 4;
  simMem.spikeBitfield[id] = 0;
  simMem.visualFlash[id] = 255;

  const mode = inspector.spawnType;
  simMem.neuronMode[id] = mode;
  simMem.baseWeight[id] = inspector.spawnWeight;
  simMem.connRadius[id] = 25.0;
  simMem.connProb[id] = 0.40;

  if (mode === NeuronMode.POISSON) {
    const probPerTick = 25.0 / 1000.0;
    simMem.poissonThresh[id] = Math.floor(probPerTick * 4294967296);
  } else if (mode === NeuronMode.BURSTER) {
    simMem.burstPeriod[id] = 200;
    simMem.burstDuty[id] = 24;
    simMem.burstPhase[id] = Math.floor(Math.random() * 200);
  }

  const newTotal = currentCount + 1;
  safeStore(simMem.control, ControlIndex.NUM_NEURONS, newTotal);

  const totalSyn = spatialHash.rewireSingleNeuron(simMem, id, newTotal);
  safeStore(simMem.control, ControlIndex.NUM_SYNAPSES, totalSyn);

  if (isUsingWorker) {
    pushCommand(simMem, CommandType.ADD_NEURON, id);
  }

  safeStore(simMem.control, ControlIndex.SELECTED_NEURON, id);
  inspector.setSelectedNeuron(id);
  sceneManager.syncPositionsFromMemory();
  sceneManager.updateSelectedNeuronVisuals(id);
}

function deleteNeuron(id: number): void {
  const currentCount = safeLoad(simMem.control, ControlIndex.NUM_NEURONS);
  if (currentCount <= 0) return;

  const updatedCount = spatialHash.deleteNeuron(simMem, id, currentCount);
  safeStore(simMem.control, ControlIndex.NUM_NEURONS, updatedCount);
  safeStore(simMem.control, ControlIndex.NUM_SYNAPSES, updatedCount > 0 ? simMem.rowPtr[updatedCount] : 0);

  if (isUsingWorker) {
    pushCommand(simMem, CommandType.DELETE_NEURON, id);
  }

  safeStore(simMem.control, ControlIndex.SELECTED_NEURON, -1);
  inspector.setSelectedNeuron(null);
  inspector.updateHintBanner();
  sceneManager.syncPositionsFromMemory();
  sceneManager.updateSelectedNeuronVisuals(null);
  sceneManager.updateGlobalSynapseGeometry();
}

function clearNetwork(): void {
  spatialHash.clearAll(simMem);
  safeStore(simMem.control, ControlIndex.NUM_NEURONS, 0);
  safeStore(simMem.control, ControlIndex.NUM_SYNAPSES, 0);
  safeStore(simMem.control, ControlIndex.SELECTED_NEURON, -1);
  safeStore(simMem.control, ControlIndex.SIM_TICK, 0);
  safeStore(simMem.control, ControlIndex.SPIKE_COUNT, 0);
  safeStore(simMem.control, ControlIndex.TOTAL_SPIKES, 0);

  if (isUsingWorker && worker) {
    worker.postMessage({ type: 'CLEAR' });
  }

  inspector.setSelectedNeuron(null);
  inspector.setToolMode('SPAWN');
  inspector.updateHintBanner();
  sceneManager.syncPositionsFromMemory();
  sceneManager.updateGlobalSynapseGeometry();
}

function generatePopulation(config: {
  count: number;
  morphology: string;
  excRatio: number;
  paceRatio: number;
  sigma: number;
}): void {
  if (config.count <= 0 || config.morphology === 'empty' || config.morphology === 'blank') {
    clearNetwork();
    return;
  }

  const count = Math.min(MAX_NEURONS, Math.max(1, config.count));
  const numPace = Math.max(0, Math.round(count * config.paceRatio));
  const numInh = Math.round(count * (1 - config.excRatio));

  for (let i = 0; i < count; i++) {
    let x = 0, y = 0, z = 0;
    let dirX = 0, dirY = 1, dirZ = 0;

    if (config.morphology === 'column') {
      const r = Math.sqrt(Math.random()) * 30.0;
      const theta = Math.random() * Math.PI * 2;
      x = r * Math.cos(theta);
      z = r * Math.sin(theta);
      y = (Math.random() - 0.5) * 150.0;
      dirY = y > 0 ? -0.7 : 0.8;
      dirX = (Math.random() - 0.5) * 0.8;
      dirZ = (Math.random() - 0.5) * 0.8;
    } else if (config.morphology === 'layered') {
      const layer = Math.floor(Math.random() * 4); // 4 horizontal sheets
      y = -60 + layer * 40;
      x = (Math.random() - 0.5) * 80.0;
      z = (Math.random() - 0.5) * 80.0;
      dirY = layer < 3 ? 0.9 : -0.9;
    } else {
      // 3D Volume / Microcircuit
      const span = config.morphology === 'microcircuit' ? 35.0 : 80.0;
      x = (Math.random() - 0.5) * span * 2;
      y = (Math.random() - 0.5) * span * 2;
      z = (Math.random() - 0.5) * span * 2;
      const angle = Math.random() * Math.PI * 2;
      dirX = Math.cos(angle);
      dirY = (Math.random() - 0.5) * 0.8;
      dirZ = Math.sin(angle);
    }

    const norm = Math.sqrt(dirX * dirX + dirY * dirY + dirZ * dirZ) || 1.0;
    dirX /= norm; dirY /= norm; dirZ /= norm;

    simMem.posXYZ[i * 3] = x;
    simMem.posXYZ[i * 3 + 1] = y;
    simMem.posXYZ[i * 3 + 2] = z;
    simMem.axonDirXYZ[i * 3] = dirX;
    simMem.axonDirXYZ[i * 3 + 1] = dirY;
    simMem.axonDirXYZ[i * 3 + 2] = dirZ;

    simMem.vMem[i] = 0;
    simMem.refractory[i] = 0;
    simMem.refrCount[i] = 0;
    simMem.role[i] = 0;
    simMem.threshold[i] = 1024;
    simMem.iSyn[i] = 0;
    simMem.spikeBitfield[i] = 0;
    simMem.visualFlash[i] = 0;
    simMem.connRadius[i] = config.sigma;

    if (i < numPace) {
      simMem.neuronMode[i] = i % 2 === 0 ? NeuronMode.POISSON : NeuronMode.BURSTER;
      simMem.baseWeight[i] = 240;
      simMem.connProb[i] = 0.50;
      simMem.shiftV[i] = 5;
      simMem.shiftS[i] = 4;
      simMem.burstPeriod[i] = 180 + Math.floor(Math.random() * 80);
      simMem.burstDuty[i] = 24 + Math.floor(Math.random() * 8);
      simMem.burstPhase[i] = Math.floor(Math.random() * simMem.burstPeriod[i]);
      simMem.poissonThresh[i] = Math.floor((22.0 / 1000.0) * 4294967296);
    } else if (i < numPace + numInh) {
      simMem.neuronMode[i] = NeuronMode.LIF;
      simMem.baseWeight[i] = -320;
      simMem.connProb[i] = 0.55;
      simMem.shiftV[i] = 4;
      simMem.shiftS[i] = 3;
    } else {
      simMem.neuronMode[i] = NeuronMode.LIF;
      simMem.baseWeight[i] = 180;
      simMem.connProb[i] = 0.38;
      simMem.shiftV[i] = 5;
      simMem.shiftS[i] = 4;
    }
  }

  safeStore(simMem.control, ControlIndex.NUM_NEURONS, count);
  const synTotal = spatialHash.rewireAll(simMem, count);
  safeStore(simMem.control, ControlIndex.NUM_SYNAPSES, synTotal);

  if (isUsingWorker && worker) {
    worker.postMessage({ type: 'INIT', buffer: simMem.buffer, numNeurons: count });
  }

  safeStore(simMem.control, ControlIndex.SELECTED_NEURON, -1);
  inspector.setSelectedNeuron(null);
  sceneManager.syncPositionsFromMemory();
  sceneManager.updateGlobalSynapseGeometry();
  inspector.captureBaseline();
}

function exportNetworkToFile(): void {
  const count = safeLoad(simMem.control, ControlIndex.NUM_NEURONS);
  const net = spatialHash.exportNetworkJSON(simMem, count);
  const blob = new Blob([JSON.stringify(net, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `snn_network_${count}neurons.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function importNetwork(net: SerializedNetwork): void {
  const loadedCount = spatialHash.importNetworkJSON(simMem, net);
  safeStore(simMem.control, ControlIndex.NUM_NEURONS, loadedCount);
  safeStore(simMem.control, ControlIndex.NUM_SYNAPSES, simMem.rowPtr[loadedCount]);

  if (isUsingWorker && worker) {
    worker.postMessage({ type: 'INIT', buffer: simMem.buffer, numNeurons: loadedCount });
  }

  safeStore(simMem.control, ControlIndex.SELECTED_NEURON, -1);
  inspector.setSelectedNeuron(null);
  sceneManager.syncPositionsFromMemory();
  sceneManager.updateGlobalSynapseGeometry();
  inspector.captureBaseline();
}

function initializeCorticalColumn(mem: SharedSimulationMemory, count: number): void {
  const colRadius = 30.0;
  const colHeight = 150.0;
  const numPoisson = 25;
  const numBurster = 25;
  const numInh = Math.round(count * 0.20);

  for (let i = 0; i < count; i++) {
    const r = Math.sqrt(Math.random()) * colRadius;
    const theta = Math.random() * Math.PI * 2;
    const x = r * Math.cos(theta);
    const z = r * Math.sin(theta);
    let y = (Math.random() - 0.5) * colHeight;

    let mode = NeuronMode.LIF;
    let baseW = 160;
    let shiftV = 5;
    let shiftS = 4;
    let connR = 28.0;
    let connP = 0.35;
    let dirX = 0, dirY = 1, dirZ = 0;

    if (i < numPoisson) {
      mode = NeuronMode.POISSON;
      baseW = 220;
      y = -65.0 + Math.random() * 30.0;
      mem.poissonThresh[i] = Math.floor((22.0 / 1000.0) * 4294967296);
      connR = 35.0;
      connP = 0.55;
      dirY = 0.98;
    } else if (i < numPoisson + numBurster) {
      mode = NeuronMode.BURSTER;
      baseW = 250;
      y = -70.0 + Math.random() * 40.0;
      mem.burstPeriod[i] = 180 + Math.floor(Math.random() * 100);
      mem.burstDuty[i] = 26;
      mem.burstPhase[i] = Math.floor(Math.random() * mem.burstPeriod[i]);
      connR = 35.0;
      connP = 0.50;
      dirY = 0.95;
    } else if (i < numPoisson + numBurster + numInh) {
      mode = NeuronMode.LIF;
      baseW = -320;
      shiftV = 4;
      shiftS = 3;
      connR = 16.0;
      connP = 0.55;
      const angle = Math.random() * Math.PI * 2;
      dirX = Math.cos(angle);
      dirY = (Math.random() - 0.5) * 0.8;
      dirZ = Math.sin(angle);
    } else {
      mode = NeuronMode.LIF;
      baseW = 160 + Math.floor(Math.random() * 60);
      shiftV = 5;
      shiftS = 4;
      connR = 26.0;
      connP = 0.38;
      if (y > 15) {
        dirY = -0.6;
        dirX = (Math.random() - 0.5) * 1.2;
        dirZ = (Math.random() - 0.5) * 1.2;
      } else {
        dirY = 0.85;
        dirX = (Math.random() - 0.5) * 0.5;
        dirZ = (Math.random() - 0.5) * 0.5;
      }
    }

    const norm = Math.sqrt(dirX * dirX + dirY * dirY + dirZ * dirZ) || 1.0;
    dirX /= norm; dirY /= norm; dirZ /= norm;

    mem.posXYZ[i * 3] = x;
    mem.posXYZ[i * 3 + 1] = y;
    mem.posXYZ[i * 3 + 2] = z;
    mem.axonDirXYZ[i * 3] = dirX;
    mem.axonDirXYZ[i * 3 + 1] = dirY;
    mem.axonDirXYZ[i * 3 + 2] = dirZ;

    mem.vMem[i] = 0;
    mem.refractory[i] = 0;
    mem.refrCount[i] = 0;
    mem.role[i] = 0;
    mem.threshold[i] = 1024;
    mem.iSyn[i] = 0;
    mem.shiftV[i] = shiftV;
    mem.shiftS[i] = shiftS;
    mem.neuronMode[i] = mode;
    mem.connRadius[i] = connR;
    mem.connProb[i] = connP;
    mem.baseWeight[i] = baseW;
    mem.spikeBitfield[i] = 0;
    mem.visualFlash[i] = 0;
  }
}

// 7. Master In-Process Simulation Step (Active if worker unavailable or in fallback)
let prngState = DEFAULT_SEED;
function stepInProcess(): void {
  const numNeurons = safeLoad(simMem.control, ControlIndex.NUM_NEURONS);
  const [tickSpikes, nextPrng] = stepKernel(simMem, numNeurons, prngState);
  prngState = nextPrng;
  safeAdd(simMem.control, ControlIndex.SIM_TICK, 1);
  safeStore(simMem.control, ControlIndex.SPIKE_COUNT, tickSpikes);
  safeAdd(simMem.control, ControlIndex.TOTAL_SPIKES, tickSpikes);
}

// 8. Master Animation Loop (60 FPS)
let lastFrameTime = performance.now();
let inProcessTickAcc = 0;

function animate(): void {
  requestAnimationFrame(animate);

  const now = performance.now();
  const dt = Math.min((now - lastFrameTime) / 1000.0, 0.1);
  lastFrameTime = now;

  // If running in-process fallback without worker:
  if (!isUsingWorker) {
    const isRunning = safeLoad(simMem.control, ControlIndex.IS_RUNNING) === 1;
    const hz = safeLoad(simMem.control, ControlIndex.SIM_HZ) || 1000;
    if (isRunning) {
      inProcessTickAcc += dt * hz;
      const ticks = Math.min(Math.floor(inProcessTickAcc), 60);
      for (let k = 0; k < ticks; k++) {
        stepInProcess();
      }
      inProcessTickAcc -= ticks;
      safeStore(simMem.control, ControlIndex.WORKER_FPS, Math.round(hz));
    }
  }

  sceneManager.render(dt);
  rasterCanvas.render();
  inspector.updateTelemetry();
}

requestAnimationFrame(animate);

inspector.captureBaseline();

// Open Simulation Setup Modal on initial startup unless in automated test mode
if (!window.location.search.includes('no-modal') && !window.location.search.includes('test=1')) {
  inspector.openStartupModal();
}
