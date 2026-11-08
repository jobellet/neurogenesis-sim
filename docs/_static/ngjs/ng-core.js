/**
 * ng-core.js: a small, dependency-free JavaScript port of neurogenesis-sim functions, for the documentation site.
 *
 * What is ported, and how closely (the Python source is named for each part):
 *   - lif_int kernel ........ exact port of neurogenesis/spiking/reference.py (IntegerSNNSimulator.step): same integer
 *                             arithmetic, same xorshift32 Poisson draws, same multi-word spike history. Identical
 *                             spikes are checked against Python in tests/test_docs_playground.py.
 *   - gene coding ........... neurogenesis/genome/genes.py (get_gene, set_gene, from_unit, to_unit).
 *   - seeds_of .............. neurogenesis/evolution/islands.py (development seeds of a generation).
 *   - coactivity ............ neurogenesis/stages/refinement.py (pre spike after the delay, then a post spike within
 *                             `window` ticks).
 *   - competitive_elimination neurogenesis/stages/competition.py with `remove: true`.
 *   - stages ................ simplified 2D versions (x = tangential axis, z = depth from the ventricle) of
 *                             seed_cells (C1), cell_cycle_clock (C14), proliferate (C2), migrate (C4), mosaic (C5) and
 *                             grow_axons with the `lamina` target rule (C8). They follow the Python formulas; random
 *                             numbers come from one stream per stage (roadmap section 2.1), but the generator is not
 *                             NumPy's PCG64, so a JavaScript network is not the network Python grows from the same seed.
 *
 * On top of these, `CortexMapDemo` is the toy problem of the front page: grow a cortex-like sheet whose spikes report
 * where a thalamic input was stimulated, and evolve its genome by keeping the best offspring of every generation.
 *
 * Usage: in a browser the script defines `window.NGJS`; in Node, `require("./ng-core.js")`.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.NGJS = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function now() {
    return typeof performance !== "undefined" && performance.now ? performance.now() : Date.now();
  }

  // ------------------------------------------------------------------------------------------------------------
  // Random streams: one independent, seeded stream per stage (no global random state).
  // ------------------------------------------------------------------------------------------------------------

  /** FNV-1a hash of a string (32 bit). */
  function hashString(s) {
    let h = 0x811c9dc5;
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 0x01000193);
    }
    return h >>> 0;
  }

  /** MurmurHash3 finaliser: a well-mixed 32-bit value from a 32-bit value. */
  function fmix32(h) {
    h ^= h >>> 16;
    h = Math.imul(h, 0x85ebca6b);
    h ^= h >>> 13;
    h = Math.imul(h, 0xc2b2ae35);
    h ^= h >>> 16;
    return h >>> 0;
  }

  /**
   * Random stream seeded from (seed, name), sfc32 generator (Doty-Humphrey's Small Fast Counter).
   * random() in [0, 1), normal() (standard normal, Box-Muller), int(n) in [0, n).
   */
  function Stream(seed, name) {
    let a = fmix32((seed >>> 0) ^ 0x9e3779b9);
    let b = fmix32(hashString(String(name || "")) ^ 0x243f6a88);
    let c = fmix32(a ^ b ^ 0xb7e15162);
    let d = 1;
    function next() {
      const t = (((a + b) | 0) + d) | 0;
      d = (d + 1) | 0;
      a = b ^ (b >>> 9);
      b = (c + (c << 3)) | 0;
      c = (c << 21) | (c >>> 11);
      c = (c + t) | 0;
      return (t >>> 0) / 4294967296;
    }
    for (let i = 0; i < 12; i++) next();
    return {
      random: next,
      normal: function () {
        let u = next();
        while (u <= 1e-12) u = next();
        return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * next());
      },
      int: function (n) {
        return Math.floor(next() * n);
      },
    };
  }

  // ------------------------------------------------------------------------------------------------------------
  // Gene coding (neurogenesis/genome/genes.py)
  // ------------------------------------------------------------------------------------------------------------

  const INTEGER_ROOTS = ["count", "excitability"];

  function deepClone(x) {
    return JSON.parse(JSON.stringify(x));
  }

  function missing(path, key) {
    return new Error("gene path " + JSON.stringify(path) + ": no key " + JSON.stringify(key));
  }

  function getGene(genome, path) {
    let node = genome;
    for (const p of path) {
      if (node === null || typeof node !== "object" || !(p in node)) throw missing(path, p);
      node = node[p];
    }
    return Number(node);
  }

  /** Set a gene in place; a path that does not exist throws (a misspelled gene must not become a dead gene). */
  function setGene(genome, path, v) {
    let node = genome;
    for (let k = 0; k < path.length - 1; k++) {
      if (node === null || typeof node !== "object" || !(path[k] in node)) throw missing(path, path[k]);
      node = node[path[k]];
    }
    const last = path[path.length - 1];
    if (node === null || typeof node !== "object" || !(last in node)) throw missing(path, last);
    node[last] = v;
  }

  function clip01(x) {
    return x < 0 ? 0 : x > 1 ? 1 : x;
  }

  /** Copy of `genome` with gene k set to lo_k + clip(u_k, 0, 1) (hi_k - lo_k); genes are {path, lo, hi}. */
  function fromUnit(genome, genes, u, integerRoots) {
    const roots = integerRoots || INTEGER_ROOTS;
    const g = deepClone(genome);
    genes.forEach(function (gene, k) {
      let v = gene.lo + clip01(u[k]) * (gene.hi - gene.lo);
      if (roots.indexOf(gene.path[0]) >= 0) v = Math.round(v);
      setGene(g, gene.path, v);
    });
    return g;
  }

  /** Gene values of a genome scaled to [0, 1] (clipped). */
  function toUnit(genome, genes) {
    return genes.map(function (gene) {
      return clip01((getGene(genome, gene.path) - gene.lo) / (gene.hi - gene.lo));
    });
  }

  /** Development seeds of one generation (neurogenesis.evolution.islands.seeds_of). */
  function seedsOf(island, generation, n) {
    const out = [];
    for (let k = 0; k < n; k++) out.push(100000 * (island + 1) + 10 * generation + k);
    return out;
  }

  function sigmoid(x) {
    return 1 / (1 + Math.exp(-x));
  }

  // ------------------------------------------------------------------------------------------------------------
  // lif_int kernel (neurogenesis/spiking/reference.py), exact integer port
  // ------------------------------------------------------------------------------------------------------------

  /** uint32 Poisson threshold of a rate in Hz (one tick = 1 ms): min(2^32 - 1, int(hz / 1000 * 2^32)). */
  function poissonThreshold(hz) {
    return Math.min(4294967295, Math.floor((hz / 1000) * 4294967296)) >>> 0;
  }

  /** Compressed sparse rows of synapses grouped by presynaptic neuron, in input order within a row. */
  function buildCSR(N, pre, post, weight, delay) {
    const E = pre.length;
    const rowPtr = new Uint32Array(N + 1);
    for (let s = 0; s < E; s++) rowPtr[pre[s] + 1]++;
    for (let i = 0; i < N; i++) rowPtr[i + 1] += rowPtr[i];
    const fill = Uint32Array.from(rowPtr.subarray(0, N));
    const colIdx = new Uint32Array(E), weights = new Int16Array(E), delays = new Uint8Array(E);
    let maxDelay = 0;
    for (let s = 0; s < E; s++) {
      const k = fill[pre[s]]++;
      colIdx[k] = post[s];
      weights[k] = weight[s];
      delays[k] = delay[s];
      if (delay[s] > maxDelay) maxDelay = delay[s];
    }
    return { rowPtr: rowPtr, colIdx: colIdx, weights: weights, delays: delays,
      W: Math.max(1, Math.floor((maxDelay + 32) / 32)) };
  }

  /**
   * Integer LIF simulator, bit for bit the Python reference.
   * cells: {threshold, shiftV, shiftS, mode, poissonHz | poissonThresh, burstPeriod, burstDuty, refractory}, arrays
   * of length N; csr: from buildCSR; seed: xorshift32 seed (the Python default is 12345).
   * step() advances one tick (1 ms) and returns the number of spikes; `spiked` holds this tick's spikes.
   * `poissonThresh` may be changed between ticks to drive inputs (the kernel reads it every tick).
   */
  function Simulator(cells, csr, seed) {
    const N = cells.threshold.length;
    const fill = function (v) {
      return new Array(N).fill(v);
    };
    const s = {
      N: N, W: csr.W, tick: 0, rng: (seed === undefined ? 12345 : seed) >>> 0, csr: csr,
      vMem: new Int16Array(N), iSyn: new Int32Array(N), spikeBitfield: new Uint32Array(N * csr.W),
      burstPhase: new Uint16Array(N), refrCount: new Uint8Array(N), spiked: new Uint8Array(N),
      threshold: Int16Array.from(cells.threshold), shiftV: Uint8Array.from(cells.shiftV),
      shiftS: Uint8Array.from(cells.shiftS), mode: Uint8Array.from(cells.mode),
      burstPeriod: Uint16Array.from(cells.burstPeriod || fill(200)), burstDuty: Uint16Array.from(cells.burstDuty || fill(24)),
      refractory: Uint8Array.from(cells.refractory),
      poissonThresh: cells.poissonThresh ? Uint32Array.from(cells.poissonThresh)
        : Uint32Array.from((cells.poissonHz || fill(0)).map(poissonThreshold)),
    };
    s.step = function () {
      return stepKernel(s);
    };
    return s;
  }

  function stepKernel(s) {
    const N = s.N, W = s.W, csr = s.csr;
    let rng = s.rng >>> 0;
    let count = 0;
    // 1. Leak, synaptic decay, spontaneous drives, threshold, refractory period, spike history
    for (let i = 0; i < N; i++) {
      let v = s.vMem[i];
      const kv = s.shiftV[i];
      if (v > 0) v -= Math.max(1, v >> kv);
      else if (v < 0) v -= Math.min(-1, v >> kv);
      let isyn = s.iSyn[i];
      const ks = s.shiftS[i];
      if (isyn > 0) isyn -= Math.max(1, isyn >> ks);
      else if (isyn < 0) isyn -= Math.min(-1, isyn >> ks);
      s.iSyn[i] = isyn;
      v += isyn >> 2;
      if (v > 2048) v = 2048;
      else if (v < -2048) v = -2048;
      const m = s.mode[i];
      if (m === 1) {
        rng ^= rng << 13;
        rng ^= rng >>> 17;
        rng ^= rng << 5;
        rng >>>= 0;
        if (rng < s.poissonThresh[i]) v = s.threshold[i];
      } else if (m === 2) {
        const period = s.burstPeriod[i] || 200;
        const duty = s.burstDuty[i] || 24;
        const phase = (s.burstPhase[i] + 1) % period;
        s.burstPhase[i] = phase;
        if (phase < duty && (phase & 3) === 0) v = s.threshold[i];
      }
      let spiked = v >= s.threshold[i] ? 1 : 0;
      if (s.refrCount[i] > 0) {
        s.refrCount[i] -= 1; // absolute refractory period: no spike, v held at the reset value
        spiked = 0;
        v = -256;
      }
      if (spiked) {
        s.refrCount[i] = s.refractory[i];
        s.vMem[i] = -256;
        count++;
      } else {
        s.vMem[i] = v;
      }
      s.spiked[i] = spiked;
      if (W === 1) {
        s.spikeBitfield[i] = ((s.spikeBitfield[i] << 1) | spiked) >>> 0;
      } else {
        const base = i * W;
        for (let w = W - 1; w > 0; w--) {
          s.spikeBitfield[base + w] = ((s.spikeBitfield[base + w] << 1) | (s.spikeBitfield[base + w - 1] >>> 31)) >>> 0;
        }
        s.spikeBitfield[base] = ((s.spikeBitfield[base] << 1) | spiked) >>> 0;
      }
    }
    // 2. Synaptic propagation through the CSR rows, delays read from the spike history
    for (let i = 0; i < N; i++) {
      const start = csr.rowPtr[i], end = csr.rowPtr[i + 1];
      if (start === end) continue;
      if (W === 1) {
        const bf = s.spikeBitfield[i];
        if (bf === 0) continue;
        for (let k = start; k < end; k++) {
          if ((bf >>> csr.delays[k]) & 1) s.iSyn[csr.colIdx[k]] += csr.weights[k];
        }
      } else {
        const base = i * W;
        let any = false;
        for (let w = 0; w < W; w++) {
          if (s.spikeBitfield[base + w] !== 0) {
            any = true;
            break;
          }
        }
        if (!any) continue;
        for (let k = start; k < end; k++) {
          const d = csr.delays[k], w = d >>> 5, bit = d & 31;
          if (w < W && ((s.spikeBitfield[base + w] >>> bit) & 1)) s.iSyn[csr.colIdx[k]] += csr.weights[k];
        }
      }
    }
    s.rng = rng >>> 0;
    s.tick++;
    return count;
  }

  /** (ticks x N) Uint8Array spike raster; drive(t, sim) may change sim.poissonThresh before each tick. */
  function simulate(cells, csr, ticks, seed, drive) {
    const sim = Simulator(cells, csr, seed);
    const N = sim.N;
    const raster = new Uint8Array(ticks * N);
    for (let t = 0; t < ticks; t++) {
      if (drive) drive(t, sim);
      sim.step();
      raster.set(sim.spiked, t * N);
    }
    return raster;
  }

  /**
   * Per synapse: number of pre spikes, arriving after `delay` ticks, followed by a post spike within `window` ticks
   * (arrival tick included) (neurogenesis.stages.refinement.coactivity). spikes: (T x N) Uint8Array.
   */
  function coactivity(spikes, T, N, pre, post, delay, window) {
    const E = pre.length;
    const out = new Int32Array(E);
    const win = Math.max(1, window | 0);
    const c = new Int32Array((T + 1) * N); // c[t N + i]: spikes of cell i in ticks [0, t)
    for (let t = 0; t < T; t++) {
      for (let i = 0; i < N; i++) c[(t + 1) * N + i] = c[t * N + i] + spikes[t * N + i];
    }
    for (let s = 0; s < E; s++) {
      const p = pre[s], q = post[s], d = delay[s];
      let n = 0;
      for (let t = d; t < T; t++) {
        if (!spikes[(t - d) * N + p]) continue;
        const hi = Math.min(t + win, T);
        if (c[hi * N + q] - c[t * N + q] > 0) n++;
      }
      out[s] = n;
    }
    return out;
  }

  /**
   * competitive_elimination (C22) with `remove`: an input loses when its target spiked at least `minTargetSpikes`
   * times, the best input onto that target scored > 0, and its own score is below `fraction` x that best score
   * (Willshaw 1981, Proc R Soc Lond B; Balice-Gordon & Lichtman 1994, Nature). Returns a Uint8Array of losers.
   */
  function competitiveLosers(score, post, spikes, T, N, fraction, minTargetSpikes) {
    const E = score.length;
    const lose = new Uint8Array(E);
    if (!(fraction > 0)) return lose;
    const best = new Float64Array(N);
    for (let s = 0; s < E; s++) if (score[s] > best[post[s]]) best[post[s]] = score[s];
    const fired = new Int32Array(N);
    for (let t = 0; t < T; t++) for (let i = 0; i < N; i++) fired[i] += spikes[t * N + i];
    for (let s = 0; s < E; s++) {
      const q = post[s];
      if (fired[q] >= minTargetSpikes && best[q] > 0 && score[s] < fraction * best[q]) lose[s] = 1;
    }
    return lose;
  }

  // ------------------------------------------------------------------------------------------------------------
  // A 2D tissue (struct of arrays) and simplified stages
  // ------------------------------------------------------------------------------------------------------------

  function Tissue() {
    return { x: [], z: [], region: [], cycling: [], generation: [], parent: [], born: [] };
  }

  function addCell(t, x, z, region, cycling, generation, parent, born) {
    t.x.push(x);
    t.z.push(z);
    t.region.push(region);
    t.cycling.push(cycling);
    t.generation.push(generation);
    t.parent.push(parent);
    t.born.push(born);
    return t.x.length - 1;
  }

  /** seed_cells (C1): cells at explicit `points` or N cells at `position`, plus Gaussian `jitter` per axis. */
  function seedCells(t, p, rng) {
    const n = p.points ? p.points.length : p.N;
    for (let i = 0; i < n; i++) {
      const base = p.points ? p.points[i] : p.position;
      const jx = p.jitter ? p.jitter[0] * rng.normal() : 0;
      const jz = p.jitter ? p.jitter[1] * rng.normal() : 0;
      addCell(t, base[0] + jx, base[1] + jz, p.region, true, 0, -1, 0);
    }
  }

  /**
   * cell_cycle_clock (C14): every cycling cell of `region` enters a new cycle (generation + 1) and leaves the cycle
   * with probability Q = min(1, k generation^a) (Takahashi, Nowakowski & Caviness 1995, J Neurosci). Returns the
   * mask of the cells that entered this cycle: they all divide in the following proliferate, and a leaving cell
   * gives two postmitotic daughters.
   */
  function cellCycleClock(t, p, rng) {
    const n = t.x.length;
    const entered = new Uint8Array(n);
    for (let i = 0; i < n; i++) {
      if (!t.cycling[i] || t.region[i] !== p.region) continue;
      entered[i] = 1;
      t.generation[i] += 1;
      if (rng.random() < Math.min(1, Math.max(0, p.k * Math.pow(t.generation[i], p.a)))) t.cycling[i] = false;
    }
    return entered;
  }

  /**
   * proliferate (C2): each selected cell divides with probability `prob`; the mother row stays, the daughter is
   * appended at a Gaussian `jitter` per axis and copies region, cycling and generation. `max_cells` bounds the number
   * of cells. `mask` (from cellCycleClock) selects the dividing cells; default: the cycling cells of `region`.
   */
  function proliferate(t, p, rng, mask) {
    const n = t.x.length;
    const div = [];
    for (let i = 0; i < n; i++) {
      const may = mask ? mask[i] : t.cycling[i] && t.region[i] === p.region;
      if (rng.random() < p.prob && may) div.push(i);
    }
    const room = p.max_cells === undefined ? div.length : Math.max(0, p.max_cells - n);
    const chosen = div.slice(0, room);
    for (const i of chosen) {
      const dx = p.jitter[0] * rng.normal(), dz = p.jitter[1] * rng.normal();
      if (!mask) t.generation[i] += 1;
      addCell(t, t.x[i] + dx, t.z[i] + dz, t.region[i], t.cycling[i], t.generation[i], i, p.stage);
    }
    return chosen.length;
  }

  /**
   * migrate (C4), deterministic: for `steps` sub-steps each listed cell moves by speed[k] along `direction`; a step
   * that would enter the stop zone (z > stop_z, the `stop_field`) or leave [x_min, x_max] (the `boundary`) is
   * refused. Returns the positions [[x, z] per cell] after every sub-step, for the animation.
   */
  function migrate(t, p, cells, speed) {
    const snap = function () {
      return cells.map(function (i) {
        return [t.x[i], t.z[i]];
      });
    };
    const path = [snap()];
    for (let s = 0; s < p.steps; s++) {
      cells.forEach(function (i, k) {
        const nx = t.x[i] + p.direction[0] * speed[k];
        const nz = t.z[i] + p.direction[1] * speed[k];
        if (nz > p.stop_z || nx < p.x_min || nx > p.x_max) return;
        t.x[i] = nx;
        t.z[i] = nz;
      });
      path.push(snap());
    }
    return path;
  }

  /**
   * mosaic (C5): homotypic exclusion. For `steps` iterations, cells closer than `radius` move apart by `rate` x half
   * their overlap, plus Gaussian motility `jitter` (Galli-Resta et al. 1997, J Neurosci); positions stay in the box
   * [x_min, x_max] x [z_min, z_max]. Dense pairs: fine for the few hundred cells of the demo.
   */
  function mosaic(t, p, cells, rng) {
    const n = cells.length;
    for (let s = 0; s < p.steps; s++) {
      const mx = new Float64Array(n), mz = new Float64Array(n);
      for (let a = 0; a < n; a++) {
        for (let b = a + 1; b < n; b++) {
          const i = cells[a], j = cells[b];
          const dx = t.x[i] - t.x[j], dz = t.z[i] - t.z[j];
          const d = Math.sqrt(dx * dx + dz * dz);
          if (d >= p.radius || d < 1e-9) continue;
          const push = (0.5 * p.rate * (p.radius - d)) / d;
          mx[a] += push * dx;
          mz[a] += push * dz;
          mx[b] -= push * dx;
          mz[b] -= push * dz;
        }
      }
      for (let a = 0; a < n; a++) {
        const i = cells[a];
        t.x[i] = Math.min(p.x_max, Math.max(p.x_min, t.x[i] + mx[a] + p.jitter * rng.normal()));
        t.z[i] = Math.min(p.z_max, Math.max(p.z_min, t.z[i] + mz[a] + p.jitter * rng.normal()));
      }
    }
  }

  /**
   * grow_axons (C8) between two groups of cells {ids, x, z (local [0, 1]), ax, az (absolute), inh}:
   *   target_a = (sigmoid(4 B (x_a - 1/2) + c), lamina)  [the `lamina` rule], or the source's own position (topographic)
   *   p_ab = p0 exp(-(x_b - tx_a)^2 / 2 sigma^2 - (z_b - tz_a)^2 / 2 sigma_z^2), one Bernoulli draw per pair;
   *   weight = w (1 or -inh) U(0.9, 1.1), rounded and clipped to [-wc, wc]; delay = round(distance / velocity) in
   *   [1, 255]. sigma_z defaults to sigma (the Python stage uses one sigma). Dense pairs (demo sizes only).
   * Returns {pre, post, weight, delay, tx}: synapses (cell ids) and the target x of every source cell.
   */
  function growAxons(src, dst, g, rng) {
    const out = { pre: [], post: [], weight: [], delay: [], tx: [] };
    const s2 = 2 * g.sigma * g.sigma;
    const s2z = g.sigma_z ? 2 * g.sigma_z * g.sigma_z : s2;
    for (let a = 0; a < src.x.length; a++) {
      const tx = g.topographic ? src.x[a] : sigmoid(4 * g.B * (src.x[a] - 0.5) + (g.c || 0));
      const tz = g.topographic ? src.z[a] : g.lamina;
      out.tx.push(tx);
      for (let b = 0; b < dst.x.length; b++) {
        const dx = dst.x[b] - tx, dz = dst.z[b] - tz;
        const p = src.ids[a] === dst.ids[b] ? 0 : g.p0 * Math.exp(-(dx * dx) / s2 - (dz * dz) / s2z);
        if (rng.random() >= p) continue;
        const w = g.w * (src.inh[a] ? -1 : 1) * (0.9 + 0.2 * rng.random());
        const ax = src.ax[a] - dst.ax[b], az = src.az[a] - dst.az[b];
        out.pre.push(src.ids[a]);
        out.post.push(dst.ids[b]);
        out.weight.push(Math.max(-g.wc, Math.min(g.wc, Math.round(w))));
        out.delay.push(Math.max(1, Math.min(255, Math.round(Math.sqrt(ax * ax + az * az) / g.velocity))));
      }
    }
    return out;
  }

  // ------------------------------------------------------------------------------------------------------------
  // Front-page toy problem: a topographic sensory map grown and evolved in the browser
  // ------------------------------------------------------------------------------------------------------------

  /** Depth bands of the slice (z = 0 at the ventricle, 1 at the pia). Labels for drawing; stages read numbers. */
  const ZONES = [
    { key: "VZ", label: "VZ", z0: 0.0, z1: 0.08 },
    { key: "IZ", label: "SVZ/IZ", z0: 0.08, z1: 0.3 },
    { key: "SP", label: "SP", z0: 0.3, z1: 0.36 },
    { key: "L6", label: "L6", z0: 0.36, z1: 0.5 },
    { key: "L5", label: "L5", z0: 0.5, z1: 0.6 },
    { key: "L4", label: "L4", z0: 0.6, z1: 0.72 },
    { key: "L23", label: "L2/3", z0: 0.72, z1: 0.9 },
    { key: "L1", label: "L1", z0: 0.9, z1: 1.0 },
  ];
  const L4_DEPTH = 0.66;

  /** Genes, in schedule order: path into the genome, bounds, the stage they act in, and how to show them. */
  const GENES = [
    { path: ["cycle", "k"], lo: 0.005, hi: 0.4, stage: "neurogenesis", label: "Cycle exit k", fmt: 3,
      doc: "cell_cycle_clock: exit probability Q = min(1, k gen^1.97). Low k: more self-renewing divisions, so more and later-born neurons." },
    { path: ["mge", "prob"], lo: 0.0, hi: 1.0, stage: "fate", label: "MGE divisions", fmt: 2,
      doc: "proliferate in the medial ganglionic eminence: division probability per round, so the number of GABAergic interneurons." },
    { path: ["migrate", "speed"], lo: 0.0, hi: 0.05, stage: "migration", label: "Radial speed", fmt: 3,
      doc: "migrate (radial, 20 sub-steps): base speed of glutamatergic neurons along radial glia; sets their final depth." },
    { path: ["migrate", "inside_out"], lo: -0.012, hi: 0.012, stage: "migration", label: "Birth-date gain", fmt: 4,
      doc: "migrate: extra speed per birth cycle. > 0: later-born neurons settle more superficially (inside-out)." },
    { path: ["mge", "speed"], lo: 0.0, hi: 0.06, stage: "migration", label: "Tangential speed", fmt: 3,
      doc: "migrate (tangential, 20 sub-steps): how far interneurons travel from the MGE into the cortex." },
    { path: ["axon", "B"], lo: -1.0, hi: 3.0, stage: "axons", label: "Gradient gain B", fmt: 2,
      doc: "grow_axons: target x = sigmoid(4 B (x_thalamus - 1/2)). Receptor-gradient gain: 0 = no map, < 0 = inverted map." },
    { path: ["axon", "sigma"], lo: 0.02, hi: 0.25, stage: "axons", label: "Arbor spread σ", fmt: 3,
      doc: "grow_axons: p = p0 exp(-d^2 / 2 sigma^2) around the target point in L4 (terminal arbor size)." },
    { path: ["refine", "fraction"], lo: 0.0, hi: 1.0, stage: "refinement", label: "Competition", fmt: 2,
      doc: "competitive_elimination: during spontaneous waves, an input scoring below this fraction of the best input onto the same cell is removed." },
    { path: ["syn", "w"], lo: 20, hi: 500, stage: "activity", label: "Excitatory weight", fmt: 0,
      doc: "Thalamocortical and pyramidal -> interneuron weight (integer kernel units; the threshold is 1024)." },
    { path: ["syn", "w_inh"], lo: 0, hi: 1500, stage: "activity", label: "Inhibitory weight", fmt: 0,
      doc: "Interneuron -> pyramidal weight magnitude (feedforward inhibition)." },
  ];

  /** Founding genome: a viable but untuned development (no map: B = 0; most neurons settle below L4). */
  const FOUNDER = {
    cycle: { k: 0.1 },
    mge: { prob: 0.3, speed: 0.025 },
    migrate: { speed: 0.022, inside_out: 0.006 },
    axon: { B: 0.0, sigma: 0.2 },
    refine: { fraction: 0.0 },
    syn: { w: 140, w_inh: 100 },
  };

  /** The schedule, as the stages of the animation. */
  const STAGES = [
    { key: "neurogenesis", label: "Neurogenesis", ops: "seed_cells → cell_cycle_clock → proliferate" },
    { key: "fate", label: "Fate", ops: "proliferate (MGE) → GABAergic fate" },
    { key: "migration", label: "Migration", ops: "migrate (radial, tangential) → mosaic" },
    { key: "axons", label: "Axon guidance", ops: "grow_axons (chemoaffinity, lamina)" },
    { key: "refinement", label: "Refinement", ops: "spontaneous waves → competitive_elimination" },
    { key: "activity", label: "Activity", ops: "simulate (lif_int) → decode position" },
  ];

  const CONST = {
    // neurogenesis
    progenitors: 12, cycles: 6, a: 1.97, clonalJitter: 0.02, maxCells: 420, vzDepth: 0.035,
    // interneurons
    mgeSeeds: 4, mgeRounds: 4, mgeX: -0.1, mgeZ: 0.2,
    // migration
    migrateSteps: 20, mzDepth: 0.9,
    // thalamus (fixed scaffold) and wiring
    thalamus: 32, thalamusDepth: -0.55, p0: 0.5, laminaSigma: 0.06, wc: 512, vThalamic: 0.12, vCortex: 0.05,
    ieSigma: 0.12, ieP0: 0.8, wcInh: 2000, eiSigma: 0.08, eiP0: 0.3,
    // refinement: spontaneous waves sweeping the thalamus
    waveTicks: 80, waveSweeps: 2, waveRate: 300, waveWidth: 0.06, window: 5,
    // evaluation: a sequence of stimuli, read out in a window after each onset
    stimuli: [0.15, 0.267, 0.383, 0.5, 0.617, 0.733, 0.85], stimRate: 500, stimWidth: 0.05,
    period: 40, stimOn: 20, readoutLag: 10, readoutTicks: 20, trials: 1,
    // fitness
    accuracyScale: 0.08, responseSpikes: 5, energyCells: 1000, energySynapses: 2500, energySpikes: 400,
  };

  /**
   * Grow one individual from a genome and a development seed. Returns {net, record, tissue}: the network (cells and
   * synapses in kernel order: thalamus, pyramidal cells, interneurons) and a record of every stage for the animation.
   */
  function develop(genome, seed) {
    const G = genome;
    const t = Tissue();
    const rec = { seed: seed };

    // 1. Neurogenesis: radial glia in the VZ; cell-cycle clock, then division, for 6 cycles.
    const pts = [];
    for (let i = 0; i < CONST.progenitors; i++) pts.push([(i + 0.5) / CONST.progenitors, CONST.vzDepth]);
    seedCells(t, { points: pts, region: 0, jitter: [0.012, 0.0] }, Stream(seed, "seed_cells"));
    const divisions = []; // [cycle, mother, daughter]
    for (let c = 1; c <= CONST.cycles; c++) {
      const entered = cellCycleClock(t, { region: 0, k: G.cycle.k, a: CONST.a }, Stream(seed, "cell_cycle_clock#" + c));
      const n0 = t.x.length;
      proliferate(t, { prob: 1.0, jitter: [CONST.clonalJitter, 0.0], max_cells: CONST.maxCells, stage: c },
        Stream(seed, "proliferate#" + c), entered);
      for (let i = n0; i < t.x.length; i++) divisions.push([c, t.parent[i], i]);
    }
    for (let i = 0; i < t.x.length; i++) t.x[i] = Math.min(0.995, Math.max(0.005, t.x[i]));
    const nCortex = t.x.length;
    rec.vz = { x: t.x.slice(), divisions: divisions };

    // 2. Fate: MGE progenitors (ventral telencephalon) make GABAergic interneurons (Anderson et al. 1997, Science).
    seedCells(t, { N: CONST.mgeSeeds, position: [CONST.mgeX, CONST.mgeZ], region: 1, jitter: [0.015, 0.02] },
      Stream(seed, "seed_cells#mge"));
    const mgeDiv = [];
    for (let r = 1; r <= CONST.mgeRounds; r++) {
      const n0 = t.x.length;
      proliferate(t, { region: 1, prob: G.mge.prob, jitter: [0.012, 0.015], stage: r }, Stream(seed, "proliferate#mge" + r));
      for (let i = n0; i < t.x.length; i++) mgeDiv.push([r, t.parent[i], i]);
    }
    const mge = [];
    for (let i = nCortex; i < t.x.length; i++) {
      t.cycling[i] = false;
      t.z[i] = Math.min(0.28, Math.max(0.1, t.z[i]));
      mge.push(i);
    }
    rec.mge = { cells: mge.slice(), x: mge.map(function (i) { return t.x[i]; }),
      z: mge.map(function (i) { return t.z[i]; }), divisions: mgeDiv };

    // Pyramidal neurons: postmitotic cells of the cortical VZ; cells still cycling stay radial glia.
    const pyr = [], glia = [];
    for (let i = 0; i < nCortex; i++) (t.cycling[i] ? glia : pyr).push(i);
    rec.glia = glia;

    // 3. Migration. Radial (along radial glia): speed = s0 + s1 (birth cycle - 3.5); the marginal zone stops it.
    const speedE = pyr.map(function (i) {
      return Math.max(0, G.migrate.speed + G.migrate.inside_out * (t.generation[i] - 3.5));
    });
    const radial = migrate(t, { steps: CONST.migrateSteps, direction: [0, 1], stop_z: CONST.mzDepth, x_min: 0, x_max: 1 },
      pyr, speedE);
    // Tangential: each interneuron leaves the stream at its own point (speed x U(0.1, 1) from the stage stream),
    // disperses (mosaic with motility), then enters the cortical plate at the depth of nearby pyramidal cells
    // (projection neurons set interneuron laminar position: Lodato et al. 2011, Neuron).
    const rngI = Stream(seed, "migrate#tangential");
    const speedI = mge.map(function () { return G.mge.speed * (0.1 + 0.9 * rngI.random()); });
    const tangential = migrate(t, { steps: CONST.migrateSteps, direction: [1, 0], stop_z: 1, x_min: -0.2, x_max: 0.995 },
      mge, speedI);
    mosaic(t, { radius: 0.05, rate: 1, steps: 8, jitter: 0.012, x_min: -0.2, x_max: 0.995, z_min: 0.1, z_max: 0.3 },
      mge, Stream(seed, "mosaic#mge"));
    const dispersed = mge.map(function (i) { return [t.x[i], t.z[i]]; });
    const rngV = Stream(seed, "migrate#invade");
    for (const i of mge) {
      let best = -1, bd = Infinity;
      for (const j of pyr) {
        const d = Math.abs(t.x[j] - t.x[i]);
        if (d < bd) {
          bd = d;
          best = j;
        }
      }
      const zt = best >= 0 && t.x[i] > 0 ? t.z[best] : t.z[i];
      t.z[i] = Math.min(0.89, Math.max(0.1, zt + 0.03 * rngV.normal()));
    }
    rec.migration = { pyr: pyr, radial: radial, mge: mge, tangential: tangential, dispersed: dispersed };

    // Network cells in kernel order: thalamus (fixed scaffold), pyramidal cells, interneurons that reached the cortex.
    const inh = mge.filter(function (i) { return t.x[i] >= 0; });
    const NT = CONST.thalamus;
    const cells = { x: [], z: [], ax: [], az: [], kind: [], tissue: [], birth: [] };
    function push(x, z, ax, az, kind, ti, birth) {
      cells.x.push(x); cells.z.push(z); cells.ax.push(ax); cells.az.push(az);
      cells.kind.push(kind); cells.tissue.push(ti); cells.birth.push(birth);
    }
    for (let k = 0; k < NT; k++) push((k + 0.5) / NT, 0, (k + 0.5) / NT, CONST.thalamusDepth, 0, -1, 0);
    for (const i of pyr) push(t.x[i], t.z[i], t.x[i], t.z[i], 1, i, t.generation[i]);
    for (const i of inh) push(t.x[i], t.z[i], t.x[i], t.z[i], 2, i, 0);
    const N = cells.x.length;
    function group(kinds) {
      const g = { ids: [], x: [], z: [], ax: [], az: [], inh: [] };
      for (let i = 0; i < N; i++) {
        if (kinds.indexOf(cells.kind[i]) < 0) continue;
        g.ids.push(i); g.x.push(cells.x[i]); g.z.push(cells.z[i]); g.ax.push(cells.ax[i]); g.az.push(cells.az[i]);
        g.inh.push(cells.kind[i] === 2);
      }
      return g;
    }
    const TH = group([0]), PYR = group([1]), INH = group([2]), CTX = group([1, 2]);

    // 4. Axon guidance: thalamocortical chemoaffinity into L4 (lamina rule), local feedforward-inhibition circuit.
    const tc = growAxons(TH, CTX, { B: G.axon.B, c: 0, sigma: G.axon.sigma, sigma_z: CONST.laminaSigma, p0: CONST.p0,
      lamina: L4_DEPTH, w: G.syn.w, wc: CONST.wc, velocity: CONST.vThalamic }, Stream(seed, "grow_axons#tc"));
    const ie = growAxons(INH, PYR, { topographic: true, sigma: CONST.ieSigma, p0: CONST.ieP0, w: G.syn.w_inh,
      wc: CONST.wcInh, velocity: CONST.vCortex }, Stream(seed, "grow_axons#ie"));
    const ei = growAxons(PYR, INH, { topographic: true, sigma: CONST.eiSigma, p0: CONST.eiP0, w: G.syn.w, wc: CONST.wc,
      velocity: CONST.vCortex }, Stream(seed, "grow_axons#ei"));
    const grown = { pre: [], post: [], weight: [], delay: [], kind: [] };
    [tc, ie, ei].forEach(function (s, kind) {
      for (let k = 0; k < s.pre.length; k++) {
        grown.pre.push(s.pre[k]); grown.post.push(s.post[k]); grown.weight.push(s.weight[k]);
        grown.delay.push(s.delay[k]); grown.kind.push(kind);
      }
    });
    rec.axons = { tx: tc.tx };

    // Kernel parameters: pyramidal cells (regular spiking) and interneurons (fast spiking: shorter time constants).
    const kc = { threshold: [], shiftV: [], shiftS: [], mode: [], poissonHz: [], refractory: [] };
    for (let i = 0; i < N; i++) {
      const k = cells.kind[i];
      kc.threshold.push(k === 2 ? 900 : 1024);
      kc.shiftV.push(k === 2 ? 4 : 5);
      kc.shiftS.push(k === 2 ? 3 : 4);
      kc.mode.push(k === 0 ? 1 : 0);
      kc.poissonHz.push(0);
      kc.refractory.push(k === 1 ? 3 : 1);
    }

    // 5. Refinement: spontaneous waves sweep the thalamus (Katz & Shatz 1996, Science), then competitive
    //    elimination of thalamocortical inputs.
    const T = CONST.waveSweeps * CONST.waveTicks;
    const wave = simulate(kc, buildCSR(N, grown.pre, grown.post, grown.weight, grown.delay), T, (seed % 0xffffffff) + 1,
      waveDrive(TH.x));
    const tcIdx = [];
    for (let s = 0; s < grown.pre.length; s++) if (grown.kind[s] === 0) tcIdx.push(s);
    const tcPost = tcIdx.map(function (s) { return grown.post[s]; });
    const score = coactivity(wave, T, N, tcIdx.map(function (s) { return grown.pre[s]; }), tcPost,
      tcIdx.map(function (s) { return grown.delay[s]; }), CONST.window);
    const lose = competitiveLosers(score, tcPost, wave, T, N, G.refine.fraction, 1);
    const keep = new Uint8Array(grown.pre.length).fill(1);
    tcIdx.forEach(function (s, k) {
      if (lose[k]) keep[s] = 0;
    });
    const kept = { pre: [], post: [], weight: [], delay: [], kind: [] };
    for (let s = 0; s < grown.pre.length; s++) {
      if (!keep[s]) continue;
      kept.pre.push(grown.pre[s]); kept.post.push(grown.post[s]); kept.weight.push(grown.weight[s]);
      kept.delay.push(grown.delay[s]); kept.kind.push(grown.kind[s]);
    }
    rec.refinement = { keep: keep, wave: wave, ticks: T };

    const net = { N: N, NT: NT, cells: cells, kernel: kc, grown: grown, synapses: kept,
      nPyr: PYR.ids.length, nInh: INH.ids.length, nGlia: glia.length, nMGE: mge.length };
    net.csr = buildCSR(N, kept.pre, kept.post, kept.weight, kept.delay);
    return { net: net, record: rec, tissue: t };
  }

  /** Spontaneous waves: a Gaussian band of thalamic activity sweeping the sheet, alternating direction. */
  function waveDrive(xs) {
    return function (tick, sim) {
      const T = CONST.waveTicks;
      const ph = (tick % T) / T;
      const pos = Math.floor(tick / T) % 2 === 0 ? -0.1 + 1.2 * ph : 1.1 - 1.2 * ph;
      for (let k = 0; k < xs.length; k++) {
        const d = xs[k] - pos;
        sim.poissonThresh[k] = poissonThreshold(CONST.waveRate * Math.exp(-(d * d) / (2 * CONST.waveWidth * CONST.waveWidth)));
      }
    };
  }

  /** Thalamic Poisson rates (Hz) of a stimulus at position s (Gaussian spot of width stimWidth). */
  function stimulusRates(xs, s) {
    return xs.map(function (x) {
      const d = x - s;
      return CONST.stimRate * Math.exp(-(d * d) / (2 * CONST.stimWidth * CONST.stimWidth));
    });
  }

  /**
   * A stimulus sequence in one continuous simulation: stimulus positions[order[k]] is on during ticks
   * [k period, k period + on), then the thalamus is silent until the next onset.
   */
  function sequenceDrive(xs, positions, order, period, on) {
    return function (tick, sim) {
      const k = Math.floor(tick / period), ph = tick % period;
      if (ph !== 0 && ph !== on) return;
      const rates = ph === 0 && k < order.length ? stimulusRates(xs, positions[order[k]]) : null;
      for (let i = 0; i < xs.length; i++) sim.poissonThresh[i] = rates ? poissonThreshold(rates[i]) : 0;
    };
  }

  /** Presentation order of the n stimuli of a trial (a seeded shuffle). */
  function stimulusOrder(n, seed) {
    const rng = Stream(seed, "stimulus_order");
    const o = [];
    for (let i = 0; i < n; i++) o.push(i);
    for (let i = n - 1; i > 0; i--) {
      const j = rng.int(i + 1);
      const tmp = o[i];
      o[i] = o[j];
      o[j] = tmp;
    }
    return o;
  }

  /** Spike-weighted mean position of the cells (population vector); 1/2 when no cell fired. */
  function decodePosition(xs, counts) {
    let n = 0, sx = 0;
    for (let i = 0; i < xs.length; i++) {
      n += counts[i];
      sx += counts[i] * xs[i];
    }
    return n > 0 ? sx / n : 0.5;
  }

  /**
   * Fitness of one grown individual: can a reader of the pyramidal spikes tell where the thalamus was stimulated,
   * and at what energy cost? The stimuli are presented in one continuous sequence; after each onset the pyramidal
   * spikes of a 20-tick window (from 10 ticks after onset: the thalamocortical delay) give
   *   decoded_k = spike-weighted mean x of the pyramidal cells, and n_k = their number of spikes.
   *   accuracy   = exp(-RMSE(decoded, true position) / 0.08)
   *   response   = mean_k (1 - exp(-n_k / 5))                              (a reliable, not silent, response)
   *   efficiency = exp(-(neurons / 1000 + thalamocortical synapses / 2500 + spikes per stimulus / 400))
   *   fitness    = accuracy x response x efficiency
   * Spikes and synaptic transmission dominate the energy budget of signalling (Attwell & Laughlin 2001,
   * J Cereb Blood Flow Metab); the weights only set the scale. keepRasters: also return the spike rasters.
   */
  function evaluate(dev, seed, keepRasters) {
    const net = dev.net, S = CONST.stimuli, NT = net.NT, P = CONST.period, lag = CONST.readoutLag;
    const thx = net.cells.x.slice(0, NT), xsPyr = net.cells.x.slice(NT, NT + net.nPyr);
    const ticks = S.length * P + lag;
    const decoded = [], spikes = [], stimuli = [], rasters = [], orders = [];
    for (let rep = 0; rep < CONST.trials; rep++) {
      const order = stimulusOrder(S.length, seed * 7 + rep);
      const r = simulate(net.kernel, net.csr, ticks, ((seed * 31 + rep * 1013) % 0xffffffff) + 1,
        sequenceDrive(thx, S, order, P, CONST.stimOn));
      for (let k = 0; k < S.length; k++) {
        const counts = new Float64Array(net.nPyr);
        let n = 0;
        for (let tk = k * P + lag; tk < k * P + lag + CONST.readoutTicks; tk++) {
          for (let i = 0; i < net.nPyr; i++) {
            if (r[tk * net.N + NT + i]) {
              counts[i]++;
              n++;
            }
          }
        }
        decoded.push(decodePosition(xsPyr, counts));
        spikes.push(n);
        stimuli.push(S[order[k]]);
      }
      orders.push(order);
      if (keepRasters) rasters.push(r);
    }
    let ssr = 0, sst = 0;
    const mean = S.reduce(function (a, b) { return a + b; }, 0) / S.length;
    for (let k = 0; k < stimuli.length; k++) {
      ssr += (decoded[k] - stimuli[k]) * (decoded[k] - stimuli[k]);
      sst += (stimuli[k] - mean) * (stimuli[k] - mean);
    }
    const rmse = Math.sqrt(ssr / stimuli.length);
    const accuracy = Math.exp(-rmse / CONST.accuracyScale);
    const response = spikes.reduce(function (a, n) { return a + 1 - Math.exp(-n / CONST.responseSpikes); }, 0) / spikes.length;
    let nTC = 0;
    for (const k of net.synapses.kind) if (k === 0) nTC++;
    const nNeurons = net.nPyr + net.nInh;
    const nSpikes = spikes.reduce(function (a, n) { return a + n; }, 0) / spikes.length;
    const energy = nNeurons / CONST.energyCells + nTC / CONST.energySynapses + nSpikes / CONST.energySpikes;
    const efficiency = Math.exp(-energy);
    return {
      fitness: accuracy * response * efficiency, accuracy: accuracy, response: response, efficiency: efficiency,
      rmse: rmse, r2: Math.max(0, 1 - ssr / sst), decoded: decoded, stimuli: stimuli, spikes: spikes,
      nNeurons: nNeurons, nTC: nTC, nSpikes: nSpikes, ticks: ticks, orders: orders, rasters: keepRasters ? rasters : null,
    };
  }

  /**
   * Per-stage summary of a grown individual (what the page compares between the founder and the champion):
   * neurogenesis: neurons, mean birth cycle; fate: interneurons that reached the cortex (and those left in the
   * MGE); migration: fraction of pyramidal cells in L4, interneuron coverage of the sheet (tenths reached);
   * axons: map slope (least-squares slope of the axon target x on the thalamic x) and synapses grown; refinement:
   * thalamocortical synapses kept; activity: spikes per stimulus and decoding error (from `ev`).
   */
  function phenotype(dev, ev) {
    const net = dev.net, c = net.cells, NT = net.NT;
    let inL4 = 0, birth = 0;
    for (let i = NT; i < NT + net.nPyr; i++) {
      if (c.z[i] >= ZONES[5].z0 && c.z[i] < ZONES[5].z1) inL4++;
      birth += c.birth[i];
    }
    const bins = new Uint8Array(10);
    for (let i = NT + net.nPyr; i < net.N; i++) bins[Math.min(9, Math.max(0, Math.floor(c.x[i] * 10)))] = 1;
    const tx = dev.record.axons.tx;
    let mx = 0, my = 0, sxy = 0, sxx = 0;
    for (let k = 0; k < NT; k++) {
      mx += c.x[k] / NT;
      my += tx[k] / NT;
    }
    for (let k = 0; k < NT; k++) {
      sxy += (c.x[k] - mx) * (tx[k] - my);
      sxx += (c.x[k] - mx) * (c.x[k] - mx);
    }
    let grownTC = 0, keptTC = 0;
    for (const k of net.grown.kind) if (k === 0) grownTC++;
    for (const k of net.synapses.kind) if (k === 0) keptTC++;
    return {
      neurons: net.nPyr + net.nInh, pyramidal: net.nPyr, birth: net.nPyr ? birth / net.nPyr : 0,
      interneurons: net.nInh, inMGE: net.nMGE - net.nInh, glia: net.nGlia,
      inL4: net.nPyr ? inL4 / net.nPyr : 0, coverage: bins.reduce(function (a, b) { return a + b; }, 0) / 10,
      slope: sxy / sxx, grownTC: grownTC, keptTC: keptTC,
      spikes: ev ? ev.nSpikes : null, rmse: ev ? ev.rmse : null, accuracy: ev ? ev.accuracy : null,
      efficiency: ev ? ev.efficiency : null, fitness: ev ? ev.fitness : null,
    };
  }

  function meanOf(list, key) {
    return list.reduce(function (a, p) { return a + p[key]; }, 0) / list.length;
  }

  /** Grow and evaluate a genome on several development seeds: mean fitness, its factors and phenotype. */
  function assess(genome, seeds) {
    const parts = seeds.map(function (sd) {
      const dev = develop(genome, sd);
      const ev = evaluate(dev, sd);
      ev.phenotype = phenotype(dev, ev);
      return ev;
    });
    const ph = parts.map(function (p) { return p.phenotype; });
    const phenoMean = {};
    Object.keys(ph[0]).forEach(function (k) {
      phenoMean[k] = meanOf(ph, k);
    });
    return { fitness: meanOf(parts, "fitness"), accuracy: meanOf(parts, "accuracy"), response: meanOf(parts, "response"),
      efficiency: meanOf(parts, "efficiency"), rmse: meanOf(parts, "rmse"), r2: meanOf(parts, "r2"),
      phenotype: phenoMean, parts: parts };
  }

  /**
   * Evolution by selection of the best offspring: a (1, lambda) evolution strategy on the [0, 1] gene coding (as
   * neurogenesis.evolution.islands, with one parent). Every generation the parent makes `lambda` mutated offspring
   * (u + sigma N(0, 1), clipped); all are grown on the same fresh development seeds (seeds_of) and the best
   * offspring becomes the next parent, even if it is worse than its parent. With `elitism` the parent competes too
   * (a (1 + lambda) strategy). The champion of each generation is also assessed on fixed held-out seeds
   * (`validationSeeds`), the audit of neurogenesis.evolution.robust.
   * work(budgetMs) evaluates offspring until the time budget is spent and returns the generation record once the
   * generation is complete (else null), so a page can evolve between animation frames; step() runs one generation.
   */
  function Evolution(opts) {
    const o = Object.assign({ genes: GENES, founder: FOUNDER, lambda: 10, sigma: 0.1, seedsPerGen: 2, island: 0,
      elitism: false, validationSeeds: [1, 2, 3] }, opts || {});
    const rng = Stream(o.island, "evolution");
    const state = { opts: o, generation: 0, history: [], pending: null, founderU: toUnit(o.founder, o.genes) };
    state.parentU = state.founderU.slice();
    state.parent = fromUnit(o.founder, o.genes, state.parentU);

    function begin() {
      const seeds = seedsOf(o.island, state.generation, o.seedsPerGen);
      const offspring = [];
      for (let j = 0; j < o.lambda; j++) {
        offspring.push({ u: state.parentU.map(function (x) { return clip01(x + o.sigma * rng.normal()); }) });
      }
      if (o.elitism) offspring.push({ u: state.parentU.slice(), parent: true });
      offspring.forEach(function (c) {
        c.genome = fromUnit(o.founder, o.genes, c.u);
      });
      state.pending = { seeds: seeds, offspring: offspring, next: 0, validation: null };
    }

    function finish() {
      const pd = state.pending;
      let best = 0;
      pd.offspring.forEach(function (c, j) {
        if (c.result.fitness > pd.offspring[best].result.fitness) best = j;
      });
      const fits = pd.offspring.map(function (c) { return c.result.fitness; }).sort(function (a, b) { return a - b; });
      const champ = pd.offspring[best];
      const record = { generation: state.generation, seeds: pd.seeds, offspring: pd.offspring, best: best,
        bestFitness: champ.result.fitness, median: fits[Math.floor(fits.length / 2)], u: champ.u.slice(),
        genome: champ.genome, result: champ.result, validation: pd.validation };
      state.history.push({ generation: state.generation, best: record.bestFitness, median: record.median,
        validation: pd.validation ? pd.validation.fitness : null, u: champ.u.slice(),
        phenotype: (pd.validation || champ.result).phenotype });
      state.parentU = champ.u.slice();
      state.parent = champ.genome;
      state.generation++;
      state.pending = null;
      return record;
    }

    state.work = function (budgetMs) {
      const t0 = now();
      if (!state.pending) begin();
      const pd = state.pending;
      while (pd.next < pd.offspring.length) {
        const c = pd.offspring[pd.next++];
        c.result = assess(c.genome, pd.seeds);
        if (now() - t0 > budgetMs) return null;
      }
      if (o.validationSeeds && o.validationSeeds.length && !pd.validation) {
        let best = 0;
        pd.offspring.forEach(function (c, j) {
          if (c.result.fitness > pd.offspring[best].result.fitness) best = j;
        });
        pd.validation = assess(pd.offspring[best].genome, o.validationSeeds);
        if (now() - t0 > budgetMs) return null;
      }
      return finish();
    };
    state.step = function () {
      let r = null;
      while (!r) r = state.work(Infinity);
      return r;
    };
    /** Continue evolution from a genome (e.g. one edited by hand); the history is kept. */
    state.setParent = function (genome) {
      state.pending = null;
      state.parentU = toUnit(genome, o.genes);
      state.parent = fromUnit(o.founder, o.genes, state.parentU);
    };
    return state;
  }

  return {
    version: "1.0.0",
    // random streams and gene coding
    Stream: Stream, hashString: hashString, INTEGER_ROOTS: INTEGER_ROOTS, getGene: getGene, setGene: setGene,
    fromUnit: fromUnit, toUnit: toUnit, seedsOf: seedsOf, sigmoid: sigmoid, deepClone: deepClone,
    // kernel and activity measures
    poissonThreshold: poissonThreshold, buildCSR: buildCSR, Simulator: Simulator, stepKernel: stepKernel,
    simulate: simulate, coactivity: coactivity, competitiveLosers: competitiveLosers,
    // stages
    Tissue: Tissue, seedCells: seedCells, cellCycleClock: cellCycleClock, proliferate: proliferate, migrate: migrate,
    mosaic: mosaic, growAxons: growAxons,
    // the front-page problem
    CortexMapDemo: {
      GENES: GENES, FOUNDER: FOUNDER, STAGES: STAGES, ZONES: ZONES, L4_DEPTH: L4_DEPTH, CONST: CONST,
      develop: develop, evaluate: evaluate, phenotype: phenotype, assess: assess, decodePosition: decodePosition,
      stimulusRates: stimulusRates, sequenceDrive: sequenceDrive, stimulusOrder: stimulusOrder, waveDrive: waveDrive,
    },
    Evolution: Evolution,
  };
});
