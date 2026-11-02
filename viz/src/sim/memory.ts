/**
 * SharedArrayBuffer / ArrayBuffer Memory Allocator & Lock-Free Ring Buffer
 * Supports SharedArrayBuffer with Atomics, and falls back to standard ArrayBuffer seamlessly.
 */

import {
  MAX_NEURONS,
  MAX_SYNAPSES,
  CMD_QUEUE_CAPACITY,
  ControlIndex,
  SharedSimulationMemory,
} from './types';

function align8(offset: number): number {
  return (offset + 7) & ~7;
}

export function isSharedMemorySupported(): boolean {
  try {
    if (typeof SharedArrayBuffer === 'undefined') return false;
    if (typeof window !== 'undefined' && !window.crossOriginIsolated) {
      return false;
    }
    const testBuf = new SharedArrayBuffer(16);
    return testBuf.byteLength === 16;
  } catch {
    return false;
  }
}

export function safeLoad(arr: Int32Array, idx: number): number {
  if (typeof SharedArrayBuffer !== 'undefined' && arr.buffer instanceof SharedArrayBuffer) {
    try {
      return Atomics.load(arr, idx);
    } catch {
      return arr[idx];
    }
  }
  return arr[idx];
}

export function safeStore(arr: Int32Array, idx: number, val: number): void {
  if (typeof SharedArrayBuffer !== 'undefined' && arr.buffer instanceof SharedArrayBuffer) {
    try {
      Atomics.store(arr, idx, val);
      return;
    } catch {
      arr[idx] = val;
      return;
    }
  }
  arr[idx] = val;
}

export function safeAdd(arr: Int32Array, idx: number, val: number): number {
  if (typeof SharedArrayBuffer !== 'undefined' && arr.buffer instanceof SharedArrayBuffer) {
    try {
      return Atomics.add(arr, idx, val);
    } catch {
      const old = arr[idx];
      arr[idx] += val;
      return old;
    }
  }
  const old = arr[idx];
  arr[idx] += val;
  return old;
}

export function safeSub(arr: Int32Array, idx: number, val: number): number {
  if (typeof SharedArrayBuffer !== 'undefined' && arr.buffer instanceof SharedArrayBuffer) {
    try {
      return Atomics.sub(arr, idx, val);
    } catch {
      const old = arr[idx];
      arr[idx] -= val;
      return old;
    }
  }
  const old = arr[idx];
  arr[idx] -= val;
  return old;
}

export function createSharedSimulationMemory(existingBuffer?: SharedArrayBuffer | ArrayBuffer): SharedSimulationMemory {
  // Compute required layout offsets
  let offset = 0;

  const posXYZOffset = offset;
  offset = align8(offset + MAX_NEURONS * 3 * Float32Array.BYTES_PER_ELEMENT);

  const axonDirXYZOffset = offset;
  offset = align8(offset + MAX_NEURONS * 3 * Float32Array.BYTES_PER_ELEMENT);

  const vMemOffset = offset;
  offset = align8(offset + MAX_NEURONS * Int16Array.BYTES_PER_ELEMENT);

  const iSynOffset = offset;
  offset = align8(offset + MAX_NEURONS * Int32Array.BYTES_PER_ELEMENT);

  const shiftVOffset = offset;
  offset = align8(offset + MAX_NEURONS * Uint8Array.BYTES_PER_ELEMENT);

  const shiftSOffset = offset;
  offset = align8(offset + MAX_NEURONS * Uint8Array.BYTES_PER_ELEMENT);

  const neuronModeOffset = offset;
  offset = align8(offset + MAX_NEURONS * Uint8Array.BYTES_PER_ELEMENT);

  const poissonThreshOffset = offset;
  offset = align8(offset + MAX_NEURONS * Uint32Array.BYTES_PER_ELEMENT);

  const burstPeriodOffset = offset;
  offset = align8(offset + MAX_NEURONS * Uint16Array.BYTES_PER_ELEMENT);

  const burstDutyOffset = offset;
  offset = align8(offset + MAX_NEURONS * Uint16Array.BYTES_PER_ELEMENT);

  const burstPhaseOffset = offset;
  offset = align8(offset + MAX_NEURONS * Uint16Array.BYTES_PER_ELEMENT);

  const connRadiusOffset = offset;
  offset = align8(offset + MAX_NEURONS * Float32Array.BYTES_PER_ELEMENT);

  const connProbOffset = offset;
  offset = align8(offset + MAX_NEURONS * Float32Array.BYTES_PER_ELEMENT);

  const baseWeightOffset = offset;
  offset = align8(offset + MAX_NEURONS * Int16Array.BYTES_PER_ELEMENT);

  const spikeBitfieldOffset = offset;
  offset = align8(offset + MAX_NEURONS * Uint32Array.BYTES_PER_ELEMENT);

  const visualFlashOffset = offset;
  offset = align8(offset + MAX_NEURONS * Uint8Array.BYTES_PER_ELEMENT);

  const refractoryOffset = offset;
  offset = align8(offset + MAX_NEURONS * Uint8Array.BYTES_PER_ELEMENT);

  const refrCountOffset = offset;
  offset = align8(offset + MAX_NEURONS * Uint8Array.BYTES_PER_ELEMENT);

  const roleOffset = offset;
  offset = align8(offset + MAX_NEURONS * Uint8Array.BYTES_PER_ELEMENT);

  const thresholdOffset = offset;
  offset = align8(offset + MAX_NEURONS * Int16Array.BYTES_PER_ELEMENT);

  const rowPtrOffset = offset;
  offset = align8(offset + (MAX_NEURONS + 1) * Uint32Array.BYTES_PER_ELEMENT);

  const colIdxOffset = offset;
  offset = align8(offset + MAX_SYNAPSES * Uint32Array.BYTES_PER_ELEMENT);

  const weightsOffset = offset;
  offset = align8(offset + MAX_SYNAPSES * Int16Array.BYTES_PER_ELEMENT);

  const delaysOffset = offset;
  offset = align8(offset + MAX_SYNAPSES * Uint8Array.BYTES_PER_ELEMENT);

  const controlOffset = offset;
  offset = align8(offset + 64 * Int32Array.BYTES_PER_ELEMENT);

  const commandQueueOffset = offset;
  offset = align8(offset + CMD_QUEUE_CAPACITY * 4 * Int32Array.BYTES_PER_ELEMENT);

  const totalByteLength = offset;

  let isShared = false;
  let buffer: SharedArrayBuffer | ArrayBuffer;

  if (existingBuffer) {
    buffer = existingBuffer;
    isShared = typeof SharedArrayBuffer !== 'undefined' && existingBuffer instanceof SharedArrayBuffer;
  } else {
    if (isSharedMemorySupported()) {
      try {
        buffer = new SharedArrayBuffer(totalByteLength);
        isShared = true;
      } catch (e) {
        console.warn('[Memory] Failed to create SharedArrayBuffer, falling back to ArrayBuffer:', e);
        buffer = new ArrayBuffer(totalByteLength);
        isShared = false;
      }
    } else {
      buffer = new ArrayBuffer(totalByteLength);
      isShared = false;
    }
  }

  const posXYZ = new Float32Array(buffer, posXYZOffset, MAX_NEURONS * 3);
  const axonDirXYZ = new Float32Array(buffer, axonDirXYZOffset, MAX_NEURONS * 3);
  const vMem = new Int16Array(buffer, vMemOffset, MAX_NEURONS);
  const iSyn = new Int32Array(buffer, iSynOffset, MAX_NEURONS);
  const shiftV = new Uint8Array(buffer, shiftVOffset, MAX_NEURONS);
  const shiftS = new Uint8Array(buffer, shiftSOffset, MAX_NEURONS);
  const neuronMode = new Uint8Array(buffer, neuronModeOffset, MAX_NEURONS);
  const poissonThresh = new Uint32Array(buffer, poissonThreshOffset, MAX_NEURONS);
  const burstPeriod = new Uint16Array(buffer, burstPeriodOffset, MAX_NEURONS);
  const burstDuty = new Uint16Array(buffer, burstDutyOffset, MAX_NEURONS);
  const burstPhase = new Uint16Array(buffer, burstPhaseOffset, MAX_NEURONS);
  const connRadius = new Float32Array(buffer, connRadiusOffset, MAX_NEURONS);
  const connProb = new Float32Array(buffer, connProbOffset, MAX_NEURONS);
  const baseWeight = new Int16Array(buffer, baseWeightOffset, MAX_NEURONS);
  const spikeBitfield = new Uint32Array(buffer, spikeBitfieldOffset, MAX_NEURONS);
  const visualFlash = new Uint8Array(buffer, visualFlashOffset, MAX_NEURONS);

  const refractory = new Uint8Array(buffer, refractoryOffset, MAX_NEURONS);
  const refrCount = new Uint8Array(buffer, refrCountOffset, MAX_NEURONS);
  const role = new Uint8Array(buffer, roleOffset, MAX_NEURONS);
  const threshold = new Int16Array(buffer, thresholdOffset, MAX_NEURONS);
  if (!existingBuffer) threshold.fill(1024);                      // default firing threshold for every slot

  const rowPtr = new Uint32Array(buffer, rowPtrOffset, MAX_NEURONS + 1);
  const colIdx = new Uint32Array(buffer, colIdxOffset, MAX_SYNAPSES);
  const weights = new Int16Array(buffer, weightsOffset, MAX_SYNAPSES);
  const delays = new Uint8Array(buffer, delaysOffset, MAX_SYNAPSES);

  const control = new Int32Array(buffer, controlOffset, 64);
  const commandQueue = new Int32Array(buffer, commandQueueOffset, CMD_QUEUE_CAPACITY * 4);

  return {
    buffer,
    isShared,
    posXYZ,
    axonDirXYZ,
    vMem,
    iSyn,
    shiftV,
    shiftS,
    neuronMode,
    poissonThresh,
    burstPeriod,
    burstDuty,
    burstPhase,
    connRadius,
    connProb,
    baseWeight,
    spikeBitfield,
    visualFlash,
    refractory,
    refrCount,
    role,
    threshold,
    rowPtr,
    colIdx,
    weights,
    delays,
    control,
    commandQueue,
  };
}

export function pushCommand(
  mem: SharedSimulationMemory,
  cmdType: number,
  arg1 = 0,
  arg2 = 0,
  arg3 = 0
): boolean {
  const head = safeLoad(mem.control, ControlIndex.CMD_HEAD);
  const tail = safeLoad(mem.control, ControlIndex.CMD_TAIL);
  const nextHead = (head + 1) % CMD_QUEUE_CAPACITY;

  if (nextHead === tail) {
    return false; // Queue full
  }

  const offset = head * 4;
  mem.commandQueue[offset + 1] = arg1;
  mem.commandQueue[offset + 2] = arg2;
  mem.commandQueue[offset + 3] = arg3;
  safeStore(mem.commandQueue, offset, cmdType);
  safeStore(mem.control, ControlIndex.CMD_HEAD, nextHead);

  return true;
}

export function popCommand(
  mem: SharedSimulationMemory
): { cmdType: number; arg1: number; arg2: number; arg3: number } | null {
  const tail = safeLoad(mem.control, ControlIndex.CMD_TAIL);
  const head = safeLoad(mem.control, ControlIndex.CMD_HEAD);

  if (tail === head) {
    return null; // Empty
  }

  const offset = tail * 4;
  const cmdType = safeLoad(mem.commandQueue, offset);
  const arg1 = mem.commandQueue[offset + 1];
  const arg2 = mem.commandQueue[offset + 2];
  const arg3 = mem.commandQueue[offset + 3];

  const nextTail = (tail + 1) % CMD_QUEUE_CAPACITY;
  safeStore(mem.control, ControlIndex.CMD_TAIL, nextTail);

  return { cmdType, arg1, arg2, arg3 };
}
