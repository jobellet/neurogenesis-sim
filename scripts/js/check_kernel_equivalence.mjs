// Runs the browser kernel (src/sim/kernel.ts, compiled to build/kernel.js) on a network JSON and prints the spike raster
// as lines "tick neuron" (for comparison with neurogenesis/spiking/reference.py). Usage: node check_kernel_equivalence.mjs net.json ticks
import { readFileSync } from 'fs';
import { stepKernel, DEFAULT_SEED } from './build/kernel.js';
const [file, ticksArg] = process.argv.slice(2);
const net = JSON.parse(readFileSync(file, 'utf8'));
const N = net.neurons.length;
const syn = net.synapses.filter(s => s.pre < N && s.post < N);
const byPre = Array.from({ length: N }, () => []);
for (const s of syn) byPre[s.pre].push(s);
const rowPtr = new Uint32Array(N + 1), colIdx = new Uint32Array(syn.length), weights = new Int16Array(syn.length), delays = new Uint8Array(syn.length);
let k = 0;
for (let i = 0; i < N; i++) { rowPtr[i] = k; for (const s of byPre[i]) { colIdx[k] = s.post; weights[k] = s.weight; delays[k] = s.delay; k++; } }
rowPtr[N] = k;
const mem = {
  vMem: new Int16Array(N), iSyn: new Int32Array(N), shiftV: Uint8Array.from(net.neurons.map(n => n.shiftV ?? 5)),
  shiftS: Uint8Array.from(net.neurons.map(n => n.shiftS ?? 4)), neuronMode: Uint8Array.from(net.neurons.map(n => n.mode ?? 0)),
  poissonThresh: Uint32Array.from(net.neurons.map(n => Math.min(4294967295, Math.floor(((n.poissonHz ?? 25) / 1000) * 4294967296)))),
  burstPeriod: Uint16Array.from(net.neurons.map(n => n.burstPeriod ?? 200)), burstDuty: Uint16Array.from(net.neurons.map(n => n.burstDuty ?? 24)),
  burstPhase: new Uint16Array(N), spikeBitfield: new Uint32Array(N), visualFlash: new Uint8Array(N),
  refractory: Uint8Array.from(net.neurons.map(n => n.refractory ?? 0)), refrCount: new Uint8Array(N),
  threshold: Int16Array.from(net.neurons.map(n => n.threshold ?? 1024)),
  rowPtr, colIdx, weights, delays,
};
let prng = DEFAULT_SEED;
const out = [];
for (let t = 0; t < Number(ticksArg); t++) {
  const before = Uint32Array.from(mem.spikeBitfield);
  [, prng] = stepKernel(mem, N, prng);
  for (let i = 0; i < N; i++) if (mem.spikeBitfield[i] & 1) out.push(`${t} ${i}`);
}
console.log(out.join('\n'));
