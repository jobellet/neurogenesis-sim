/**
 * Real-Time Cyber-Neuromorphic Inspector GUI
 * Directly binds to SharedArrayBuffer views for instantaneous parameter mutation.
 * Features drag-and-drop synapse creation modal, live oscilloscope, synapse manager list,
 * population generator modal, and JSON import/export.
 */

import {
  ControlIndex,
  CommandType,
  NeuronMode,
  ToolMode,
  SharedSimulationMemory,
  SerializedNetwork,
  MAX_NEURONS,
  MAX_SYNAPSES,
} from '../sim/types';
import { safeLoad, safeStore, pushCommand } from '../sim/memory';
import { SpatialHashManager } from '../sim/spatialHash';

export class Inspector {
  private container: HTMLElement;
  public selectedNeuronId: number | null = null;
  public spatialHash: SpatialHashManager;

  // DOM Elements
  private rootEl: HTMLElement;
  private globalToolbarEl: HTMLElement;
  private hintBannerEl: HTMLElement;
  private neuronPanelEl: HTMLElement;
  private modalContainerEl: HTMLElement;

  // Oscilloscope canvas for selected neuron
  private oscCanvas: HTMLCanvasElement | null = null;
  private oscCtx: CanvasRenderingContext2D | null = null;
  private vHistory: number[] = new Array(150).fill(0);

  // Real-time telemetry DOM elements
  private voltMeterFill: HTMLElement | null = null;
  private voltMeterText: HTMLElement | null = null;
  private fireRateText: HTMLElement | null = null;
  private inDegreeText: HTMLElement | null = null;
  private outDegreeText: HTMLElement | null = null;

  // Global status elements
  private tickCounterEl: HTMLElement | null = null;
  private workerFpsEl: HTMLElement | null = null;
  private neuronCountEl: HTMLElement | null = null;
  private synCountEl: HTMLElement | null = null;
  private syncIndexEl: HTMLElement | null = null;
  private playPauseBtn: HTMLButtonElement | null = null;

  // Discovery Target & Live Fitness State
  public targetObjective: string = 'alpha_sync'; // 'alpha_sync' | 'gamma_critical' | 'theta_rhythm'
  public geneEIRatio: number = 1.0;
  public geneSigmaScale: number = 1.0;
  public drugGabaDose: number = 0.0;
  public drugAmpaGain: number = 1.0;

  // Baseline copies of simulation memory arrays for non-destructive live scaling
  public initialBaseWeights: Int16Array = new Int16Array(MAX_NEURONS);
  public initialWeights: Int16Array = new Int16Array(MAX_SYNAPSES);
  public initialConnRadius: Float32Array = new Float32Array(MAX_NEURONS);
  private initialAdjWeights: Int16Array[] = [];
  public baselineCaptured = false;

  // History buffer for envelope frequency detection
  public currentFitnessScore = 0;
  public currentPeakHz = 0;
  public currentSyncIndex = 0;

  // Discovery DOM Elements
  private discoverySectionEl: HTMLElement | null = null;
  private neuronDetailsSectionEl: HTMLElement | null = null;
  private fitnessScoreTextEl: HTMLElement | null = null;
  private fitnessMeterEl: HTMLElement | null = null;
  private fitnessFreqTextEl: HTMLElement | null = null;
  private fitnessSyncTextEl: HTMLElement | null = null;

  // Active Tool Mode
  public currentTool: ToolMode = 'SELECT';
  public spawnType: NeuronMode = NeuronMode.LIF;
  public spawnWeight = 160;

  // Callbacks
  public onNeuronParamsUpdated: (() => void) | null = null;
  public onGlobalRewireRequested: (() => void) | null = null;
  public onPlaneYChanged: ((y: number) => void) | null = null;
  public onToggleGlobalSynapses: ((show: boolean) => void) | null = null;
  public onToolModeChanged: ((mode: ToolMode) => void) | null = null;
  public onRegeneratePopulation: ((config: any) => void) | null = null;
  public onImportNetwork: ((net: SerializedNetwork) => void) | null = null;
  public onExportNetwork: (() => void) | null = null;
  public onNeuronDelete: ((id: number) => void) | null = null;
  public onClearNetwork: (() => void) | null = null;
  public onStartConfiguredSimulation: ((config: any) => void) | null = null;

  // Telemetry rate calculation
  private spikeWindowStart = performance.now();
  private spikeWindowCount = 0;
  private runningHz = 0;

  constructor(container: HTMLElement, private mem: SharedSimulationMemory, spatialHash: SpatialHashManager) {
    this.container = container;
    this.spatialHash = spatialHash;

    this.rootEl = document.createElement('div');
    this.rootEl.className = 'snn-ui-overlay';

    this.globalToolbarEl = document.createElement('div');
    this.globalToolbarEl.className = 'snn-toolbar';

    this.hintBannerEl = document.createElement('div');
    this.hintBannerEl.className = 'snn-hint-banner';

    this.neuronPanelEl = document.createElement('div');
    this.neuronPanelEl.className = 'snn-inspector-panel';

    this.discoverySectionEl = document.createElement('div');
    this.discoverySectionEl.className = 'inspector-section discovery-section';

    this.neuronDetailsSectionEl = document.createElement('div');
    this.neuronDetailsSectionEl.className = 'inspector-neuron-details';

    this.neuronPanelEl.appendChild(this.discoverySectionEl);
    this.neuronPanelEl.appendChild(this.neuronDetailsSectionEl);

    this.modalContainerEl = document.createElement('div');
    this.modalContainerEl.className = 'snn-modal-container';
    this.modalContainerEl.style.display = 'none';

    this.rootEl.appendChild(this.globalToolbarEl);
    this.rootEl.appendChild(this.hintBannerEl);
    this.rootEl.appendChild(this.neuronPanelEl);
    this.rootEl.appendChild(this.modalContainerEl);
    this.container.appendChild(this.rootEl);

    this.renderToolbar();
    this.updateHintBanner();
    this.renderDiscoveryPanel();
    this.renderNeuronPanel();
  }

  public setSelectedNeuron(id: number | null): void {
    this.selectedNeuronId = id;
    this.vHistory.fill(0);
    this.renderNeuronPanel();
  }

  public setToolMode(mode: ToolMode): void {
    this.currentTool = mode;
    const selectBtn = this.globalToolbarEl.querySelector('#tool-select') as HTMLButtonElement;
    const wireBtn = this.globalToolbarEl.querySelector('#tool-wire') as HTMLButtonElement;
    const spawnBtn = this.globalToolbarEl.querySelector('#tool-spawn') as HTMLButtonElement;

    if (selectBtn) selectBtn.className = mode === 'SELECT' ? 'btn btn-primary' : 'btn btn-secondary';
    if (wireBtn) wireBtn.className = mode === 'WIRE' ? 'btn btn-warning' : 'btn btn-secondary';
    if (spawnBtn) spawnBtn.className = mode === 'SPAWN' ? 'btn btn-success' : 'btn btn-secondary';

    this.updateHintBanner();
    if (this.onToolModeChanged) this.onToolModeChanged(mode);
  }

  public updateHintBanner(): void {
    const numNeurons = safeLoad(this.mem.control, ControlIndex.NUM_NEURONS);
    if (numNeurons === 0) {
      this.hintBannerEl.innerHTML = `
        <span class="hint-icon">🌱</span>
        <span class="hint-text"><strong class="text-success">BLANK CANVAS (0 NEURONS)</strong> — Click on reference grid to place <strong>Neuron #0</strong>, then place <strong>Neuron #1</strong> and connect them via <strong>Wire Tool</strong>!</span>
      `;
      return;
    }

    if (this.currentTool === 'SELECT') {
      this.hintBannerEl.innerHTML = `
        <span class="hint-icon">🎯</span>
        <span class="hint-text"><strong>SELECT MODE</strong> — Click any neuron to inspect membrane dynamics & biophysics. Drag mouse to orbit 3D view; <kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd> <kbd>Q</kbd><kbd>E</kbd> fly through.</span>
      `;
    } else if (this.currentTool === 'WIRE') {
      this.hintBannerEl.innerHTML = `
        <span class="hint-icon">🔗</span>
        <span class="hint-text"><strong class="text-warning">WIRE (DRAG & DROP) MODE</strong> — Click a source neuron and drag to a target neuron to create a synapse with custom weight and delay.</span>
      `;
    } else if (this.currentTool === 'SPAWN') {
      this.hintBannerEl.innerHTML = `
        <span class="hint-icon">➕</span>
        <span class="hint-text"><strong class="text-success">PLACE NEURON MODE</strong> — Click anywhere on the 3D reference grid to spawn a neuron. <kbd>Alt</kbd> + <kbd>Scroll</kbd> moves grid height.</span>
      `;
    }
  }

  private renderToolbar(): void {
    this.globalToolbarEl.innerHTML = `
      <div class="toolbar-brand">
        <span class="brand-badge">SNN-3D</span>
        <span class="brand-title">neurogenesis-sim viewer</span>
      </div>

      <!-- Mode & Interaction Tools -->
      <div class="toolbar-tools">
        <button id="tool-select" class="btn btn-primary" title="Select and inspect neurons">🎯 SELECT</button>
        <button id="tool-wire" class="btn btn-secondary" title="Click & Drag from one neuron to another to wire!">🔗 WIRE (DRAG & DROP)</button>
        <button id="tool-spawn" class="btn btn-secondary" title="Click on reference plane to place neuron">➕ PLACE NEURON</button>
      </div>

      <div class="toolbar-stats">
        <div class="stat-pill"><span class="stat-label">NEURONS:</span> <span id="stat-neurons" class="stat-value">0</span></div>
        <div class="stat-pill"><span class="stat-label">SYNAPSES:</span> <span id="stat-synapses" class="stat-value">0</span></div>
        <div class="stat-pill"><span class="stat-label">TICK:</span> <span id="stat-tick" class="stat-value">0</span></div>
        <div class="stat-pill"><span class="stat-label">SYNC:</span> <span id="stat-sync" class="stat-value">0%</span></div>
        <div class="stat-pill"><span class="stat-label">WORKER:</span> <span id="stat-fps" class="stat-value">0 Hz</span></div>
      </div>

      <div class="toolbar-actions">
        <button id="btn-startup-setup" class="btn btn-primary" title="Open Simulation Setup & Initial Parameters">⚙️ SETUP</button>
        <button id="btn-blank-canvas" class="btn btn-secondary" title="Start from scratch with 0 neurons">🌱 BLANK (0)</button>
        <button id="btn-play-pause" class="btn btn-primary">PAUSE</button>
        <button id="btn-step" class="btn btn-secondary">STEP</button>
        <button id="btn-population" class="btn btn-secondary">POPULATION (N)</button>
        <button id="btn-rewire-all" class="btn btn-warning">AUTO-REWIRE</button>

        <div class="dropdown-wrapper">
          <label>PRESET:</label>
          <select id="select-quick-preset" class="select-styled">
            <option value="" disabled selected>Quick Presets</option>
            <option value="empty">🌱 Blank Canvas (0 Neurons)</option>
            <option value="column">Cortical Column (1k)</option>
            <option value="microcircuit">Microcircuit (100)</option>
            <option value="layered">Layered Sheets (600)</option>
            <option value="volume">Random 3D Volume (500)</option>
            <option value="macro">Macro Column (2.5k)</option>
          </select>
        </div>

        <div class="dropdown-wrapper">
          <label>SPEED:</label>
          <select id="select-hz" class="select-styled">
            <option value="100">100 Hz</option>
            <option value="500">500 Hz</option>
            <option value="1000" selected>1,000 Hz</option>
            <option value="2000">2,000 Hz</option>
            <option value="5000">5,000 Hz</option>
          </select>
        </div>

        <div class="dropdown-wrapper">
          <label>SPAWN TYPE:</label>
          <select id="select-spawn-mode" class="select-styled">
            <option value="0_exc" selected>Excitatory LIF (+160)</option>
            <option value="0_inh">Inhibitory LIF (-320)</option>
            <option value="1">Poisson Driver (25 Hz)</option>
            <option value="2">Burster Pacemaker</option>
          </select>
        </div>

        <button id="btn-import-json" class="btn btn-secondary" title="Import network from JSON">IMPORT</button>
        <input type="file" id="file-import-json" accept=".json" style="display: none;" />
        <button id="btn-export-json" class="btn btn-secondary" title="Export network to JSON">EXPORT</button>

        <label class="toggle-checkbox">
          <input type="checkbox" id="check-global-syn" />
          <span>ALL SYNAPSES</span>
        </label>
      </div>
    `;

    // Tool Buttons
    this.globalToolbarEl.querySelector('#tool-select')?.addEventListener('click', () => this.setToolMode('SELECT'));
    this.globalToolbarEl.querySelector('#tool-wire')?.addEventListener('click', () => this.setToolMode('WIRE'));
    this.globalToolbarEl.querySelector('#tool-spawn')?.addEventListener('click', () => this.setToolMode('SPAWN'));

    this.tickCounterEl = this.globalToolbarEl.querySelector('#stat-tick');
    this.workerFpsEl = this.globalToolbarEl.querySelector('#stat-fps');
    this.neuronCountEl = this.globalToolbarEl.querySelector('#stat-neurons');
    this.synCountEl = this.globalToolbarEl.querySelector('#stat-synapses');
    this.syncIndexEl = this.globalToolbarEl.querySelector('#stat-sync');
    this.playPauseBtn = this.globalToolbarEl.querySelector('#btn-play-pause');

    this.globalToolbarEl.querySelector('#btn-startup-setup')?.addEventListener('click', () => {
      this.openStartupModal();
    });

    this.globalToolbarEl.querySelector('#btn-blank-canvas')?.addEventListener('click', () => {
      if (this.onClearNetwork) this.onClearNetwork();
    });

    const selectQuickPreset = this.globalToolbarEl.querySelector('#select-quick-preset') as HTMLSelectElement;
    selectQuickPreset?.addEventListener('change', () => {
      const val = selectQuickPreset.value;
      if (!val) return;
      if (val === 'empty') {
        if (this.onClearNetwork) this.onClearNetwork();
        selectQuickPreset.value = '';
        return;
      }
      let config = { count: 1000, morphology: 'column', excRatio: 0.80, paceRatio: 0.05, sigma: 28.0 };
      if (val === 'column') {
        config = { count: 1000, morphology: 'column', excRatio: 0.80, paceRatio: 0.05, sigma: 28.0 };
      } else if (val === 'microcircuit') {
        config = { count: 100, morphology: 'microcircuit', excRatio: 0.80, paceRatio: 0.08, sigma: 18.0 };
      } else if (val === 'layered') {
        config = { count: 600, morphology: 'layered', excRatio: 0.80, paceRatio: 0.05, sigma: 24.0 };
      } else if (val === 'volume') {
        config = { count: 500, morphology: 'volume', excRatio: 0.80, paceRatio: 0.05, sigma: 28.0 };
      } else if (val === 'macro') {
        config = { count: 2500, morphology: 'column', excRatio: 0.80, paceRatio: 0.04, sigma: 32.0 };
      }
      if (this.onRegeneratePopulation) {
        this.onRegeneratePopulation(config);
      }
      selectQuickPreset.value = '';
    });

    this.playPauseBtn?.addEventListener('click', () => {
      const isRunning = safeLoad(this.mem.control, ControlIndex.IS_RUNNING) === 1;
      const nextState = isRunning ? 0 : 1;
      pushCommand(this.mem, CommandType.SET_RUNNING, nextState);
      if (this.playPauseBtn) {
        this.playPauseBtn.textContent = nextState ? 'PAUSE' : 'PLAY';
        this.playPauseBtn.className = nextState ? 'btn btn-primary' : 'btn btn-success';
      }
    });

    this.globalToolbarEl.querySelector('#btn-step')?.addEventListener('click', () => {
      pushCommand(this.mem, CommandType.STEP, 1);
    });

    this.globalToolbarEl.querySelector('#btn-population')?.addEventListener('click', () => {
      this.openPopulationModal();
    });

    this.globalToolbarEl.querySelector('#btn-rewire-all')?.addEventListener('click', () => {
      pushCommand(this.mem, CommandType.REWIRE_ALL);
      setTimeout(() => {
        if (this.onGlobalRewireRequested) this.onGlobalRewireRequested();
      }, 50);
    });

    const selectHz = this.globalToolbarEl.querySelector('#select-hz') as HTMLSelectElement;
    selectHz?.addEventListener('change', () => {
      const hz = parseInt(selectHz.value, 10);
      pushCommand(this.mem, CommandType.SET_HZ, hz);
    });

    const selectSpawn = this.globalToolbarEl.querySelector('#select-spawn-mode') as HTMLSelectElement;
    selectSpawn?.addEventListener('change', () => {
      const val = selectSpawn.value;
      if (val === '0_exc') {
        this.spawnType = NeuronMode.LIF;
        this.spawnWeight = 160;
      } else if (val === '0_inh') {
        this.spawnType = NeuronMode.LIF;
        this.spawnWeight = -320;
      } else if (val === '1') {
        this.spawnType = NeuronMode.POISSON;
        this.spawnWeight = 200;
      } else if (val === '2') {
        this.spawnType = NeuronMode.BURSTER;
        this.spawnWeight = 240;
      }
    });

    // Import / Export
    const fileInput = this.globalToolbarEl.querySelector('#file-import-json') as HTMLInputElement;
    this.globalToolbarEl.querySelector('#btn-import-json')?.addEventListener('click', () => fileInput.click());

    fileInput?.addEventListener('change', (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (evt) => {
        try {
          const json = JSON.parse(evt.target?.result as string);
          if (this.onImportNetwork) this.onImportNetwork(json);
          this.modalContainerEl.style.display = 'none';            // close the startup dialog so the imported network is visible
          fileInput.value = '';                                   // allow re-importing the same file
        } catch (err) {
          alert('Invalid Network JSON file: ' + err);
        }
      };
      reader.readAsText(file);
    });

    this.globalToolbarEl.querySelector('#btn-export-json')?.addEventListener('click', () => {
      if (this.onExportNetwork) this.onExportNetwork();
    });

    const checkGlobalSyn = this.globalToolbarEl.querySelector('#check-global-syn') as HTMLInputElement;
    checkGlobalSyn?.addEventListener('change', () => {
      if (this.onToggleGlobalSynapses) {
        this.onToggleGlobalSynapses(checkGlobalSyn.checked);
      }
    });
  }

  public showSynapseModal(preId: number, postId: number, distance: number): void {
    const defaultDelay = Math.min(31, Math.max(1, Math.round(distance / 4.0)));
    const preMode = this.mem.neuronMode[preId];
    const defaultWeight = preMode === NeuronMode.LIF && this.mem.baseWeight[preId] < 0 ? -280 : 180;

    this.modalContainerEl.style.display = 'flex';
    this.modalContainerEl.innerHTML = `
      <div class="snn-modal">
        <div class="modal-header">
          <span class="modal-title">CREATE SYNAPSE</span>
          <button id="modal-close" class="btn-icon">✕</button>
        </div>
        <div class="modal-body">
          <div class="syn-route">
            <div class="syn-node">
              <span class="node-id">NEURON #${preId}</span>
              <span class="node-mode">${preMode === 1 ? 'Poisson' : preMode === 2 ? 'Burster' : 'LIF'}</span>
            </div>
            <div class="syn-arrow">━━━ ➔</div>
            <div class="syn-node">
              <span class="node-id">NEURON #${postId}</span>
              <span class="node-mode">${this.mem.neuronMode[postId] === 1 ? 'Poisson' : this.mem.neuronMode[postId] === 2 ? 'Burster' : 'LIF'}</span>
            </div>
          </div>

          <div class="modal-info-row">
            <span>Spatial Distance: <strong>${distance.toFixed(1)} units</strong></span>
            <span>Axonal Delay: <strong>${defaultDelay} ticks (${defaultDelay} ms)</strong></span>
          </div>

          <div class="control-row">
            <label>Synaptic Weight: <strong id="modal-val-weight">${defaultWeight}</strong></label>
            <input type="range" id="modal-slider-weight" min="-512" max="512" step="1" value="${defaultWeight}" />
          </div>

          <div class="preset-btn-row">
            <button class="btn btn-secondary preset-btn" data-w="180">Exc (+180)</button>
            <button class="btn btn-secondary preset-btn" data-w="350">Strong Exc (+350)</button>
            <button class="btn btn-secondary preset-btn" data-w="-280">Inh (-280)</button>
            <button class="btn btn-secondary preset-btn" data-w="-450">Strong Inh (-450)</button>
          </div>

          <div class="control-row" style="margin-top: 10px;">
            <label>Delay (ticks): <strong id="modal-val-delay">${defaultDelay}</strong></label>
            <input type="range" id="modal-slider-delay" min="1" max="31" step="1" value="${defaultDelay}" />
          </div>

          <div class="modal-actions">
            <button id="modal-btn-confirm" class="btn btn-primary btn-block">CONFIRM SYNAPSE</button>
          </div>
        </div>
      </div>
    `;

    const sliderW = this.modalContainerEl.querySelector('#modal-slider-weight') as HTMLInputElement;
    const valW = this.modalContainerEl.querySelector('#modal-val-weight');
    const sliderD = this.modalContainerEl.querySelector('#modal-slider-delay') as HTMLInputElement;
    const valD = this.modalContainerEl.querySelector('#modal-val-delay');

    sliderW?.addEventListener('input', () => {
      if (valW) valW.textContent = sliderW.value;
    });

    sliderD?.addEventListener('input', () => {
      if (valD) valD.textContent = sliderD.value;
    });

    this.modalContainerEl.querySelectorAll('.preset-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const w = (btn as HTMLElement).dataset.w;
        if (w && sliderW && valW) {
          sliderW.value = w;
          valW.textContent = w;
        }
      });
    });

    const closeModal = () => {
      this.modalContainerEl.style.display = 'none';
      this.modalContainerEl.innerHTML = '';
    };

    this.modalContainerEl.querySelector('#modal-close')?.addEventListener('click', closeModal);

    this.modalContainerEl.querySelector('#modal-btn-confirm')?.addEventListener('click', () => {
      const weight = parseInt(sliderW.value, 10);
      const delay = parseInt(sliderD.value, 10);
      const numNeurons = safeLoad(this.mem.control, ControlIndex.NUM_NEURONS);

      // Add to spatial hash adjacency and rebuild CSR immediately
      const newTotal = this.spatialHash.setManualSynapse(this.mem, preId, postId, weight, delay, numNeurons);
      safeStore(this.mem.control, ControlIndex.NUM_SYNAPSES, newTotal);

      // Encode command for worker
      const rawW = (weight < 0 ? weight + 0x10000 : weight) & 0xffff;
      const arg3 = rawW | ((delay & 0xff) << 16);
      pushCommand(this.mem, CommandType.SET_SYNAPSE, preId, postId, arg3);

      closeModal();
      if (this.onNeuronParamsUpdated) this.onNeuronParamsUpdated();
      this.renderNeuronPanel();
    });
  }

  public openStartupModal(): void {
    const currentN = safeLoad(this.mem.control, ControlIndex.NUM_NEURONS);
    const currentHz = safeLoad(this.mem.control, ControlIndex.SIM_HZ) || 1000;
    const isRunning = safeLoad(this.mem.control, ControlIndex.IS_RUNNING) === 1;

    let selectedMorph = currentN === 0 ? 'empty' : 'column';

    this.modalContainerEl.style.display = 'flex';
    this.modalContainerEl.innerHTML = `
      <div class="snn-modal snn-startup-modal">
        <div class="modal-header">
          <div>
            <span class="modal-title">SIMULATION SETUP & INITIAL PARAMETERS</span>
            <div class="modal-subtitle">Configure neural architecture, population size, and dynamics before starting.</div>
          </div>
          <button id="modal-close" class="btn-icon">✕</button>
        </div>
        <div class="modal-body">
          <div class="section-label" style="margin-bottom: 8px;">SELECT INITIAL ARCHITECTURE</div>
          <div class="startup-cards-grid">
            <div class="startup-card ${currentN === 0 ? 'active' : ''}" data-morph="empty" data-n="0">
              <div class="card-icon">🌱</div>
              <div class="card-title">Blank Canvas</div>
              <div class="card-desc">0 Neurons. Build your circuit from scratch, neuron by neuron, and wire with 3D drag & drop.</div>
              <button class="btn btn-xs btn-success btn-card-direct" data-target-morph="empty" style="margin-top: 8px; width: 100%;">START BLANK (0)</button>
            </div>
            <div class="startup-card ${currentN > 0 ? 'active' : ''}" data-morph="column" data-n="1000">
              <div class="card-icon">🏛️</div>
              <div class="card-title">Cortical Column</div>
              <div class="card-desc">1,000 Neurons. L1–L6 laminar column with anisotropic travelling waves.</div>
              <button class="btn btn-xs btn-primary btn-card-direct" data-target-morph="column" style="margin-top: 8px; width: 100%;">START COLUMN (1,000)</button>
            </div>
            <div class="startup-card" data-morph="microcircuit" data-n="100">
              <div class="card-icon">🔬</div>
              <div class="card-title">Microcircuit</div>
              <div class="card-desc">100 Neurons. High-density cluster for detailed micro-inspection.</div>
              <button class="btn btn-xs btn-secondary btn-card-direct" data-target-morph="microcircuit" style="margin-top: 8px; width: 100%;">START MICROCIRCUIT (100)</button>
            </div>
            <div class="startup-card" data-morph="layered" data-n="600">
              <div class="card-icon">📑</div>
              <div class="card-title">Layered Sheets</div>
              <div class="card-desc">600 Neurons. 4 horizontal laminar sensory-motor sheets.</div>
              <button class="btn btn-xs btn-secondary btn-card-direct" data-target-morph="layered" style="margin-top: 8px; width: 100%;">START SHEETS (600)</button>
            </div>
            <div class="startup-card" data-morph="volume" data-n="500">
              <div class="card-icon">📦</div>
              <div class="card-title">3D Volume</div>
              <div class="card-desc">500 Neurons. Isotropic spatial distribution.</div>
              <button class="btn btn-xs btn-secondary btn-card-direct" data-target-morph="volume" style="margin-top: 8px; width: 100%;">START VOLUME (500)</button>
            </div>
            <div class="startup-card" data-morph="custom" data-n="${currentN > 0 ? currentN : 500}">
              <div class="card-icon">⚙️</div>
              <div class="card-title">Custom Setup</div>
              <div class="card-desc">Configure custom population and biophysical parameters below.</div>
              <button class="btn btn-xs btn-secondary btn-card-direct" data-target-morph="custom" style="margin-top: 8px; width: 100%;">CUSTOMIZE BELOW</button>
            </div>
          </div>

          <div class="section-label" style="margin-top: 14px; margin-bottom: 8px;">INITIAL PARAMETERS</div>
          <div class="control-row">
            <label>Initial Population Size (Neurons): <strong id="val-startup-n">${currentN === 0 ? '0' : '1,000'}</strong></label>
            <input type="range" id="slider-startup-n" min="0" max="5000" step="10" value="${currentN === 0 ? '0' : '1000'}" />
          </div>

          <div class="grid-two-col">
            <div class="control-row">
              <label>Simulation Clock Rate</label>
              <select id="select-startup-hz" class="select-styled">
                <option value="100">100 Hz (Slow Motion)</option>
                <option value="500">500 Hz</option>
                <option value="1000" selected>1,000 Hz (Real-Time 1ms tick)</option>
                <option value="2000">2,000 Hz</option>
                <option value="5000">5,000 Hz (Fast Acceleration)</option>
              </select>
            </div>
            <div class="control-row">
              <label>Initial Execution State</label>
              <select id="select-startup-state" class="select-styled">
                <option value="1" selected>Active (Running immediately)</option>
                <option value="0">Paused at Tick 0 (Step-by-step)</option>
              </select>
            </div>
          </div>

          <div class="grid-two-col">
            <div class="control-row">
              <label>Excitatory Ratio: <strong id="val-startup-exc">80%</strong></label>
              <input type="range" id="slider-startup-exc" min="50" max="95" value="80" />
            </div>
            <div class="control-row">
              <label>Pacemaker Drivers: <strong id="val-startup-pace">5%</strong></label>
              <input type="range" id="slider-startup-pace" min="0" max="25" value="5" />
            </div>
          </div>

          <div class="control-row">
            <label>Axonal Projection Radius σ: <strong id="val-startup-sigma">28.0</strong></label>
            <input type="range" id="slider-startup-sigma" min="8" max="60" value="28" />
          </div>

          <div class="startup-modal-actions">
            <button id="btn-startup-blank" class="btn btn-success">🌱 START FROM SCRATCH (0 NEURONS)</button>
            <button id="btn-startup-launch" class="${currentN === 0 ? 'btn btn-success' : 'btn btn-primary'}">
              ${currentN === 0 ? '🌱 START BLANK CANVAS (0 NEURONS)' : '🚀 LAUNCH CONFIGURED SIMULATION'}
            </button>
            <button id="btn-startup-quick" class="btn btn-secondary">⚡ QUICK START (1,000 NEURONS)</button>
          </div>
        </div>
      </div>
    `;

    const sliderN = this.modalContainerEl.querySelector('#slider-startup-n') as HTMLInputElement;
    const valN = this.modalContainerEl.querySelector('#val-startup-n');
    const btnLaunch = this.modalContainerEl.querySelector('#btn-startup-launch') as HTMLButtonElement;

    const updateLaunchBtn = (morph: string, count: number) => {
      if (btnLaunch) {
        if (morph === 'empty' || count === 0) {
          btnLaunch.textContent = '🌱 START BLANK CANVAS (0 NEURONS)';
          btnLaunch.className = 'btn btn-success';
        } else {
          btnLaunch.textContent = '🚀 LAUNCH CONFIGURED SIMULATION';
          btnLaunch.className = 'btn btn-primary';
        }
      }
    };

    sliderN?.addEventListener('input', () => {
      const n = parseInt(sliderN.value, 10);
      if (valN) valN.textContent = n.toLocaleString();
      updateLaunchBtn(selectedMorph, n);
    });

    const sliderExc = this.modalContainerEl.querySelector('#slider-startup-exc') as HTMLInputElement;
    const valExc = this.modalContainerEl.querySelector('#val-startup-exc');
    sliderExc?.addEventListener('input', () => { if (valExc) valExc.textContent = `${sliderExc.value}%`; });

    const sliderPace = this.modalContainerEl.querySelector('#slider-startup-pace') as HTMLInputElement;
    const valPace = this.modalContainerEl.querySelector('#val-startup-pace');
    sliderPace?.addEventListener('input', () => { if (valPace) valPace.textContent = `${sliderPace.value}%`; });

    const sliderSigma = this.modalContainerEl.querySelector('#slider-startup-sigma') as HTMLInputElement;
    const valSigma = this.modalContainerEl.querySelector('#val-startup-sigma');
    sliderSigma?.addEventListener('input', () => { if (valSigma) valSigma.textContent = parseFloat(sliderSigma.value).toFixed(1); });

    const selectHz = this.modalContainerEl.querySelector('#select-startup-hz') as HTMLSelectElement;
    const selectState = this.modalContainerEl.querySelector('#select-startup-state') as HTMLSelectElement;

    const closeModal = () => {
      this.modalContainerEl.style.display = 'none';
      this.modalContainerEl.innerHTML = '';
    };

    const applyPresetDirect = (morph: string) => {
      closeModal();
      if (morph === 'empty') {
        if (this.onClearNetwork) this.onClearNetwork();
      } else if (morph === 'column') {
        if (this.onStartConfiguredSimulation) {
          this.onStartConfiguredSimulation({ count: 1000, morphology: 'column', excRatio: 0.80, paceRatio: 0.05, sigma: 28.0, hz: 1000, isRunning: 1 });
        }
      } else if (morph === 'microcircuit') {
        if (this.onStartConfiguredSimulation) {
          this.onStartConfiguredSimulation({ count: 100, morphology: 'microcircuit', excRatio: 0.80, paceRatio: 0.08, sigma: 18.0, hz: 1000, isRunning: 1 });
        }
      } else if (morph === 'layered') {
        if (this.onStartConfiguredSimulation) {
          this.onStartConfiguredSimulation({ count: 600, morphology: 'layered', excRatio: 0.80, paceRatio: 0.05, sigma: 24.0, hz: 1000, isRunning: 1 });
        }
      } else if (morph === 'volume') {
        if (this.onStartConfiguredSimulation) {
          this.onStartConfiguredSimulation({ count: 500, morphology: 'volume', excRatio: 0.80, paceRatio: 0.05, sigma: 28.0, hz: 1000, isRunning: 1 });
        }
      }
    };

    // Direct Action Buttons on Cards
    this.modalContainerEl.querySelectorAll('.btn-card-direct').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const targetMorph = (btn as HTMLElement).dataset.targetMorph || 'empty';
        if (targetMorph === 'custom') {
          // just scroll to inputs
          sliderN?.focus();
        } else {
          applyPresetDirect(targetMorph);
        }
      });
    });

    // Card Selection
    const cards = this.modalContainerEl.querySelectorAll('.startup-card');
    cards.forEach((card) => {
      card.addEventListener('click', () => {
        cards.forEach((c) => c.classList.remove('active'));
        card.classList.add('active');

        const morph = (card as HTMLElement).dataset.morph || 'column';
        const n = (card as HTMLElement).dataset.n || '1000';
        selectedMorph = morph;

        if (sliderN && valN) {
          sliderN.value = n;
          valN.textContent = parseInt(n, 10).toLocaleString();
        }

        if (morph === 'empty') {
          if (sliderPace && valPace) { sliderPace.value = '0'; valPace.textContent = '0%'; }
        } else if (morph === 'microcircuit') {
          if (sliderSigma && valSigma) { sliderSigma.value = '18'; valSigma.textContent = '18.0'; }
        } else if (morph === 'layered') {
          if (sliderSigma && valSigma) { sliderSigma.value = '24'; valSigma.textContent = '24.0'; }
        } else if (morph === 'column') {
          if (sliderSigma && valSigma) { sliderSigma.value = '28'; valSigma.textContent = '28.0'; }
        }

        updateLaunchBtn(morph, parseInt(n, 10));
      });

      card.addEventListener('dblclick', () => {
        const morph = (card as HTMLElement).dataset.morph || 'column';
        applyPresetDirect(morph);
      });
    });

    this.modalContainerEl.querySelector('#modal-close')?.addEventListener('click', () => {
      closeModal();
      if (currentN === 0 && selectedMorph === 'empty') {
        if (this.onClearNetwork) this.onClearNetwork();
      }
    });

    // Button: Start from scratch (0 neurons)
    this.modalContainerEl.querySelector('#btn-startup-blank')?.addEventListener('click', () => {
      closeModal();
      if (this.onClearNetwork) this.onClearNetwork();
    });

    // Button: Quick start (1,000 neurons)
    this.modalContainerEl.querySelector('#btn-startup-quick')?.addEventListener('click', () => {
      closeModal();
      const config = {
        count: 1000,
        morphology: 'column',
        excRatio: 0.80,
        paceRatio: 0.05,
        sigma: 28.0,
        hz: 1000,
        isRunning: 1,
      };
      if (this.onStartConfiguredSimulation) {
        this.onStartConfiguredSimulation(config);
      } else if (this.onRegeneratePopulation) {
        this.onRegeneratePopulation(config);
      }
    });

    // Button: Launch configured simulation
    this.modalContainerEl.querySelector('#btn-startup-launch')?.addEventListener('click', () => {
      const count = parseInt(sliderN.value, 10);
      const hz = parseInt(selectHz.value, 10);
      const isRun = parseInt(selectState.value, 10);

      closeModal();

      if (count === 0 || selectedMorph === 'empty') {
        if (this.onClearNetwork) this.onClearNetwork();
        pushCommand(this.mem, CommandType.SET_HZ, hz);
        pushCommand(this.mem, CommandType.SET_RUNNING, isRun);
        return;
      }

      const config = {
        count,
        morphology: selectedMorph === 'custom' ? 'column' : selectedMorph,
        excRatio: parseInt(sliderExc.value, 10) / 100,
        paceRatio: parseInt(sliderPace.value, 10) / 100,
        sigma: parseFloat(sliderSigma.value),
        hz,
        isRunning: isRun,
      };

      if (this.onStartConfiguredSimulation) {
        this.onStartConfiguredSimulation(config);
      } else if (this.onRegeneratePopulation) {
        this.onRegeneratePopulation(config);
      }
    });
  }

  public openPopulationModal(): void {
    const currentN = safeLoad(this.mem.control, ControlIndex.NUM_NEURONS);

    this.modalContainerEl.style.display = 'flex';
    this.modalContainerEl.innerHTML = `
      <div class="snn-modal">
        <div class="modal-header">
          <span class="modal-title">POPULATION & MORPHOGENETIC CONFIG</span>
          <button id="modal-close" class="btn-icon">✕</button>
        </div>
        <div class="modal-body">
          <div class="control-row">
            <label>Population Size (Neurons): <strong id="val-pop-n">${currentN}</strong></label>
            <input type="range" id="slider-pop-n" min="20" max="5000" step="20" value="${currentN}" />
          </div>

          <div class="preset-btn-row">
            <button class="btn btn-secondary pop-preset" data-n="100" data-morph="microcircuit">Micro (100)</button>
            <button class="btn btn-secondary pop-preset" data-n="500" data-morph="volume">Volume (500)</button>
            <button class="btn btn-secondary pop-preset" data-n="1000" data-morph="column">Column (1,000)</button>
            <button class="btn btn-secondary pop-preset" data-n="2500" data-morph="column">Macro (2,500)</button>
          </div>

          <div class="control-row" style="margin-top: 10px;">
            <label>Morphology Architecture</label>
            <select id="select-pop-morph" class="select-styled">
              <option value="column" selected>Cortical Column (L1–L6 Laminar)</option>
              <option value="layered">Layered Sheets (Sensory-Motor)</option>
              <option value="volume">Random 3D Volume</option>
              <option value="microcircuit">Dense Microcircuit</option>
            </select>
          </div>

          <div class="control-row">
            <label>Excitatory Ratio: <strong id="val-pop-exc">80%</strong></label>
            <input type="range" id="slider-pop-exc" min="50" max="95" value="80" />
          </div>

          <div class="control-row">
            <label>Pacemaker / Thalamic Drivers: <strong id="val-pop-pace">5%</strong></label>
            <input type="range" id="slider-pop-pace" min="1" max="20" value="5" />
          </div>

          <div class="control-row">
            <label>Mean Axonal Radius σ: <strong id="val-pop-sigma">28.0</strong></label>
            <input type="range" id="slider-pop-sigma" min="8" max="60" value="28" />
          </div>

          <div class="modal-actions">
            <button id="modal-btn-generate" class="btn btn-warning btn-block">REGENERATE POPULATION</button>
          </div>
        </div>
      </div>
    `;

    const sliderN = this.modalContainerEl.querySelector('#slider-pop-n') as HTMLInputElement;
    const valN = this.modalContainerEl.querySelector('#val-pop-n');
    sliderN?.addEventListener('input', () => { if (valN) valN.textContent = sliderN.value; });

    const selectMorph = this.modalContainerEl.querySelector('#select-pop-morph') as HTMLSelectElement;

    this.modalContainerEl.querySelectorAll('.pop-preset').forEach((btn) => {
      btn.addEventListener('click', () => {
        const n = (btn as HTMLElement).dataset.n;
        const m = (btn as HTMLElement).dataset.morph;
        if (n && sliderN && valN) { sliderN.value = n; valN.textContent = n; }
        if (m && selectMorph) selectMorph.value = m;
      });
    });

    const closeModal = () => {
      this.modalContainerEl.style.display = 'none';
      this.modalContainerEl.innerHTML = '';
    };

    this.modalContainerEl.querySelector('#modal-close')?.addEventListener('click', closeModal);

    this.modalContainerEl.querySelector('#modal-btn-generate')?.addEventListener('click', () => {
      const config = {
        count: parseInt(sliderN.value, 10),
        morphology: selectMorph.value,
        excRatio: parseInt((this.modalContainerEl.querySelector('#slider-pop-exc') as HTMLInputElement).value, 10) / 100,
        paceRatio: parseInt((this.modalContainerEl.querySelector('#slider-pop-pace') as HTMLInputElement).value, 10) / 100,
        sigma: parseFloat((this.modalContainerEl.querySelector('#slider-pop-sigma') as HTMLInputElement).value),
      };

      closeModal();
      if (this.onRegeneratePopulation) this.onRegeneratePopulation(config);
    });
  }

  public renderDiscoveryPanel(): void {
    if (!this.discoverySectionEl) return;

    this.discoverySectionEl.innerHTML = `
      <div class="panel-header discovery-header">
        <span class="panel-title" style="color: var(--accent-cyan); display: flex; align-items: center; gap: 6px;">
          <span>🎯</span> DISCOVERY TARGET & FITNESS
        </span>
        <span id="badge-fitness-pill" class="badge badge-gold">FITNESS: <strong id="val-fitness-score-badge">0.00</strong></span>
      </div>

      <!-- Target Selector -->
      <div class="control-row" style="margin-top: 4px;">
        <label style="font-size: 11px;">Target Objective:</label>
        <select id="select-discovery-target" class="select-styled" style="width: 100%;">
          <option value="alpha_sync" ${this.targetObjective === 'alpha_sync' ? 'selected' : ''}>Alpha Synchrony (10 Hz Peak & R ≥ 60%)</option>
          <option value="gamma_critical" ${this.targetObjective === 'gamma_critical' ? 'selected' : ''}>Gamma Criticality (40 Hz Peak & R ≥ 45%)</option>
          <option value="theta_rhythm" ${this.targetObjective === 'theta_rhythm' ? 'selected' : ''}>Theta Rhythm (6 Hz Peak & R ≥ 50%)</option>
        </select>
      </div>

      <!-- Live Fitness Meter HUD -->
      <div class="meter-group" style="background: rgba(0,0,0,0.4); padding: 8px; border-radius: 6px; border: 1px solid rgba(0,240,255,0.18); margin-top: 6px;">
        <div style="display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 4px;">
          <span>Fitness Score: <strong id="val-fitness-score" style="color: var(--accent-gold); font-size: 13px;">0.00</strong></span>
          <span>Freq: <strong id="val-fitness-freq" style="color: var(--accent-cyan);">0.0 Hz</strong> · Sync: <strong id="val-fitness-sync" style="color: var(--accent-gold);">0%</strong></span>
        </div>
        <div class="meter-bar" style="height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden;">
          <div id="meter-fitness-fill" class="meter-fill" style="width: 0%; height: 100%; background: linear-gradient(90deg, #00f0ff, #ffd700); transition: width 0.08s ease;"></div>
        </div>
      </div>

      <!-- Genomic Parameters -->
      <div style="margin-top: 8px; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 6px;">
        <div class="section-label" style="font-size: 10px; color: var(--accent-green); margin-bottom: 4px;">GENOMIC PARAMETERS</div>

        <div class="control-row">
          <div style="display: flex; justify-content: space-between; font-size: 11px;">
            <label>Gene E/I Ratio:</label>
            <strong id="val-gene-ei" style="color: var(--accent-green);">${this.geneEIRatio.toFixed(2)}x</strong>
          </div>
          <input type="range" id="slider-gene-ei" min="0.1" max="3.0" step="0.05" value="${this.geneEIRatio}" />
        </div>

        <div class="control-row">
          <div style="display: flex; justify-content: space-between; font-size: 11px;">
            <label>Arbor Radius σ:</label>
            <strong id="val-gene-sigma" style="color: var(--accent-green);">${this.geneSigmaScale.toFixed(2)}x</strong>
          </div>
          <input type="range" id="slider-gene-sigma" min="0.2" max="2.5" step="0.05" value="${this.geneSigmaScale}" />
        </div>
      </div>

      <!-- Pharmacological Perturbations -->
      <div style="margin-top: 6px; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 6px;">
        <div class="section-label" style="font-size: 10px; color: var(--accent-magenta); margin-bottom: 4px;">PHARMACOLOGICAL PERTURBATIONS</div>

        <div class="control-row">
          <div style="display: flex; justify-content: space-between; font-size: 11px;">
            <label>Drug GABA-A Modulator Dose:</label>
            <strong id="val-drug-gaba" style="color: var(--accent-magenta);">${this.drugGabaDose >= 0 ? '+' : ''}${this.drugGabaDose.toFixed(2)}</strong>
          </div>
          <input type="range" id="slider-drug-gaba" min="-1.0" max="1.5" step="0.05" value="${this.drugGabaDose}" />
        </div>

        <div class="control-row">
          <div style="display: flex; justify-content: space-between; font-size: 11px;">
            <label>Drug AMPA/NMDA Gain:</label>
            <strong id="val-drug-ampa" style="color: var(--accent-magenta);">${this.drugAmpaGain.toFixed(2)}x</strong>
          </div>
          <input type="range" id="slider-drug-ampa" min="0.2" max="2.0" step="0.05" value="${this.drugAmpaGain}" />
        </div>
      </div>
    `;

    this.fitnessScoreTextEl = this.discoverySectionEl.querySelector('#val-fitness-score');
    this.fitnessMeterEl = this.discoverySectionEl.querySelector('#meter-fitness-fill');
    this.fitnessFreqTextEl = this.discoverySectionEl.querySelector('#val-fitness-freq');
    this.fitnessSyncTextEl = this.discoverySectionEl.querySelector('#val-fitness-sync');

    const targetSelect = this.discoverySectionEl.querySelector('#select-discovery-target') as HTMLSelectElement;
    targetSelect?.addEventListener('change', () => {
      this.targetObjective = targetSelect.value;
    });

    const sliderEI = this.discoverySectionEl.querySelector('#slider-gene-ei') as HTMLInputElement;
    sliderEI?.addEventListener('input', (e) => {
      this.geneEIRatio = parseFloat((e.target as HTMLInputElement).value);
      const valEl = this.discoverySectionEl?.querySelector('#val-gene-ei');
      if (valEl) valEl.textContent = `${this.geneEIRatio.toFixed(2)}x`;
      this.applyLiveModulations();
    });

    const sliderSigma = this.discoverySectionEl.querySelector('#slider-gene-sigma') as HTMLInputElement;
    sliderSigma?.addEventListener('input', (e) => {
      this.geneSigmaScale = parseFloat((e.target as HTMLInputElement).value);
      const valEl = this.discoverySectionEl?.querySelector('#val-gene-sigma');
      if (valEl) valEl.textContent = `${this.geneSigmaScale.toFixed(2)}x`;
      this.applyLiveModulations();
    });

    const sliderGaba = this.discoverySectionEl.querySelector('#slider-drug-gaba') as HTMLInputElement;
    sliderGaba?.addEventListener('input', (e) => {
      this.drugGabaDose = parseFloat((e.target as HTMLInputElement).value);
      const valEl = this.discoverySectionEl?.querySelector('#val-drug-gaba');
      if (valEl) valEl.textContent = `${this.drugGabaDose >= 0 ? '+' : ''}${this.drugGabaDose.toFixed(2)}`;
      this.applyLiveModulations();
    });

    const sliderAmpa = this.discoverySectionEl.querySelector('#slider-drug-ampa') as HTMLInputElement;
    sliderAmpa?.addEventListener('input', (e) => {
      this.drugAmpaGain = parseFloat((e.target as HTMLInputElement).value);
      const valEl = this.discoverySectionEl?.querySelector('#val-drug-ampa');
      if (valEl) valEl.textContent = `${this.drugAmpaGain.toFixed(2)}x`;
      this.applyLiveModulations();
    });
  }

  public captureBaseline(): void {
    const numNeurons = safeLoad(this.mem.control, ControlIndex.NUM_NEURONS);
    const numSynapses = safeLoad(this.mem.control, ControlIndex.NUM_SYNAPSES);
    if (numNeurons <= 0) return;

    if (this.initialBaseWeights.length < numNeurons) {
      this.initialBaseWeights = new Int16Array(MAX_NEURONS);
      this.initialConnRadius = new Float32Array(MAX_NEURONS);
    }
    if (this.initialWeights.length < numSynapses) {
      this.initialWeights = new Int16Array(Math.max(MAX_SYNAPSES, numSynapses));
    }

    for (let i = 0; i < numNeurons; i++) {
      this.initialBaseWeights[i] = this.mem.baseWeight[i];
      this.initialConnRadius[i] = this.mem.connRadius[i];
    }
    for (let k = 0; k < numSynapses; k++) {
      this.initialWeights[k] = this.mem.weights[k];
    }
    this.initialAdjWeights = [];
    for (let i = 0; i < numNeurons; i++) {
      const wArr = this.spatialHash.adjWeights[i];
      this.initialAdjWeights[i] = wArr ? wArr.slice() : new Int16Array(0);
    }
    this.baselineCaptured = true;
  }

  public applyLiveModulations(): void {
    const numNeurons = safeLoad(this.mem.control, ControlIndex.NUM_NEURONS);
    const numSynapses = safeLoad(this.mem.control, ControlIndex.NUM_SYNAPSES);
    if (numNeurons <= 0) return;

    if (!this.baselineCaptured) {
      this.captureBaseline();
    }

    const eiRatio = this.geneEIRatio;
    const sigmaScale = this.geneSigmaScale;
    const gabaDose = this.drugGabaDose;
    const ampaGain = this.drugAmpaGain;

    const inhFactor = Math.max(0.0, eiRatio * (1.0 + gabaDose));
    const excFactor = Math.max(0.05, ampaGain);

    // 1. Mutate mem.baseWeight in-place
    for (let i = 0; i < numNeurons; i++) {
      const orig = this.initialBaseWeights[i];
      if (orig < 0) {
        this.mem.baseWeight[i] = Math.max(-512, Math.min(0, Math.round(orig * inhFactor)));
      } else if (orig > 0) {
        this.mem.baseWeight[i] = Math.max(0, Math.min(512, Math.round(orig * excFactor)));
      }
    }

    // 2. Mutate mem.weights in-place
    for (let k = 0; k < numSynapses; k++) {
      const origW = this.initialWeights[k];
      if (origW < 0) {
        this.mem.weights[k] = Math.max(-512, Math.min(0, Math.round(origW * inhFactor)));
      } else if (origW > 0) {
        this.mem.weights[k] = Math.max(0, Math.min(512, Math.round(origW * excFactor)));
      }
    }

    // 3. Mutate mem.connRadius in-place
    for (let i = 0; i < numNeurons; i++) {
      this.mem.connRadius[i] = Math.max(2.0, Math.min(120.0, this.initialConnRadius[i] * sigmaScale));
    }

    // 4. Update spatialHash.adjWeights in-place
    for (let i = 0; i < numNeurons; i++) {
      const wArr = this.spatialHash.adjWeights[i];
      const w0 = this.initialAdjWeights[i];
      if (wArr && w0 && w0.length === wArr.length) {   // scale the baseline, never the already-scaled weights
        for (let k = 0; k < wArr.length; k++) {
          const w = w0[k];
          if (w < 0) {
            wArr[k] = Math.max(-512, Math.min(0, Math.round(w * inhFactor)));
          } else if (w > 0) {
            wArr[k] = Math.max(0, Math.min(512, Math.round(w * excFactor)));
          }
        }
      }
    }

    if (this.onNeuronParamsUpdated) {
      this.onNeuronParamsUpdated();
    }
  }

  public setGeneEIRatio(val: number): void {
    this.geneEIRatio = Math.max(0.1, Math.min(3.0, val));
    const el = this.discoverySectionEl?.querySelector('#slider-gene-ei') as HTMLInputElement;
    if (el) el.value = this.geneEIRatio.toString();
    const valEl = this.discoverySectionEl?.querySelector('#val-gene-ei');
    if (valEl) valEl.textContent = `${this.geneEIRatio.toFixed(2)}x`;
    this.applyLiveModulations();
  }

  public setGeneSigmaScale(val: number): void {
    this.geneSigmaScale = Math.max(0.2, Math.min(2.5, val));
    const el = this.discoverySectionEl?.querySelector('#slider-gene-sigma') as HTMLInputElement;
    if (el) el.value = this.geneSigmaScale.toString();
    const valEl = this.discoverySectionEl?.querySelector('#val-gene-sigma');
    if (valEl) valEl.textContent = `${this.geneSigmaScale.toFixed(2)}x`;
    this.applyLiveModulations();
  }

  public setDrugGabaDose(val: number): void {
    this.drugGabaDose = Math.max(-1.0, Math.min(1.5, val));
    const el = this.discoverySectionEl?.querySelector('#slider-drug-gaba') as HTMLInputElement;
    if (el) el.value = this.drugGabaDose.toString();
    const valEl = this.discoverySectionEl?.querySelector('#val-drug-gaba');
    if (valEl) valEl.textContent = `${this.drugGabaDose >= 0 ? '+' : ''}${this.drugGabaDose.toFixed(2)}`;
    this.applyLiveModulations();
  }

  public setDrugAmpaGain(val: number): void {
    this.drugAmpaGain = Math.max(0.2, Math.min(2.0, val));
    const el = this.discoverySectionEl?.querySelector('#slider-drug-ampa') as HTMLInputElement;
    if (el) el.value = this.drugAmpaGain.toString();
    const valEl = this.discoverySectionEl?.querySelector('#val-drug-ampa');
    if (valEl) valEl.textContent = `${this.drugAmpaGain.toFixed(2)}x`;
    this.applyLiveModulations();
  }

  public getTargetFitness(): { fitness: number; peakHz: number; syncIndex: number } {
    return {
      fitness: this.currentFitnessScore,
      peakHz: this.currentPeakHz,
      syncIndex: this.currentSyncIndex,
    };
  }

  private renderNeuronPanel(): void {
    if (this.selectedNeuronId === null || this.selectedNeuronId < 0) {
      const numNeurons = safeLoad(this.mem.control, ControlIndex.NUM_NEURONS);
      if (numNeurons === 0) {
        if (this.neuronDetailsSectionEl) {
          this.neuronDetailsSectionEl.innerHTML = `
            <div class="panel-header">
              <span class="panel-title">NEURON INSPECTOR</span>
              <span class="badge badge-inactive">BLANK CANVAS</span>
            </div>
            <div class="panel-empty-state">
              <div class="empty-icon" style="color: var(--accent-green);">🌱</div>
              <p><strong style="color: var(--accent-green);">Blank Canvas (0 Neurons)</strong></p>
              <p style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">Click anywhere on the holographic grid to place <strong>Neuron #0</strong>, then place <strong>Neuron #1</strong> to wire them!</p>
              <div class="empty-instructions" style="margin-top: 14px;">
                <div><kbd>➕ Place Tool</kbd> Click on grid to spawn neurons</div>
                <div><kbd>🔗 Wire Tool</kbd> Drag from Neuron #0 to #1 to connect</div>
                <div><kbd>⚙️ Setup</kbd> Launch standard or custom population</div>
              </div>
            </div>
          `;
        }
      } else {
        if (this.neuronDetailsSectionEl) {
          this.neuronDetailsSectionEl.innerHTML = `
            <div class="panel-header">
              <span class="panel-title">NEURON INSPECTOR</span>
              <span class="badge badge-inactive">NO SELECTION</span>
            </div>
            <div class="panel-empty-state">
              <div class="empty-icon">⬡</div>
              <p><strong>Click a neuron</strong> in 3D to inspect, live-tune biophysics, or manage synapses.</p>
              <div class="empty-instructions">
                <div><kbd>Wire Tool</kbd> Drag from one neuron to another to connect</div>
                <div><kbd>Shift</kbd> + <kbd>Click</kbd> Spawn neuron on grid</div>
                <div><kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd> <kbd>Q</kbd><kbd>E</kbd> Fly camera</div>
              </div>
            </div>
          `;
        }
      }
      this.voltMeterFill = null;
      this.voltMeterText = null;
      this.fireRateText = null;
      this.inDegreeText = null;
      this.outDegreeText = null;
      this.oscCanvas = null;
      this.oscCtx = null;
      return;
    }

    const id = this.selectedNeuronId;
    const mode = this.mem.neuronMode[id];
    const shiftV = this.mem.shiftV[id];
    const shiftS = this.mem.shiftS[id];
    const baseW = this.mem.baseWeight[id];
    const sigma = this.mem.connRadius[id];
    const p0 = this.mem.connProb[id];
    const period = this.mem.burstPeriod[id];
    const duty = this.mem.burstDuty[id];
    const refractory = this.mem.refractory[id];
    const roleName = ['internal', 'input', 'output'][this.mem.role[id]] ?? 'internal';

    const uxi = this.mem.axonDirXYZ[id * 3];
    const uyi = this.mem.axonDirXYZ[id * 3 + 1];
    const uzi = this.mem.axonDirXYZ[id * 3 + 2];
    const thetaDeg = Math.round(((Math.atan2(uzi, uxi) * 180 / Math.PI) + 360) % 360);
    const phiDeg = Math.round(Math.asin(Math.max(-1, Math.min(1, uyi))) * 180 / Math.PI);

    const numNeurons = safeLoad(this.mem.control, ControlIndex.NUM_NEURONS);
    const inDeg = this.spatialHash.getInDegree(this.mem, id, numNeurons);
    const outDeg = this.spatialHash.getOutDegree(this.mem, id);
    const outgoingSyns = this.spatialHash.getOutgoingSynapses(id);

    let modeBadge = '<span class="badge badge-cyan">EXCITATORY LIF</span>';
    if (mode === NeuronMode.LIF && baseW < 0) {
      modeBadge = '<span class="badge badge-magenta">INHIBITORY LIF</span>';
    } else if (mode === NeuronMode.POISSON) {
      modeBadge = '<span class="badge badge-gold">POISSON DRIVER</span>';
    } else if (mode === NeuronMode.BURSTER) {
      modeBadge = '<span class="badge badge-gold">BURSTER</span>';
    }

    // Build synapses list HTML
    let synListHtml = '';
    if (outgoingSyns.length === 0) {
      synListHtml = '<div class="no-syn-notice">No outgoing synapses. Use <strong>Wire Tool</strong> to connect to another neuron!</div>';
    } else {
      for (let sIdx = 0; sIdx < outgoingSyns.length; sIdx++) {
        const syn = outgoingSyns[sIdx];
        synListHtml += `
          <div class="syn-item-row" data-post="${syn.post}">
            <div class="syn-item-info">
              <span class="syn-target">➔ #${syn.post}</span>
              <span class="syn-delay">${syn.delay}ms</span>
            </div>
            <div class="syn-item-weight">
              <input type="range" class="syn-weight-slider" data-post="${syn.post}" data-delay="${syn.delay}" min="-512" max="512" step="1" value="${syn.weight}" />
              <span class="syn-w-val ${syn.weight >= 0 ? 'text-cyan' : 'text-magenta'}">${syn.weight}</span>
            </div>
            <button class="btn-icon btn-delete-syn" data-post="${syn.post}" title="Delete synapse">✕</button>
          </div>
        `;
      }
    }

    if (this.neuronDetailsSectionEl) {
      this.neuronDetailsSectionEl.innerHTML = `
        <div class="panel-header">
          <div>
            <span class="panel-title">NEURON #${id}</span>
            ${modeBadge}
          </div>
          <div class="panel-header-actions">
            <button id="btn-delete-neuron" class="btn btn-danger btn-sm" title="Delete this neuron">DELETE</button>
            <button id="btn-close-inspector" class="btn-icon" title="Deselect">✕</button>
          </div>
        </div>

      <!-- Real-Time Oscilloscope Voltage Waveform -->
      <div class="inspector-section">
        <div class="section-label">REAL-TIME OSCILLOSCOPE (v_mem)</div>
        <div class="oscilloscope-wrapper">
          <canvas id="osc-canvas" width="300" height="90"></canvas>
          <div class="osc-labels">
            <span class="osc-lbl-spike">+1024 mV (Threshold)</span>
            <span class="osc-lbl-rest">0 mV (Rest)</span>
            <span class="osc-lbl-reset">-256 mV (Reset)</span>
          </div>
        </div>

        <div class="telemetry-grid">
          <div class="telemetry-item">
            <span class="telemetry-label">VOLTAGE</span>
            <span id="meter-v-val" class="telemetry-value">0 mV</span>
          </div>
          <div class="telemetry-item">
            <span class="telemetry-label">RATE</span>
            <span id="telem-rate" class="telemetry-value">0 Hz</span>
          </div>
          <div class="telemetry-item">
            <span class="telemetry-label">OUT-DEGREE</span>
            <span id="telem-outdeg" class="telemetry-value">${outDeg}</span>
          </div>
        </div>

        <div class="action-btn-row">
          <button id="btn-stimulate" class="btn btn-accent btn-block">STIMULATE / INJECT SPIKE</button>
        </div>
      </div>

      <!-- Outgoing Synapses & Real-time Weight Tuning -->
      <div class="inspector-section">
        <div class="section-label">OUTGOING SYNAPSES (${outgoingSyns.length})</div>
        <div class="synapses-list-container">
          ${synListHtml}
        </div>
      </div>

      <!-- Biophysical Dynamics -->
      <div class="inspector-section">
        <div class="section-label">BIOPHYSICAL DYNAMICS</div>
        
        <div class="control-row">
          <label>Firing Mode</label>
          <select id="slider-mode" class="select-styled">
            <option value="0" ${mode === NeuronMode.LIF ? 'selected' : ''}>Integrate-and-Fire (LIF)</option>
            <option value="1" ${mode === NeuronMode.POISSON ? 'selected' : ''}>Spontaneous Poisson</option>
            <option value="2" ${mode === NeuronMode.BURSTER ? 'selected' : ''}>Autonomous Burster</option>
          </select>
        </div>

        <div class="control-row">
          <label>Membrane Leak Exp (k_v): <strong id="val-shift-v">${shiftV}</strong></label>
          <input type="range" id="slider-shift-v" min="1" max="10" value="${shiftV}" />
        </div>

        <div class="control-row">
          <label>Synaptic Decay Exp (k_s): <strong id="val-shift-s">${shiftS}</strong></label>
          <input type="range" id="slider-shift-s" min="1" max="10" value="${shiftS}" />
        </div>

        <div class="control-row">
          <label>Refractory Period (ticks): <strong id="val-refractory">${refractory}</strong> · role: ${roleName}</label>
          <input type="range" id="slider-refractory" min="0" max="20" value="${refractory}" />
        </div>

        <div id="section-poisson-controls" style="${mode === NeuronMode.POISSON ? '' : 'display: none;'}">
          <div class="control-row">
            <label>Poisson Target Rate: <strong id="val-poisson-hz">25 Hz</strong></label>
            <input type="range" id="slider-poisson-hz" min="1" max="150" value="25" />
          </div>
        </div>

        <div id="section-burst-controls" style="${mode === NeuronMode.BURSTER ? '' : 'display: none;'}">
          <div class="control-row">
            <label>Burst Period T (ticks): <strong id="val-burst-t">${period}</strong></label>
            <input type="range" id="slider-burst-t" min="20" max="1000" step="10" value="${period}" />
          </div>
          <div class="control-row">
            <label>Burst Duty D (ticks): <strong id="val-burst-d">${duty}</strong></label>
            <input type="range" id="slider-burst-d" min="4" max="120" step="2" value="${duty}" />
          </div>
        </div>
      </div>

      <!-- Morphogenetic Axon Controls -->
      <div class="inspector-section">
        <div class="section-label">MORPHOGENETIC AXON & GROWTH CONE</div>

        <div class="control-row">
          <label>Axon Azimuth θ: <strong id="val-cone-theta">${thetaDeg}°</strong></label>
          <input type="range" id="slider-cone-theta" min="0" max="360" value="${thetaDeg}" />
        </div>

        <div class="control-row">
          <label>Axon Elevation φ: <strong id="val-cone-phi">${phiDeg}°</strong></label>
          <input type="range" id="slider-cone-phi" min="-90" max="90" value="${phiDeg}" />
        </div>

        <div class="control-row">
          <label>Radius σ: <strong id="val-conn-radius">${sigma.toFixed(1)}</strong></label>
          <input type="range" id="slider-conn-radius" min="5" max="80" step="1" value="${sigma}" />
        </div>

        <div class="control-row">
          <label>Base Probability P_0: <strong id="val-conn-prob">${p0.toFixed(2)}</strong></label>
          <input type="range" id="slider-conn-prob" min="0.02" max="1.0" step="0.02" value="${p0}" />
        </div>

        <div class="action-btn-row">
          <button id="btn-rewire-neuron" class="btn btn-warning btn-block">REWIRE OUTGOING (PROBABILISTIC)</button>
        </div>
      </div>
    `;
    }

    // Cache oscilloscope
    this.oscCanvas = this.neuronPanelEl.querySelector('#osc-canvas');
    if (this.oscCanvas) {
      this.oscCtx = this.oscCanvas.getContext('2d');
    }

    this.voltMeterText = this.neuronPanelEl.querySelector('#meter-v-val');
    this.fireRateText = this.neuronPanelEl.querySelector('#telem-rate');
    this.inDegreeText = this.neuronPanelEl.querySelector('#telem-indeg');
    this.outDegreeText = this.neuronPanelEl.querySelector('#telem-outdeg');

    // Delete Neuron
    this.neuronPanelEl.querySelector('#btn-delete-neuron')?.addEventListener('click', () => {
      if (confirm(`Delete Neuron #${id} and remove all its synapses?`)) {
        if (this.onNeuronDelete) this.onNeuronDelete(id);
      }
    });

    this.neuronPanelEl.querySelector('#btn-close-inspector')?.addEventListener('click', () => {
      this.setSelectedNeuron(null);
      safeStore(this.mem.control, ControlIndex.SELECTED_NEURON, -1);
      if (this.onNeuronParamsUpdated) this.onNeuronParamsUpdated();
    });

    this.neuronPanelEl.querySelector('#btn-stimulate')?.addEventListener('click', () => {
      this.mem.vMem[id] = 1024;
      this.mem.visualFlash[id] = 255;
      pushCommand(this.mem, CommandType.INJECT_CURRENT, id, 600);
    });

    // Synapse weight sliders (real-time modification)
    this.neuronPanelEl.querySelectorAll('.syn-weight-slider').forEach((sliderEl) => {
      sliderEl.addEventListener('input', (e) => {
        const input = e.target as HTMLInputElement;
        const post = parseInt(input.dataset.post || '-1', 10);
        const delay = parseInt(input.dataset.delay || '1', 10);
        const weight = parseInt(input.value, 10);

        const valSpan = input.nextElementSibling as HTMLElement;
        if (valSpan) {
          valSpan.textContent = weight.toString();
          valSpan.className = `syn-w-val ${weight >= 0 ? 'text-cyan' : 'text-magenta'}`;
        }

        const numN = safeLoad(this.mem.control, ControlIndex.NUM_NEURONS);
        this.spatialHash.setManualSynapse(this.mem, id, post, weight, delay, numN);

        const rawW = (weight < 0 ? weight + 0x10000 : weight) & 0xffff;
        const arg3 = rawW | ((delay & 0xff) << 16);
        pushCommand(this.mem, CommandType.SET_SYNAPSE, id, post, arg3);

        if (this.onNeuronParamsUpdated) this.onNeuronParamsUpdated();
      });
    });

    // Delete synapse buttons
    this.neuronPanelEl.querySelectorAll('.btn-delete-syn').forEach((btnEl) => {
      btnEl.addEventListener('click', (e) => {
        const btn = e.target as HTMLElement;
        const post = parseInt(btn.dataset.post || '-1', 10);
        if (post >= 0) {
          const numN = safeLoad(this.mem.control, ControlIndex.NUM_NEURONS);
          const total = this.spatialHash.removeSynapse(this.mem, id, post, numN);
          safeStore(this.mem.control, ControlIndex.NUM_SYNAPSES, total);
          pushCommand(this.mem, CommandType.REMOVE_SYNAPSE, id, post);
          this.renderNeuronPanel();
          if (this.onNeuronParamsUpdated) this.onNeuronParamsUpdated();
        }
      });
    });

    // Firing Mode dropdown
    const selectMode = this.neuronPanelEl.querySelector('#slider-mode') as HTMLSelectElement;
    const secPoisson = this.neuronPanelEl.querySelector('#section-poisson-controls') as HTMLElement;
    const secBurst = this.neuronPanelEl.querySelector('#section-burst-controls') as HTMLElement;

    selectMode?.addEventListener('change', () => {
      const newMode = parseInt(selectMode.value, 10) as NeuronMode;
      this.mem.neuronMode[id] = newMode;
      secPoisson.style.display = newMode === NeuronMode.POISSON ? '' : 'none';
      secBurst.style.display = newMode === NeuronMode.BURSTER ? '' : 'none';
      if (this.onNeuronParamsUpdated) this.onNeuronParamsUpdated();
    });

    // ShiftV & ShiftS
    const sliderShiftV = this.neuronPanelEl.querySelector('#slider-shift-v') as HTMLInputElement;
    const valShiftV = this.neuronPanelEl.querySelector('#val-shift-v');
    sliderShiftV?.addEventListener('input', () => {
      const v = parseInt(sliderShiftV.value, 10);
      this.mem.shiftV[id] = v;
      if (valShiftV) valShiftV.textContent = v.toString();
    });

    const sliderShiftS = this.neuronPanelEl.querySelector('#slider-shift-s') as HTMLInputElement;
    const valShiftS = this.neuronPanelEl.querySelector('#val-shift-s');
    sliderShiftS?.addEventListener('input', () => {
      const s = parseInt(sliderShiftS.value, 10);
      this.mem.shiftS[id] = s;
      if (valShiftS) valShiftS.textContent = s.toString();
    });

    const sliderRefr = this.neuronPanelEl.querySelector('#slider-refractory') as HTMLInputElement;
    const valRefr = this.neuronPanelEl.querySelector('#val-refractory');
    sliderRefr?.addEventListener('input', () => {
      const r = parseInt(sliderRefr.value, 10);
      this.mem.refractory[id] = r;
      if (valRefr) valRefr.textContent = r.toString();
    });

    // Poisson & Burst
    const sliderPoisson = this.neuronPanelEl.querySelector('#slider-poisson-hz') as HTMLInputElement;
    const valPoisson = this.neuronPanelEl.querySelector('#val-poisson-hz');
    sliderPoisson?.addEventListener('input', () => {
      const hz = parseInt(sliderPoisson.value, 10);
      const simHz = safeLoad(this.mem.control, ControlIndex.SIM_HZ) || 1000;
      this.mem.poissonThresh[id] = Math.floor((hz / simHz) * 4294967296);
      if (valPoisson) valPoisson.textContent = `${hz} Hz`;
    });

    const sliderBurstT = this.neuronPanelEl.querySelector('#slider-burst-t') as HTMLInputElement;
    const valBurstT = this.neuronPanelEl.querySelector('#val-burst-t');
    sliderBurstT?.addEventListener('input', () => {
      const t = parseInt(sliderBurstT.value, 10);
      this.mem.burstPeriod[id] = t;
      if (valBurstT) valBurstT.textContent = t.toString();
    });

    const sliderBurstD = this.neuronPanelEl.querySelector('#slider-burst-d') as HTMLInputElement;
    const valBurstD = this.neuronPanelEl.querySelector('#val-burst-d');
    sliderBurstD?.addEventListener('input', () => {
      const d = parseInt(sliderBurstD.value, 10);
      this.mem.burstDuty[id] = d;
      if (valBurstD) valBurstD.textContent = d.toString();
    });

    // Axon Cone
    const sliderTheta = this.neuronPanelEl.querySelector('#slider-cone-theta') as HTMLInputElement;
    const valTheta = this.neuronPanelEl.querySelector('#val-cone-theta');
    const sliderPhi = this.neuronPanelEl.querySelector('#slider-cone-phi') as HTMLInputElement;
    const valPhi = this.neuronPanelEl.querySelector('#val-cone-phi');

    const updateConeDirection = () => {
      const th = parseInt(sliderTheta.value, 10) * Math.PI / 180;
      const ph = parseInt(sliderPhi.value, 10) * Math.PI / 180;
      const cosPh = Math.cos(ph);

      this.mem.axonDirXYZ[id * 3] = cosPh * Math.cos(th);
      this.mem.axonDirXYZ[id * 3 + 1] = Math.sin(ph);
      this.mem.axonDirXYZ[id * 3 + 2] = cosPh * Math.sin(th);

      if (valTheta) valTheta.textContent = `${sliderTheta.value}°`;
      if (valPhi) valPhi.textContent = `${sliderPhi.value}°`;
      if (this.onNeuronParamsUpdated) this.onNeuronParamsUpdated();
    };

    sliderTheta?.addEventListener('input', updateConeDirection);
    sliderPhi?.addEventListener('input', updateConeDirection);

    // Radius, Prob
    const sliderRadius = this.neuronPanelEl.querySelector('#slider-conn-radius') as HTMLInputElement;
    const valRadius = this.neuronPanelEl.querySelector('#val-conn-radius');
    sliderRadius?.addEventListener('input', () => {
      const r = parseFloat(sliderRadius.value);
      this.mem.connRadius[id] = r;
      if (valRadius) valRadius.textContent = r.toFixed(1);
    });

    const sliderProb = this.neuronPanelEl.querySelector('#slider-conn-prob') as HTMLInputElement;
    const valProb = this.neuronPanelEl.querySelector('#val-conn-prob');
    sliderProb?.addEventListener('input', () => {
      const p = parseFloat(sliderProb.value);
      this.mem.connProb[id] = p;
      if (valProb) valProb.textContent = p.toFixed(2);
    });

    // Rewire button
    this.neuronPanelEl.querySelector('#btn-rewire-neuron')?.addEventListener('click', () => {
      pushCommand(this.mem, CommandType.REWIRE_NEURON, id);
      setTimeout(() => {
        if (this.onNeuronParamsUpdated) this.onNeuronParamsUpdated();
        this.renderNeuronPanel();
      }, 50);
    });
  }

  public updateTelemetry(): void {
    if (this.tickCounterEl) {
      this.tickCounterEl.textContent = safeLoad(this.mem.control, ControlIndex.SIM_TICK).toLocaleString();
    }
    if (this.workerFpsEl) {
      this.workerFpsEl.textContent = `${safeLoad(this.mem.control, ControlIndex.WORKER_FPS)} Hz`;
    }
    if (this.neuronCountEl) {
      this.neuronCountEl.textContent = safeLoad(this.mem.control, ControlIndex.NUM_NEURONS).toString();
    }
    if (this.synCountEl) {
      this.synCountEl.textContent = safeLoad(this.mem.control, ControlIndex.NUM_SYNAPSES).toLocaleString();
    }

    // Rhythm of the population at 1-ms resolution, computed by the simulation worker (sim/rhythm.ts): dominant
    // frequency in Hz of simulated time and coefficient of variation of the 5-ms population count (shown in %).
    const peakHzWorker = safeLoad(this.mem.control, ControlIndex.RHYTHM_PEAK_MHZ) / 1000;
    const syncIndex = Math.min(100, Math.round(safeLoad(this.mem.control, ControlIndex.RHYTHM_CV_MILLI) / 10));
    this.currentSyncIndex = syncIndex;

    // Dynamic Target Fitness evaluation (frequency resonance + synchrony index R)
    let targetFreq = 10.0;
    let targetSync = 60.0;
    let sigmaFreq = 2.5;

    if (this.targetObjective === 'gamma_critical') {
      targetFreq = 40.0;
      targetSync = 45.0;
      sigmaFreq = 6.0;
    } else if (this.targetObjective === 'theta_rhythm') {
      targetFreq = 6.0;
      targetSync = 50.0;
      sigmaFreq = 1.8;
    }

    const peakHz = peakHzWorker;
    this.currentPeakHz = peakHz;

    let freqScore = 0.0;
    if (peakHz > 0) {
      freqScore = Math.exp(-Math.pow(peakHz - targetFreq, 2) / (2 * Math.pow(sigmaFreq, 2)));
    }
    const syncScore = Math.min(1.0, syncIndex / targetSync);
    const fitnessRaw = Math.max(0.0, Math.min(1.0, 0.5 * freqScore + 0.5 * syncScore));
    this.currentFitnessScore = parseFloat(fitnessRaw.toFixed(3));
    const fitnessPercent = Math.round(fitnessRaw * 100);

    if (this.fitnessMeterEl) {
      this.fitnessMeterEl.style.width = `${fitnessPercent}%`;
    }
    if (this.fitnessScoreTextEl) {
      this.fitnessScoreTextEl.textContent = this.currentFitnessScore.toFixed(2);
    }
    const badgeScore = this.discoverySectionEl?.querySelector('#val-fitness-score-badge');
    if (badgeScore) {
      badgeScore.textContent = this.currentFitnessScore.toFixed(2);
    }
    if (this.fitnessFreqTextEl) {
      this.fitnessFreqTextEl.textContent = `${peakHz.toFixed(1)} Hz`;
    }
    if (this.fitnessSyncTextEl) {
      this.fitnessSyncTextEl.textContent = `${syncIndex}%`;
    }

    if (this.syncIndexEl) {
      this.syncIndexEl.textContent = `${syncIndex}%`;
      if (syncIndex >= 65) {
        this.syncIndexEl.style.color = 'var(--accent-gold)';
      } else if (syncIndex >= 25) {
        this.syncIndexEl.style.color = 'var(--accent-cyan)';
      } else {
        this.syncIndexEl.style.color = 'var(--text-muted)';
      }
    }

    if (this.selectedNeuronId !== null && this.selectedNeuronId >= 0) {
      const id = this.selectedNeuronId;
      const v = this.mem.vMem[id];

      if (this.voltMeterText) {
        this.voltMeterText.textContent = `${v} mV`;
      }

      // Update oscilloscope buffer
      this.vHistory.shift();
      this.vHistory.push(v);
      this.drawOscilloscope();

      const bf = this.mem.spikeBitfield[id];
      if ((bf & 1) === 1) {
        this.spikeWindowCount++;
      }

      const now = performance.now();
      if (now - this.spikeWindowStart >= 500) {
        const elapsedSec = (now - this.spikeWindowStart) / 1000.0;
        this.runningHz = Math.round(this.spikeWindowCount / elapsedSec);
        this.spikeWindowCount = 0;
        this.spikeWindowStart = now;
        if (this.fireRateText) {
          this.fireRateText.textContent = `${this.runningHz} Hz`;
        }
      }
    }
  }

  private drawOscilloscope(): void {
    if (!this.oscCtx || !this.oscCanvas) return;
    const ctx = this.oscCtx;
    const w = this.oscCanvas.width;
    const h = this.oscCanvas.height;

    ctx.fillStyle = '#0a0d18';
    ctx.fillRect(0, 0, w, h);

    // Guide lines:
    // Voltage range: [-256, 1024] => total span 1280
    const toY = (volt: number) => h - ((volt + 256) / 1280.0) * h;

    // Threshold line (+1024)
    ctx.strokeStyle = 'rgba(255, 0, 127, 0.4)';
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(0, toY(1024));
    ctx.lineTo(w, toY(1024));
    ctx.stroke();

    // Resting line (0)
    ctx.strokeStyle = 'rgba(0, 240, 255, 0.3)';
    ctx.beginPath();
    ctx.moveTo(0, toY(0));
    ctx.lineTo(w, toY(0));
    ctx.stroke();

    // Reset line (-256)
    ctx.strokeStyle = 'rgba(119, 51, 255, 0.3)';
    ctx.beginPath();
    ctx.moveTo(0, toY(-256));
    ctx.lineTo(w, toY(-256));
    ctx.stroke();
    ctx.setLineDash([]);

    // Draw waveform
    ctx.strokeStyle = '#00f0ff';
    ctx.lineWidth = 1.8;
    ctx.beginPath();

    const len = this.vHistory.length;
    const stepX = w / (len - 1);

    for (let i = 0; i < len; i++) {
      const x = i * stepX;
      const y = toY(this.vHistory[i]);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Draw glow at rightmost tip
    const lastY = toY(this.vHistory[len - 1]);
    ctx.fillStyle = '#ffffff';
    ctx.beginPath();
    ctx.arc(w - 2, lastY, 3, 0, Math.PI * 2);
    ctx.fill();

    // Draw top-right spike indicator LED & state badge
    const isSpiking = (this.selectedNeuronId !== null && this.selectedNeuronId >= 0) &&
      (this.mem.vMem[this.selectedNeuronId] >= 1024 || this.mem.visualFlash[this.selectedNeuronId] > 100);

    ctx.save();
    if (isSpiking) {
      ctx.fillStyle = '#ff007f';
      ctx.shadowColor = '#ff007f';
      ctx.shadowBlur = 8;
      ctx.beginPath();
      ctx.arc(w - 55, 12, 4.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;

      ctx.fillStyle = '#ff007f';
      ctx.font = 'normal 10px monospace';
      ctx.fillText('SPIKE', w - 46, 15);
    } else {
      ctx.fillStyle = 'rgba(0, 240, 255, 0.4)';
      ctx.beginPath();
      ctx.arc(w - 72, 12, 3.5, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = '#556677';
      ctx.font = 'normal 9px monospace';
      ctx.fillText('SUB-THRESH', w - 63, 15);
    }
    ctx.restore();
  }
}
