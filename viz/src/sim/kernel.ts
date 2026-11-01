/**
 * Integer spiking kernel shared by the Web Worker and the in-process fallback.
 * Bit-for-bit the same as neurogenesis/spiking/reference.py (IntegerSNNSimulator) and neurogenesis/spiking/jax_backend.py, given the
 * same xorshift32 seed (DEFAULT_SEED = 12345, the Python default).
 */
import type { SharedSimulationMemory } from './types';

export const DEFAULT_SEED = 12345;

/** Advances the network by one tick. Returns [spikes this tick, new PRNG state]. */
export function stepKernel(mem: SharedSimulationMemory, numNeurons: number, prngIn: number): [number, number] {
  let prngState = prngIn >>> 0;
  let tickSpikeCount = 0;

  // 1. Bit-shift decay with underflow clamping, drives, refractory period and firing
  for (let i = 0; i < numNeurons; i++) {
    let v = mem.vMem[i];
    if (v > 0) v -= Math.max(1, v >> mem.shiftV[i]);
    else if (v < 0) v -= Math.min(-1, v >> mem.shiftV[i]);

    let isyn = mem.iSyn[i];
    if (isyn > 0) isyn -= Math.max(1, isyn >> mem.shiftS[i]);
    else if (isyn < 0) isyn -= Math.min(-1, isyn >> mem.shiftS[i]);
    mem.iSyn[i] = isyn;

    v += isyn >> 2;
    if (v > 2048) v = 2048;
    else if (v < -2048) v = -2048;

    const mode = mem.neuronMode[i];
    if (mode === 1) {
      prngState ^= prngState << 13;
      prngState ^= prngState >>> 17;
      prngState ^= prngState << 5;
      prngState = prngState >>> 0;
      if (prngState < mem.poissonThresh[i]) v = mem.threshold[i];
    } else if (mode === 2) {
      const period = mem.burstPeriod[i] || 200;
      const duty = mem.burstDuty[i] || 24;
      const phase = (mem.burstPhase[i] + 1) % period;
      mem.burstPhase[i] = phase;
      if (phase < duty && (phase & 3) === 0) v = mem.threshold[i];
    }

    let spiked = v >= mem.threshold[i] ? 1 : 0;
    if (mem.refrCount[i] > 0) {
      // absolute refractory period: no spike, v held at the reset value (the PRNG draw above is still consumed)
      mem.refrCount[i] -= 1;
      spiked = 0;
      v = -256;
    }
    if (spiked) {
      mem.refrCount[i] = mem.refractory[i];
      mem.vMem[i] = -256;
      mem.visualFlash[i] = 255;
      tickSpikeCount++;
    } else {
      mem.vMem[i] = v;
    }
    mem.spikeBitfield[i] = ((mem.spikeBitfield[i] << 1) | spiked) >>> 0;
  }

  // 2. Synaptic propagation with bitwise delays via CSR
  for (let i = 0; i < numNeurons; i++) {
    const bf = mem.spikeBitfield[i];
    if (bf === 0) continue;
    const start = mem.rowPtr[i];
    const end = mem.rowPtr[i + 1];
    for (let syn = start; syn < end; syn++) {
      if ((bf >>> mem.delays[syn]) & 1) {
        mem.iSyn[mem.colIdx[syn]] += mem.weights[syn];
      }
    }
  }
  return [tickSpikeCount, prngState];
}
