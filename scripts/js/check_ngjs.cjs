// Harness for tests/test_docs_playground.py: runs functions of the documentation's JavaScript port
// (docs/_static/ngjs/ng-core.js) and prints their results as JSON (or, for "kernel", the spike raster as lines
// "tick neuron", like scripts/js/check_kernel_equivalence.mjs).
// Usage: node check_ngjs.cjs <command> <input.json> [ticks]
//   kernel  net.json ticks   lif_int raster of a network JSON (seed 12345, as the Python reference)
//   genes   spec.json        from_unit / to_unit of {genome, genes, u}
//   seeds   spec.json        seeds_of for {island, generation, n}
//   coact   spec.json        coactivity and competitive losers for {spikes, pre, post, delay, window, fraction}
//   evolve  spec.json        a short evolution {island, generations, lambda}: fitness history and determinism
"use strict";
const fs = require("fs");
const path = require("path");
const NG = require(path.join(__dirname, "..", "..", "docs", "_static", "ngjs", "ng-core.js"));

const [cmd, file, ticksArg] = process.argv.slice(2);
const spec = JSON.parse(fs.readFileSync(file, "utf8"));

if (cmd === "kernel") {
  const N = spec.neurons.length;
  const syn = spec.synapses.filter((s) => s.pre < N && s.post < N);
  const csr = NG.buildCSR(N, syn.map((s) => s.pre), syn.map((s) => s.post), syn.map((s) => s.weight), syn.map((s) => s.delay));
  const cells = {
    threshold: spec.neurons.map((n) => n.threshold ?? 1024), shiftV: spec.neurons.map((n) => n.shiftV ?? 5),
    shiftS: spec.neurons.map((n) => n.shiftS ?? 4), mode: spec.neurons.map((n) => n.mode ?? 0),
    poissonHz: spec.neurons.map((n) => n.poissonHz ?? 25), burstPeriod: spec.neurons.map((n) => n.burstPeriod ?? 200),
    burstDuty: spec.neurons.map((n) => n.burstDuty ?? 24), refractory: spec.neurons.map((n) => n.refractory ?? 0),
  };
  const T = Number(ticksArg);
  const raster = NG.simulate(cells, csr, T, 12345);
  const out = [];
  for (let t = 0; t < T; t++) for (let i = 0; i < N; i++) if (raster[t * N + i]) out.push(`${t} ${i}`);
  console.log(out.join("\n"));
} else if (cmd === "genes") {
  const genes = spec.genes.map(([p, lo, hi]) => ({ path: p, lo: lo, hi: hi }));
  const g = NG.fromUnit(spec.genome, genes, spec.u);
  console.log(JSON.stringify({ genome: g, unit: NG.toUnit(g, genes) }));
} else if (cmd === "seeds") {
  console.log(JSON.stringify(NG.seedsOf(spec.island, spec.generation, spec.n)));
} else if (cmd === "coact") {
  const T = spec.spikes.length, N = spec.spikes[0].length;
  const flat = new Uint8Array(T * N);
  spec.spikes.forEach((row, t) => row.forEach((v, i) => { flat[t * N + i] = v; }));
  const score = NG.coactivity(flat, T, N, spec.pre, spec.post, spec.delay, spec.window);
  const lose = NG.competitiveLosers(score, spec.post, flat, T, N, spec.fraction, 1);
  console.log(JSON.stringify({ score: Array.from(score), lose: Array.from(lose) }));
} else if (cmd === "evolve") {
  const D = NG.CortexMapDemo;
  const run = () => {
    const E = NG.Evolution({ island: spec.island, lambda: spec.lambda });
    for (let g = 0; g < spec.generations; g++) E.step();
    return E.history.map((h) => ({ best: h.best, validation: h.validation, u: h.u }));
  };
  const a = run(), b = run();
  const founder = D.assess(D.FOUNDER, [1, 2, 3]);
  console.log(JSON.stringify({ history: a, identical: JSON.stringify(a) === JSON.stringify(b), founder: founder.fitness }));
} else {
  throw new Error("unknown command " + cmd);
}
