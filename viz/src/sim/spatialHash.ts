/**
 * 3D Spatial Hashing & Probabilistic Morphogenetic Wiring Engine
 * Supports automated probabilistic rewiring, granular manual drag-and-drop synapse editing,
 * and JSON serialization/deserialization.
 */

import {
  MAX_NEURONS,
  MAX_SYNAPSES,
  SharedSimulationMemory,
  SerializedNetwork,
  SerializedNeuron,
  SerializedSynapse,
} from './types';

export const CELL_SIZE = 25.0;
export const GRID_DIM = 8; // 8 * 25 = 200 units, covering [-100, 100]
export const TOTAL_VOXELS = GRID_DIM * GRID_DIM * GRID_DIM; // 512
export const CONDUCTION_VELOCITY = 4.0; // Spatial distance to tick delay ratio

export class SpatialHashManager {
  private head: Int32Array;
  private next: Int32Array;
  private rngState = 123456789;

  // Working buffers for fast single-neuron or batch rewiring
  public adjTargets: Uint16Array[];
  public adjWeights: Int16Array[];
  public adjDelays: Uint8Array[];

  constructor() {
    this.head = new Int32Array(TOTAL_VOXELS);
    this.next = new Int32Array(MAX_NEURONS);
    this.head.fill(-1);
    this.next.fill(-1);

    this.adjTargets = new Array(MAX_NEURONS);
    this.adjWeights = new Array(MAX_NEURONS);
    this.adjDelays = new Array(MAX_NEURONS);

    for (let i = 0; i < MAX_NEURONS; i++) {
      this.adjTargets[i] = new Uint16Array(0);
      this.adjWeights[i] = new Int16Array(0);
      this.adjDelays[i] = new Uint8Array(0);
    }
  }

  private nextRandom(): number {
    this.rngState ^= this.rngState << 13;
    this.rngState ^= this.rngState >>> 17;
    this.rngState ^= this.rngState << 5;
    return (this.rngState >>> 0) / 4294967296.0;
  }

  public getVoxelCoord(val: number): number {
    return Math.min(GRID_DIM - 1, Math.max(0, Math.floor((val + 100.0) / CELL_SIZE)));
  }

  public getVoxelIndex(x: number, y: number, z: number): number {
    const cx = this.getVoxelCoord(x);
    const cy = this.getVoxelCoord(y);
    const cz = this.getVoxelCoord(z);
    return (cx << 6) | (cy << 3) | cz;
  }

  public buildGrid(mem: SharedSimulationMemory, numNeurons: number): void {
    this.head.fill(-1);
    this.next.fill(-1);

    const pos = mem.posXYZ;
    for (let i = 0; i < numNeurons; i++) {
      const idx = i * 3;
      const vIdx = this.getVoxelIndex(pos[idx], pos[idx + 1], pos[idx + 2]);
      this.next[i] = this.head[vIdx];
      this.head[vIdx] = i;
    }
  }

  public rewireNeuronAdjacency(mem: SharedSimulationMemory, i: number, numNeurons: number): void {
    const pos = mem.posXYZ;
    const axon = mem.axonDirXYZ;

    const xi = pos[i * 3];
    const yi = pos[i * 3 + 1];
    const zi = pos[i * 3 + 2];

    let uxi = axon[i * 3];
    let uyi = axon[i * 3 + 1];
    let uzi = axon[i * 3 + 2];

    const uNorm = Math.sqrt(uxi * uxi + uyi * uyi + uzi * uzi);
    if (uNorm > 1e-4) {
      uxi /= uNorm;
      uyi /= uNorm;
      uzi /= uNorm;
    } else {
      uxi = 0;
      uyi = 1;
      uzi = 0;
    }

    const sigma = Math.max(1.0, mem.connRadius[i]);
    const twoSigmaSq = 2.0 * sigma * sigma;
    const p0 = Math.min(1.0, Math.max(0.0, mem.connProb[i]));
    const baseW = mem.baseWeight[i];

    const cx = this.getVoxelCoord(xi);
    const cy = this.getVoxelCoord(yi);
    const cz = this.getVoxelCoord(zi);

    const tempTargets: number[] = [];
    const tempWeights: number[] = [];
    const tempDelays: number[] = [];

    // Search 27 neighboring spatial cells
    for (let dx = -1; dx <= 1; dx++) {
      const nx = cx + dx;
      if (nx < 0 || nx >= GRID_DIM) continue;

      for (let dy = -1; dy <= 1; dy++) {
        const ny = cy + dy;
        if (ny < 0 || ny >= GRID_DIM) continue;

        for (let dz = -1; dz <= 1; dz++) {
          const nz = cz + dz;
          if (nz < 0 || nz >= GRID_DIM) continue;

          const vIdx = (nx << 6) | (ny << 3) | nz;
          let curr = this.head[vIdx];

          while (curr !== -1) {
            const j = curr;
            curr = this.next[curr];

            if (j === i || j >= numNeurons) continue;

            const rx = pos[j * 3] - xi;
            const ry = pos[j * 3 + 1] - yi;
            const rz = pos[j * 3 + 2] - zi;
            const distSq = rx * rx + ry * ry + rz * rz;
            const dist = Math.sqrt(distSq);

            if (dist < 0.1) continue;

            const dot = (uxi * rx + uyi * ry + uzi * rz) / dist;
            const directionalFactor = Math.max(0.1, dot);

            const prob = p0 * Math.exp(-distSq / twoSigmaSq) * directionalFactor;

            if (this.nextRandom() < prob) {
              const delay = Math.min(31, Math.max(1, Math.round(dist / CONDUCTION_VELOCITY)));
              const jitter = 0.9 + this.nextRandom() * 0.2;
              let w = Math.round(baseW * jitter);
              if (w > 512) w = 512;
              if (w < -512) w = -512;

              tempTargets.push(j);
              tempWeights.push(w);
              tempDelays.push(delay);
            }
          }
        }
      }
    }

    const count = tempTargets.length;
    const tgtArr = new Uint16Array(count);
    const wArr = new Int16Array(count);
    const dArr = new Uint8Array(count);

    for (let k = 0; k < count; k++) {
      tgtArr[k] = tempTargets[k];
      wArr[k] = tempWeights[k];
      dArr[k] = tempDelays[k];
    }

    this.adjTargets[i] = tgtArr;
    this.adjWeights[i] = wArr;
    this.adjDelays[i] = dArr;
  }

  public setManualSynapse(
    mem: SharedSimulationMemory,
    pre: number,
    post: number,
    weight: number,
    delay: number,
    numNeurons: number
  ): number {
    if (pre < 0 || pre >= numNeurons || post < 0 || post >= numNeurons || pre === post) {
      return mem.control[1];
    }

    const targets = this.adjTargets[pre];
    const weights = this.adjWeights[pre];
    const delays = this.adjDelays[pre];

    // Check if synapse already exists
    let existingIndex = -1;
    for (let k = 0; k < targets.length; k++) {
      if (targets[k] === post) {
        existingIndex = k;
        break;
      }
    }

    if (existingIndex !== -1) {
      // Update in-place
      weights[existingIndex] = Math.max(-512, Math.min(512, weight));
      delays[existingIndex] = Math.max(1, Math.min(31, delay));
    } else {
      // Append new synapse
      const count = targets.length;
      const newTgt = new Uint16Array(count + 1);
      const newW = new Int16Array(count + 1);
      const newD = new Uint8Array(count + 1);

      newTgt.set(targets);
      newW.set(weights);
      newD.set(delays);

      newTgt[count] = post;
      newW[count] = Math.max(-512, Math.min(512, weight));
      newD[count] = Math.max(1, Math.min(31, delay));

      this.adjTargets[pre] = newTgt;
      this.adjWeights[pre] = newW;
      this.adjDelays[pre] = newD;
    }

    return this.rebuildCSR(mem, numNeurons);
  }

  public removeSynapse(
    mem: SharedSimulationMemory,
    pre: number,
    post: number,
    numNeurons: number
  ): number {
    if (pre < 0 || pre >= numNeurons) return mem.control[1];

    const targets = this.adjTargets[pre];
    const weights = this.adjWeights[pre];
    const delays = this.adjDelays[pre];

    let foundIdx = -1;
    for (let k = 0; k < targets.length; k++) {
      if (targets[k] === post) {
        foundIdx = k;
        break;
      }
    }

    if (foundIdx === -1) return mem.control[1];

    const count = targets.length - 1;
    const newTgt = new Uint16Array(count);
    const newW = new Int16Array(count);
    const newD = new Uint8Array(count);

    let dst = 0;
    for (let src = 0; src < targets.length; src++) {
      if (src === foundIdx) continue;
      newTgt[dst] = targets[src];
      newW[dst] = weights[src];
      newD[dst] = delays[src];
      dst++;
    }

    this.adjTargets[pre] = newTgt;
    this.adjWeights[pre] = newW;
    this.adjDelays[pre] = newD;

    return this.rebuildCSR(mem, numNeurons);
  }

  public clearAll(mem: SharedSimulationMemory): void {
    for (let i = 0; i < MAX_NEURONS; i++) {
      this.adjTargets[i] = new Uint16Array(0);
      this.adjWeights[i] = new Int16Array(0);
      this.adjDelays[i] = new Uint8Array(0);
    }
    this.head.fill(-1);
    this.next.fill(-1);
    mem.rowPtr.fill(0);
  }

  public deleteNeuron(
    mem: SharedSimulationMemory,
    neuronId: number,
    numNeurons: number
  ): number {
    if (neuronId < 0 || neuronId >= numNeurons || numNeurons <= 0) {
      return numNeurons;
    }

    if (numNeurons === 1) {
      this.adjTargets[0] = new Uint16Array(0);
      this.adjWeights[0] = new Int16Array(0);
      this.adjDelays[0] = new Uint8Array(0);
      mem.rowPtr[0] = 0;
      mem.rowPtr[1] = 0;
      this.head.fill(-1);
      this.next.fill(-1);
      return 0;
    }

    const last = numNeurons - 1;

    // Swap neuronId with last neuron in SoA buffers
    if (neuronId !== last) {
      mem.posXYZ[neuronId * 3] = mem.posXYZ[last * 3];
      mem.posXYZ[neuronId * 3 + 1] = mem.posXYZ[last * 3 + 1];
      mem.posXYZ[neuronId * 3 + 2] = mem.posXYZ[last * 3 + 2];

      mem.axonDirXYZ[neuronId * 3] = mem.axonDirXYZ[last * 3];
      mem.axonDirXYZ[neuronId * 3 + 1] = mem.axonDirXYZ[last * 3 + 1];
      mem.axonDirXYZ[neuronId * 3 + 2] = mem.axonDirXYZ[last * 3 + 2];

      mem.vMem[neuronId] = mem.vMem[last];
      mem.iSyn[neuronId] = mem.iSyn[last];
      mem.shiftV[neuronId] = mem.shiftV[last];
      mem.shiftS[neuronId] = mem.shiftS[last];
      mem.neuronMode[neuronId] = mem.neuronMode[last];
      mem.poissonThresh[neuronId] = mem.poissonThresh[last];
      mem.burstPeriod[neuronId] = mem.burstPeriod[last];
      mem.burstDuty[neuronId] = mem.burstDuty[last];
      mem.burstPhase[neuronId] = mem.burstPhase[last];
      mem.refractory[neuronId] = mem.refractory[last];
      mem.refrCount[neuronId] = mem.refrCount[last];
      mem.role[neuronId] = mem.role[last];
      mem.threshold[neuronId] = mem.threshold[last];
      mem.connRadius[neuronId] = mem.connRadius[last];
      mem.connProb[neuronId] = mem.connProb[last];
      mem.baseWeight[neuronId] = mem.baseWeight[last];
      mem.spikeBitfield[neuronId] = mem.spikeBitfield[last];
      mem.visualFlash[neuronId] = mem.visualFlash[last];

      this.adjTargets[neuronId] = this.adjTargets[last];
      this.adjWeights[neuronId] = this.adjWeights[last];
      this.adjDelays[neuronId] = this.adjDelays[last];
    }

    this.adjTargets[last] = new Uint16Array(0);
    this.adjWeights[last] = new Int16Array(0);
    this.adjDelays[last] = new Uint8Array(0);

    const updatedCount = numNeurons - 1;

    // Fix incoming synapses referencing last -> neuronId, and delete references to neuronId
    for (let i = 0; i < updatedCount; i++) {
      const tgts = this.adjTargets[i];
      const ws = this.adjWeights[i];
      const ds = this.adjDelays[i];

      const keepTgt: number[] = [];
      const keepW: number[] = [];
      const keepD: number[] = [];

      for (let k = 0; k < tgts.length; k++) {
        let t = tgts[k];
        if (t === neuronId) {
          // was pointing to deleted neuron
          continue;
        } else if (t === last) {
          // was pointing to the neuron that got moved to neuronId
          t = neuronId;
        }
        keepTgt.push(t);
        keepW.push(ws[k]);
        keepD.push(ds[k]);
      }

      const count = keepTgt.length;
      this.adjTargets[i] = new Uint16Array(count);
      this.adjWeights[i] = new Int16Array(count);
      this.adjDelays[i] = new Uint8Array(count);

      for (let k = 0; k < count; k++) {
        this.adjTargets[i][k] = keepTgt[k];
        this.adjWeights[i][k] = keepW[k];
        this.adjDelays[i][k] = keepD[k];
      }
    }

    this.rebuildCSR(mem, updatedCount);
    return updatedCount;
  }

  public rebuildCSR(mem: SharedSimulationMemory, numNeurons: number): number {
    let synCount = 0;

    mem.rowPtr[0] = 0;
    for (let i = 0; i < numNeurons; i++) {
      const count = this.adjTargets[i].length;
      if (synCount + count > MAX_SYNAPSES) {
        const allowed = Math.max(0, MAX_SYNAPSES - synCount);
        mem.rowPtr[i + 1] = synCount + allowed;
        synCount += allowed;
      } else {
        mem.rowPtr[i + 1] = synCount + count;
        synCount += count;
      }
    }

    for (let i = numNeurons + 1; i <= MAX_NEURONS; i++) {
      mem.rowPtr[i] = synCount;
    }

    for (let i = 0; i < numNeurons; i++) {
      const start = mem.rowPtr[i];
      const end = mem.rowPtr[i + 1];
      const targets = this.adjTargets[i];
      const weights = this.adjWeights[i];
      const delays = this.adjDelays[i];

      let k = 0;
      for (let syn = start; syn < end; syn++) {
        mem.colIdx[syn] = targets[k];
        mem.weights[syn] = weights[k];
        mem.delays[syn] = delays[k];
        k++;
      }
    }

    return synCount;
  }

  public rewireAll(mem: SharedSimulationMemory, numNeurons: number): number {
    this.buildGrid(mem, numNeurons);
    for (let i = 0; i < numNeurons; i++) {
      this.rewireNeuronAdjacency(mem, i, numNeurons);
    }
    return this.rebuildCSR(mem, numNeurons);
  }

  public rewireSingleNeuron(mem: SharedSimulationMemory, i: number, numNeurons: number): number {
    this.buildGrid(mem, numNeurons);
    this.rewireNeuronAdjacency(mem, i, numNeurons);
    return this.rebuildCSR(mem, numNeurons);
  }

  public getInDegree(mem: SharedSimulationMemory, neuronId: number, numNeurons: number): number {
    let inDegree = 0;
    for (let i = 0; i < numNeurons; i++) {
      const tgts = this.adjTargets[i];
      for (let s = 0; s < tgts.length; s++) {
        if (tgts[s] === neuronId) inDegree++;
      }
    }
    return inDegree;
  }

  public getOutDegree(mem: SharedSimulationMemory, neuronId: number): number {
    return this.adjTargets[neuronId]?.length || 0;
  }

  public getOutgoingSynapses(neuronId: number): { post: number; weight: number; delay: number }[] {
    const list: { post: number; weight: number; delay: number }[] = [];
    const tgts = this.adjTargets[neuronId];
    const ws = this.adjWeights[neuronId];
    const ds = this.adjDelays[neuronId];
    if (!tgts) return list;

    for (let i = 0; i < tgts.length; i++) {
      list.push({ post: tgts[i], weight: ws[i], delay: ds[i] });
    }
    return list;
  }

  public getIncomingSynapses(
    neuronId: number,
    numNeurons: number
  ): { pre: number; weight: number; delay: number }[] {
    const list: { pre: number; weight: number; delay: number }[] = [];
    for (let pre = 0; pre < numNeurons; pre++) {
      if (pre === neuronId) continue;
      const tgts = this.adjTargets[pre];
      const ws = this.adjWeights[pre];
      const ds = this.adjDelays[pre];
      for (let k = 0; k < tgts.length; k++) {
        if (tgts[k] === neuronId) {
          list.push({ pre, weight: ws[k], delay: ds[k] });
        }
      }
    }
    return list;
  }

  public exportNetworkJSON(mem: SharedSimulationMemory, numNeurons: number, morphology = 'Custom'): SerializedNetwork {
    const neurons: SerializedNeuron[] = [];
    const synapses: SerializedSynapse[] = [];

    for (let i = 0; i < numNeurons; i++) {
      neurons.push({
        id: i,
        x: Number(mem.posXYZ[i * 3].toFixed(2)),
        y: Number(mem.posXYZ[i * 3 + 1].toFixed(2)),
        z: Number(mem.posXYZ[i * 3 + 2].toFixed(2)),
        dirX: Number(mem.axonDirXYZ[i * 3].toFixed(3)),
        dirY: Number(mem.axonDirXYZ[i * 3 + 1].toFixed(3)),
        dirZ: Number(mem.axonDirXYZ[i * 3 + 2].toFixed(3)),
        mode: mem.neuronMode[i],
        shiftV: mem.shiftV[i],
        shiftS: mem.shiftS[i],
        baseWeight: mem.baseWeight[i],
        connRadius: Number(mem.connRadius[i].toFixed(1)),
        connProb: Number(mem.connProb[i].toFixed(2)),
        burstPeriod: mem.burstPeriod[i],
        burstDuty: mem.burstDuty[i],
        poissonHz: Number(((mem.poissonThresh[i] / 4294967296) * 1000.0).toFixed(1)),
        refractory: mem.refractory[i],
        role: mem.role[i],
        threshold: mem.threshold[i],
      });

      const tgts = this.adjTargets[i];
      const ws = this.adjWeights[i];
      const ds = this.adjDelays[i];
      for (let k = 0; k < tgts.length; k++) {
        synapses.push({
          pre: i,
          post: tgts[k],
          weight: ws[k],
          delay: ds[k],
        });
      }
    }

    return {
      version: '1.0.0',
      numNeurons,
      numSynapses: synapses.length,
      morphology,
      neurons,
      synapses,
    };
  }

  public importNetworkJSON(mem: SharedSimulationMemory, net: SerializedNetwork): number {
    const count = Math.min(MAX_NEURONS, net.neurons.length);

    // Reset adjacency
    for (let i = 0; i < MAX_NEURONS; i++) {
      this.adjTargets[i] = new Uint16Array(0);
      this.adjWeights[i] = new Int16Array(0);
      this.adjDelays[i] = new Uint8Array(0);
    }

    // Temporary buckets for synapses
    const preSyns: { post: number; weight: number; delay: number }[][] = new Array(count)
      .fill(null)
      .map(() => []);

    for (let i = 0; i < count; i++) {
      const n = net.neurons[i];
      mem.posXYZ[i * 3] = n.x;
      mem.posXYZ[i * 3 + 1] = n.y;
      mem.posXYZ[i * 3 + 2] = n.z;

      mem.axonDirXYZ[i * 3] = n.dirX;
      mem.axonDirXYZ[i * 3 + 1] = n.dirY;
      mem.axonDirXYZ[i * 3 + 2] = n.dirZ;

      mem.vMem[i] = 0;
      mem.iSyn[i] = 0;
      mem.shiftV[i] = n.shiftV;
      mem.shiftS[i] = n.shiftS;
      mem.neuronMode[i] = n.mode;
      mem.baseWeight[i] = n.baseWeight;
      mem.connRadius[i] = n.connRadius;
      mem.connProb[i] = n.connProb;
      mem.burstPeriod[i] = n.burstPeriod || 200;
      mem.burstDuty[i] = n.burstDuty || 24;
      mem.burstPhase[i] = 0;
      mem.spikeBitfield[i] = 0;
      mem.visualFlash[i] = 0;
      mem.refractory[i] = n.refractory ?? 0;
      mem.refrCount[i] = 0;
      mem.role[i] = n.role ?? 0;
      mem.threshold[i] = n.threshold ?? 1024;
      const hz = n.poissonHz ?? 25.0;
      mem.poissonThresh[i] = Math.min(4294967295, Math.floor((hz / 1000.0) * 4294967296));
    }

    for (const syn of net.synapses) {
      if (syn.pre < count && syn.post < count) {
        preSyns[syn.pre].push({
          post: syn.post,
          weight: syn.weight,
          delay: syn.delay,
        });
      }
    }

    for (let i = 0; i < count; i++) {
      const syns = preSyns[i];
      const sCount = syns.length;
      this.adjTargets[i] = new Uint16Array(sCount);
      this.adjWeights[i] = new Int16Array(sCount);
      this.adjDelays[i] = new Uint8Array(sCount);

      for (let k = 0; k < sCount; k++) {
        this.adjTargets[i][k] = syns[k].post;
        this.adjWeights[i][k] = syns[k].weight;
        this.adjDelays[i][k] = syns[k].delay;
      }
    }

    this.rebuildCSR(mem, count);
    return count;
  }
}
