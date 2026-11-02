/**
 * 3D Spiking Neural Network & Morphogenetic Sandbox
 * System Architecture & Type Definitions
 */

export const MAX_NEURONS = 10000;
export const MAX_SYNAPSES = 500000;
export const CMD_QUEUE_CAPACITY = 64;

export const enum NeuronMode {
  LIF = 0,
  POISSON = 1,
  BURSTER = 2,
}

export const enum CommandType {
  NONE = 0,
  ADD_NEURON = 1,
  REWIRE_NEURON = 2,
  REWIRE_ALL = 3,
  INJECT_CURRENT = 4,
  SET_HZ = 5,
  SET_RUNNING = 6,
  STEP = 7,
  RESET_VOLTAGES = 8,
  SET_SYNAPSE = 9,      // arg1: preId, arg2: postId, arg3: (weight & 0xFFFF) | (delay << 16)
  REMOVE_SYNAPSE = 10,   // arg1: preId, arg2: postId
  DELETE_NEURON = 11,    // arg1: neuronId
  SET_POPULATION = 12,   // arg1: newCount
}

export const enum ControlIndex {
  NUM_NEURONS = 0,
  NUM_SYNAPSES = 1,
  SIM_TICK = 2,
  SIM_HZ = 3,
  IS_RUNNING = 4,
  STEP_COUNT = 5,
  SPIKE_COUNT = 6,
  SELECTED_NEURON = 7,
  CMD_HEAD = 8,
  CMD_TAIL = 9,
  TOTAL_SPIKES = 10,
  WORKER_FPS = 11,
}

export interface SharedSimulationMemory {
  buffer: SharedArrayBuffer | ArrayBuffer;
  isShared: boolean;
  // SoA Neuron Buffers
  posXYZ: Float32Array;         // [MAX_NEURONS * 3]
  axonDirXYZ: Float32Array;     // [MAX_NEURONS * 3]
  vMem: Int16Array;             // [MAX_NEURONS]
  iSyn: Int32Array;             // [MAX_NEURONS]
  shiftV: Uint8Array;           // [MAX_NEURONS]
  shiftS: Uint8Array;           // [MAX_NEURONS]
  neuronMode: Uint8Array;       // [MAX_NEURONS]
  poissonThresh: Uint32Array;   // [MAX_NEURONS]
  burstPeriod: Uint16Array;     // [MAX_NEURONS]
  burstDuty: Uint16Array;       // [MAX_NEURONS]
  burstPhase: Uint16Array;      // [MAX_NEURONS]
  connRadius: Float32Array;     // [MAX_NEURONS]
  connProb: Float32Array;       // [MAX_NEURONS]
  baseWeight: Int16Array;       // [MAX_NEURONS]
  spikeBitfield: Uint32Array;   // [MAX_NEURONS]
  visualFlash: Uint8Array;      // [MAX_NEURONS]
  refractory: Uint8Array;       // [MAX_NEURONS] absolute refractory period (ticks; 0 = none)
  refrCount: Uint8Array;        // [MAX_NEURONS] remaining refractory ticks
  role: Uint8Array;             // [MAX_NEURONS] 0 internal, 1 input, 2 output
  threshold: Int16Array;        // [MAX_NEURONS] per-neuron firing threshold (default 1024)

  // CSR Synaptic Graph Buffers
  rowPtr: Uint32Array;          // [MAX_NEURONS + 1]
  colIdx: Uint32Array;          // [MAX_SYNAPSES]
  weights: Int16Array;          // [MAX_SYNAPSES]
  delays: Uint8Array;           // [MAX_SYNAPSES]

  // Lock-Free Control & Command Buffers
  control: Int32Array;          // [64]
  commandQueue: Int32Array;     // [CMD_QUEUE_CAPACITY * 4]
}

export interface NeuronConfig {
  x: number;
  y: number;
  z: number;
  dirX: number;
  dirY: number;
  dirZ: number;
  mode: NeuronMode;
  shiftV: number;
  shiftS: number;
  baseWeight: number;
  connRadius: number;
  connProb: number;
  poissonHz?: number;
  burstPeriod?: number;
  burstDuty?: number;
  refractory?: number;
  role?: number;
}

export interface SerializedSynapse {
  pre: number;
  post: number;
  weight: number;
  delay: number;
}

export interface SerializedNeuron {
  id: number;
  x: number;
  y: number;
  z: number;
  dirX: number;
  dirY: number;
  dirZ: number;
  mode: number;
  shiftV: number;
  shiftS: number;
  baseWeight: number;
  connRadius: number;
  connProb: number;
  poissonHz?: number;
  burstPeriod?: number;
  burstDuty?: number;
  refractory?: number;
  role?: number;
  threshold?: number;
}

export interface SerializedNetwork {
  version: string;
  numNeurons: number;
  numSynapses: number;
  morphology?: string;
  neurons: SerializedNeuron[];
  synapses: SerializedSynapse[];
}

export type ToolMode = 'SELECT' | 'WIRE' | 'SPAWN';
