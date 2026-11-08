/**
 * ng-hero.js: the front-page playground. Grows a founder genome and the champion of an evolution run with the
 * JavaScript port of neurogenesis-sim (ng-core.js), and animates both, side by side, through the six stages of their
 * development. Everything drawn comes from the records of the grown individuals: cell lineages, migration paths,
 * axon targets, synapses kept by competition and spikes of the lif_int kernel.
 */
(function () {
  "use strict";

  const STAGE_COLOR = { neurogenesis: "#4ade80", fate: "#facc15", migration: "#38bdf8", axons: "#f472b6",
    refinement: "#c084fc", activity: "#fb923c" };
  const PREWARM = 5; // generations evolved before the first paint
  const TAG = { neurogenesis: "cell_cycle_clock", fate: "proliferate", migration: "migrate", axons: "grow_axons",
    refinement: "competitive_elimination", activity: "lif_int" };
  const DUR = { neurogenesis: 7, fate: 4.5, migration: 7.5, axons: 7.5, refinement: 7, activity: 8 };
  const COL = { glia: "#4ade80", newborn: "#f472b6", pyr: "#ff6fa8", inter: "#ffd166", bg: "#04070d" };

  const INFO = {
    neurogenesis: {
      title: "Neurogenesis: progenitors divide, then leave the cell cycle",
      text: "Radial glial progenitors divide at the ventricular surface; their nuclei move up and down with the cell " +
        "cycle (interkinetic nuclear migration). At every cycle a progenitor leaves the cycle with a probability Q that " +
        "rises from cycle to cycle; its last division then gives two postmitotic daughters, which become neurons. " +
        "Fewer early exits mean more divisions: more neurons, born later.",
      refs: "Sauer 1935, J Comp Neurol · Takahashi, Nowakowski & Caviness 1996, J Neurosci",
    },
    fate: {
      title: "Fate: GABAergic interneurons come from the ventral telencephalon",
      text: "Pyramidal neurons are glutamatergic and born in the cortical ventricular zone. Most cortical interneurons " +
        "come from the medial ganglionic eminence (MGE), others from the caudal ganglionic eminence (CGE); the model " +
        "has one source, the MGE, and the number of its divisions sets how many interneurons there are.",
      refs: "Anderson et al. 1997, Science · Wonders & Anderson 2006, Nat Rev Neurosci",
    },
    migration: {
      title: "Migration: radial climbing, inside-out layers, tangential streams",
      text: "Each pyramidal neuron moves radially for 20 steps at the radial speed plus the birth-date gain × (birth " +
        "cycle − 3.5); a positive gain makes later-born neurons settle more superficially " +
        "(inside-out, as in the real cortex). Interneurons travel tangentially from the MGE, disperse, then enter the " +
        "cortical plate at the depth of nearby pyramidal cells. The drawing adds the multipolar pause and saltatory " +
        "jumps of real migrating neurons.",
      refs: "Rakic 1972, J Comp Neurol · Angevine & Sidman 1961, Nature · Marín & Rubenstein 2001, Nat Rev Neurosci · " +
        "Lodato et al. 2011, Neuron",
    },
    axons: {
      title: "Axon guidance: thalamic axons find their place in layer 4",
      text: "Each thalamic axon (coloured by its position in the thalamus) targets the point x = sigmoid(4B(x_thalamus − ½)) " +
        "in layer 4, set by graded receptor expression, and contacts cells around it within a spread σ. B = 0 sends " +
        "every axon to the centre; a positive B lays out an ordered map. The route drawn (intermediate zone, a wait in the " +
        "subplate, then layer 4) is the one real thalamocortical axons take.",
      refs: "Sperry 1963, PNAS · Ghosh & Shatz 1992, J Neurosci · López-Bendito & Molnár 2003, Nat Rev Neurosci",
    },
    refinement: {
      title: "Refinement: spontaneous waves, then competition between inputs",
      text: "Before any sensory input, waves of spontaneous activity sweep the thalamus (before eye opening, retinal " +
        "waves drive the visual thalamus). On every cortical cell that fired, an input whose spikes were followed by " +
        "the cell's spikes (within 5 ms) less often than a fraction, the competition gene, of the cell's best input " +
        "is eliminated (grey).",
      refs: "Katz & Shatz 1996, Science · Willshaw 1981, Proc R Soc Lond B · Balice-Gordon & Lichtman 1994, Nature",
    },
    activity: {
      title: "Activity: where was the thalamus stimulated?",
      text: "The grown network runs on the integer lif_int kernel (1 tick = 1 ms); this JavaScript port gives the same " +
        "spikes as the Python reference. Seven flashes, one every 40 ms; in a 20 ms window starting 10 ms after each " +
        "flash, the spike-weighted mean position of the pyramidal cells is the decoded position (◆), against the true " +
        "one (▼). " +
        "Interneurons, driven by the thalamus and by pyramidal cells, inhibit nearby pyramidal cells.",
      refs: "Gabernet et al. 2005, Neuron · Attwell & Laughlin 2001, J Cereb Blood Flow Metab",
    },
  };

  /** Founder -> champion rows of each stage: [label, phenotype key, format, definition]. */
  const METRICS = {
    neurogenesis: [
      ["Pyramidal neurons", "pyramidal", 0, "Neurons born in the cortical ventricular zone"],
      ["Mean birth cycle", "birth", 1, "Mean cell cycle (1–6) at which the pyramidal neurons were born"],
      ["Radial glia left", "glia", 0, "Progenitors still cycling after the 6 cycles (not neurons)"]],
    fate: [
      ["Interneurons in cortex", "interneurons", 0, "MGE-born interneurons that reached the cortex"],
      ["Left in the MGE", "inMGE", 0, "Interneurons that did not reach the cortex (not in the network)"]],
    migration: [
      ["Pyramidal cells in L4", "inL4", "%", "Fraction of pyramidal neurons whose final depth is in layer 4"],
      ["Interneuron coverage", "coverage", "%", "Fraction of the 10 tenths of the sheet that hold at least one interneuron"]],
    axons: [
      ["Map slope", "slope", 2, "Least-squares slope of axon target x on thalamic x: 0 = no map, 1 = one-to-one map"],
      ["Thalamocortical synapses", "grownTC", 0, "Synapses formed by thalamic axons, before refinement"]],
    refinement: [
      ["Synapses grown", "grownTC", 0, "Thalamocortical synapses before competition"],
      ["Synapses kept", "keptTC", 0, "Thalamocortical synapses left after competitive elimination"]],
    activity: [
      ["Decoding error (RMSE)", "rmse", 3, "Root-mean-square error of the decoded flash position, in sheet widths"],
      ["Pyramidal spikes per flash", "spikes", 0, "Mean number of pyramidal spikes in the 20 ms readout window"],
      ["Fitness", "fitness", 3, "accuracy × response × efficiency (see the formula below)"]],
  };

  // ----------------------------------------------------------------------------------------------------------------
  // small helpers
  // ----------------------------------------------------------------------------------------------------------------
  function clamp01(x) {
    return x < 0 ? 0 : x > 1 ? 1 : x;
  }
  function lerp(a, b, t) {
    return a + (b - a) * t;
  }
  function ease(t) {
    t = clamp01(t);
    return t * t * (3 - 2 * t);
  }
  function hash(i, s) {
    let h = Math.imul((i + 1) ^ 0x9e3779b9, 0x85ebca6b) ^ Math.imul((s | 0) + 7, 0xc2b2ae35);
    h ^= h >>> 15;
    h = Math.imul(h, 0x2c1b3c6d);
    h ^= h >>> 12;
    return (h >>> 0) / 4294967296;
  }
  /** Turbo colour map (polynomial fit, Mikhailov 2019), for the topographic identity of thalamic axons. */
  function turbo(x) {
    x = 0.12 + 0.76 * clamp01(x);
    const r = 0.13572138 + x * (4.6153926 + x * (-42.66032258 + x * (132.13108234 + x * (-152.94239396 + x * 59.28637943))));
    const g = 0.09140261 + x * (2.19418839 + x * (4.84296658 + x * (-14.18503333 + x * (4.27729857 + x * 2.82956604))));
    const b = 0.1066733 + x * (12.64194608 + x * (-60.58204836 + x * (110.36276771 + x * (-89.90310912 + x * 27.34824973))));
    const c = function (v) {
      return Math.round(255 * clamp01(v));
    };
    return "rgb(" + c(r) + "," + c(g) + "," + c(b) + ")";
  }
  function fmt(v, d) {
    if (v === null || v === undefined || isNaN(v)) return "–";
    if (d === "%") return Math.round(100 * v) + "%";
    return Number(v).toFixed(d);
  }
  function el(tag, cls, html) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html !== undefined) e.innerHTML = html;
    return e;
  }

  const sprites = new Map();
  /** A soft radial glow of one colour, drawn with additive blending for fluorescence-like light. */
  function glow(color) {
    let c = sprites.get(color);
    if (c) return c;
    c = document.createElement("canvas");
    c.width = c.height = 64;
    const g = c.getContext("2d");
    const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    gr.addColorStop(0, color);
    gr.addColorStop(0.25, color);
    gr.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = gr;
    g.globalAlpha = 1;
    g.fillRect(0, 0, 64, 64);
    // fade the colour to transparent towards the edge
    g.globalCompositeOperation = "destination-in";
    const m = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    m.addColorStop(0, "rgba(0,0,0,1)");
    m.addColorStop(0.35, "rgba(0,0,0,0.45)");
    m.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = m;
    g.fillRect(0, 0, 64, 64);
    sprites.set(color, c);
    return c;
  }
  function drawGlow(ctx, color, x, y, r, a) {
    if (a <= 0.01 || r <= 0.5) return;
    ctx.globalAlpha = Math.min(1, a);
    ctx.drawImage(glow(color), x - r, y - r, 2 * r, 2 * r);
  }

  const textures = new Map();
  /** Speckled tissue texture (Nissl-like grain), deterministic. */
  function texture(w, h) {
    const key = w + "x" + h;
    if (textures.has(key)) return textures.get(key);
    const c = document.createElement("canvas");
    c.width = Math.max(1, w);
    c.height = Math.max(1, h);
    const g = c.getContext("2d");
    const n = Math.floor((w * h) / 90);
    for (let i = 0; i < n; i++) {
      const x = hash(i, 1) * w, y = hash(i, 2) * h, r = 0.4 + hash(i, 3) * 1.1;
      g.fillStyle = "rgba(170,190,255," + (0.03 + 0.06 * hash(i, 4)).toFixed(3) + ")";
      g.beginPath();
      g.arc(x, y, r, 0, 6.283);
      g.fill();
    }
    textures.set(key, c);
    return c;
  }

  // ----------------------------------------------------------------------------------------------------------------
  // scene: one grown individual, prepared for drawing (positions are in slice coordinates x in [-0.2, 1], z in [0, 1])
  // ----------------------------------------------------------------------------------------------------------------
  function buildScene(NG, genome, seed) {
    const D = NG.CortexMapDemo;
    const dev = D.develop(genome, seed);
    const ev = D.evaluate(dev, seed, true);
    const ph = D.phenotype(dev, ev);
    const t = dev.tissue, rec = dev.record, net = dev.net, C = D.CONST;
    const nCortex = rec.vz.x.length;
    const pyrK = new Map(), mgeK = new Map(), netOf = new Map();
    rec.migration.pyr.forEach(function (ti, k) { pyrK.set(ti, k); });
    rec.migration.mge.forEach(function (ti, k) { mgeK.set(ti, k); });
    net.cells.tissue.forEach(function (ti, n) { if (ti >= 0) netOf.set(ti, n); });

    // cortical VZ lineage
    const vz = [];
    for (let i = 0; i < nCortex; i++) {
      const neuron = !t.cycling[i];
      vz.push({ i: i, born: t.born[i], exit: neuron ? t.generation[i] : 99, parent: t.parent[i], x: rec.vz.x[i],
        px: t.parent[i] >= 0 ? rec.vz.x[t.parent[i]] : rec.vz.x[i], h: hash(i, seed), k: pyrK.has(i) ? pyrK.get(i) : -1,
        n: netOf.has(i) ? netOf.get(i) : -1, izZ: 0.11 + 0.15 * hash(i, seed + 3) });
    }
    // MGE lineage
    const mge = rec.mge.cells.map(function (ti, k) {
      return { i: ti, k: k, born: t.born[ti], x: rec.mge.x[k], z: rec.mge.z[k],
        px: t.parent[ti] >= nCortex ? rec.mge.x[rec.mge.cells.indexOf(t.parent[ti])] : rec.mge.x[k],
        pz: t.parent[ti] >= nCortex ? rec.mge.z[rec.mge.cells.indexOf(t.parent[ti])] : rec.mge.z[k],
        fx: t.x[ti], fz: t.z[ti], n: netOf.has(ti) ? netOf.get(ti) : -1, h: hash(ti, seed + 11) };
    });
    // network cells: final positions and kinds
    const cells = [];
    for (let n = 0; n < net.N; n++) {
      cells.push({ x: net.cells.x[n], z: net.cells.z[n], kind: net.cells.kind[n], h: hash(n, seed + 5) });
    }
    // thalamic axons: path through the intermediate zone and subplate to layer 4, branches to their targets
    const NT = net.NT, L4 = D.L4_DEPTH;
    const axons = [];
    for (let k = 0; k < NT; k++) {
      const x = net.cells.x[k], tx = rec.axons.tx[k], lane = (k / NT - 0.5) * 0.05;
      const pts = [[x, -1]];
      for (let s = 0; s <= 4; s++) pts.push([x, 0.02 + 0.08 * (s / 4)]);
      for (let s = 1; s <= 18; s++) {
        const u = s / 18, v = 1 - u;
        const bx = v * v * v * x + 3 * v * v * u * x + 3 * v * u * u * tx + u * u * u * tx;
        const bz = v * v * v * 0.1 + 3 * v * v * u * (0.22 + lane) + 3 * v * u * u * (0.17 + lane) + u * u * u * 0.29;
        pts.push([bx, bz]);
      }
      const sp = pts.length;
      pts.push([tx, 0.33]);
      for (let s = 1; s <= 8; s++) pts.push([tx, 0.33 + (L4 - 0.33) * (s / 8)]);
      axons.push({ k: k, x: x, tx: tx, color: turbo(x), pts: pts, sp: sp, branches: [], kept: 0, h: hash(k, seed + 17) });
    }
    const g = net.grown;
    for (let s = 0; s < g.pre.length; s++) {
      if (g.kind[s] !== 0) continue;
      const keep = rec.refinement.keep[s] === 1;
      const ax = axons[g.pre[s]];
      ax.branches.push({ post: g.post[s], keep: keep, h: hash(s, seed + 23) });
      if (keep) ax.kept++;
    }
    return { genome: genome, seed: seed, dev: dev, ev: ev, ph: ph, vz: vz, mge: mge, cells: cells, axons: axons,
      glia: rec.glia, NT: NT, N: net.N, nPyr: net.nPyr, rec: rec, net: net, C: C, L4: L4,
      wave: rec.refinement.wave, waveTicks: rec.refinement.ticks, raster: ev.rasters[0], ticks: ev.ticks,
      order: ev.orders[0] };
  }

  // ----------------------------------------------------------------------------------------------------------------
  // drawing
  // ----------------------------------------------------------------------------------------------------------------
  function geometry(P) {
    const g = { P: P };
    g.top = P.y + 24;
    g.thalH = Math.max(22, P.h * 0.085);
    g.bot = P.y + P.h - g.thalH - 16;
    g.gut = Math.max(40, P.w * 0.13);
    g.x0 = P.x + g.gut;
    g.x1 = P.x + P.w - 10;
    g.thY = P.y + P.h - g.thalH * 0.5 - 4;
    g.s0 = Math.max(0.75, Math.min(1.5, (g.x1 - g.x0) / 380));
    g.zTop = 1;
    g.s = g.s0;
    /** Camera: the slice shows depths [0, zTop] (the cortical wall is thin while neurons are being born). */
    g.view = function (zTop) {
      g.zTop = zTop;
      g.s = g.s0 * Math.pow(1 / zTop, 0.3);
    };
    g.X = function (x) {
      return x >= 0 ? g.x0 + x * (g.x1 - g.x0) : g.x0 + x * ((g.gut - 6) / 0.22);
    };
    g.Y = function (z) {
      return z <= -0.5 ? g.thY : g.bot - (z / g.zTop) * (g.bot - g.top);
    };
    return g;
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function drawBackground(ctx, g, D, opt) {
    const P = g.P;
    ctx.save();
    roundRect(ctx, P.x, P.y, P.w, P.h, 10);
    ctx.fillStyle = COL.bg;
    ctx.fill();
    ctx.clip();
    // tissue
    const tg = ctx.createLinearGradient(0, g.top, 0, g.bot);
    tg.addColorStop(0, "#141a33");
    tg.addColorStop(0.35, "#10162b");
    tg.addColorStop(1, "#0b1122");
    ctx.fillStyle = tg;
    ctx.fillRect(g.x0, g.top, g.x1 - g.x0, g.bot - g.top);
    // ventral telencephalon (gutter) and MGE
    const vg = ctx.createLinearGradient(P.x, 0, g.x0, 0);
    vg.addColorStop(0, "#0a0f1e");
    vg.addColorStop(1, "#10172b");
    ctx.fillStyle = vg;
    ctx.fillRect(P.x, Math.max(g.top, g.Y(0.42)), g.x0 - P.x, g.bot - Math.max(g.top, g.Y(0.42)));
    ctx.save();
    ctx.globalAlpha = 0.6 * opt.mge;
    const mx = g.X(-0.1), my = g.Y(0.2);
    const mg = ctx.createRadialGradient(mx, my, 2, mx, my, (g.gut - 6) * 0.7);
    mg.addColorStop(0, "rgba(250,204,21,0.18)");
    mg.addColorStop(1, "rgba(250,204,21,0)");
    ctx.fillStyle = mg;
    ctx.beginPath();
    ctx.ellipse(mx, my, (g.gut - 6) * 0.55, (g.bot - g.top) * 0.16, 0, 0, 6.283);
    ctx.fill();
    ctx.restore();
    // zones
    const Z = D.ZONES;
    ctx.fillStyle = "rgba(74,222,128,0.05)";
    ctx.fillRect(g.x0, g.Y(Z[0].z1), g.x1 - g.x0, g.Y(0) - g.Y(Z[0].z1));
    ctx.save();
    ctx.globalAlpha = 0.5;
    ctx.strokeStyle = "rgba(160,180,230,0.05)";
    ctx.lineWidth = 1;
    for (let i = 0; i < 14; i++) { // fibre streaks of the intermediate zone
      const z = 0.1 + 0.19 * hash(i, 99), y = g.Y(z);
      ctx.beginPath();
      ctx.moveTo(g.x0, y);
      ctx.bezierCurveTo(g.x0 + (g.x1 - g.x0) * 0.3, y - 2, g.x0 + (g.x1 - g.x0) * 0.7, y + 2, g.x1, y);
      ctx.stroke();
    }
    ctx.restore();
    if (opt.l4 > 0.01) {
      const y0 = g.Y(Z[5].z1), y1 = g.Y(Z[5].z0);
      const lg = ctx.createLinearGradient(0, y0, 0, y1);
      lg.addColorStop(0, "rgba(244,114,182,0)");
      lg.addColorStop(0.5, "rgba(244,114,182," + (0.11 * opt.l4).toFixed(3) + ")");
      lg.addColorStop(1, "rgba(244,114,182,0)");
      ctx.fillStyle = lg;
      ctx.fillRect(g.x0, y0, g.x1 - g.x0, y1 - y0);
    }
    ctx.drawImage(texture(Math.round(g.x1 - g.x0), Math.round(g.bot - g.top)), g.x0, g.top);
    const FONT = "px -apple-system, Segoe UI, Roboto, sans-serif";
    ctx.font = Math.max(8, Math.round(9 * Math.min(1.2, g.s))) + FONT;
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (let i = 0; i < Z.length; i++) {
      const y = g.Y(Z[i].z1);
      if (Z[i].z0 >= g.zTop - 0.01) continue;
      if (i < Z.length - 1) {
        ctx.strokeStyle = "rgba(148,163,184,0.10)";
        ctx.setLineDash([2, 4]);
        ctx.beginPath();
        ctx.moveTo(g.x0, y);
        ctx.lineTo(g.x1, y);
        ctx.stroke();
        ctx.setLineDash([]);
      }
      ctx.fillStyle = Z[i].key === "L4" && opt.l4 > 0.3 ? "rgba(249,168,212,0.9)" : "rgba(148,163,184,0.55)";
      ctx.fillText(Z[i].label, g.x1 - 3, (g.Y(Z[i].z0) + Math.max(g.top + 6, g.Y(Z[i].z1))) / 2);
    }
    // pia and ventricle
    ctx.strokeStyle = "rgba(186,230,253," + (0.55 * clamp01((g.zTop - 0.9) * 10)).toFixed(3) + ")";
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(g.x0, g.top);
    ctx.lineTo(g.x1, g.top);
    ctx.stroke();
    ctx.fillStyle = "#03050a";
    ctx.fillRect(g.x0, g.bot, g.x1 - g.x0, 5);
    ctx.strokeStyle = "rgba(74,222,128,0.35)";
    ctx.beginPath();
    ctx.moveTo(g.x0, g.bot);
    ctx.lineTo(g.x1, g.bot);
    ctx.stroke();
    // thalamus
    ctx.fillStyle = "rgba(125,211,252,0.05)";
    roundRect(ctx, g.x0, g.thY - g.thalH * 0.42, g.x1 - g.x0, g.thalH * 0.84, 6);
    ctx.fill();
    // labels of the left margin: shrunk to fit the gutter at narrow widths, never below 6.5 px
    ctx.textAlign = "left";
    const margin = function (text, y, alpha) {
      let f = Math.max(8, Math.min(10.5, 9 * g.s));
      ctx.font = f + FONT;
      while (f > 6.5 && ctx.measureText(text).width > g.gut - 9) {
        f -= 0.5;
        ctx.font = f + FONT;
      }
      ctx.fillStyle = "rgba(148,163,184," + alpha + ")";
      ctx.fillText(text, P.x + 5, y);
    };
    margin("thalamus", g.thY, 0.8);
    margin("MGE", Math.max(g.top + 8, g.Y(0.36)), 0.8);
    if (g.zTop > 0.95) margin("pia", g.top, 0.5);
    margin("ventricle", g.bot + 2, 0.5);
    ctx.restore();
  }

  function drawFiber(ctx, g, x, zSoma, h, a) {
    const X = g.X(x), Y = g.Y(zSoma), T = g.Y(1) + 1;
    const bend = (h - 0.5) * 10 * g.s;
    ctx.globalAlpha = a;
    ctx.beginPath();
    ctx.moveTo(X, Y);
    ctx.quadraticCurveTo(X + bend, (Y + T) / 2, X + bend * 0.4, T);
    ctx.stroke();
    ctx.beginPath(); // endfoot on the pia
    ctx.moveTo(X + bend * 0.4 - 2 * g.s, T);
    ctx.lineTo(X + bend * 0.4 + 2 * g.s, T);
    ctx.lineTo(X + bend * 0.4, T + 3 * g.s);
    ctx.fill();
  }

  function drawProgenitor(ctx, g, X, Y, s, rounded, a) {
    drawGlow(ctx, COL.glia, X, Y, 7 * s, 0.35 * a);
    ctx.globalAlpha = a;
    ctx.fillStyle = "rgba(74,222,128,0.85)";
    ctx.beginPath();
    ctx.ellipse(X, Y, 2.1 * s, (rounded ? 2.5 : 3.6) * s, 0, 0, 6.283);
    ctx.fill();
    ctx.fillStyle = "rgba(10,40,25,0.7)";
    ctx.beginPath();
    ctx.ellipse(X, Y, 1.1 * s, (rounded ? 1.4 : 2) * s, 0, 0, 6.283);
    ctx.fill();
  }

  function drawMultipolar(ctx, X, Y, s, color, h, a) {
    drawGlow(ctx, color, X, Y, 6 * s, 0.3 * a);
    ctx.globalAlpha = a;
    ctx.strokeStyle = color;
    ctx.lineWidth = 0.7;
    for (let j = 0; j < 4; j++) {
      const an = 6.283 * (h + j / 4 + 0.08 * Math.sin(j * 7.1 + h * 13)), l = (3 + 2.5 * hash(j, h * 1e6)) * s;
      ctx.beginPath();
      ctx.moveTo(X, Y);
      ctx.lineTo(X + Math.cos(an) * l, Y + Math.sin(an) * l);
      ctx.stroke();
    }
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(X, Y, 1.9 * s, 0, 6.283);
    ctx.fill();
  }

  function drawMigrating(ctx, X, Y, s, color, dirx, diry, a, forked) {
    drawGlow(ctx, color, X, Y, 6 * s, 0.32 * a);
    ctx.globalAlpha = a;
    ctx.strokeStyle = color;
    ctx.lineWidth = 0.9;
    const lx = X + dirx * 9 * s, ly = Y + diry * 9 * s;
    ctx.beginPath(); // leading process
    ctx.moveTo(X, Y);
    ctx.lineTo(lx, ly);
    if (forked) { // branched leading process of migrating interneurons
      ctx.moveTo(lx, ly);
      ctx.lineTo(lx + (dirx - diry * 0.7) * 4 * s, ly + (diry + dirx * 0.7) * 4 * s);
      ctx.moveTo(lx, ly);
      ctx.lineTo(lx + (dirx + diry * 0.7) * 4 * s, ly + (diry - dirx * 0.7) * 4 * s);
    }
    ctx.stroke();
    ctx.globalAlpha = a * 0.6;
    ctx.beginPath(); // trailing process
    ctx.moveTo(X, Y);
    ctx.lineTo(X - dirx * 4 * s, Y - diry * 4 * s);
    ctx.stroke();
    ctx.globalAlpha = a;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.ellipse(X, Y, (1.6 + Math.abs(dirx)) * s, (1.6 + Math.abs(diry)) * s, 0, 0, 6.283);
    ctx.fill();
  }

  function drawPyramidal(ctx, g, X, Y, s, color, m, h, a, lit) {
    if (lit > 0.02) drawGlow(ctx, "#fff3c4", X, Y, (7 + 9 * lit) * s, 0.9 * lit);
    drawGlow(ctx, color, X, Y, 6 * s, 0.22 * a);
    ctx.globalAlpha = a * (0.28 + 0.4 * lit);
    ctx.strokeStyle = color;
    ctx.lineWidth = 0.6;
    if (m > 0.02) {
      const topY = g.Y(0.985) + 6 * h;
      const ay = lerp(Y - 3 * s, topY, m), bend = (h - 0.5) * 4 * s;
      ctx.beginPath(); // apical dendrite to layer 1
      ctx.moveTo(X, Y - 2.5 * s);
      ctx.quadraticCurveTo(X + bend, (Y + ay) / 2, X + bend * 0.5, ay);
      if (m > 0.75) { // apical tuft
        const tl = 5 * s * (m - 0.75) * 4;
        ctx.moveTo(X + bend * 0.5, ay);
        ctx.lineTo(X + bend * 0.5 - tl, ay - tl * 0.4);
        ctx.moveTo(X + bend * 0.5, ay);
        ctx.lineTo(X + bend * 0.5 + tl, ay - tl * 0.5);
      }
      for (let j = 0; j < 3; j++) { // basal dendrites
        const an = Math.PI * (0.25 + 0.25 * j) + (h - 0.5) * 0.5, l = (4 + 3 * hash(j, h * 1e6)) * s * m;
        ctx.moveTo(X, Y + s);
        ctx.lineTo(X + Math.cos(an) * l, Y + Math.sin(an) * l);
      }
      ctx.stroke();
    }
    ctx.globalAlpha = a;
    ctx.fillStyle = lit > 0.5 ? "#fff7d6" : color;
    ctx.beginPath(); // triangular soma
    ctx.moveTo(X, Y - 3.1 * s);
    ctx.lineTo(X - 2.3 * s, Y + 1.7 * s);
    ctx.lineTo(X + 2.3 * s, Y + 1.7 * s);
    ctx.closePath();
    ctx.fill();
  }

  function drawInterneuron(ctx, X, Y, s, h, a, lit) {
    if (lit > 0.02) drawGlow(ctx, "#fff3c4", X, Y, (6 + 8 * lit) * s, 0.8 * lit);
    drawGlow(ctx, COL.inter, X, Y, 6 * s, 0.3 * a);
    ctx.globalAlpha = a * 0.6;
    ctx.strokeStyle = COL.inter;
    ctx.lineWidth = 0.6;
    ctx.beginPath();
    for (let j = 0; j < 5; j++) {
      const an = 6.283 * (h + j / 5), l = (3.5 + 2 * hash(j, h * 1e5)) * s;
      ctx.moveTo(X, Y);
      ctx.lineTo(X + Math.cos(an) * l, Y + Math.sin(an) * l);
    }
    ctx.stroke();
    ctx.globalAlpha = a;
    ctx.fillStyle = lit > 0.5 ? "#fff7d6" : COL.inter;
    ctx.beginPath();
    ctx.arc(X, Y, 1.9 * s, 0, 6.283);
    ctx.fill();
  }

  function axonPoint(g, ax, f) {
    // point at fraction f in [0, 1] of the path (by index), in screen coordinates
    const n = ax.pts.length - 1, u = clamp01(f) * n, i = Math.min(n - 1, Math.floor(u)), r = u - i;
    const a = ax.pts[i], b = ax.pts[i + 1];
    return [lerp(g.X(a[0]), g.X(b[0]), r), lerp(g.Y(a[1]), g.Y(b[1]), r)];
  }

  function drawAxon(ctx, g, ax, f, alpha, width) {
    const n = ax.pts.length - 1, upto = clamp01(f) * n;
    ctx.strokeStyle = ax.color;
    ctx.lineWidth = width;
    ctx.beginPath();
    ctx.moveTo(g.X(ax.pts[0][0]), g.Y(ax.pts[0][1]));
    for (let i = 1; i <= Math.floor(upto); i++) {
      const p = ax.pts[i];
      if (i === 1) { // the schematic crossing below the slice is faint
        ctx.globalAlpha = alpha * 0.35;
        ctx.lineTo(g.X(p[0]), g.Y(p[1]));
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(g.X(p[0]), g.Y(p[1]));
        ctx.globalAlpha = alpha;
        continue;
      }
      ctx.lineTo(g.X(p[0]), g.Y(p[1]));
    }
    const tip = axonPoint(g, ax, f);
    ctx.lineTo(tip[0], tip[1]);
    ctx.globalAlpha = alpha;
    ctx.stroke();
    return tip;
  }

  function drawGrowthCone(ctx, g, tip, prev, color, s, t) {
    const dx = tip[0] - prev[0], dy = tip[1] - prev[1], L = Math.hypot(dx, dy) || 1, ux = dx / L, uy = dy / L;
    drawGlow(ctx, color, tip[0], tip[1], 7 * s, 0.5);
    ctx.globalAlpha = 0.8;
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 0.6;
    ctx.beginPath(); // filopodia exploring
    for (let j = -2; j <= 2; j++) {
      const an = Math.atan2(uy, ux) + j * 0.42 + 0.25 * Math.sin(t * 6 + j * 2.1), l = (3.5 + 1.5 * Math.sin(t * 4 + j)) * s;
      ctx.moveTo(tip[0], tip[1]);
      ctx.lineTo(tip[0] + Math.cos(an) * l, tip[1] + Math.sin(an) * l);
    }
    ctx.stroke();
    ctx.globalAlpha = 0.45;
    ctx.fillStyle = color;
    ctx.beginPath(); // lamellipodium
    ctx.ellipse(tip[0] + ux * s, tip[1] + uy * s, 2.6 * s, 1.6 * s, Math.atan2(uy, ux) + Math.PI / 2, 0, 6.283);
    ctx.fill();
  }

  function branchGeom(g, sc, ax, br) {
    const c = sc.cells[br.post];
    const x0 = g.X(ax.tx), y0 = g.Y(sc.L4), x1 = g.X(c.x), y1 = g.Y(c.z);
    return { x0: x0, y0: y0, x1: x1, y1: y1, cx: (x0 + x1) / 2 + (br.h - 0.5) * 8 * g.s, cy: (y0 + y1) / 2 - 3 * g.s };
  }

  function drawBranch(ctx, bg, f, color, alpha, width) {
    if (f <= 0) return;
    ctx.strokeStyle = color;
    ctx.globalAlpha = alpha;
    ctx.lineWidth = width;
    ctx.beginPath();
    ctx.moveTo(bg.x0, bg.y0);
    if (f >= 1) {
      ctx.quadraticCurveTo(bg.cx, bg.cy, bg.x1, bg.y1);
    } else { // partial quadratic (de Casteljau split)
      const ax = lerp(bg.x0, bg.cx, f), ay = lerp(bg.y0, bg.cy, f);
      const bx = lerp(bg.cx, bg.x1, f), by = lerp(bg.cy, bg.y1, f);
      ctx.quadraticCurveTo(ax, ay, lerp(ax, bx, f), lerp(ay, by, f));
    }
    ctx.stroke();
  }

  /** Per-panel animation state that depends on time (calcium-like light, action potentials in flight). */
  function PanelState() {
    return { tick: -1, ca: null, aps: [], mode: "" };
  }

  function advanceRaster(st, raster, N, NT, tick, axonDelay, mode) {
    if (st.mode !== mode || tick < st.tick || !st.ca || st.ca.length !== N) {
      st.mode = mode;
      st.tick = -1;
      st.ca = new Float32Array(N);
      st.aps = [];
    }
    for (let t = st.tick + 1; t <= tick; t++) {
      for (let i = 0; i < N; i++) st.ca[i] *= 0.86;
      const base = t * N;
      if (base + N > raster.length) break;
      for (let i = 0; i < N; i++) {
        if (raster[base + i]) {
          st.ca[i] = Math.min(1.2, st.ca[i] + 0.9);
          if (i < NT) st.aps.push({ k: i, t0: t });
        }
      }
    }
    st.tick = Math.max(st.tick, tick);
    st.aps = st.aps.filter(function (a) { return tick - a.t0 <= axonDelay + 2; });
  }

  function drawPanel(ctx, g, sc, D, stage, p, time, st, label) {
    g.view(stage === "neurogenesis" || stage === "fate" ? 0.42 : stage === "migration" ? lerp(0.42, 1, ease(p / 0.4)) : 1);
    const s = g.s, C = sc.C;
    const isStage = function (k) { return stage === k; };
    drawBackground(ctx, g, D, {
      mge: stage === "fate" || stage === "migration" ? 1 : 0.4,
      l4: stage === "axons" || stage === "refinement" || stage === "activity" ? 1 : stage === "migration" ? p : 0,
    });
    ctx.save();
    roundRect(ctx, g.P.x, g.P.y, g.P.w, g.P.h, 10);
    ctx.clip();
    ctx.globalCompositeOperation = "lighter";
    let hud = "";

    // ---------------- radial glia fibres (progenitors present in this stage)
    const tau = isStage("neurogenesis") ? p * C.cycles : C.cycles + 1;
    ctx.strokeStyle = "rgba(74,222,128,0.8)";
    ctx.fillStyle = "rgba(74,222,128,0.8)";
    ctx.lineWidth = 0.8;
    for (const c of sc.vz) {
      const exists = c.born === 0 || tau >= c.born - 1 + 0.85;
      const progenitor = exists && tau < c.exit - 0.15;
      if (!progenitor) continue;
      const f = isStage("neurogenesis") ? tau - Math.floor(tau) : 0.5;
      const zN = 0.012 + 0.055 * Math.pow(Math.sin(Math.PI * f), 1.5);
      drawFiber(ctx, g, c.x, zN, c.h, isStage("neurogenesis") ? 0.2 : 0.1);
    }
    ctx.globalAlpha = 1;

    // ---------------- stage 1: neurogenesis
    if (isStage("neurogenesis")) {
      const cyc = Math.min(C.cycles, Math.floor(tau) + 1), f = tau - Math.floor(tau);
      let nProg = 0, nNeu = 0;
      for (const c of sc.vz) {
        const appear = c.born === 0 ? -1 : c.born - 1 + 0.85;
        if (tau < appear) continue;
        const sep = c.born === 0 ? 1 : ease((tau - appear) / 0.25);
        const x = lerp(c.px, c.x, sep);
        if (tau < c.exit - 0.15) { // progenitor: nucleus moves with the cycle, mitosis at the apical surface
          nProg++;
          const z = 0.012 + 0.058 * Math.pow(Math.sin(Math.PI * f), 1.5);
          const mitotic = f > 0.82 || sep < 1;
          drawProgenitor(ctx, g, g.X(x), g.Y(sep < 1 ? 0.01 : z), s, mitotic, 1);
        } else { // newborn neuron: rises into the intermediate zone as a multipolar cell
          nNeu++;
          const born = c.exit - 0.15, m = ease((tau - born) / 0.9);
          const z = lerp(0.012, c.izZ, m);
          drawMultipolar(ctx, g.X(x + 0.004 * Math.sin(time * 1.3 + c.h * 9)), g.Y(z), 0.85 * s, COL.newborn, c.h, 0.9);
        }
      }
      hud = "cycle " + cyc + "/" + C.cycles + " · " + nProg + " progenitors · " + nNeu + " neurons";
    }

    // pyramidal neurons waiting in the intermediate zone (stage 2)
    if (isStage("fate")) {
      for (const c of sc.vz) {
        if (c.exit > C.cycles) {
          drawProgenitor(ctx, g, g.X(c.x), g.Y(0.035), s, false, 0.8);
          continue;
        }
        drawMultipolar(ctx, g.X(c.x + 0.004 * Math.sin(time * 1.3 + c.h * 9)), g.Y(c.izZ), 0.85 * s, COL.newborn, c.h, 0.75);
      }
      const tauM = p * (C.mgeRounds + 0.6);
      let n = 0;
      for (const m of sc.mge) {
        const appear = m.born === 0 ? -1 : m.born - 1 + 0.6;
        if (tauM < appear) continue;
        n++;
        const sep = m.born === 0 ? 1 : ease((tauM - appear) / 0.35);
        const X = g.X(lerp(m.px, m.x, sep)), Y = g.Y(lerp(m.pz, m.z, sep));
        drawInterneuron(ctx, X + Math.sin(time * 2 + m.h * 7) * 0.6, Y, 0.9 * s, m.h, 1, 0);
      }
      hud = "MGE: " + n + " interneurons";
    }

    // ---------------- stage 3: migration
    if (isStage("migration")) {
      const R = sc.rec.migration.radial, steps = R.length - 1;
      let inL4 = 0;
      for (const c of sc.vz) {
        if (c.exit > C.cycles) {
          drawProgenitor(ctx, g, g.X(c.x), g.Y(0.035), s, false, 0.7);
          continue;
        }
        const k = c.k, p0 = 0.04 * (c.exit - 1) + 0.05 * c.h;
        const a = clamp01((p - p0) / 0.62);
        const sf = a * steps, n = Math.floor(sf), fr = sf - n;
        const step = Math.min(steps, n + ease((fr - 0.35) / 0.55)); // saltatory nucleokinesis
        const i0 = Math.min(steps, Math.floor(step)), i1 = Math.min(steps, i0 + 1), r = step - i0;
        const x = lerp(R[i0][k][0], R[i1][k][0], r);
        const zPath = lerp(R[i0][k][1], R[i1][k][1], r);
        const z = Math.max(zPath, Math.min(c.izZ, R[steps][k][1])); // multipolar pause in the intermediate zone
        const m = clamp01((p - p0 - 0.62) / 0.2);
        if (m > 0) {
          drawPyramidal(ctx, g, g.X(x), g.Y(z), s, COL.pyr, m, c.h, 1, 0);
        } else if (a < 0.02) {
          drawMultipolar(ctx, g.X(x), g.Y(z), 0.85 * s, COL.newborn, c.h, 0.85);
        } else {
          drawMigrating(ctx, g.X(x), g.Y(z), 0.85 * s, COL.newborn, 0, -1, 0.95, false);
        }
        const zf = R[steps][k][1];
        if (zf >= D.ZONES[5].z0 && zf < D.ZONES[5].z1 && m > 0.5) inL4++;
      }
      const T = sc.rec.migration.tangential, tsteps = T.length - 1, disp = sc.rec.migration.dispersed;
      let inside = 0;
      for (const m of sc.mge) {
        const k = m.k;
        let x, z, dir = 1, moving = true;
        if (p < 0.55) {
          const sf = (p / 0.55) * tsteps, i0 = Math.floor(sf), r = sf - i0, i1 = Math.min(tsteps, i0 + 1);
          x = lerp(T[i0][k][0], T[i1][k][0], r);
          z = lerp(T[i0][k][1], T[i1][k][1], r);
        } else if (p < 0.7) {
          const r = ease((p - 0.55) / 0.15);
          x = lerp(T[tsteps][k][0], disp[k][0], r);
          z = lerp(T[tsteps][k][1], disp[k][1], r);
        } else {
          const r = ease((p - 0.7) / 0.25);
          x = disp[k][0];
          z = lerp(disp[k][1], m.fz, r);
          dir = 0;
          moving = r < 1;
        }
        if (m.fx >= 0) inside++;
        const a = m.fx >= 0 ? 1 : 0.45;
        if (moving) drawMigrating(ctx, g.X(x), g.Y(z), 0.8 * s, COL.inter, dir, dir ? 0 : -1, a, true);
        else drawInterneuron(ctx, g.X(x), g.Y(z), 0.9 * s, m.h, a, 0);
      }
      hud = "neurons in L4: " + inL4 + " · interneurons in cortex: " + inside;
    }

    // ---------------- stages 4-6: the wired cortex
    if (isStage("axons") || isStage("refinement") || isStage("activity")) {
      for (const k of sc.glia) {
        const c = sc.vz[k];
        drawProgenitor(ctx, g, g.X(c.x), g.Y(0.035), s, false, 0.55);
      }
      let tick = 0, raster = null, mode = stage;
      if (isStage("refinement")) {
        tick = Math.min(sc.waveTicks - 1, Math.floor(clamp01(p / 0.6) * sc.waveTicks));
        raster = sc.wave;
      } else if (isStage("activity")) {
        tick = Math.min(sc.ticks - 1, Math.floor(clamp01(p / 0.97) * sc.ticks));
        raster = sc.raster;
      }
      if (raster) advanceRaster(st, raster, sc.N, sc.NT, tick, 10, mode);
      const ca = raster ? st.ca : null;

      // axons and branches
      let grown = 0, kept = 0;
      for (const ax of sc.axons) {
        let f = 1, alpha = 0.55;
        if (isStage("axons")) {
          const d = 0.06 * ax.h, fsp = (ax.sp) / (ax.pts.length - 1);
          const q = p - d;
          f = q < 0.4 ? fsp * ease(q / 0.4) : q < 0.5 ? fsp : fsp + (1 - fsp) * ease((q - 0.5) / 0.16);
          alpha = 0.7;
        } else if (isStage("activity")) {
          alpha = ax.kept > 0 ? 0.32 : 0.08;
        } else {
          alpha = 0.45;
        }
        const tip = drawAxon(ctx, g, ax, f, alpha, 0.9);
        if (isStage("axons") && f < 0.999) {
          drawGrowthCone(ctx, g, tip, axonPoint(g, ax, Math.max(0, f - 0.04)), ax.color, s, time + ax.h * 5);
        }
        if (f >= 0.999) {
          for (const br of ax.branches) {
            grown++;
            const bg = branchGeom(g, sc, ax, br);
            let bf = 1, ba = 0.5, col = ax.color;
            if (isStage("axons")) {
              bf = ease((p - 0.68 - 0.18 * br.h) / 0.14);
              ba = 0.55;
            } else if (isStage("refinement")) {
              if (!br.keep) {
                const r = clamp01((p - 0.62 - 0.1 * br.h) / 0.18);
                bf = 1 - 0.85 * ease(r);
                ba = 0.5 * (1 - 0.7 * r);
                col = r > 0.05 ? "#64748b" : ax.color;
              }
            } else if (isStage("activity")) {
              if (!br.keep) continue;
              ba = 0.28 + (ca ? 0.6 * Math.min(1, ca[ax.k]) : 0);
            }
            if (br.keep) kept++;
            drawBranch(ctx, bg, bf, col, ba, 0.7);
            if (bf >= 1 && (br.keep || !isStage("refinement") || p < 0.62)) {
              drawGlow(ctx, ax.color, bg.x1, bg.y1, 3 * s, 0.5);
            }
          }
        }
      }
      // action potentials in flight along thalamic axons
      if (raster && st.aps.length) {
        for (const ap of st.aps) {
          const ax = sc.axons[ap.k];
          if (isStage("activity") && ax.kept === 0) continue;
          const f = clamp01((tick - ap.t0) / 10);
          const pt = axonPoint(g, ax, f);
          drawGlow(ctx, "#ffffff", pt[0], pt[1], 4 * s, 0.9 * (1 - f * 0.3));
        }
      }
      // cortical cells
      for (let n = sc.NT; n < sc.N; n++) {
        const c = sc.cells[n], lit = ca ? Math.min(1, ca[n]) : 0;
        if (c.kind === 1) drawPyramidal(ctx, g, g.X(c.x), g.Y(c.z), s, COL.pyr, 1, c.h, 0.95, lit);
        else drawInterneuron(ctx, g.X(c.x), g.Y(c.z), 0.95 * s, c.h, 0.95, lit);
      }
      for (const m of sc.mge) { // interneurons that never left the MGE
        if (m.fx < 0) drawInterneuron(ctx, g.X(m.fx), g.Y(m.fz), 0.85 * s, m.h, 0.4, 0);
      }
      // thalamic relay cells
      for (const ax of sc.axons) {
        const X = g.X(ax.x), Y = g.thY, lit = ca ? Math.min(1, ca[ax.k]) : 0;
        drawGlow(ctx, ax.color, X, Y, (5 + 6 * lit) * s, 0.5 + 0.5 * lit);
        ctx.globalAlpha = 1;
        ctx.fillStyle = lit > 0.5 ? "#ffffff" : ax.color;
        ctx.beginPath();
        ctx.arc(X, Y, 2 * s, 0, 6.283);
        ctx.fill();
      }
      if (isStage("axons")) hud = "map slope " + sc.ph.slope.toFixed(2) + " · " + grown + " synapses";
      if (isStage("refinement")) {
        hud = p < 0.6 ? "spontaneous wave · tick " + tick + " ms" : "kept " + kept + " of " + grown + " inputs";
      }
      if (isStage("activity")) {
        const P = sc.C.period, k = Math.min(sc.order.length - 1, Math.floor(tick / P));
        const on = tick % P < sc.C.stimOn && Math.floor(tick / P) < sc.order.length;
        const sx = sc.C.stimuli[sc.order[k]];
        if (on) { // the stimulus: a spot of light on the thalamus
          drawGlow(ctx, "#ffffff", g.X(sx), g.thY, 16 * s, 0.35 + 0.15 * Math.sin(time * 20));
        }
        // readout ruler under the pia: true position (▼) and decoded position (◆) of the finished windows
        ctx.globalCompositeOperation = "source-over";
        const ry = g.top + 7;
        ctx.globalAlpha = 0.5;
        ctx.strokeStyle = "rgba(226,232,240,0.5)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(g.X(0), ry);
        ctx.lineTo(g.X(1), ry);
        ctx.stroke();
        for (let w = 0; w <= k; w++) {
          const done = tick >= w * P + sc.C.readoutLag + sc.C.readoutTicks;
          const tx = sc.C.stimuli[sc.order[w]], recent = w === k ? 1 : 0.35;
          ctx.globalAlpha = recent;
          ctx.fillStyle = "#ffffff";
          ctx.beginPath();
          ctx.moveTo(g.X(tx) - 4, ry - 7);
          ctx.lineTo(g.X(tx) + 4, ry - 7);
          ctx.lineTo(g.X(tx), ry - 1);
          ctx.fill();
          if (done) {
            const dx = sc.ev.decoded[w], err = Math.abs(dx - tx);
            ctx.fillStyle = err < 0.05 ? "#4ade80" : err < 0.12 ? "#facc15" : "#f87171";
            ctx.beginPath();
            ctx.moveTo(g.X(dx), ry + 1);
            ctx.lineTo(g.X(dx) + 4, ry + 5);
            ctx.lineTo(g.X(dx), ry + 9);
            ctx.lineTo(g.X(dx) - 4, ry + 5);
            ctx.fill();
          }
        }
        const doneK = tick >= k * P + sc.C.readoutLag + sc.C.readoutTicks;
        hud = "flash " + (k + 1) + "/7 at " + sx.toFixed(2) + (doneK ? " → decoded " + sc.ev.decoded[k].toFixed(2) : "");
      }
    }

    // labels
    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = 1;
    let fs = Math.max(8.5, 10.5 * Math.min(1.15, g.s0));
    ctx.font = "600 " + fs + "px -apple-system, Segoe UI, Roboto, sans-serif";
    while (fs > 7 && ctx.measureText(label.left).width + ctx.measureText(label.right).width + 28 > g.P.w) {
      fs -= 0.5;
      ctx.font = "600 " + fs + "px -apple-system, Segoe UI, Roboto, sans-serif";
    }
    ctx.textBaseline = "top";
    ctx.textAlign = "left";
    ctx.fillStyle = label.color;
    ctx.fillText(label.left, g.P.x + 8, g.P.y + 6);
    ctx.textAlign = "right";
    ctx.fillStyle = "#e2e8f0";
    ctx.fillText(label.right, g.P.x + g.P.w - 8, g.P.y + 6);
    if (hud) {
      ctx.font = Math.round(9.5 * Math.min(1.15, g.s)) + "px SFMono-Regular, Menlo, Consolas, monospace";
      ctx.textAlign = "left";
      ctx.textBaseline = "bottom";
      ctx.fillStyle = "rgba(4,7,13,0.65)";
      const w = ctx.measureText(hud).width;
      ctx.fillRect(g.x0 + 4, g.bot - 17, w + 8, 14);
      ctx.fillStyle = "#cbd5e1";
      ctx.fillText(hud, g.x0 + 8, g.bot - 5);
    }
    ctx.restore();
  }

  // ----------------------------------------------------------------------------------------------------------------
  // the page widget
  // ----------------------------------------------------------------------------------------------------------------
  function init(root) {
    const NG = window.NGJS;
    if (!NG || root.dataset.ready) return;
    root.dataset.ready = "1";
    const D = NG.CortexMapDemo;
    const STAGES = D.STAGES;
    const reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    root.innerHTML = "";
    const card = el("div", "ngx-card");
    root.appendChild(card);
    const head = el("div", "ngx-head");
    head.appendChild(el("div", "", '<h3 class="ngx-title">Evolve a cortical map, live in your browser</h3>' +
      '<p class="ngx-sub">Each individual is grown stage by stage by a JavaScript port of the toolbox and simulated ' +
      "with the integer <code>lif_int</code> kernel. Every generation, the best of the offspring becomes the parent. " +
      '<span class="ngx-where">Left: the founder. Right: the current champion.</span></p>'));
    const ctrl = el("div", "ngx-controls");
    const bRun = el("button", "ngx-btn primary", "▶ Evolve");
    const bStep = el("button", "ngx-btn", "Step");
    const bReset = el("button", "ngx-btn", "Reset");
    const bSeed = el("button", "ngx-btn", "New seed");
    bSeed.title = "Grow the founder and the champion again from another development seed";
    bStep.title = "Run one generation";
    bReset.title = "Back to the founder: generation 0, stage 1";
    [bRun, bStep, bReset, bSeed].forEach(function (b) {
      b.type = "button";
      ctrl.appendChild(b);
    });
    head.appendChild(ctrl);
    card.appendChild(head);

    const tabs = el("div", "ngx-tabs");
    tabs.setAttribute("role", "tablist");
    const tabEls = STAGES.map(function (st, i) {
      const b = el("button", "ngx-tab", '<b><span class="dot"></span>' + (i + 1) + ". " + st.label + "</b><span>" +
        TAG[st.key] + "</span><i></i>");
      b.type = "button";
      b.setAttribute("role", "tab");
      b.style.setProperty("--c", STAGE_COLOR[st.key]);
      b.addEventListener("click", function () {
        if (state.stage === i && !state.tour) {
          state.tour = true;
        } else {
          state.stage = i;
          state.t = 0;
          state.tour = false;
          applyPending();
        }
        state.speed = 1;
        updateStageText();
      });
      tabs.appendChild(b);
      return b;
    });
    card.appendChild(tabs);

    const wrap = el("div", "ngx-stage-wrap");
    const canvas = el("canvas", "ngx-slice");
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", "Animated cortical slices of the founder and of the champion genome");
    wrap.appendChild(canvas);
    const key = el("div", "ngx-key");
    key.setAttribute("aria-label", "Colour key of the slices");
    const turboStops = [0, 0.25, 0.5, 0.75, 1].map(function (x) { return turbo(x); }).join(", ");
    key.innerHTML =
      '<span><i class="tri" style="--k:' + COL.pyr + '"></i>pyramidal neuron</span>' +
      '<span><i class="dot" style="--k:' + COL.inter + '"></i>interneuron</span>' +
      '<span><i class="pill" style="--k:' + COL.glia + '"></i>radial glia (progenitor)</span>' +
      '<span><i class="bar" style="background:linear-gradient(90deg, ' + turboStops + ')"></i>thalamic axon, coloured by ' +
      "its position in the thalamus</span>" +
      '<span><i class="bar" style="background:#64748b"></i>eliminated synapse</span>' +
      '<span><i class="dot spike"></i>spike</span>';
    wrap.appendChild(key);
    card.appendChild(wrap);

    const cap = el("div", "ngx-caption");
    const capText = el("div", "");
    const capDelta = el("div", "ngx-delta");
    cap.appendChild(capText);
    cap.appendChild(capDelta);
    card.appendChild(cap);

    const evo = el("div", "ngx-evo");
    const boxChart = el("div", "ngx-box");
    const chartTitle = el("h5", "", "Fitness <em></em>");
    const chart = el("canvas", "ngx-chart");
    boxChart.appendChild(chartTitle);
    boxChart.appendChild(chart);
    boxChart.appendChild(el("div", "ngx-legend",
      '<span><i style="background:#4ade80"></i>champion, held-out seeds</span>' +
      '<span><i style="background:#7dd3fc"></i>best offspring</span>' +
      '<span><i style="background:#475569"></i>median offspring</span>' +
      '<span><i style="background:#94a3b8;height:1px"></i>founder</span>'));
    const opts = el("div", "ngx-row",
      '<label title="Offspring per generation">λ <input type="range" min="4" max="16" step="1" value="10"><output>10</output></label>' +
      '<label title="Mutation size on the [0, 1] gene coding">σ <input type="range" min="0.02" max="0.25" step="0.01" value="0.1"><output>0.10</output></label>' +
      '<label title="(1 + λ): the parent competes with its offspring"><input type="checkbox"> keep parent</label>' +
      '<label title="Wait 0.9 s after each generation, to follow the offspring"><input type="checkbox" checked> pause between generations</label>');
    boxChart.appendChild(opts);
    const boxGen = el("div", "ngx-box");
    const genTitle = el("h5", "", "Offspring of this generation <em></em>");
    const kids = el("div", "ngx-offspring");
    const genesTitle = el("h5", "", "Genome <em>drag a gene to edit it by hand</em>");
    const genes = el("div", "ngx-genes");
    boxGen.appendChild(genTitle);
    boxGen.appendChild(kids);
    boxGen.appendChild(genesTitle);
    boxGen.appendChild(genes);
    const bFromHere = el("button", "ngx-btn", "Evolve from this genome");
    bFromHere.type = "button";
    bFromHere.style.display = "none";
    bFromHere.style.marginTop = "6px";
    boxGen.appendChild(bFromHere);
    evo.appendChild(boxChart);
    evo.appendChild(boxGen);
    card.appendChild(evo);

    const foot = el("div", "ngx-foot");
    foot.innerHTML = '<details><summary><b>Fitness</b> = accuracy × response × efficiency</summary><p>' +
      "accuracy = exp(−RMSE / 0.08), RMSE = error of the decoded flash position (in sheet widths)<br>" +
      "response = mean over flashes of 1 − exp(−pyramidal spikes / 5)<br>" +
      "efficiency = exp(−(neurons / 1000 + thalamocortical synapses / 2500 + spikes per flash / 400))</p></details>" +
      "<div>Everything runs in this page. The functions are in <code>window.NGJS</code>: try " +
      "<code>NGJS.CortexMapDemo.assess(NGJS.CortexMapDemo.FOUNDER, [1, 2, 3])</code> in the console. " +
      '<a href="getting-started/playground.html">How the playground works →</a></div>';
    const det = el("details", "");
    det.innerHTML = "<summary>Champion genome (JSON)</summary><pre></pre>";
    foot.appendChild(det);
    card.appendChild(foot);

    // ---- state
    const state = {
      stage: 0, t: reduced ? DUR.neurogenesis : 0, tour: !reduced, speed: reduced ? 0 : 1, running: false,
      seed: 1, evo: null, founder: null, champ: null, pending: null, gen: 0, manual: false, lastGen: 0,
      founderVal: null, champVal: null, visible: true, stF: PanelState(), stC: PanelState(), editTimer: 0,
      lastRecord: null,
    };
    const lambdaIn = opts.querySelectorAll("input")[0], sigmaIn = opts.querySelectorAll("input")[1];
    const elitIn = opts.querySelectorAll("input")[2], slowIn = opts.querySelectorAll("input")[3];
    const outs = opts.querySelectorAll("output");

    function newEvolution() {
      state.evo = NG.Evolution({ lambda: +lambdaIn.value, sigma: +sigmaIn.value, elitism: elitIn.checked });
      state.gen = 0;
      state.lastRecord = null;
    }
    function rebuildScenes() {
      state.founder = buildScene(NG, D.FOUNDER, state.seed);
      const g = state.champ ? state.champ.genome : D.FOUNDER;
      state.champ = buildScene(NG, g, state.seed);
      state.stF = PanelState();
      state.stC = PanelState();
    }
    function applyPending() {
      if (!state.pending) return;
      state.champ = buildScene(NG, state.pending, state.seed);
      state.champShownGen = state.pendingGen;
      state.champShownFit = state.pendingFit;
      state.stC = PanelState();
      state.pending = null;
    }
    /** Back to the founder (generation 0) and to the start of the stage tour; evolution waits for Evolve or Step. */
    function reset() {
      state.running = false;
      state.manual = false;
      state.stage = 0;
      state.t = reduced ? DUR.neurogenesis : 0;
      state.tour = !reduced;
      state.speed = reduced ? 0 : 1;
      newEvolution();
      state.champ = null;
      state.pending = null;
      state.champShownGen = 0;
      state.pendingGen = 0;
      state.champShownFit = state.pendingFit = null;
      rebuildScenes();
      state.founderVal = D.assess(D.FOUNDER, [1, 2, 3]);
      state.champVal = state.founderVal;
      state.champGenome = D.FOUNDER;
      renderKids(null);
      renderGenes();
      updateStageText();
      updateButtons();
      drawChart();
    }

    // ---- gene table
    const geneRows = D.GENES.map(function (gene, k) {
      const row = el("div", "ngx-gene");
      row.style.setProperty("--c", STAGE_COLOR[gene.stage]);
      row.innerHTML = '<span class="dot"></span><span class="name"></span><input type="range" min="0" max="1000" step="1">' +
        '<canvas width="124" height="36"></canvas><span class="val"></span>';
      row.querySelector(".name").textContent = gene.label;
      row.querySelector(".name").title = gene.doc;
      const input = row.querySelector("input");
      input.setAttribute("aria-label", gene.label);
      input.addEventListener("input", function () {
        const u = NG.toUnit(state.champGenome, D.GENES);
        u[k] = +input.value / 1000;
        const genome = NG.fromUnit(D.FOUNDER, D.GENES, u);
        state.manual = true;
        state.running = false;
        state.champGenome = genome;
        row.querySelector(".val").textContent = fmtGene(gene, NG.getGene(genome, gene.path));
        clearTimeout(state.editTimer);
        state.editTimer = setTimeout(function () {
          state.champVal = D.assess(genome, [1, 2, 3]);
          state.champ = buildScene(NG, genome, state.seed);
          state.stC = PanelState();
          updateStageText();
          updateButtons();
          drawChart();
        }, 90);
        updateButtons();
      });
      genes.appendChild(row);
      return row;
    });
    function fmtGene(gene, v) {
      return gene.fmt === 0 ? String(Math.round(v)) : Number(v).toFixed(gene.fmt);
    }
    function renderGenes() {
      const u = NG.toUnit(state.champGenome, D.GENES), fu = NG.toUnit(D.FOUNDER, D.GENES);
      const hist = state.evo ? state.evo.history : [];
      D.GENES.forEach(function (gene, k) {
        const row = geneRows[k];
        row.querySelector("input").value = String(Math.round(u[k] * 1000));
        row.querySelector(".val").textContent = fmtGene(gene, NG.getGene(state.champGenome, gene.path));
        const cv = row.querySelector("canvas"), c = cv.getContext("2d");
        c.clearRect(0, 0, cv.width, cv.height);
        c.strokeStyle = "rgba(148,163,184,0.5)";
        c.setLineDash([2, 3]);
        c.beginPath();
        c.moveTo(0, 34 - 32 * fu[k]);
        c.lineTo(124, 34 - 32 * fu[k]);
        c.stroke();
        c.setLineDash([]);
        if (hist.length) {
          c.strokeStyle = STAGE_COLOR[gene.stage];
          c.lineWidth = 2;
          c.beginPath();
          const n = Math.max(2, hist.length + 1);
          c.moveTo(0, 34 - 32 * fu[k]);
          hist.forEach(function (h, i) {
            c.lineTo(((i + 1) / (n - 1)) * 122, 34 - 32 * h.u[k]);
          });
          c.stroke();
        }
      });
    }

    // ---- offspring tiles
    function renderKids(pd) {
      const list = pd ? pd.offspring : [];
      kids.innerHTML = "";
      list.forEach(function (o, j) {
        const tile = el("div", "ngx-kid" + (o.result ? "" : " pending") + (pd.best === j ? " best" : "") + (o.parent ? " parent" : ""));
        const cv = el("canvas");
        cv.width = 60;
        cv.height = 24;
        const c = cv.getContext("2d");
        D.GENES.forEach(function (gene, k) {
          c.fillStyle = STAGE_COLOR[gene.stage];
          const w = 60 / D.GENES.length, h = 3 + 20 * o.u[k];
          c.globalAlpha = 0.85;
          c.fillRect(k * w + 0.5, 24 - h, w - 1, h);
        });
        tile.appendChild(cv);
        tile.appendChild(el("div", "", o.result ? o.result.fitness.toFixed(3) : "…"));
        tile.title = o.parent ? "the parent (elitism)" : "offspring " + (j + 1);
        kids.appendChild(tile);
      });
      genTitle.querySelector("em").textContent = pd ? "generation " + (pd.generation + 1) + " · " +
        list.filter(function (o) { return o.result; }).length + "/" + list.length + " grown" : "press Evolve";
    }

    // ---- fitness chart
    function drawChart() {
      const dpr = window.devicePixelRatio || 1, w = chart.clientWidth || 300, h = Math.round(Math.max(120, w * 0.42));
      if (chart.width !== Math.round(w * dpr) || chart.height !== Math.round(h * dpr)) {
        chart.width = Math.round(w * dpr);
        chart.height = Math.round(h * dpr);
        chart.style.height = h + "px";
      }
      const c = chart.getContext("2d");
      c.setTransform(dpr, 0, 0, dpr, 0, 0);
      c.clearRect(0, 0, w, h);
      const hist = state.evo ? state.evo.history : [];
      const L = 30, R = 8, T = 8, B = 20;
      const G = Math.max(20, hist.length);
      let ymax = 0.1;
      hist.forEach(function (x) {
        ymax = Math.max(ymax, x.best, x.validation || 0);
      });
      if (state.champVal) ymax = Math.max(ymax, state.champVal.fitness);
      ymax = Math.ceil(ymax * 10 + 0.5) / 10;
      const X = function (i) { return L + (i / G) * (w - L - R); };
      const Y = function (v) { return h - B - (v / ymax) * (h - T - B); };
      c.font = "10px -apple-system, Segoe UI, Roboto, sans-serif";
      c.fillStyle = "#64748b";
      c.strokeStyle = "rgba(100,116,139,0.18)";
      c.textAlign = "right";
      c.textBaseline = "middle";
      for (let v = 0; v <= ymax + 1e-9; v += ymax > 0.5 ? 0.2 : 0.1) {
        c.beginPath();
        c.moveTo(L, Y(v));
        c.lineTo(w - R, Y(v));
        c.stroke();
        c.fillText(v.toFixed(1), L - 4, Y(v));
      }
      c.textAlign = "center";
      c.textBaseline = "top";
      for (let i = 0; i <= G; i += G > 40 ? 20 : 10) c.fillText(String(i), X(i), h - B + 4);
      if (state.founderVal) {
        c.strokeStyle = "rgba(148,163,184,0.7)";
        c.setLineDash([3, 3]);
        c.beginPath();
        c.moveTo(L, Y(state.founderVal.fitness));
        c.lineTo(w - R, Y(state.founderVal.fitness));
        c.stroke();
        c.setLineDash([]);
      }
      const line = function (key, color, width) {
        c.strokeStyle = color;
        c.lineWidth = width;
        c.beginPath();
        c.moveTo(X(0), Y(state.founderVal ? state.founderVal.fitness : 0));
        hist.forEach(function (x, i) {
          c.lineTo(X(i + 1), Y(x[key]));
        });
        c.stroke();
      };
      if (hist.length) {
        line("median", "#475569", 1);
        c.fillStyle = "#7dd3fc";
        hist.forEach(function (x, i) {
          c.beginPath();
          c.arc(X(i + 1), Y(x.best), 1.8, 0, 6.283);
          c.fill();
        });
        line("validation", "#4ade80", 2.2);
      }
      const last = hist.length ? hist[hist.length - 1].validation : state.founderVal ? state.founderVal.fitness : 0;
      chartTitle.querySelector("em").textContent = "generation " + hist.length + " · champion " + last.toFixed(3) +
        (state.founderVal ? " (founder " + state.founderVal.fitness.toFixed(3) + ")" : "");
    }

    // ---- captions and the founder -> champion table
    /** One founder -> champion row; a value that selection has not changed (yet) is shown as "same". */
    function row(label, f, c, title) {
      const same = f === c;
      return '<tr title="' + title.replace(/"/g, "&quot;") + '"><td>' + label + '</td><td class="v f">' + f +
        '</td><td class="arrow">' + (same ? "=" : "→") + '</td><td class="v c' + (same ? " same" : "") + '">' +
        (same ? "same" : c) + "</td></tr>";
    }
    function updateStageText() {
      const st = STAGES[state.stage], info = INFO[st.key];
      card.style.setProperty("--c", STAGE_COLOR[st.key]);
      cap.style.setProperty("--c", STAGE_COLOR[st.key]);
      capText.innerHTML = '<div class="ops"></div><h4></h4><p></p><p class="refs"></p>';
      capText.querySelector(".ops").textContent = st.ops;
      capText.querySelector("h4").textContent = info.title;
      capText.querySelector("p").textContent = info.text;
      capText.querySelector(".refs").textContent = info.refs;
      const genesHere = D.GENES.filter(function (g) { return g.stage === st.key; });
      let html = "<h5>What selection changed (mean of 3 held-out seeds)</h5><table>";
      html += '<tr><td></td><td class="v f">founder</td><td class="arrow"></td><td class="v c">' +
        (state.manual ? "edited" : "champion") + "</td></tr>";
      METRICS[st.key].forEach(function (m) {
        const f = state.founderVal ? state.founderVal.phenotype[m[1]] : null;
        const c = state.champVal ? state.champVal.phenotype[m[1]] : null;
        html += row(m[0], fmt(f, m[2]), fmt(c, m[2]), m[3]);
      });
      genesHere.forEach(function (gene) {
        html += row("gene: " + gene.label, fmtGene(gene, NG.getGene(D.FOUNDER, gene.path)),
          fmtGene(gene, NG.getGene(state.champGenome, gene.path)), gene.doc);
      });
      capDelta.innerHTML = html + "</table>";
      tabEls.forEach(function (b, i) {
        b.classList.toggle("active", i === state.stage);
        b.setAttribute("aria-selected", i === state.stage ? "true" : "false");
      });
      det.querySelector("pre").textContent = JSON.stringify(state.champGenome, null, 2);
    }
    function updateButtons() {
      bRun.textContent = state.running ? "⏸ Pause" : state.manual ? "▶ Resume evolution" : "▶ Evolve";
      bFromHere.style.display = state.manual ? "" : "none";
    }

    // ---- events
    bRun.addEventListener("click", function () {
      if (state.manual) {
        state.manual = false;
        state.champGenome = state.evo.parent || D.FOUNDER;
        state.champVal = state.lastRecord ? state.lastRecord.validation : state.founderVal;
        state.pending = state.champGenome;
        state.pendingGen = state.evo.history.length;
        state.pendingFit = state.champVal ? state.champVal.fitness : null;
      }
      state.running = !state.running;
      if (state.running && state.speed === 0) state.speed = 1;
      updateButtons();
      updateStageText();
    });
    bStep.addEventListener("click", function () {
      state.running = false;
      state.manual = false;
      const r = state.evo.step();
      onRecord(r);
      updateButtons();
    });
    bReset.addEventListener("click", reset);
    bSeed.addEventListener("click", function () {
      state.seed = 1 + ((state.seed * 7 + 3) % 97);
      if (state.champ) {
        state.pending = state.champ.genome;
        state.pendingGen = state.champShownGen;
        state.pendingFit = state.champShownFit;
      }
      state.founder = buildScene(NG, D.FOUNDER, state.seed);
      state.stF = PanelState();
      applyPending();
    });
    bFromHere.addEventListener("click", function () {
      state.evo.setParent(state.champGenome);
      state.manual = false;
      state.running = true;
      updateButtons();
    });
    lambdaIn.addEventListener("input", function () {
      outs[0].textContent = lambdaIn.value;
      state.evo.opts.lambda = +lambdaIn.value;
    });
    sigmaIn.addEventListener("input", function () {
      outs[1].textContent = Number(sigmaIn.value).toFixed(2);
      state.evo.opts.sigma = +sigmaIn.value;
    });
    elitIn.addEventListener("change", function () {
      state.evo.opts.elitism = elitIn.checked;
    });

    function onRecord(r) {
      state.lastRecord = r;
      state.champGenome = r.genome;
      state.champVal = r.validation;
      state.pending = r.genome;
      state.pendingGen = r.generation + 1;
      state.pendingFit = r.validation ? r.validation.fitness : r.bestFitness;
      // A new champion is shown at the next stage boundary (no jump mid-animation), except the first one.
      if (state.speed === 0 || state.champShownGen === 0) applyPending();
      renderKids(r);
      renderGenes();
      updateStageText();
      drawChart();
    }

    // ---- canvas size
    let layout = null;
    function resize() {
      const w = wrap.clientWidth - 24 > 0 ? wrap.clientWidth - (window.innerWidth < 760 ? 12 : 24) : 600;
      const stacked = w < 640;
      head.querySelector(".ngx-where").textContent = stacked ? "Top: the founder. Bottom: the current champion."
        : "Left: the founder. Right: the current champion.";
      const pw = stacked ? w : (w - 10) / 2, ph = Math.round(Math.min(430, Math.max(250, pw * (stacked ? 0.78 : 0.86))));
      const h = stacked ? 2 * ph + 10 : ph;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      canvas.style.height = h + "px";
      layout = { w: w, h: h, dpr: dpr,
        F: geometry({ x: 0, y: 0, w: pw, h: ph }),
        C: geometry(stacked ? { x: 0, y: ph + 10, w: pw, h: ph } : { x: pw + 10, y: 0, w: pw, h: ph }) };
      drawChart();
    }
    if (window.ResizeObserver) new ResizeObserver(function () { resize(); }).observe(wrap);
    window.addEventListener("resize", resize);
    if (window.IntersectionObserver) {
      new IntersectionObserver(function (es) {
        state.visible = es[0].isIntersecting;
      }).observe(card);
    }

    // ---- main loop
    const ctx = canvas.getContext("2d");
    let last = performance.now(), waitUntil = 0;
    function frame(now) {
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      if (state.visible && layout) {
        const key = STAGES[state.stage].key, dur = DUR[key];
        state.t += dt * state.speed;
        if (state.t >= dur) {
          if (state.tour) {
            state.stage = (state.stage + 1) % STAGES.length;
            state.t = 0;
            applyPending();
            updateStageText();
          } else if (state.speed > 0) {
            state.t = 0;
            applyPending();
          } else {
            state.t = dur;
          }
        }
        const k2 = STAGES[state.stage].key, p = clamp01(state.t / DUR[k2]);
        tabEls.forEach(function (b, i) {
          b.querySelector("i").style.width = i === state.stage ? (100 * p).toFixed(1) + "%" : "0";
        });
        ctx.setTransform(layout.dpr, 0, 0, layout.dpr, 0, 0);
        ctx.clearRect(0, 0, layout.w, layout.h);
        const time = now / 1000;
        drawPanel(ctx, layout.F, state.founder, D, k2, p, time, state.stF,
          { left: "FOUNDER · generation 0", right: "fitness " + state.founderVal.fitness.toFixed(3), color: "#94a3b8" });
        const cg = state.manual ? "EDITED BY HAND" : state.champShownGen === 0 ? "CHAMPION SO FAR = FOUNDER · gen. 0"
          : "CHAMPION · generation " + state.champShownGen;
        drawPanel(ctx, layout.C, state.champ, D, k2, p, time, state.stC,
          { left: cg, right: "fitness " + fmt(state.manual ? state.champVal && state.champVal.fitness
            : state.champShownFit === null ? state.founderVal.fitness : state.champShownFit, 3), color: "#4ade80" });
        // evolution between frames
        if (state.running && now >= waitUntil) {
          const r = state.evo.work(6);
          if (state.evo.pending) renderKids(Object.assign({ generation: state.evo.generation }, state.evo.pending));
          if (r) {
            onRecord(r);
            waitUntil = now + (slowIn.checked ? 900 : 0);
            if (state.evo.history.length % 40 === 0) {
              state.running = false;
              updateButtons();
            }
          }
        }
      }
      requestAnimationFrame(frame);
    }

    newEvolution();
    reset();
    // Run the first generations before the first paint, so that the two slices already differ. Deterministic: the
    // evolution's random stream is seeded (island 0), so every visitor sees the same generation-PREWARM champion.
    for (let k = 0; k < PREWARM; k++) onRecord(state.evo.step());
    applyPending();
    resize();
    if (!reduced) {
      state.running = true;
      updateButtons();
    }
    requestAnimationFrame(frame);
  }

  function boot() {
    const root = document.getElementById("ng-hero-anim-root");
    if (root) init(root);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
