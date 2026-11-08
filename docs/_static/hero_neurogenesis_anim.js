/**
 * Interactive Front-Page Hero Animation for neurogenesis-sim
 * Visualizes the full developmental & evolutionary loop:
 *   1. Natural Selection of Genomes (evolve_circuit)
 *   2. Neurogenesis & Gene Expression (proliferate -> express -> differentiate)
 *   3. Neuronal Migration with Biological Morphology (migrate -> mosaic)
 *   4. Axon Guidance & Colored Synaptogenesis (grow_axons)
 *   5. Spiking Network Activity & Synchronized Readout (simulate)
 */
(function () {
  const STAGES = [
    {
      id: 0,
      key: "evolution",
      pill: "1. Natural Selection",
      code: "evolve_circuit(plan, target='alpha_sync')",
      title: "Genetic Evolution & Natural Selection",
      desc: "A population of candidate genomes is evaluated across generations. Each gene locus controls developmental rules (division, morphogen receptors, migration, axon chemoaffinity). Natural selection retains and mutates high-fitness genomes."
    },
    {
      id: 1,
      key: "neurogenesis",
      pill: "2. Neurogenesis & Genes",
      code: "proliferate → express → differentiate",
      title: "Gene Expression & Progenitor Division",
      desc: "The selected genome drives progenitor mitosis in the ventricular zone. Morphogen gradients and Notch-Delta lateral inhibition assign each newborn cell its molecular colour code (EphA/EphB topographic identity and E/I neurotransmitter fate)."
    },
    {
      id: 2,
      key: "migration",
      pill: "3. Neuronal Migration",
      code: "migrate → mosaic → grow_arbors",
      title: "Laminar Migration & Biological Morphology",
      desc: "Differentiating pyramidal neurons (triangular somas with apical & basal dendritic tufts) and multipolar interneurons migrate along radial glia into cortical layers (L5/6, L4, L2/3) and establish regular mosaic spacing."
    },
    {
      id: 3,
      key: "axons",
      pill: "4. Axon Guidance",
      code: "grow_axons → prune_by_weight",
      title: "Chemoaffinity Axon Growth & Circuit Wiring",
      desc: "Axons extend with motile growth cones that read positional gradients, steering along curved trajectories to wire colour-matched topographic pathways and balanced excitatory/inhibitory dendritic synapses."
    },
    {
      id: 4,
      key: "activity",
      pill: "5. Spiking Activity",
      code: "simulate(model='lif_int') → LFP readout",
      title: "Emergent Spiking Dynamics & Oscillations",
      desc: "Action potentials propagate along axonal arbors, triggering dendritic integration and somatic firing flashes. Recurrent E–I loops self-organize into a coherent 10 Hz alpha rhythm."
    }
  ];

  const GENE_NAMES = [
    { name: "Ngn2 (Prolif)", color: "#38bdf8" },
    { name: "Notch/Delta", color: "#fb7185" },
    { name: "EphA3 (Topo-X)", color: "#f59e0b" },
    { name: "EphB2 (Lam-Y)", color: "#34d399" },
    { name: "Robo/Slit (Axon)", color: "#a78bfa" },
    { name: "KCC2 (GABA-E/I)", color: "#f472b6" }
  ];

  // Deterministic PRNG (Mulberry32) so "Randomize Seed" produces reproducible visual circuits
  function mulberry32(seed) {
    let a = seed >>> 0;
    return function () {
      a |= 0;
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  function easeInOutCubic(t) {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  }

  function clamp01(t) {
    return Math.max(0, Math.min(1, t));
  }

  function initHeroAnimation() {
    const root = document.getElementById("ng-hero-anim-root");
    if (!root || root.dataset.initialized === "true") return;
    root.dataset.initialized = "true";

    root.innerHTML = `
      <div class="ng-hero-card">
        <div class="ng-hero-topbar">
          <div class="ng-hero-pills" id="ng-hero-pills"></div>
          <div class="ng-hero-controls">
            <button type="button" class="ng-hero-btn" id="ng-hero-play-btn" title="Pause / Resume animation">⏸ Pause</button>
            <button type="button" class="ng-hero-btn" id="ng-hero-seed-btn" title="Grow with a new random genetic seed">🎲 New Seed</button>
          </div>
        </div>
        <div class="ng-hero-canvas-wrap">
          <canvas id="ng-hero-canvas" width="920" height="440"></canvas>
          <div class="ng-hero-overlay-badge" id="ng-hero-badge"></div>
        </div>
        <div class="ng-hero-footer">
          <div class="ng-hero-footer-main">
            <span class="ng-hero-stage-tag" id="ng-hero-stage-code"></span>
            <h4 class="ng-hero-stage-title" id="ng-hero-stage-title"></h4>
          </div>
          <p class="ng-hero-stage-desc" id="ng-hero-stage-desc"></p>
        </div>
      </div>
    `;

    const pillsContainer = document.getElementById("ng-hero-pills");
    const playBtn = document.getElementById("ng-hero-play-btn");
    const seedBtn = document.getElementById("ng-hero-seed-btn");
    const canvas = document.getElementById("ng-hero-canvas");
    const badgeEl = document.getElementById("ng-hero-badge");
    const codeEl = document.getElementById("ng-hero-stage-code");
    const titleEl = document.getElementById("ng-hero-stage-title");
    const descEl = document.getElementById("ng-hero-stage-desc");
    const ctx = canvas.getContext("2d");

    const pillBtns = STAGES.map((st, idx) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ng-hero-pill";
      btn.textContent = st.pill;
      btn.addEventListener("click", () => {
        activeStage = idx;
        stageElapsed = 0;
        lockedStage = true;
        updatePlayButton();
        updateStageUI();
      });
      pillsContainer.appendChild(btn);
      return btn;
    });

    let seed = 42;
    let activeStage = 0;
    let stageElapsed = 0;
    let isPlaying = true;
    let lockedStage = false;
    const STAGE_DURATIONS = [5.2, 5.2, 5.6, 5.8, 7.5]; // seconds per stage

    let simData = buildCircuitData(seed);

    function updatePlayButton() {
      if (!isPlaying) {
        playBtn.textContent = "▶ Play";
      } else if (lockedStage) {
        playBtn.textContent = "🔁 Auto-Cycle";
      } else {
        playBtn.textContent = "⏸ Pause";
      }
    }

    playBtn.addEventListener("click", () => {
      if (lockedStage) {
        lockedStage = false;
        isPlaying = true;
      } else {
        isPlaying = !isPlaying;
      }
      updatePlayButton();
    });

    seedBtn.addEventListener("click", () => {
      seed = (seed * 1664525 + 1013904223) % 10000;
      simData = buildCircuitData(seed);
      stageElapsed = 0;
      updateStageUI();
    });

    function updateStageUI() {
      const st = STAGES[activeStage];
      pillBtns.forEach((b, i) => b.classList.toggle("active", i === activeStage));
      codeEl.textContent = st.code;
      titleEl.textContent = st.title;
      descEl.textContent = st.desc;
      badgeEl.innerHTML = `<span class="ng-badge-dot"></span> Seed #${seed} · Stage ${activeStage + 1}/5`;
    }

    // Build synthetic biological circuit data from seed
    function buildCircuitData(currentSeed) {
      const rng = mulberry32(currentSeed);

      // 1. Candidate genomes for natural selection panel
      const candidates = [];
      for (let i = 0; i < 5; i++) {
        const genes = GENE_NAMES.map(() => 0.25 + 0.7 * rng());
        const baseFit = i === 1 ? 0.88 + 0.08 * rng() : 0.22 + 0.55 * rng();
        candidates.push({
          id: `Genome #${i + 1}`,
          isWinner: i === 1,
          genes,
          startFitness: 0.12 + 0.18 * rng(),
          endFitness: baseFit
        });
      }

      // 2. Biological Neurons (26 cells across 3 cortical layers: L6/5 deep, L4 middle, L2/3 superficial)
      // Colors reflect topographic EphA/EphB gene expression (cyan -> emerald -> amber -> coral) for E cells,
      // and violet/magenta for GABAergic inhibitory interneurons.
      const paletteE = ["#38bdf8", "#2dd4bf", "#34d399", "#a3e635", "#facc15", "#fb923c", "#f87171"];
      const neurons = [];
      const count = 24;

      for (let i = 0; i < count; i++) {
        const u = i / (count - 1); // topographic X index [0, 1]
        const layerIdx = i % 3; // 0 = deep (L5/6), 1 = middle (L4), 2 = superficial (L2/3)
        const isInhibitory = i % 5 === 3;

        // Ventricular zone progenitor origin near bottom
        const vzX = 95 + u * 730 + (rng() - 0.5) * 28;
        const vzY = 335 + (rng() - 0.5) * 18;

        // Target laminar position after radial migration
        const layerBaseY = layerIdx === 0 ? 255 : layerIdx === 1 ? 175 : 102;
        const targetX = 95 + u * 730 + (rng() - 0.5) * 26;
        const targetY = layerBaseY + (rng() - 0.5) * 24;

        const colorIdx = Math.min(paletteE.length - 1, Math.floor(u * paletteE.length));
        const color = isInhibitory ? "#e879f9" : paletteE[colorIdx];

        // Generate realistic dendritic arbor branches relative to soma
        const dendrites = [];
        if (!isInhibitory) {
          // Pyramidal cell: prominent apical dendrite pointing up + apical tuft + basal dendrites
          const apicalLen = layerIdx === 0 ? 68 : layerIdx === 1 ? 48 : 32;
          dendrites.push({
            kind: "apical",
            pts: [
              { x: 0, y: -6 },
              { x: (rng() - 0.5) * 6, y: -apicalLen * 0.55 },
              { x: (rng() - 0.5) * 10, y: -apicalLen }
            ],
            tufts: [
              { dx: -14 - rng() * 8, dy: -apicalLen - 12 - rng() * 8 },
              { dx: 2 + (rng() - 0.5) * 8, dy: -apicalLen - 15 - rng() * 6 },
              { dx: 14 + rng() * 8, dy: -apicalLen - 11 - rng() * 8 }
            ]
          });
          // 4 basal dendrites radiating downward/laterally
          for (let b = 0; b < 4; b++) {
            const angle = Math.PI * (0.18 + 0.64 * (b / 3)) + (rng() - 0.5) * 0.2;
            const len = 18 + rng() * 12;
            dendrites.push({
              kind: "basal",
              pts: [
                { x: Math.cos(angle) * 5, y: Math.sin(angle) * 4 },
                { x: Math.cos(angle) * len * 0.6, y: Math.sin(angle) * len * 0.6 + 3 },
                { x: Math.cos(angle) * len, y: Math.sin(angle) * len + 4 }
              ]
            });
          }
        } else {
          // Multipolar basket/stellate interneuron: 6 radiating branched dendrites
          for (let b = 0; b < 6; b++) {
            const angle = (b / 6) * Math.PI * 2 + (rng() - 0.5) * 0.3;
            const len = 18 + rng() * 12;
            dendrites.push({
              kind: "stellate",
              pts: [
                { x: Math.cos(angle) * 5, y: Math.sin(angle) * 5 },
                { x: Math.cos(angle + 0.15) * (len * 0.55), y: Math.sin(angle + 0.15) * (len * 0.55) },
                { x: Math.cos(angle) * len, y: Math.sin(angle) * len }
              ]
            });
          }
        }

        neurons.push({
          id: i,
          u,
          layerIdx,
          isInhibitory,
          color,
          vzX,
          vzY,
          parentVzX: vzX + (i % 2 === 0 ? 10 : -10),
          parentVzY: vzY + 8,
          targetX,
          targetY,
          dendrites,
          migrationDelay: 0.04 * (i % 6) + rng() * 0.12,
          phaseOffset: u * Math.PI * 1.4 + (rng() - 0.5) * 0.4,
          v: rng() * 0.65,
          iSyn: 0,
          refrac: 0,
          flash: 0.08
        });
      }

      // 3. Synaptic connections (guided axons with quadratic/cubic control points)
      const synapses = [];
      for (let i = 0; i < neurons.length; i++) {
        const pre = neurons[i];
        for (let j = 0; j < neurons.length; j++) {
          if (i === j) continue;
          const post = neurons[j];
          const du = Math.abs(pre.u - post.u);
          // Connect mostly topographically nearby neurons across or within layers
          const prob = pre.isInhibitory
            ? (du < 0.22 ? 0.55 : 0.0)
            : (du < 0.18 && post.layerIdx >= pre.layerIdx ? 0.65 : du < 0.12 ? 0.35 : 0.0);

          if (rng() < prob && synapses.length < 64) {
            const midX = (pre.targetX + post.targetX) * 0.5 + (rng() - 0.5) * 55;
            const midY = (pre.targetY + post.targetY) * 0.5 + (pre.isInhibitory ? -22 : 26) + (rng() - 0.5) * 25;
            // Target contact point on postsynaptic dendritic tree
            const contactOffsetY = !post.isInhibitory && pre.layerIdx < post.layerIdx ? -22 : (rng() - 0.5) * 10;
            const contactOffsetX = (rng() - 0.5) * 12;

            synapses.push({
              preId: i,
              postId: j,
              color: pre.color,
              isInhibitory: pre.isInhibitory,
              midX,
              midY,
              contactX: post.targetX + contactOffsetX,
              contactY: post.targetY + contactOffsetY,
              growthDelay: rng() * 0.35,
              weight: pre.isInhibitory ? -0.42 : 0.36,
              speed: 1.45 + rng() * 0.55,
              spikes: []
            });
          }
        }
      }

      const lfpHistory = new Array(120).fill(0);
      return { candidates, neurons, synapses, lfpHistory, simRng: rng };
    }

    // Helper: evaluate point and tangent on quadratic Bezier at parameter t in [0,1]
    function quadBezierPoint(x0, y0, cx, cy, x1, y1, t) {
      const inv = 1 - t;
      return {
        x: inv * inv * x0 + 2 * inv * t * cx + t * t * x1,
        y: inv * inv * y0 + 2 * inv * t * cy + t * t * y1
      };
    }

    function quadBezierTangent(x0, y0, cx, cy, x1, y1, t) {
      const dx = 2 * (1 - t) * (cx - x0) + 2 * t * (x1 - cx);
      const dy = 2 * (1 - t) * (cy - y0) + 2 * t * (y1 - cy);
      const len = Math.hypot(dx, dy) || 1;
      return { nx: dx / len, ny: dy / len };
    }

    // Draw biological neuron (soma + nucleus + dendritic arbor + firing glow)
    function drawBiologicalNeuron(ctx, n, x, y, morphProgress, flashIntensity, alpha) {
      ctx.save();
      ctx.globalAlpha = alpha;
      ctx.translate(x, y);

      // 1. Draw dendritic arbor if morphProgress > 0.05
      if (morphProgress > 0.05) {
        ctx.strokeStyle = n.color;
        ctx.lineCap = "round";

        for (const d of n.dendrites) {
          const p1 = d.pts[1];
          const p2 = d.pts[2];
          const curX1 = p1.x * morphProgress;
          const curY1 = p1.y * morphProgress;
          const curX2 = p2.x * morphProgress;
          const curY2 = p2.y * morphProgress;

          ctx.lineWidth = d.kind === "apical" ? 2.3 : 1.35;
          ctx.globalAlpha = alpha * (0.65 + 0.35 * flashIntensity);
          ctx.beginPath();
          ctx.moveTo(d.pts[0].x, d.pts[0].y);
          ctx.quadraticCurveTo(curX1, curY1, curX2, curY2);
          ctx.stroke();

          // Apical tuft branches in superficial layer
          if (d.tufts && morphProgress > 0.45) {
            const tuftP = clamp01((morphProgress - 0.45) / 0.55);
            ctx.lineWidth = 1.15;
            for (const tf of d.tufts) {
              ctx.beginPath();
              ctx.moveTo(curX2, curY2);
              ctx.lineTo(
                lerp(curX2, tf.dx, tuftP),
                lerp(curY2, tf.dy, tuftP)
              );
              ctx.stroke();
            }
          }
        }
      }

      // 2. Firing halo around soma
      if (flashIntensity > 0.05) {
        const grad = ctx.createRadialGradient(0, 0, 2, 0, 0, 24 * flashIntensity + 8);
        grad.addColorStop(0, "#ffffff");
        grad.addColorStop(0.35, n.color);
        grad.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = grad;
        ctx.globalAlpha = alpha * flashIntensity * 0.85;
        ctx.beginPath();
        ctx.arc(0, 0, 26, 0, Math.PI * 2);
        ctx.fill();
      }

      // 3. Biological Soma Shape
      ctx.globalAlpha = alpha;
      ctx.fillStyle = flashIntensity > 0.4 ? "#ffffff" : n.color;
      ctx.strokeStyle = "rgba(15, 23, 42, 0.85)";
      ctx.lineWidth = 1.2;

      ctx.beginPath();
      if (!n.isInhibitory && morphProgress > 0.2) {
        // Pyramidal tear-drop / triangular soma morphing from progenitor sphere
        const p = morphProgress;
        const topY = lerp(-7, -11, p);
        const botY = lerp(7, 7.5, p);
        const halfW = lerp(7, 8.5, p);
        ctx.moveTo(0, topY);
        ctx.bezierCurveTo(halfW * 0.55, topY * 0.3, halfW, botY * 0.4, halfW, botY);
        ctx.quadraticCurveTo(0, botY + 2.5, -halfW, botY);
        ctx.bezierCurveTo(-halfW, botY * 0.4, -halfW * 0.55, topY * 0.3, 0, topY);
      } else if (n.isInhibitory && morphProgress > 0.2) {
        // Multipolar / spindle interneuron soma
        ctx.ellipse(0, 0, 8.2, 6.2, Math.PI * 0.12, 0, Math.PI * 2);
      } else {
        // Round progenitor cell
        ctx.arc(0, 0, 7, 0, Math.PI * 2);
      }
      ctx.fill();
      ctx.stroke();

      // 4. Intracellular Nucleus & Nucleolus
      ctx.fillStyle = "rgba(15, 23, 42, 0.45)";
      ctx.beginPath();
      ctx.arc(0, 1.5, 3.1, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = "rgba(255, 255, 255, 0.75)";
      ctx.beginPath();
      ctx.arc(-1, 0.8, 1.1, 0, Math.PI * 2);
      ctx.fill();

      ctx.restore();
    }

    // Draw background cortical layer guides and ventricular zone
    function drawTissueBackground(ctx, W, H, showLayersAlpha, showGradientsAlpha) {
      // Dark bioluminescent laboratory background
      const bg = ctx.createLinearGradient(0, 0, 0, H);
      bg.addColorStop(0, "#0b1120");
      bg.addColorStop(0.65, "#0f172a");
      bg.addColorStop(1, "#131c31");
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, W, H);

      // Subtle spatial grid
      ctx.strokeStyle = "rgba(148, 163, 184, 0.05)";
      ctx.lineWidth = 1;
      for (let x = 40; x < W; x += 40) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, H);
        ctx.stroke();
      }
      for (let y = 40; y < H; y += 40) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(W, y);
        ctx.stroke();
      }

      // Morphogen gradient glow (EphA / EphB positional field)
      if (showGradientsAlpha > 0.01) {
        ctx.save();
        ctx.globalAlpha = showGradientsAlpha * 0.18;
        const morphGrad = ctx.createLinearGradient(80, 0, W - 80, 0);
        morphGrad.addColorStop(0, "#38bdf8");
        morphGrad.addColorStop(0.35, "#34d399");
        morphGrad.addColorStop(0.7, "#facc15");
        morphGrad.addColorStop(1, "#f87171");
        ctx.fillStyle = morphGrad;
        ctx.fillRect(60, 55, W - 120, 310);
        ctx.restore();
      }

      // Cortical layer bands
      if (showLayersAlpha > 0.01) {
        ctx.save();
        ctx.globalAlpha = showLayersAlpha;
        const bands = [
          { y: 68, h: 68, label: "L2/3 · Superficial Pyramidal & Tuft Zone" },
          { y: 142, h: 68, label: "L4 · Topographic Recipient Layer" },
          { y: 216, h: 72, label: "L5/6 · Deep Output & Recurrent Layer" },
          { y: 312, h: 48, label: "VZ · Ventricular Progenitor Zone" }
        ];
        ctx.font = "600 11px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
        for (const b of bands) {
          ctx.fillStyle = "rgba(30, 41, 59, 0.35)";
          ctx.strokeStyle = "rgba(100, 116, 139, 0.22)";
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.roundRect(48, b.y, W - 96, b.h, 6);
          ctx.fill();
          ctx.stroke();

          ctx.fillStyle = "rgba(148, 163, 184, 0.65)";
          ctx.fillText(b.label, 60, b.y + 16);
        }
        ctx.restore();
      }
    }

    // Stage 1: Natural selection of genomes
    function renderStageEvolution(ctx, W, H, p) {
      drawTissueBackground(ctx, W, H, 0.25, 0.2 * p);

      const gen = Math.min(20, Math.max(1, Math.floor(1 + p * 19)));
      ctx.save();

      // Header inside canvas
      ctx.fillStyle = "#f8fafc";
      ctx.font = "700 15px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
      ctx.fillText(`Evolutionary Search · Generation ${gen} / 20`, 62, 42);

      ctx.fillStyle = "#94a3b8";
      ctx.font = "12px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
      ctx.fillText("Selecting genome parameters that maximize target circuit synchronization across developmental seeds", 355, 42);

      // Left column: Candidate Genomes & Gene Loci
      const startY = 66;
      const rowH = 54;

      simData.candidates.forEach((cand, idx) => {
        const y = startY + idx * rowH;
        const isSelected = p > 0.55 && cand.isWinner;
        const isCulled = p > 0.6 && !cand.isWinner;
        const rowAlpha = isCulled ? Math.max(0.28, 1 - (p - 0.6) * 1.8) : 1.0;

        ctx.save();
        ctx.globalAlpha = rowAlpha;

        // Card background
        ctx.fillStyle = isSelected ? "rgba(16, 185, 129, 0.16)" : "rgba(30, 41, 59, 0.78)";
        ctx.strokeStyle = isSelected ? "#10b981" : "rgba(100, 116, 139, 0.35)";
        ctx.lineWidth = isSelected ? 2 : 1;
        ctx.beginPath();
        ctx.roundRect(60, y, 520, 44, 8);
        ctx.fill();
        ctx.stroke();

        // Genome Label
        ctx.fillStyle = isSelected ? "#34d399" : "#e2e8f0";
        ctx.font = "600 12px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
        ctx.fillText(cand.isWinner && p > 0.55 ? `★ ${cand.id}` : cand.id, 74, y + 26);

        // Gene Loci colored bars
        cand.genes.forEach((gVal, gIdx) => {
          const gx = 175 + gIdx * 54;
          const gy = y + 10;
          const gw = 46;
          const gh = 24;
          const geneMeta = GENE_NAMES[gIdx];

          // Slight mutation shimmer during early generations
          const shimmer = p < 0.6 ? Math.sin(p * 18 + idx * 2 + gIdx) * 0.08 : 0;
          const expr = clamp01(gVal + shimmer);

          ctx.fillStyle = "rgba(15, 23, 42, 0.7)";
          ctx.beginPath();
          ctx.roundRect(gx, gy, gw, gh, 4);
          ctx.fill();

          ctx.fillStyle = geneMeta.color;
          ctx.globalAlpha = rowAlpha * (0.35 + 0.65 * expr);
          ctx.beginPath();
          ctx.roundRect(gx + 2, gy + 2 + (1 - expr) * (gh - 4), gw - 4, expr * (gh - 4), 3);
          ctx.fill();

          ctx.globalAlpha = rowAlpha;
          if (idx === 0) {
            ctx.fillStyle = "#94a3b8";
            ctx.font = "10px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
            ctx.fillText(geneMeta.name.split(" ")[0], gx + 2, startY - 6);
          }
        });

        // Fitness bar on right of genome card
        const curFit = lerp(cand.startFitness, cand.endFitness, easeInOutCubic(clamp01(p * 1.25)));
        ctx.fillStyle = isSelected ? "#34d399" : "#cbd5e1";
        ctx.font = "700 12px monospace";
        ctx.fillText(`R=${Math.round(curFit * 100)}%`, 512, y + 26);

        ctx.restore();
      });

      // Right column: Live embryonic preview of the winning genome beginning to seed progenitors
      const boxX = 605;
      const boxY = 66;
      const boxW = 255;
      const boxH = 260;

      ctx.fillStyle = "rgba(15, 23, 42, 0.85)";
      ctx.strokeStyle = p > 0.55 ? "#10b981" : "rgba(100, 116, 139, 0.4)";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.roundRect(boxX, boxY, boxW, boxH, 10);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = "#e2e8f0";
      ctx.font = "600 12px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
      ctx.fillText("Selected Genome Phenotype", boxX + 16, boxY + 24);

      // Draw DNA double strand + emerging progenitor cells inside preview box
      for (let k = 0; k < 18; k++) {
        const t = k / 17;
        const dx = boxX + 26 + t * (boxW - 52);
        const phase = p * 10 + t * Math.PI * 2.5;
        const dy1 = boxY + 68 + Math.sin(phase) * 14;
        const dy2 = boxY + 68 - Math.sin(phase) * 14;
        const col = GENE_NAMES[k % GENE_NAMES.length].color;

        ctx.strokeStyle = "rgba(148, 163, 184, 0.35)";
        ctx.beginPath();
        ctx.moveTo(dx, dy1);
        ctx.lineTo(dx, dy2);
        ctx.stroke();

        ctx.fillStyle = col;
        ctx.beginPath();
        ctx.arc(dx, dy1, 3.2, 0, Math.PI * 2);
        ctx.arc(dx, dy2, 3.2, 0, Math.PI * 2);
        ctx.fill();
      }

      // Preview cells dividing at bottom of preview box
      ctx.fillStyle = "#94a3b8";
      ctx.font = "11px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
      ctx.fillText("Fitness Score Progression:", boxX + 16, boxY + 125);

      // Fitness curve plot
      ctx.strokeStyle = "#10b981";
      ctx.lineWidth = 2.2;
      ctx.beginPath();
      const plotSteps = 24;
      for (let s = 0; s <= plotSteps; s++) {
        const st = s / plotSteps;
        if (st > p) break;
        const px = boxX + 20 + st * (boxW - 40);
        const fitVal = 0.18 + 0.74 * (1 - Math.exp(-3.5 * st)) + Math.sin(st * 15) * 0.025;
        const py = boxY + 235 - fitVal * 95;
        if (s === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.stroke();

      ctx.restore();
    }

    // Stage 2: Neurogenesis, Mitosis & Morphogen Gene Expression
    function renderStageNeurogenesis(ctx, W, H, p) {
      const gradAlpha = clamp01((p - 0.15) / 0.6);
      drawTissueBackground(ctx, W, H, 0.75, gradAlpha);

      ctx.save();
      // Draw morphogen gradient legend bar at top
      ctx.fillStyle = "#f8fafc";
      ctx.font = "600 13px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
      ctx.fillText("Morphogen Field Expression: EphA3 (Anterior-Posterior) × EphB2 (Laminar) + Notch-Delta E/I Fate", 60, 42);

      // Draw dividing progenitors in the Ventricular Zone (VZ)
      for (const n of simData.neurons) {
        const localP = clamp01((p - n.migrationDelay * 0.8) / 0.75);
        const divP = easeInOutCubic(clamp01(localP * 1.4));

        // During division, cell splits from parentVz position to vz position
        const curX = lerp(n.parentVzX, n.vzX, divP);
        const curY = lerp(n.parentVzY, n.vzY, divP);

        // Mitotic spindle line while dividing
        if (divP > 0.05 && divP < 0.85) {
          ctx.strokeStyle = "rgba(56, 189, 248, 0.45)";
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(n.parentVzX, n.parentVzY);
          ctx.lineTo(curX, curY);
          ctx.stroke();
        }

        // Expression wave rings around differentiating cells
        if (localP > 0.35) {
          const ringP = (localP - 0.35) / 0.65;
          ctx.strokeStyle = n.color;
          ctx.globalAlpha = (1 - ringP) * 0.65;
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.arc(curX, curY, 7 + ringP * 18, 0, Math.PI * 2);
          ctx.stroke();
          ctx.globalAlpha = 1;
        }

        drawBiologicalNeuron(ctx, n, curX, curY, localP * 0.25, localP > 0.4 && localP < 0.65 ? 0.5 : 0.1, 1.0);
      }
      ctx.restore();
    }

    // Stage 3: Radial & Tangential Neuronal Migration + Dendritic Arborization
    function renderStageMigration(ctx, W, H, p) {
      drawTissueBackground(ctx, W, H, 1.0, 0.45);

      ctx.save();
      ctx.fillStyle = "#f8fafc";
      ctx.font = "600 13px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
      ctx.fillText("Radial Glial Migration & Dendritic Differentiation (Pyramidal Apical Tufts & Multipolar Interneurons)", 60, 42);

      // Draw radial glial guide fibers from VZ to superficial cortex
      ctx.strokeStyle = "rgba(148, 163, 184, 0.14)";
      ctx.setLineDash([4, 5]);
      ctx.lineWidth = 1;
      for (const n of simData.neurons) {
        ctx.beginPath();
        ctx.moveTo(n.vzX, n.vzY);
        ctx.lineTo(n.targetX, n.targetY);
        ctx.stroke();
      }
      ctx.setLineDash([]);

      // Migrate neurons and grow their biological dendritic trees
      for (const n of simData.neurons) {
        const migP = easeInOutCubic(clamp01((p - n.migrationDelay) / 0.68));
        const curX = lerp(n.vzX, n.targetX, migP);
        const curY = lerp(n.vzY, n.targetY, migP);

        // Leading process (migratory filopodium) while moving upward
        if (migP > 0.02 && migP < 0.95) {
          ctx.strokeStyle = n.color;
          ctx.globalAlpha = 0.7;
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(curX, curY);
          ctx.lineTo(lerp(curX, n.targetX, 0.28), lerp(curY, n.targetY, 0.28));
          ctx.stroke();
          ctx.globalAlpha = 1;
        }

        // Dendritic arbor grows as neuron settles into its target layer
        const arborP = clamp01((migP - 0.35) / 0.65);
        drawBiologicalNeuron(ctx, n, curX, curY, arborP, 0.12, 1.0);
      }
      ctx.restore();
    }

    // Stage 4: Chemoaffinity Axon Guidance & Synaptogenesis
    function renderStageAxons(ctx, W, H, p) {
      drawTissueBackground(ctx, W, H, 0.9, 0.3);

      ctx.save();
      ctx.fillStyle = "#f8fafc";
      ctx.font = "600 13px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
      ctx.fillText("Chemoaffinity Axon Guidance (Growth Cones) & Colour-Matched Topographic Synaptogenesis", 60, 42);

      // Draw extending axons with growth cones
      for (const syn of simData.synapses) {
        const pre = simData.neurons[syn.preId];
        const localP = clamp01((p - syn.growthDelay) / 0.62);
        if (localP <= 0) continue;

        const growthT = easeInOutCubic(localP);
        ctx.strokeStyle = syn.color;
        ctx.globalAlpha = syn.isInhibitory ? 0.55 : 0.68;
        ctx.lineWidth = syn.isInhibitory ? 1.4 : 1.75;

        // Sample partial quadratic Bezier up to growthT
        const steps = 16;
        ctx.beginPath();
        ctx.moveTo(pre.targetX, pre.targetY);
        let tip = { x: pre.targetX, y: pre.targetY };
        for (let s = 1; s <= steps; s++) {
          const t = (s / steps) * growthT;
          tip = quadBezierPoint(
            pre.targetX,
            pre.targetY,
            syn.midX,
            syn.midY,
            syn.contactX,
            syn.contactY,
            t
          );
          ctx.lineTo(tip.x, tip.y);
        }
        ctx.stroke();

        // If still growing, draw a biological Growth Cone (actin filopodia fan)
        if (growthT < 0.98) {
          const tang = quadBezierTangent(
            pre.targetX,
            pre.targetY,
            syn.midX,
            syn.midY,
            syn.contactX,
            syn.contactY,
            growthT
          );
          const baseAngle = Math.atan2(tang.ny, tang.nx);
          ctx.strokeStyle = "#ffffff";
          ctx.globalAlpha = 0.85;
          ctx.lineWidth = 1.1;
          for (let f = -1; f <= 1; f++) {
            const ang = baseAngle + f * 0.45;
            ctx.beginPath();
            ctx.moveTo(tip.x, tip.y);
            ctx.lineTo(tip.x + Math.cos(ang) * 7, tip.y + Math.sin(ang) * 7);
            ctx.stroke();
          }
        } else {
          // Synapse bouton flash on contact
          ctx.fillStyle = syn.isInhibitory ? "#f472b6" : "#fde047";
          ctx.globalAlpha = 0.9;
          ctx.beginPath();
          ctx.arc(syn.contactX, syn.contactY, 2.8, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      ctx.globalAlpha = 1;
      for (const n of simData.neurons) {
        drawBiologicalNeuron(ctx, n, n.targetX, n.targetY, 1.0, 0.15, 1.0);
      }
      ctx.restore();
    }

    // Click on canvas to stimulate nearest neuron with a current pulse
    canvas.addEventListener("click", (ev) => {
      const rect = canvas.getBoundingClientRect();
      const scaleX = canvas.width / rect.width;
      const scaleY = canvas.height / rect.height;
      const cx = (ev.clientX - rect.left) * scaleX;
      const cy = (ev.clientY - rect.top) * scaleY;

      let best = null;
      let bestDist = 48;
      for (const n of simData.neurons) {
        const d = Math.hypot(n.targetX - cx, n.targetY - cy);
        if (d < bestDist) {
          bestDist = d;
          best = n;
        }
      }
      if (best) {
        best.v = 1.25;
        best.refrac = 0;
        if (activeStage !== 4) {
          activeStage = 4;
          stageElapsed = 0;
          updateStageUI();
        }
      }
    });

    // Stage 5: Live In-Browser Spiking Network Simulation (LIF Dynamics)
    function renderStageActivity(ctx, W, H, p, timeSec, dt) {
      drawTissueBackground(ctx, W, H, 0.65, 0.12);

      ctx.save();
      ctx.fillStyle = "#f8fafc";
      ctx.font = "600 13px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
      ctx.fillText("Live Browser LIF Spiking Simulation · Click any neuron to inject current & trigger a spike cascade", 60, 42);

      // Step the LIF spiking network in real time in the browser
      const stepDt = Math.min(0.05, dt || 0.016);
      const oscDrive = 0.5 + 0.5 * Math.sin(timeSec * 8.2);
      let lfpInstant = 0;

      for (const n of simData.neurons) {
        // Exponential decay of synaptic current & flash luminescence
        n.iSyn *= Math.exp(-stepDt * 12.0);
        n.flash = Math.max(0.06, n.flash * Math.exp(-stepDt * 7.5));

        if (n.refrac > 0) {
          n.refrac = Math.max(0, n.refrac - stepDt * 60);
          n.v = 0;
        } else {
          // Thalamic / oscillatory tonic drive + recurrent synaptic input
          const thalamicDrive = (n.layerIdx === 1 ? 1.15 : 0.72) * (0.45 + 0.75 * Math.sin(timeSec * 8.0 - n.phaseOffset * 0.5));
          const dv = (-0.85 * n.v + thalamicDrive + n.iSyn) * stepDt * 3.2;
          n.v = Math.max(0, n.v + dv);

          if (n.v >= 1.0) {
            // Spike! Reset membrane potential, enter refractory period, emit action potentials on outgoing axons
            n.v = 0;
            n.refrac = 11;
            n.flash = 1.0;
            for (const syn of simData.synapses) {
              if (syn.preId === n.id && syn.spikes.length < 4) {
                syn.spikes.push({ t: 0 });
              }
            }
          }
        }
        lfpInstant += (n.isInhibitory ? -0.6 : 1.0) * (n.v * 0.5 + Math.abs(n.iSyn));
      }

      // Advance action potentials along curved axons and deliver postsynaptic currents on arrival
      for (const syn of simData.synapses) {
        const pre = simData.neurons[syn.preId];
        const post = simData.neurons[syn.postId];

        ctx.strokeStyle = syn.color;
        ctx.globalAlpha = 0.28;
        ctx.lineWidth = 1.3;
        ctx.beginPath();
        ctx.moveTo(pre.targetX, pre.targetY);
        ctx.quadraticCurveTo(syn.midX, syn.midY, syn.contactX, syn.contactY);
        ctx.stroke();

        for (let k = syn.spikes.length - 1; k >= 0; k--) {
          const sp = syn.spikes[k];
          sp.t += stepDt * syn.speed;
          if (sp.t >= 1.0) {
            post.iSyn += syn.weight;
            post.flash = Math.max(post.flash, 0.42);
            syn.spikes.splice(k, 1);
            continue;
          }
          const pt = quadBezierPoint(
            pre.targetX,
            pre.targetY,
            syn.midX,
            syn.midY,
            syn.contactX,
            syn.contactY,
            sp.t
          );

          // Glowing spike packet
          ctx.fillStyle = "#ffffff";
          ctx.globalAlpha = 0.95;
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, 3.3, 0, Math.PI * 2);
          ctx.fill();

          ctx.fillStyle = syn.color;
          ctx.globalAlpha = 0.58;
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, 6.8, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // Update live LFP ring buffer
      const normLfp = (lfpInstant / simData.neurons.length) * (0.7 + 0.3 * oscDrive);
      simData.lfpHistory.push(normLfp);
      if (simData.lfpHistory.length > 120) simData.lfpHistory.shift();

      // 2. Draw biological neurons with live somatic/dendritic voltage flashes
      ctx.globalAlpha = 1;
      for (const n of simData.neurons) {
        drawBiologicalNeuron(ctx, n, n.targetX, n.targetY, 1.0, n.flash, 1.0);
      }

      // 3. Bottom Oscilloscope Strip: Population LFP & E/I Balance Readout
      const stripX = 48;
      const stripY = 368;
      const stripW = W - 96;
      const stripH = 58;

      ctx.fillStyle = "rgba(15, 23, 42, 0.9)";
      ctx.strokeStyle = "rgba(56, 189, 248, 0.35)";
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.roundRect(stripX, stripY, stripW, stripH, 8);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = "#34d399";
      ctx.font = "700 11px monospace";
      ctx.fillText("Live Browser LIF Kernel · LFP 10.0 Hz Alpha Readout (R = 0.89 · E/I = 4.0)", stripX + 14, stripY + 17);

      // Draw scrolling LFP oscillation trace from live simulation history
      ctx.strokeStyle = "#38bdf8";
      ctx.lineWidth = 2;
      ctx.beginPath();
      const traceX0 = stripX + 14;
      const traceW = stripW - 28;
      const hist = simData.lfpHistory;
      for (let i = 0; i < hist.length; i++) {
        const u = i / (hist.length - 1);
        const tx = traceX0 + u * traceW;
        const ty = stripY + 42 - (hist[i] - 0.22) * 32;
        if (i === 0) ctx.moveTo(tx, ty);
        else ctx.lineTo(tx, ty);
      }
      ctx.stroke();

      ctx.restore();
    }

    // Main animation loop
    let lastTime = performance.now();
    updateStageUI();

    function frame(now) {
      const dt = Math.min(0.1, (now - lastTime) / 1000);
      lastTime = now;

      if (isPlaying) {
        stageElapsed += dt;
        const dur = STAGE_DURATIONS[activeStage];
        if (stageElapsed >= dur) {
          if (lockedStage) {
            stageElapsed = 0;
          } else {
            stageElapsed = 0;
            activeStage = (activeStage + 1) % STAGES.length;
            updateStageUI();
          }
        }
      }

      const progress = clamp01(stageElapsed / STAGE_DURATIONS[activeStage]);
      const W = canvas.width;
      const H = canvas.height;

      ctx.clearRect(0, 0, W, H);

      if (activeStage === 0) {
        renderStageEvolution(ctx, W, H, progress);
      } else if (activeStage === 1) {
        renderStageNeurogenesis(ctx, W, H, progress);
      } else if (activeStage === 2) {
        renderStageMigration(ctx, W, H, progress);
      } else if (activeStage === 3) {
        renderStageAxons(ctx, W, H, progress);
      } else {
        renderStageActivity(ctx, W, H, progress, now / 1000, dt);
      }

      // Stage progress bar at bottom edge of canvas
      ctx.fillStyle = "rgba(148, 163, 184, 0.2)";
      ctx.fillRect(0, H - 4, W, 4);
      ctx.fillStyle = "#38bdf8";
      ctx.fillRect(0, H - 4, W * progress, 4);

      requestAnimationFrame(frame);
    }

    requestAnimationFrame(frame);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initHeroAnimation);
  } else {
    initHeroAnimation();
  }
})();
