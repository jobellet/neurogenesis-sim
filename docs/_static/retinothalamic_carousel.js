(function () {
  const STAGES = [
    {
      num: 1,
      title: "Progenitor Seeding & Proliferation",
      age: "E14–E15",
      operator: "seed_cells → proliferate",
      pills: "1. Seed & Proliferate",
      modelDetails: "Seeds founder cells into two Box regions—a 100 × 100 retinal sheet and a 60 × 60 × 20 thalamic relay nucleus (at z = 40 in Run 2, or inside the p2A alar thalamus voxel mask from the Allen P4 Atlas in Run 3)—and runs proliferate to divide progenitors with daughter displacement (jitter) and lineage tracking (parent_id, clone_id, birth_stage).",
      stateChanges: "Tissue struct-of-arrays initialized: positions seeded for retina (region 0) and relay (region 1). proliferate duplicates progenitors along x/y with Gaussian jitter (σ = 3.0), advancing cell count from 260 to 440 alive cells.Lineage tracked via clone_id and birth_stage.",
      params: "seed_cells: N=60 (retina), N=200 (relay)\nproliferate: repeat=2, prob=1.0*(region==0), jitter=3.0, expression_noise=0.2",
      cli: "python examples/retinothalamic.py --cpu --seed 0 --from-stage start --until-stage proliferate --out out_dir/step_01.ngb\npython -m neurogenesis stats --network out_dir/step_01.ngb",
      citation: "Thompson, C. L., Ng, L., Menon, V., Martinez, S., Lee, C. K., Glattfelder, K., Sunkin, S. M., Henry, A., Lau, C., Dang, C., Garcia-Verdugo, J. M., Lovick, J., & Hawrylycz, M. (2014). A high-resolution spatiotemporal atlas of gene expression of the developing mouse brain. <em>Neuron</em>, 83(2), 309–323. https://doi.org/10.1016/j.neuron.2014.05.033"
    },
    {
      num: 2,
      title: "Morphogen Gradients & Lateral-Inhibition Gene Expression",
      age: "E15–E16",
      operator: "express",
      pills: "2. Express",
      modelDetails: "Updates expression channels (K = 3): one fate gene driven by contact lateral inhibition among neighbours (neighbor_weights < 0 through the cell list) and two graded positional genes read from analytic x and y gradient fields (representing retinal EphA / EphB gradients).",
      stateChanges: "expression array (N, 3) populated. Channel 0 settles into binary salt-and-pepper pattern (Notch-Delta analogue) determining RGC vs other fate. Channels 1 and 2 store normalized EphA (x) and EphB (y) chemoaffinity values read from linear spatial gradient fields.",
      params: "express: repeat=6, dt=1.0, radius=12.0\nweights=[[6,0,0],[0,0,0],[0,0,0]], neighbor_weights=[[-1.5,0,0],[0,0,0],[0,0,0]]\nmorphogens: grad_x (gain=epha_gain), grad_y (gain=ephb_gain), one (bias=-3.0)",
      cli: "python examples/retinothalamic.py --cpu --seed 0 --in out_dir/step_01.ngb --from-stage proliferate --until-stage express --out out_dir/step_02.ngb",
      citation: "Collier, J. R., Monk, N. A. M., Maini, P. K., & Lewis, J. H. (1996). Pattern formation by lateral inhibition with feedback: A mathematical model of delta-notch intercellular signalling. <em>Journal of Theoretical Biology</em>, 183(4), 429–446.<br>Flanagan, J. G., & Vanderhaeghen, P. (1998). The ephrins and Eph receptors in neural development. <em>Annual Review of Neuroscience</em>, 21(1), 309–345."
    },
    {
      num: 3,
      title: "Cell Fate Differentiation",
      age: "E16–E17",
      operator: "differentiate",
      pills: "3. Differentiate",
      modelDetails: "Assigns discrete cell types and synaptic signs (sign = +1 or -1) from the lateral-inhibition expression channel and region labels: excitatory Retinal Ganglion Cells (RGCs, circles), other retinal cells (grey), excitatory thalamic relay cells (squares, ~80%), and inhibitory relay interneurons (triangles, ~20%).",
      stateChanges: "cell_type mapped: 1 = RGC (~66 cells), 2 = OTHER retinal cells (~174), 3 = RELAY (~160), 4 = INTER (~40). Synaptic signs assigned: sign = +1 for RGC, OTHER, and RELAY; sign = -1 for INTER interneurons. Refractory periods set to 5 ticks for thalamic neurons.",
      params: "types: [\n  {type_id: 2, condition: '(region == 0) & (expr[0] <= 0.5)', region: 2, sign: 1},\n  {type_id: 1, condition: '(region == 0) & (expr[0] > 0.5)', sign: 1},\n  {type_id: 3, condition: 'region == 1', sign: 1, refractory: 5},\n  {type_id: 4, condition: '(region == 1) & (cell_id % 5 == 0)', sign: -1, refractory: 5}\n]",
      cli: "python examples/retinothalamic.py --cpu --seed 0 --in out_dir/step_02.ngb --from-stage express --until-stage differentiate --out out_dir/step_03.ngb",
      citation: "Arcelli, P., Frassoni, C., Regondi, M. C., De Biasi, S., & Spreafico, R. (1997). GABAergic neurons in mammalian thalamus: A marker of thalamic complexity? <em>Brain Research Bulletin</em>, 42(1), 27–37."
    },
    {
      num: 4,
      title: "Neuronal Migration",
      age: "E17–E18",
      operator: "migrate",
      pills: "4. Migrate",
      modelDetails: "Moves newly differentiated cells toward their target laminar coordinates within the retinal sheet and relay volume, resolving local soma collisions in O(N) via the spatial cell list.",
      stateChanges: "positions updated in 5 relaxation steps. Cells maintain minimum distance = 2.0 space units through pairwise spatial hash repulsion. Resolves somatic overlap between clones produced during proliferation.",
      params: "migrate: steps=5, min_distance=2.0",
      cli: "python examples/retinothalamic.py --cpu --seed 0 --in out_dir/step_03.ngb --from-stage differentiate --until-stage migrate --out out_dir/step_04.ngb",
      citation: "Angevine, J. B., & Sidman, R. L. (1961). Autoradiographic study of cell migration during histogenesis of cerebral cortex in the mouse. <em>Nature</em>, 192(4804), 766–768."
    },
    {
      num: 5,
      title: "Homotypic Retinal Mosaic Spacing",
      age: "E18–P0",
      operator: "mosaic",
      pills: "5. Mosaic",
      modelDetails: "Applies short-range homotypic soma repulsion (exclusion zones) to RGCs only. Because every stage draws from its own deterministic random stream (seed, stage_name, repeat), this raises RGC spatial regularity from ~1.9 (random) to NND/SD = 2.77 ± 0.53 identically across all four experimental conditions (WT, b2KO, TTX, EphAKO).",
      stateChanges: "positions of RGCs (type 1) repelled locally within radius = 12.0. Nearest-neighbor regularity (mean / SD of distance to nearest RGC) increases from 1.90 to 2.77. Other retinal cells and relay cells remain stationary.",
      params: "mosaic: radius=12.0, steps=60, rate=0.5, types=[1]",
      cli: "python examples/retinothalamic.py --cpu --seed 0 --in out_dir/step_04.ngb --from-stage migrate --until-stage mosaic --out out_dir/step_05.ngb\nprintf '%s\\n' '{\"id\":1,\"method\":\"regularity\",\"params\":{\"ngb\":\"out_dir/step_05.ngb\"}}' | python -m neurogenesis.bridge",
      citation: "Eglen, S. J., & Willshaw, D. J. (2002). Influence of cell fate mechanisms on regularity in the retinal mosaic: Model and analysis. <em>The Journal of Neuroscience</em>, 22(24), 10751–10762.<br>Galli-Resta, L., Resta, G., Tan, S. S., & Reese, B. E. (1997). Mosaics of islet-1-expressing amacrine cells assembled by short-range cellular interactions. <em>The Journal of Neuroscience</em>, 17(20), 7831–7838."
    },
    {
      num: 6,
      title: "Exuberant Chemoaffinity Axon Guidance",
      age: "E18–P2",
      operator: "grow_axons",
      pills: "6. Grow Axons",
      modelDetails: "Forms the exuberant retina → relay projection (sigma = 0.3, target gain per axis B = diag(2·EphA_gain, 2·EphB_gain, 0), conduction_velocity = 8 in Run 2) and local interneuron → relay connections (~710 retinal synapses per network). In the EphAKO condition, setting the x chemoaffinity gain to 0 collapses r_x from 0.91 to 0.02–0.03 while leaving r_y (0.91) intact.",
      stateChanges: "connectivity table instantiated: pre, post, weight, delay. Synapse count jumps from 0 to ~1581 (1411 retinogeniculate + 170 intrathalamic inhibitory). Delays assigned from 3D Euclidean distance divided by conduction_velocity=8.0 (clipped to [1, 255] ticks).",
      params: "grow_axons: projections=['0->1', '1->1'], conduction_velocity=8.0, w_clip=2047, exact=true\nguidance 0->1: B=diag([2*epha_gain, 2*ephb_gain, 0]), sigma=0.3, p0=0.6, w=250.0\nguidance 1->1: B=diag([2, 2, 0]), sigma=0.1, p0=0.3, w=60.0, source='inh'",
      cli: "python examples/retinothalamic.py --cpu --seed 0 --condition WT --in out_dir/step_05.ngb --from-stage mosaic --until-stage grow_axons --out out_dir/step_06.ngb\npython -m neurogenesis stats --network out_dir/step_06.ngb",
      citation: "Sperry, R. W. (1963). Chemoaffinity in the orderly growth of nerve fiber patterns and connections. <em>Proceedings of the National Academy of Sciences</em>, 50(4), 703–710.<br>Brown, A., Yates, P. A., Burrola, P., Ortuño, D., Vaidya, A., Jessell, T. M., Pfaff, S. L., O'Leary, D. D. M., & Lemke, G. (2000). Topographic mapping from the retina to the midbrain is controlled by relative but not absolute levels of EphA receptor signaling. <em>Cell</em>, 102(1), 77–88.<br>Hindges, R., McLaughlin, T., Genoud, N., Henkemeyer, M., & O'Leary, D. D. M. (2002). EphB forward signaling controls directional branch extension and arborization required for dorsal-ventral retinotopic mapping. <em>Neuron</em>, 35(3), 475–487."
    },
    {
      num: 7,
      title: "Neurotrophic Apoptosis of Under-Innervated Relay Cells",
      age: "P1–P3",
      operator: "apoptosis",
      pills: "7. Apoptosis",
      modelDetails: "Eliminates thalamic relay neurons that receive fewer than 3 incoming synapses (min_inputs evaluated via a per-cell Field with threshold z > 20 so retinal cells are spared), then compacts the tissue and re-indexes connectivity (~66 RGCs and ~145 relay cells survive).",
      stateChanges: "alive mask set to False for un-innervated or under-innervated relay cells (in_degree < 3 where z > 20). compact() re-indexes all arrays and trims dead cells. Relay population drops from 200 to ~145. Synapse endpoints remapped seamlessly.",
      params: "apoptosis: min_inputs=trophic_need (AnalyticField: '3.0 * (z > 20.0)')",
      cli: "python examples/retinothalamic.py --cpu --seed 0 --in out_dir/step_06.ngb --from-stage grow_axons --until-stage apoptosis --out out_dir/step_07.ngb\npython -m neurogenesis stats --network out_dir/step_07.ngb",
      citation: "van Ooyen, A., & Willshaw, D. J. (1999). Competition for neurotrophic factor in the development of nerve connections. <em>Proceedings of the Royal Society of London. Series B: Biological Sciences</em>, 266(1422), 883–892."
    },
    {
      num: 8,
      title: "Early Transmitter & Depolarizing GABA Pharmacology",
      age: "P2–P4",
      operator: "set_transmitters → express_receptors → assign_receptors → pharmacology (context: \"immature\")",
      pills: "8. Immature Pharmacology",
      modelDetails: "Assigns neurotransmitter bitmasks and postsynaptic receptors, then compiles synaptic weights in the \"immature\" developmental context where high intracellular chloride makes GABA_A transmission depolarizing (sign: +1), amplifying early circuit excitability prior to KCC2 upregulation.",
      stateChanges: "transmitters mask assigned: glutamate for sign > 0, GABA for sign < 0. Receptors ampa and gaba_a assigned to relay cells. In pharmacology context 'immature', gaba_a postsynaptic reversal potential is depolarizing (effective sign +1).",
      params: "set_transmitters: glutamate (sign > 0), gaba (sign < 0)\nexpress_receptors: ampa=1.0, gaba_a=1.0 (region == 1)\nassign_receptors: mode='max'\npharmacology: profile='pharmacology_retinothalamic.json', context='immature'",
      cli: "python examples/retinothalamic.py --cpu --seed 0 --in out_dir/step_07.ngb --from-stage apoptosis --until-stage pharmacology_immature --out out_dir/step_08.ngb",
      citation: "Ben-Ari, Y. (2002). Excitatory actions of GABA during development: The nature of the nurture. <em>Nature Reviews Neuroscience</em>, 3(9), 728–739."
    },
    {
      num: 9,
      title: "Stage II Spontaneous Retinal Waves & STDP Refinement",
      age: "P4–P8",
      operator: "refine_by_activity (×4 calls, rule: \"stdp\")",
      pills: "9. Retinal Waves & STDP",
      modelDetails: "Runs four refine_by_activity stages inside development. In WT, each call launches a propagating retinal wave (waves.cells restricted to the retina, random origin, speed 0.4 space units/tick, one 600-unit tick of drive per RGC) with STDP (A_plus = 20, A_minus = 21). In b2KO, waves are replaced by independent Poisson firing at the same mean rate (1 spike per RGC per 300-tick window, cleaned up by restore_modes). In TTX, no spikes occur.",
      stateChanges: "Synaptic weights updated by spike-timing-dependent plasticity (STDP). Correlated RGC firing across waves selectively strengthens retinotopic co-active inputs (long-term potentiation) and depresses uncorrelated divergent inputs. Weight distribution broadens toward bounds [0, 1000].",
      params: "refine_by_activity (x4): rule='stdp', ticks=300, A_plus=20.0, A_minus=21.0, w_min=0.0, w_max=1000.0, restore_modes=true\nwaves: sources=[origin], speed=0.4, amplitude=600.0, cells={'region': [0]}",
      cli: "python examples/retinothalamic.py --cpu --seed 0 --condition WT --in out_dir/step_08.ngb --from-stage pharmacology_immature --until-stage refine_by_activity --out out_dir/step_09.ngb\npython -m neurogenesis simulate --network out_dir/step_09.ngb --ticks 300 --raster out_dir/wave_raster.png",
      citation: "Meister, M., Wong, R. O. L., Baylor, D. A., & Shatz, C. J. (1991). Synchronous bursts of action potentials in ganglion cells of the developing mammalian retina. <em>Science</em>, 252(5008), 939–943.<br>Penn, A. A., Riquelme, P. A., Feller, M. B., & Shatz, C. J. (1998). Competition in retinogeniculate patterning driven by spontaneous activity. <em>Science</em>, 279(5359), 2108–2112.<br>Xu, H. P., Furman, M., Mineur, Y. S., Chen, H., King, S. L., Zenisek, D., Zhou, Z. J., Butts, D. A., Tian, N., Picciotto, M. R., & Crair, M. C. (2011). An instructive role for patterned spontaneous retinal activity in mouse visual map development. <em>Neuron</em>, 70(6), 1115–1127."
    },
    {
      num: 10,
      title: "Mature KCC2 Inhibitory Switch & Homeostatic Scaling",
      age: "P8–P10",
      operator: "pharmacology (context: \"mature\") → scale",
      pills: "10. Mature Switch & Scale",
      modelDetails: "Re-compiles synaptic weights in the \"mature\" context—switching GABA_A synapses to hyperpolarizing inhibition (sign: -1)—and applies multiplicative homeostatic synaptic scaling (scale) so each relay neuron's incoming weight sum normalizes to target = 1500 before structural pruning.",
      stateChanges: "pharmacology re-evaluated in 'mature' context: GABA_A synapses switch from depolarizing to hyperpolarizing (sign -1). scale multiplies all incoming weights per relay post cell so sum(|w|) = 1500.0, stabilizing postsynaptic excitability.",
      params: "pharmacology: profile='pharmacology_retinothalamic.json', context='mature'\nscale: target=1500.0",
      cli: "python examples/retinothalamic.py --cpu --seed 0 --in out_dir/step_09.ngb --from-stage refine_by_activity --until-stage scale --out out_dir/step_10.ngb",
      citation: "Turrigiano, G. G., Leslie, K. R., Desai, N. S., Rutherford, L. C., & Nelson, S. B. (1998). Activity-dependent scaling of quantal amplitude in neocortical neurons. <em>Nature</em>, 391(6670), 892–896."
    },
    {
      num: 11,
      title: "Activity-Dependent Synaptic Pruning",
      age: "P10–P12",
      operator: "prune",
      pills: "11. Prune",
      modelDetails: "Removes weak retinogeniculate synapses with |w| < 150 (\"use it or lose it\"), eliminating projections that were depressed or failed to strengthen during wave-driven STDP and homeostatic scaling.",
      stateChanges: "connectivity compacted: synapses with |weight| < 150 removed. Retinal synapse count drops from ~1555 to ~710–760. Divergent off-target axon collaterals are permanently cleared, sharpening the receptive fields of relay neurons.",
      params: "prune: threshold=150",
      cli: "python examples/retinothalamic.py --cpu --seed 0 --in out_dir/step_10.ngb --from-stage scale --until-stage prune --out out_dir/step_11.ngb\npython -m neurogenesis stats --network out_dir/step_11.ngb",
      citation: "Shatz, C. J., & Stryker, M. P. (1988). Prenatal tetrodotoxin infusion blocks segregation of retinogeniculate afferents. <em>Science</em>, 242(4875), 87–89.<br>Katz, L. C., & Shatz, C. J. (1996). Synaptic activity and the construction of cortical circuits. <em>Science</em>, 274(5290), 1133–1138."
    },
    {
      num: 12,
      title: "Axonal Myelination & Network Compilation",
      age: "P12–P14",
      operator: "myelinate → freeze",
      pills: "12. Myelinate & Freeze",
      modelDetails: "Shortens conduction delays of retinal axons by factor = 0.5 (clipped to [1, 31] ticks) and runs freeze with Dale's principle validation to compile the final SNNNetwork for evoked corner-separation testing and multi-seed ablation comparison.",
      stateChanges: "connectivity.delay scaled by 0.5 for retinal projections (pre_region=[0]), accelerating conduction. freeze validates Dale's principle and structural integrity, generating SNNNetwork. Final network: ~66 RGCs, ~145 relay cells, ~710 retinal synapses.",
      params: "myelinate: factor=0.5, pre_region=[0]\nfreeze: dale=true",
      cli: "python examples/retinothalamic.py --cpu --seed 0 --in out_dir/step_11.ngb --from-stage prune --until-stage freeze --out out_dir/final_network.json\npython -m neurogenesis simulate --network out_dir/final_network.json --ticks 100 --raster out_dir/evoked_raster.png",
      citation: "Gibson, E. M., Purger, D., Mount, C. W., Goldstein, A. K., Lin, G. L., Wood, L. S., Inema, I., Miller, S. E., Bieri, G., Zuchero, J. B., Barres, B. A., Woo, P. J., Vogel, H., & Monje, M. (2014). Neuronal activity promotes oligodendrogenesis and adaptive myelination in the mammalian brain. <em>Science</em>, 344(6183), 1252304.<br>Mrsic-Flogel, T. D., Hofer, S. B., Creutzfeldt, C., Cloëz-Tayarani, I., Changeux, J. P., Bonhoeffer, T., & Hübener, M. (2005). Altered map of visual space in the superior colliculus of mice lacking early retinal waves. <em>The Journal of Neuroscience</em>, 25(29), 6921–6928."
    }
  ];

  let currentStage = 0;
  let currentVisual = "box"; // "box" or "p4"

  function updateCarousel() {
    const stage = STAGES[currentStage];
    const pad = (n) => (n < 10 ? "0" + n : "" + n);
    const imgPrefix = currentVisual === "p4" ? "retino_stage_p4_" : "retino_stage_";
    const imgSrc = `../_static/media/${imgPrefix}${pad(stage.num)}.png`;

    // Update Counter
    const counterEl = document.getElementById("ng-stage-counter");
    if (counterEl) counterEl.textContent = `Stage ${stage.num} / ${STAGES.length}`;

    // Update Pills
    const pills = document.querySelectorAll(".ng-pill");
    pills.forEach((p, idx) => {
      if (idx === currentStage) {
        p.classList.add("active");
        p.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
      } else {
        p.classList.remove("active");
      }
    });

    // Update Visual
    const imgEl = document.getElementById("ng-carousel-img");
    if (imgEl) {
      imgEl.src = imgSrc;
      imgEl.alt = `${stage.title} (${currentVisual === "p4" ? "P4 Atlas" : "Box Relay"})`;
    }

    // Update Details
    const titleEl = document.getElementById("ng-stage-title");
    if (titleEl) titleEl.textContent = `${stage.num}. ${stage.title}`;

    const ageEl = document.getElementById("ng-stage-age");
    if (ageEl) ageEl.textContent = stage.age;

    const opEl = document.getElementById("ng-stage-operator");
    if (opEl) opEl.textContent = stage.operator;

    const detailsEl = document.getElementById("ng-stage-details");
    if (detailsEl) detailsEl.textContent = stage.modelDetails;

    const changesEl = document.getElementById("ng-stage-changes");
    if (changesEl) changesEl.textContent = stage.stateChanges;

    const paramsEl = document.getElementById("ng-stage-params");
    if (paramsEl) paramsEl.textContent = stage.params;

    // Update CLI Banner
    const cliEl = document.getElementById("ng-cli-code");
    if (cliEl) cliEl.textContent = stage.cli;

    // Update Citation Footer
    const citEl = document.getElementById("ng-citation-text");
    if (citEl) citEl.innerHTML = stage.citation;
  }

  function initCarousel() {
    const carouselRoot = document.querySelector(".ng-retino-carousel");
    if (!carouselRoot) return;

    // Render Pills
    const pillContainer = document.getElementById("ng-pills-container");
    if (pillContainer) {
      pillContainer.innerHTML = "";
      STAGES.forEach((st, idx) => {
        const btn = document.createElement("button");
        btn.className = "ng-pill" + (idx === 0 ? " active" : "");
        btn.textContent = st.pills;
        btn.addEventListener("click", () => {
          currentStage = idx;
          updateCarousel();
        });
        pillContainer.appendChild(btn);
      });
    }

    // Prev / Next Buttons
    const prevBtn = document.getElementById("ng-prev-btn");
    const nextBtn = document.getElementById("ng-next-btn");
    if (prevBtn) {
      prevBtn.addEventListener("click", () => {
        currentStage = (currentStage - 1 + STAGES.length) % STAGES.length;
        updateCarousel();
      });
    }
    if (nextBtn) {
      nextBtn.addEventListener("click", () => {
        currentStage = (currentStage + 1) % STAGES.length;
        updateCarousel();
      });
    }

    // Keyboard support
    window.addEventListener("keydown", (e) => {
      if (document.activeElement && (document.activeElement.tagName === "INPUT" || document.activeElement.tagName === "TEXTAREA")) return;
      if (e.key === "ArrowLeft") {
        currentStage = (currentStage - 1 + STAGES.length) % STAGES.length;
        updateCarousel();
      } else if (e.key === "ArrowRight") {
        currentStage = (currentStage + 1) % STAGES.length;
        updateCarousel();
      }
    });

    // Visual Toggle
    const toggleBox = document.getElementById("ng-toggle-box");
    const toggleP4 = document.getElementById("ng-toggle-p4");
    if (toggleBox && toggleP4) {
      toggleBox.addEventListener("click", () => {
        currentVisual = "box";
        toggleBox.classList.add("active");
        toggleP4.classList.remove("active");
        updateCarousel();
      });
      toggleP4.addEventListener("click", () => {
        currentVisual = "p4";
        toggleP4.classList.add("active");
        toggleBox.classList.remove("active");
        updateCarousel();
      });
    }

    // Copy CLI Button
    const copyBtn = document.getElementById("ng-cli-copy-btn");
    if (copyBtn) {
      copyBtn.addEventListener("click", () => {
        const text = STAGES[currentStage].cli;
        navigator.clipboard.writeText(text).then(() => {
          const original = copyBtn.textContent;
          copyBtn.textContent = "Copied!";
          setTimeout(() => {
            copyBtn.textContent = original;
          }, 1500);
        });
      });
    }

    // Global jump helper for interactive condition links
    window.jumpToRetinoStage = function (stageNum) {
      if (stageNum >= 1 && stageNum <= STAGES.length) {
        currentStage = stageNum - 1;
        updateCarousel();
        const el = document.querySelector(".ng-retino-carousel");
        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    };

    updateCarousel();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initCarousel);
  } else {
    initCarousel();
  }
})();
