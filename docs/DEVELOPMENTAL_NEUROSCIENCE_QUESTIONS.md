# Developmental Neuroscience Questions for Circuit Modeling

Use these foundational neuroscience questions to query textbooks, review papers, or literature notebooks (e.g., via NotebookLM or PubMed) to determine the exact biological rules and mathematical abstractions to prioritize in a developmental neural simulator.

---

## 1. Progenitor Division, Temporal Identity & Mitosis

1. **Symmetric vs. Asymmetric Division Transitions**
   - How do neural stem cells and radial glial progenitors transition from symmetric proliferative divisions (amplifying progenitor pool) to asymmetric neurogenic divisions (generating one self-renewing progenitor and one differentiated neuron or intermediate progenitor)?
   - What molecular or environmental signals determine the switch between proliferative and neurogenic modes?

   > **Literature Summary / Findings:**
   > - **Spindle Orientation & Cleavage Plane:** In the ventricular zone (VZ), early symmetric proliferative divisions feature a vertical cleavage plane (spindle parallel to ventricular surface), dividing the apical membrane patch and junctional complexes equally so both daughters remain as ventricular radial glia. Neurogenic asymmetric divisions switch to horizontal or oblique cleavage planes, causing only one daughter to retain apical contact/polarity determinants, while the other detaches and migrates basally (as an intermediate progenitor or nascent post-mitotic neuron).
   > - **Polarized Notch–Numb Circuit:** Asymmetric divisions partition the Notch antagonist Numb unequally. The daughter receiving high Numb exhibits Notch repression, upregulating proneural bHLH transcription factors (Ngn1/2, NeuroD) and exiting the cell cycle. The sister cell retains active Notch (forming NotchICD → HES repressors) and apical PAR complex (mPar3/mPar6/aPKC), preserving the self-renewing progenitor state.
   > - **Cell Cycle Kinetics ($G_1$ Lengthening):** Across neurogenesis, overall cell cycle time ($T_C$) and specifically $G_1$ phase length ($T_{G1}$) progressively lengthen. Progenitor maintenance ($P$ fraction) vs. cell-cycle exit ($Q$ fraction) depends on the balance of cell-cycle promoters (Cdk4/6, Cyclin D/E) vs. inhibitors ($\text{p27}^{Kip1}$, $\text{p21}^{Cip1}$). A surge in p27 and decline in Cyclin E drives an increasing fraction ($Q$) to exit mitosis into differentiation.
   > - **Extrinsic Niche Mitogens:** High early concentrations of FGF-2 and EGF sustain short $T_{G1}$ and suppress exit ($Q \to 0$), maintaining symmetric proliferation. Progressive mitogen decay permits $T_{G1}$ lengthening and allows intrinsic proneural and asymmetric neurogenic cascades to take over.

2. **Temporal Competence & Birth-Order Identity**
   - How do neural progenitors change their competence over time to generate different neuronal subtypes in a deterministic sequence (such as cortical deep layers before upper layers, or retinal ganglion cells before photoreceptors)?
   - Is temporal competence driven primarily by cell-intrinsic transcriptional clocks (e.g., sequential transcription factor cascades), extrinsic feedback cues from earlier-born neurons, or a fixed count of cell divisions?

   > **Literature Summary / Findings:**
   > - **Unidirectional Competence Restriction:** Progenitors undergo an irreversible, unidirectional narrowing of competence: early progenitors are broadly multipotent (can generate deep, intermediate, and superficial subtypes), whereas late progenitors permanently lose the ability to generate early/deep subtypes. Postmitotic migratory neurons are irreversibly fate-committed at birth.
   > - **Cell-Intrinsic Clocks:** Isolated clonal cultures confirm that temporal cascades operate autonomously in single progenitors without tissue-level feedback (e.g., Drosophila *Hunchback → Krüppel → PDM-1 → Castor*; vertebrate mammalian cascades).
   > - **Cell Cycle & Division Dependency:** Competence progression is not a strict integer-counting mechanism. While cytokinesis can act as a permissive gate for initial state transitions, subsequent competence states continue to advance on schedule even when divisions are blocked. Instead, $G_1$ lengthening ($T_{G1}$ quadrupling over integer cycles) expands the temporal window at the restriction point, enabling the gradual accumulation of downstream master transcription factors and proneural bHLH cascades.
   > - **Extrinsic Calibrating Feedback & Heterochronic Asymmetry:** Environmental cues can modulate velocity: heterochronic transplants show early progenitors in an older niche can "fast-forward" to superficial fates, but older progenitors in a younger niche cannot revert to deep fates. Paracrine signals from earlier-born cohorts (e.g., non-synaptic depolarizing GABA from migrating interneurons via $\text{GABA}_A$ receptors) provide negative feedback, slowing proliferation and tuning differentiation rates.

3. **Cleavage Plane & Daughter Cell Spacing**
   - Does the physical orientation of the mitotic spindle and cleavage plane (vertical vs. horizontal / apical vs. basal) influence the fate or subsequent spatial displacement of daughter cells?
   - How far are daughter cells physically displaced immediately following cytokinesis?

   > **Literature Summary / Findings:**
   > - **Spindle Orientation Dictates Fate & Trajectory:**
   >   - *Vertical Cleavage (perpendicular to ventricular surface):* Bisects the apical membrane patch (PAR complex) and divides Notch-1 and Numb symmetrically. Both daughters retain apical contact and adherens junctions at the ventricular surface, remaining in the VZ as proliferating radial glia.
   >   - *Horizontal/Oblique Cleavage (parallel/tilted relative to ventricular surface):* Asymmetrically partitions the apical membrane patch and segregates Numb preferentially into the basal daughter, while Notch-1 signaling remains unopposed in the apical daughter. The apical daughter remains at the ventricular margin in the cell cycle; the basal daughter detaches from the ventricular edge, exits the cell cycle, and begins active outward displacement toward the mantle zone / cortical plate.
   > - **Immediate Post-Cytokinesis Spacing:** Mitosis occurs with the progenitor rounded directly at the ventricular margin; cytokinesis deposits the two daughter cells immediately adjacent to one another (minimal steric separation, contact distance).
   > - **Subsequent Spatial Trajectories:**
   >   - Progenitors undergo *interkinetic nuclear migration* within the pseudostratified epithelium: elongating and ascending outward during $G_1$ into outer VZ for $S$ phase, then descending back to the apical surface during $G_2$ for mitosis.
   >   - Committed neuroblasts permanently detach from the apical edge and undergo radial migration (locomotion along radial glial guides or somal translocation), traveling hundreds to thousands of microns to their target laminar destinations.

---

## 2. Neuronal Migration, Laminar Organization & Cell Sorting

4. **Mechanisms of Inside-Out Cortical Layering**
   - How do later-born excitatory projection neurons navigate past earlier-born, deep-layer neurons to form an "inside-out" laminar gradient?
   - What are the relative contributions of radial glial scaffolding, chemoattractive cues, and detachment/stop signals (such as Reelin from Cajal-Retzius cells in the marginal zone) in terminating migration?

   > **Literature Summary / Findings:**
   > - **Radial Scaffolding & Bypassing Mechanisms:**
   >   - Preplate splitting: The earliest postmitotic wave forms the preplate (PP). Subsequent cortical plate (CP) neurons split this into the superficial marginal zone (MZ / Layer I with Cajal–Retzius cells) and the deep subplate (SP).
   >   - Successive waves (Layer VI $\to$ V $\to$ IV $\to$ III/II) crawl along common elongated radial glial fibers using saltatory *glial-guided locomotion* (dependent on astrotactin / Astn1 adhesion), followed by terminal *somal translocation* upon reaching beneath the marginal zone.
   >   - Young neuroblasts actively crawl *through* the intermediate zone and *past* older, already-settled deep-layer neurons, taking up residence immediately beneath the marginal zone.
   > - **Chemoattraction & Directionality:** Contact guidance along radial glia provides directional bias, supported by superficial chemoattractive cues (e.g. meningeal CXCL12 patterning Cajal–Retzius cells).
   > - **Reelin as a Glial-Detachment / Stop Signal:**
   >   - Cajal–Retzius cells in the MZ continuously secrete the large extracellular glycoprotein **Reelin**.
   >   - As migrating neuroblasts reach the top of the cortical plate beneath the MZ, Reelin signaling instructs them to disengage from the radial glial fiber and terminate forward locomotion.
   >   - **The "Log-Jam" Phenomenon (*reeler* phenotype):** Without functional Reelin, migrating neurons fail to detach from radial glial tracks upon reaching the top of the plate. Because successive waves share the same radial fibers, un-detached older neurons physically block subsequent waves ("log-jam"), causing later-born neurons to pile up in deeper layers and resulting in inverted/disorganized cortical lamination.

5. **Radial vs. Tangential Migration Interactions**
   - How do tangentially migrating inhibitory interneurons (originating from subcortical progenitor zones such as the ganglionic eminences) determine where to stop and integrate into specific cortical layers?
   - What mechanisms govern their transition from tangential wandering to radial insertion?

   > **Literature Summary / Findings:**
   > - **Subcortical Origin & Dual Tangential Streams:** Cortical GABAergic interneurons originate subcortically in the ventral telencephalon (medial and caudal ganglionic eminences, MGE/CGE) and migrate tangentially parallel to the ventricular surface along two prominent streams: a deep stream (near VZ/intermediate zone) and a superficial stream (through the marginal zone / Layer I).
   > - **Phenotypic Differentiation En Route:** Tangentially migrating interneurons mature while migrating—synthesizing GABA, extending leading processes, and displaying premature excitability.
   > - **Switch from Tangential Wandering to Radial Insertion:** Interneurons exit tangential streams by switching trajectories perpendicularly to invade the cortical plate:
   >   - *Physical substrates:* Turning and radial ascent frequently utilize descending *corticofugal axon fibers* as physical guidance tracks, or form *homotypic cellular chains* (in the SVZ).
   >   - *Paracrine GABA as a brake:* Migrating interneurons release non-vesicular GABA en route, activating $\text{GABA}_A$ receptors, which depolarizes immature neurons (high intracellular chloride), triggering voltage-gated $\text{Ca}^{2+}$ influx that acts as an autocrine/paracrine brake to slow and terminate migration into the cortical plate.
   > - **Open Questions / Incomplete Mechanisms in Biology:** The precise molecular receptor-ligand pairs and the temporal match-maker linking an interneuron's birthdate to the specific laminar depth of co-temporal pyramidal neurons remain active areas of ongoing research.

6. **Homotypic Repulsion & Retinal/Cortical Mosaics**
   - How do specific neuronal subtypes (e.g., retinal ganglion cells, horizontal cells, or cortical interneurons) establish regular spatial mosaics with non-random spacing?
   - Is homotypic spacing driven by contact-mediated mechanical repulsion, short-range diffusible repulsants, or selective apoptosis of overcrowded neighbours?

   > **Literature Summary / Findings:**
   > - **Exclusion Zones & Statistical Regularity:** Autocorrelation of retinal mosaics (e.g., cholinergic amacrine and alpha/beta ganglion cells) fits a random spatial distribution constrained by a minimal spacing or **exclusion zone** between homotypic somata. Drawing exclusion distances from a Gaussian distribution closely reproduces biological spatial packing.
   > - **Dendritic Tiling & Territoriality:** Forward-pathway sensory neurons (cone bipolars, alpha/beta/midget/parasol RGCs) display contact-mediated self-avoidance and mutual territoriality: advancing dendrites retract upon contact with homotypic dendrites, creating non-overlapping tiles. In contrast, lateral interneurons (horizontal cells) exhibit substantial overlap (3–8× coverage) and gap junction coupling; starburst amacrine cells overlap in territory but fasciculate into regular bundles.
   > - **Multi-Mechanism Origin of Full Mosaic Precision:**
   >   - *Contact Lateral Inhibition (Notch–Delta):* Juxtacrine signaling among Voronoi neighbours forces adjacent progenitors into distinct fates, creating an initial salt-and-pepper pattern. However, computational models (Eglen & Willshaw, 2002) demonstrate that lateral inhibition alone is mathematically insufficient to reach biological mosaic regularity.
   >   - *Selective Apoptosis of Crowded Neighbours:* Apoptosis acts downstream of lateral inhibition, pruning excess or improperly spaced cells in dense clusters (triggered by local density sensors like extracellular purines/ATP), raising mosaic regularity from ~2–3 to biological levels (>4–6 regularity index).
   >   - *Mechanical Somal & Arbor Repulsion:* Physical repulsion and differential adhesion push neighboring homotypic cell bodies apart after migration.
   > - **Scope & Limits:** Detailed experimental mosaic models are established in the retina; equivalent quantitative mosaic rules for neocortical interneurons remain less characterized in classical textbooks.

---

## 3. Gene Regulatory Dynamics & Cell Fate Differentiation

7. **Contact-Dependent Lateral Inhibition (Notch–Delta)**
   - What are the minimal dynamical rules and kinetic timescales governing Notch–Delta lateral inhibition in breaking spatial symmetry among adjacent progenitors?
   - How does contact-mediated juxtacrine signalling interact with long-range morphogen gradients (e.g., Wnt, BMP, Sonic Hedgehog) during pattern formation?

   > **Literature Summary / Findings:**
   > - **Minimal Collier–Eglen–Willshaw Dynamical System:**
   >   - For cells $i$ on a lattice with contact Voronoi neighbours $K_i$, state variables are membrane **Delta** ligand $D_i(t)$ and activated **Notch** receptor $N_i(t)$:
   >     $$\frac{dD_i}{dt} = -D_i + g(\bar{N}_i), \quad \frac{dN_i}{dt} = -N_i + f(\bar{D}_i)$$
   >   - Average neighbor Delta: $\bar{D}_i = \frac{1}{|K_i|} \sum_{j \in K_i} D_j$.
   >   - Transactivation: $f(x) = \frac{x^k}{A + x^k}$ ($k \approx 2$, Hill function of neighbor Delta).
   >   - Repression: $g(x) = \frac{1}{1 + B x^k}$ (NotchICD/SU(H) drives HES/E(spl) bHLH repressors, shutting down proneural bHLH genes and Delta transcription).
   > - **Bistability & Symmetry Breaking:**
   >   - Progenitors start in a metastable state of mutual inhibition.
   >   - Stochastic fluctuations trigger positive feedback: small increases in $D_i$ elevate $\bar{N}_j$ in adjacent cells, repressing their $D_j \to 0$.
   >   - Cell $i$ escapes incoming Notch inhibition ($D_i \to 1$), adopting the primary fate (proneural surge, cell-cycle exit, neurogenesis), while neighbors adopt secondary fates (progenitor renewal / radial glia).
   > - **Multi-Scale Morphogen–Notch Hierarchy:**
   >   - *Long-range morphogens (SHH, BMPs, Wnts):* Form macroscopic continuous gradients over dozens of cell diameters, inducing concentration-dependent homeodomain transcription factors (e.g. *Pax6*, *Nkx6.1*, *Dbx1/2*) that gate *proneural gene competence* in regional clusters (*Ngn1/2*, *Ascl1*, *Atoh1*).
   >   - *Juxtacrine Notch–Delta:* Operates within these morphogen-competence fields at the single-cell / sub-cellular scale. It prevents catastrophic simultaneous differentiation, maintaining a steady, self-renewing radial glial progenitor pool across iterative developmental cycles.

8. **Co-Transmission & Dale's Law in Developing Circuits**
   - Does neurotransmitter identity (excitatory vs. inhibitory) remain strictly invariant across a neuron's lifetime, or can immature neurons co-release multiple transmitters (e.g., GABA and glycine, or glutamate and dopamine) or flip functional polarity during development?
   - Under what developmental conditions do neurotransmitter receptors produce inverse electrical effects (e.g., depolarizing vs. hyperpolarizing GABA due to high intracellular chloride driven by NKCC1 vs. KCC2 expression)?

   > **Literature Summary / Findings:**
   > - **Violations of Dale's Principle & Co-Release:**
   >   - Neurons routinely co-release classical fast neurotransmitters alongside neuropeptides (substance P, somatostatin) or ATP.
   >   - Specific developing/mature circuits co-release multiple classical small-molecule transmitters: *Glutamate + Acetylcholine* in spinal descending interneurons (dINs), *GABA + Glycine* in ascending interneurons (aINs), and *Dopamine + Norepinephrine* in shared adrenergic terminals.
   >   - Immature projection systems can transiently accumulate non-synthesized transmitters (e.g., thalamocortical axons transiently expressing 5-HTT and VMAT to take up serotonin during whisker barrel formation).
   > - **Postsynaptic Receptor-Driven Divergence:** A single presynaptic transmitter produces opposing signs depending on target receptor complement: photoreceptor glutamate depolarizes OFF-bipolars (ionotropic AMPA/kainate) while hyperpolarizing ON-bipolars (metabotropic mGluR6 closing cGMP channels).
   > - **Developmental Transporter Switch (NKCC1 $\to$ KCC2):**
   >   - Fast GABAergic/glycinergic polarity is set by the chloride driving force: $I_{\text{Cl}} = g_{\text{Cl}}(V_m - E_{\text{Cl}})$.
   >   - *Immature neurons (NKCC1 predominance):* High expression of $\text{Na}^+\text{-K}^+\text{-2Cl}^-$ cotransporter actively concentrates $[\text{Cl}^-]_i$, shifting $E_{\text{Cl}}$ positive relative to $V_{\text{rest}}$. Opening $\text{GABA}_A$ causes $\text{Cl}^-$ efflux, triggering **depolarization and $\text{Ca}^{2+}$ influx**, which suppresses progenitor proliferation and modulates cell motility.
   >   - *Mature neurons (KCC2 upregulation):* Upregulation of $\text{K}^+\text{-Cl}^-$ cotransporter extrudes $\text{Cl}^-$, depressing $[\text{Cl}^-]_i$ and driving $E_{\text{Cl}}$ to $\sim -75\text{ mV}$, below $V_{\text{rest}}$, transforming GABA into a classical hyperpolarizing, inhibitory transmitter.
   >   - *Specialized adaptations:* Mature avian auditory coincidence detectors (nucleus laminaris) and retinal ON-bipolars retain elevated $[\text{Cl}^-]_i$ via persistent NKCC, while neuropathic injury can cause KCC2 downregulation and pathological depolarizing GABA.

---

## 4. Axon Guidance & Synaptogenesis

9. **Target Finding: Gradients vs. Intermediate Guideposts**
   - Do growing axons reach distant targets predominantly through continuous chemotropic morphogen gradients (e.g., Ephrins, Netrins, Semaphorins, Slits), or through discrete, multi-step navigation between intermediate guidepost cells?
   - How do axon growth cones reset their sensitivity after reaching an intermediate landmark (such as the midline or optic chiasm)?

   > **Literature Summary / Findings:**
   > - **Modular Multi-Step Trajectories vs. Long-Distance Gradients:**
   >   - Continuous diffusible gradients (Netrins, Slits) operate effectively only across short distances ($\le 1\text{–}2\text{ mm}$); long-distance axonal trajectories are therefore partitioned into sequential, shorter segments connecting intermediate guidepost cells or choice points.
   >   - Pioneer axons blaze intermediate pathways (e.g., grasshopper Ti1 pioneers making 90° turns at guideposts), while follower axons navigate via contact-mediated *fasciculation* (homophilic CAMs like Fasciclin I/II), with local anti-adhesive signals (e.g., BEATs) triggering defasciculation at targets.
   > - **Dynamic Sensitivity Reset at Choice Points:**
   >   - *The Ventral Midline Switch:* Approaching growth cones express DCC (attracted by floor plate Netrin-1) while Robo (Slit receptor) is intracellularly trapped/degraded (by Comm in flies, Rig-1 in mice). Upon crossing the midline, Comm/Rig-1 downregulates, Robo rapidly mobilizes to the growth cone surface, DCC is silenced and internalized, and high Slit chemorepulsion expels the growth cone forward, preventing recrossing. Post-crossing axons then switch to an orthogonal, ascending longitudinal gradient (e.g., Wnt4/Frizzled-3).
   >   - *Differential Receptor Gating (Optic Chiasm):* Ventrotemporal RGCs express ZIC2 $\to$ high EphB1, mediating contact repulsion against midline ephrinB to divert into the ipsilateral tract; contralateral RGCs express Islet2, repressing ZIC2/EphB1 to cross unhindered.
   > - **Local Cytoskeletal & Translational Autonomy:** Growth cones surgically severed from cell bodies continue navigating and turning accurately; sensitivity resets are mediated locally through *local cytoplasmic protein translation* and calcium transients via TRP channels governing rapid actin/microtubule reorganization.

10. **Topographic Mapping & Chemoaffinity**
    - What mathematical models (e.g., Sperry's chemoaffinity hypothesis, Preston-Willshaw, or competitive marker induction) best predict topographic projection fidelity under varying target-to-source tissue size ratios?
    - How do molecular gradients interact with activity-dependent mechanisms to establish precise retinotopic or tonotopic maps?

    > **Literature Summary / Findings:**
    > - **Systems-Matching & Failure of Rigid Chemoaffinity:**
    >   - Surgical mismatch experiments (half-retina expanding over a full tectum, intact retina compressing into a half-tectum) prove that target matching is dynamically regulated rather than fixed.
    >   - *Sperry Type I (rigid lock-and-key):* Fails systems-matching because fixed address tags leave unoccupied target territory permanently empty.
    >   - *Prestige–Willshaw Type II (graded affinities + finite contact limits):* Affinities represent contact lifetimes across continuous gradients; dynamic competition for limited synaptic slots produces expansion/compression without changing molecular markers.
    >   - *Gierer Countergradient Energy Model:* Combines guidance force $-\nabla p(x)$ with an accumulated terminal density term $r(x, t)$ ($dr/dt = \varepsilon \rho(x)$). Crowding builds an repulsive pressure that pushes terminals into unoccupied target territory until density equilibrates.
    >   - *Marker Induction (von der Malsburg & Willshaw):* Axons dynamically inject markers into target cells with lateral target diffusion ($\beta \nabla^2 T$) and synaptic normalization ($\Delta S_{ij} \propto \Phi_{ij} / \sum \Phi$), allowing the target to continuously rescale its coordinates to match incoming axon pools.
    > - **Two-Stage Hierarchical Topographic Assembly:**
    >   - *Stage 1: Molecular Guidance (Activity-Independent):* Orthogonal countergradients (e.g. retinal EphA vs. tectal ephrin-A nasotemporal; EphB vs. ephrin-B mediolateral) establish coarse topographic polarity and approximate target regions, but leave terminal arbors broad, exuberant, and overlapping.
    >   - *Stage 2: Activity-Dependent Refinement (Correlated Spontaneous Bursts):* Pre-sensory spontaneous bursts (cholinergic/glutamatergic retinal waves, spontaneous cochlear bursts) convert spatial proximity into temporal synchrony. Neighboring afferents firing together stabilize and strengthen synapses through NMDA-dependent Hebbian LTP / tLTP (STDP). Uncorrelated/asynchronous inputs undergo tLTD and competitive elimination via Mexican-hat lateral inhibition / sum-rule constraints, pruning exuberant branches into sharp, single-cell receptive fields (and eye-specific stripes in three-eyed frog assays).

11. **Multi-Synapse Connectivity & Bouton Distribution**
    - When an axon forms functional connections with a dendritic arbor, what determines whether it establishes a single synaptic contact versus multiple distributed synaptic boutons?
    - How does physical proximity constrain the probability of functional synaptogenesis (Peters' rule vs. cell-type-specific partner selection)?

    > **Literature Summary / Findings:**
    > - **Bouton Distribution is Cell-Type & Computationally Programmed:**
    >   - *Excitatory-to-Excitatory (Sparse, 1–few contacts):* Pyramidal–pyramidal and parallel fiber–Purkinje projections form only 1–2 boutons per target cell, distributing sparse contacts across thousands of distinct afferents to maximize combinatorial associative capacity and prevent input monopolization.
    >   - *Inhibitory Interneurons (Dense, multi-bouton clusters):* Basket cells systematically place 10–30 boutons across the soma and proximal dendrites; chandelier cells form vertical "cartridges" of up to 40 symmetric boutons along the axon initial segment (AIS).
    >   - *Specialized High-Gain Afferents:* Single hippocampal mossy fibers make up to 37 active zones on a single CA3 thorny excrescence; Group Ia afferents place ~10–35 boutons on motoneuron arbors; endbulbs of Held deploy >100 release sites to raise transmission safety factors given low quantal release probability ($P_r \approx 0.1\text{–}0.2$).
    >   - *Electrotonic Dispersion:* Spreading multiple boutons across distinct dendritic branches avoids local driving-force saturation that occurs when contacts cluster on the same electrotonic compartment.
    > - **Reconciling Peters' Rule with Molecular Specificity (Two-Stage Model):**
    >   - *Peters' Rule (Proximity as Necessary Geometric Substrate):* Spatial overlap of axonal and dendritic arbors defines potential connectivity and distance-dependent connection decay ($P_{\text{conn}} \to 0$ over hundreds of $\mu\text{m}$).
    >   - *Breakdown of Pure Proximity:* Intermingled neurons in identical volumes bypass thousands of overlapping dendrites (extreme sparsity in striatum; highly coupled subnetwork clustering in cortex; subcellular targeting to AIS vs. spines).
    >   - *Two-Stage Assembly:*
    >     1. *Geometric Exploration:* Random filopodial outgrowth samples overlapping territory.
    >     2. *Molecular & Activity Validation:* Transmembrane recognition molecules (Neurexin–Neuroligin-1 on excitatory spines vs. Neuroligin-2 on inhibitory shafts/somata; Cadherins) trigger local $\text{Ca}^{2+}$ transients to induce postsynaptic density assembly. Inappropriate contacts fail to evoke $\text{Ca}^{2+}$ transients and retract within minutes, followed by activity-dependent STDP consolidation or pruning.

---

## 5. Spontaneous Activity, Refinement & Homeostasis

12. **Spontaneous Developmental Waves & Bursts**
    - Prior to sensory experience (e.g., in embryonic or early postnatal retina, cochlea, and spinal cord), what generates large-scale propagating waves of spontaneous activity?
    - What cellular pacemakers, network architectures, and refractory recovery mechanisms dictate the velocity, initiation frequency, and spatial boundary of these waves?

    > **Literature Summary / Findings:**
    > - **Pacemaking & Network Drivers Across Sensory & Motor Systems:**
    >   - *Early Retina:* Initiated by lateral cholinergic starburst amacrine pacemakers, propagating via acetylcholine (nicotinic receptors) and early depolarizing GABA/glycine (NKCC1 chloride phenotype), electrical gap junctions, and extracellular potassium shifts.
    >   - *Developing Spinal Cord:* Rhythmic locomotor pacemaking driven by an excitatory interneuron core using persistent sodium ($I_{\text{Na,p}}$), low-threshold T-type calcium ($I_T$), and hyperpolarization-activated cation ($I_h$) conductances coupled via AMPA, NMDA, and gap junctions.
    >   - *Auditory Pathway & Cochlea:* Endogenous bursts originating in the immature sensory epithelium drive patterned bursts through spiral ganglion neurons, calibrating tonotopic maps and binaural coincidence circuits before hearing onset.
    > - **Wave Kinetics, Propagation Velocity & Refractory Mechanics:**
    >   - *Initiation & Limit Cycles:* Driven by slow inward currents ($I_h$, $I_{\text{Na,p}}$, $I_T$) triggering periodic transitions into bursting.
    >   - *Burst Termination & Inter-Wave Interval:* Intracellular $\text{Ca}^{2+}$ and $\text{Na}^+$ accumulation activates calcium- and sodium-activated potassium currents ($\text{sK}_{\text{Ca}}$, $\text{fK}_{\text{Ca}}$, $\text{K}_{\text{Na}}$), generating prolonged afterhyperpolarizations (AHPs) lasting seconds. Wave re-initiation is gated by the time required for $\text{Ca}^{2+}$ clearance, $\text{K}^+$ channel deactivation, and recovery of voltage-gated $\text{Na}^+$ channels from inactivation.
    >   - *Velocity & Spatial Footprint:* Wavefront velocity $v$ is governed by the spatial coupling kernel $w(|\mathbf{r} - \mathbf{r}'|)$ (recurrent collaterals, starburst arbors, gap junctions), membrane time constant $\tau_m$, and firing threshold $\vartheta$ ($u(vt, y, t) = \vartheta$).
    >   - *Boundaries & Mutual Annihilation:* Propagating wavefronts do not reflect; they terminate where recurrent coupling attenuates or upon colliding with refractory tissue left in the wake of another wave (mutual annihilation).

13. **Activity-Dependent Pruning vs. Neurotrophic Apoptosis**
    - What distinguishes the mechanisms of early neuronal apoptosis (regulated by target-derived neurotrophins such as NGF and BDNF) from subsequent synapse-level pruning (regulated by classic STDP, microglia/complement cascade, or heterosynaptic depression)?
    - Does synaptic elimination require direct competitive punishment of silent synapses, or simple withdrawal of positive trophic stabilization?

    > **Literature Summary / Findings:**
    > - **Different Spatial Scales and Execution Targets:**
    >   - *Early Apoptosis (Whole-cell death):* Adjusts global population size to match target tissue volume (15–50% of neurons die shortly after migration). Target tissues secrete limited neurotrophins (NGF, BDNF) binding Trk receptors, retrogradely transported along microtubules to somatic nuclei to repress cell-death genes. Deprivation activates caspase cascades (caspase-9), executing programmed cell death.
    >   - *Synapse Pruning (Subcellular remodeling):* Refines exuberant connectivity (~50% more synapses in infant than adult cortex) without killing the parent neuron. Presynaptic/postsynaptic decorrelation drives AMPA receptor endocytosis, PSD-95 degradation, and terminal retraction, with debris cleared by microglial phagocytosis.
    > - **Elimination Requires Active Competitive Punishment:**
    >   - *Biological Proof:* Passive disuse alone does not eliminate synapses. Globally silencing all receptors (e.g. blocking all NMDA/AChRs) arrests pruning and preserves multi-innervation. Pruning occurs only when active competitors depolarize the postsynaptic target (e.g. focal $\alpha$-bungarotoxin blockade at the NMJ or monocular deprivation in striate cortex, where active open-eye inputs actively displace silent closed-eye inputs).
    >   - *Computational & Mathematical Proof:* Passive competition models fail to eliminate isolated inactive terminals once sole occupancy is reached. Robust single-innervation models require active punishment: acausal spike arrivals drive timing-dependent depression (tLTD) via subtractive constraints, destabilizing silent or uncorrelated synapses below elimination thresholds.

14. **Homeostatic Synaptic Plasticity & Firing Rate Setpoints**
    - How do developing neurons distinguish between transient physiological burst patterns and chronic hypo-/hyper-activity to adjust their overall synaptic strengths (synaptic scaling) or intrinsic membrane excitability?
    - Are homeostatic weight adjustments multiplicative across all synapses, or are they locally compartmentalized on dendritic branches?

    > **Literature Summary / Findings:**
    > - **Temporal & Spatial Calcium Filtering (Bursts vs. Chronic Deviations):**
    >   - *Multi-Timescale Sensor Integration (Liu–Abbott formalism):* Neurons track activity via distinct temporal sensors (fast ms, intermediate tens of ms, slow minutes/hours). High-frequency burst patterns simply oscillate around target setpoints in fast sensors; only chronic deviations produce persistent net error $(\bar{S}_{\text{slow}} - S_{\text{slow}} \neq 0)$, driving homeostatic compensation without reacting to normal bursts.
    >   - *Microdomains vs. Bulk/Nuclear Calcium:* Physiological bursts produce high, transient $\text{Ca}^{2+}$ spikes ($10\text{–}100\ \mu\text{M}$) confined to spine heads and active zone microdomains (triggering CaMKII/Hebbian plasticity). Chronic hyperactivity saturates cytosolic buffers (calbindin, parvalbumin), spilling into the bulk cytoplasm and nucleus to recruit calcineurin–NFAT and CaMKIV–CREB cascades, altering channel and AMPA gene transcription over hours/days.
    >   - *BDNF/TrkB Setpoint Tuning:* Elevated chronic activity prompts BDNF release, triggering homeostatic depression of recurrent excitatory weights while scaling up somatic inhibition.
    > - **Global Multiplicative Scaling vs. Local Dendritic Normalization:**
    >   - *Multiplicative Scaling (Turrigiano et al.):* Cell-wide scaling multiplies all excitatory inputs by a scalar $\gamma$ ($w_i \to \gamma w_i$). This stabilizes global activity while preserving relative synaptic weight ratios ($w_i / w_j$) established by prior Hebbian learning, protecting stored information.
    >   - *Local Dendritic Compartmentalization:* Individual dendritic branches operate as semi-independent processing subunits with local spine-head isolation and distance-dependent synaptic scaling (distal synapses express larger AMPA densities to counterbalance passive dendritic cable attenuation and equalize somatic impact).

---

## 6. Myelination & Conduction Velocity Tuning

15. **Myelination Onset and Activity Dependence**
    - What cues trigger oligodendrocytes or Schwann cells to initiate myelin sheath deposition along specific axon segments?
    - To what extent is myelination regulated by spike activity versus physical axon diameter and length?
    - How does selective myelination synchronize conduction delays across pathways of unequal physical distance (e.g., in auditory coincidence detection or transcallosal projections)?

    > **Literature Summary / Findings:**
    > - **Glial-Axon Interactions & Initiation Cues:**
    >   - Oligodendrocytes (CNS, single cell wrapping multiple axons) and Schwann cells (PNS, 1:1 segment wrapping) differentiate and compact membranes via myelin basic protein (MBP) and proteolipid protein (PLP).
    >   - The exact primary molecular trigger activating the "myelination program" remains incompletely identified; in adult CNS, myelin also presents inhibitory molecules (Nogo) that block regeneration.
    > - **Caliber Thresholds, Conduction Direction & Systemic Timetables:**
    >   - *Hursh Factor & Caliber Thresholds:* Unmyelinated conduction velocity scales as $\sqrt{d}$; myelinated velocity scales linearly: $\text{Velocity (m/s)} \approx 6 \times \text{Axon Diameter (}\mu\text{m)}$.
    >   - *The $1\ \mu\text{m}$ Efficiency Limit:* For axons smaller than $\sim 1\ \mu\text{m}$ (e.g. C fibers, $0.2\text{–}1.5\ \mu\text{m}$ conducting at $0.5\text{–}2\text{ m/s}$), myelination is geometrically and metabolically inefficient; thin fibers remain unmyelinated.
    >   - *Myelogenetic Sequence:* Myelination follows the direction of impulse conduction (proximal tracts before distal), with hierarchical progression: primary sensory before motor in CNS, primary projection before intracortical association, and occipital before frontotemporal.
    > - **Delay Synchronization in Asymmetric Networks:**
    >   - *Binaural Coincidence Detection (Jeffress Delay Lines):* In auditory interaural time difference (ITD) circuits (medial superior olive / nucleus laminaris), contralateral and ipsilateral axons vary in physical length. Axons act as anatomical delay lines, while activity-dependent STDP selects and stabilizes delay lines that coincide with postsynaptic firing to achieve sub-millisecond arrival synchrony.
    >   - *Interhemispheric / Callosal Synchronization:* Long-range commissural fibers (corpus callosum body/splenium before genu/rostrum) use accelerated myelination and axon diameter variation to compensate for physical distance disparities and synchronize bilateral cortical oscillations.

---

REFS:

1.

Calegari, F., & Huttner, W. B. (2003). An inhibition of cyclin-dependent kinases that lengthens, but does not arrest, neuroepithelial cell cycle induces premature neurogenesis. *Journal of Cell Science*, 116(24), 4947–4955.
Caviness, V. S., Jr., Takahashi, T., & Nowakowski, R. S. (1995). Numbers, time and neocortical neuronogenesis: A general model. *Trends in Neurosciences*, 18(9), 379–383.
Chenn, A., & Walsh, C. A. (2002). Regulation of cerebral cortical size by control of cell cycle exit in neural precursors. *Science*, 297(5580), 365–369.
Götz, M., & Huttner, W. B. (2005). The cell biology of neurogenesis. *Nature Reviews Molecular Cell Biology*, 6(10), 777–788.
Zhong, W., Feder, J. N., Jiang, M. M., Jan, L. Y., & Jan, Y. N. (1996). Asymmetric localization of a mammalian numb homolog during neurogenesis. *Neuron*, 17(1), 43–53.

2.

Isshiki, T., Pearson, B., Holbrook, S., & Doe, C. Q. (2001). Drosophila neuroblasts sequentially express transcription factors which specify the temporal identity of their neuronal progeny. *Cell*, 106(4), 511–521.
McConnell, S. K. (1995). Constructing the cerebral cortex: Neurogenesis and fate determination. *Neuron*, 15(4), 761–768.
McConnell, S. K., & Kaznowski, C. E. (1991). Cell cycle dependence of laminar determination in cultured neocortical precursors. *Science*, 254(5029), 282–285.
Shen, Q., Wang, Y., Dimos, J. T., Fasano, C. A., Phoenix, T. N., Lemischka, I. R., Ivanova, N. B., Stifani, S., Morrisey, E. E., & Temple, S. (2006). The timing of cortical neurogenesis is encoded within lineages of individual progenitor cells. *Nature Neuroscience*, 9(6), 743–751.

3.

Haydar, T. F., Ang, E., Jr., & Rakic, P. (2003). Mitotic spindle rotation and mode of cell division in the developing telencephalon. *Proceedings of the National Academy of Sciences*, 100(5), 2890–2895.
Miyata, T., Kawaguchi, A., Okano, H., & Matsuzaki, F. (2001). Asymmetric inheritance of radial glial fibers by cortical neurons. *Neuron*, 31(5), 727–741.
Sanada, K., & Tsai, L. H. (2005). G protein βγ subunits and AGS3 control spindle orientation and asymmetric cell fate of cerebral cortical progenitors. *Cell*, 122(1), 119–131.
Sauer, F. C. (1935). Mitosis in the neural tube. *Journal of Comparative Neurology*, 62(2), 377–405.

4.

Caviness, V. S., Jr., & Sidman, R. L. (1973). Time of origin of corresponding cell classes in the cerebral cortex of normal and reeler mutant mice: An autoradiographic analysis. *Journal of Comparative Neurology*, 148(2), 141–151.
D'Arcangelo, G., Miao, G. G., Chen, S. C., Soares, H. D., Morgan, J. I., & Curran, T. (1995). A protein related to extracellular matrix proteins deleted in the mouse mutant reeler. *Nature*, 374(6524), 719–723.
Rakic, P. (1972). Mode of cell migration to the superficial layers of fetal monkey neocortex. *Journal of Comparative Neurology*, 145(1), 61–83.
Zheng, C., Heintz, N., & Hatten, M. E. (1996). CNS gene encoding astrotactin, which supports neuronal migration along radial glia. *Science*, 272(5260), 417–419.

5.

Anderson, S. A., Eisenstat, D. D., Shi, L., & Rubenstein, J. L. (1997). Interneuron migration from basal forebrain to neocortex: Dependence on Dlx genes. *Science*, 278(5337), 474–476.
Behar, T. N., Schaffner, A. E., Scott, C. A., O'Connell, C., & Barker, J. L. (1998). Differential response of cortical plate and ventricular zone cells to GABA as a migration stimulus. *Journal of Neuroscience*, 18(16), 6378–6387.
Bortone, D., & Polleux, F. (2009). KCC2 expression promotes the termination of cortical interneuron migration in a voltage-sensitive calcium-dependent manner. *Neuron*, 62(1), 53–71.
Marín, O., & Rubenstein, J. L. (2001). A long, remarkable journey: Tangential migration in the telencephalon. *Nature Reviews Neuroscience*, 2(11), 780–790.

6.

Eglen, S. J., & Willshaw, D. J. (2002). Influence of cell fate mechanisms upon retinal mosaic formation: a modelling study. *Development*, 129(23), 5399–5408.
Fuerst, P. G., Koizumi, A., Masland, R. H., & Burgess, R. W. (2008). Neurite branching and mosaic mosaicism require DSCAM. *Nature*, 451(7177), 470–474.
Galli-Resta, L., Resta, G., Tan, S. S., & Reese, B. E. (1997). Mosaics of Islet-1-expressing amacrine cells assembled by short-range cellular interactions. *Journal of Neuroscience*, 17(20), 7831–7838.
Wässle, H., & Riemann, H. J. (1978). The mosaic of nerve cells in the mammalian retina. *Proceedings of the Royal Society of London. Series B. Biological Sciences*, 200(1141), 441–461.

7.

Artavanis-Tsakonas, S., Rand, M. D., & Lake, R. J. (1999). Notch signaling: Cell fate control and signal integration in development. *Science*, 284(5415), 770–776.
Collier, J. R., Monk, N. A., Maini, P. K., & Lewis, J. (1996). Pattern formation by lateral inhibition with feedback: A mathematical model of Delta–Notch signalling. *Journal of Theoretical Biology*, 183(4), 429–446.
Kageyama, R., Ohtsuka, T., Shimojo, H., & Imayoshi, I. (2008). Dynamic Notch signaling in neural progenitor cells and a modern view of hairy, Hes and basic helix-loop-helix transcription factors. *Development, Growth & Differentiation*, 50(Suppl. 1), S87–S102.

8.

Ben-Ari, Y. (2002). Excitatory actions of GABA during development: The nature of the nurture. *Nature Reviews Neuroscience*, 3(9), 728–739.
Jonas, P., Bischofberger, J., & Sandkühler, J. (1998). Corelease of two fast neurotransmitters at a central synapse. *Science*, 281(5375), 419–424.
Rivera, C., Voipio, J., Payne, J. A., Ruusuvuori, E., Lahtinen, H., Lamsa, K., Pirvola, U., Saarma, M., & Kaila, K. (1999). The K+/Cl- co-transporter KCC2 renders GABA hyperpolarizing during neuronal maturation. *Nature*, 397(6716), 251–255.

9.

Bentley, D., & Caudy, M. (1983). Pioneer axons lose directed growth in the absence of guidepost cells. *Nature*, 304(5921), 62–65.
Dickson, B. J. (2002). Molecular mechanisms of axon guidance. *Science*, 298(5600), 1959–1964.
Herrera, E., Brown, L., Aruga, J., Rachel, R. A., Dolen, G., Mikoshiba, K., Brown, S., & Mason, C. A. (2003). Zic2 patterns binocular vision by specifying the uncrossed retinal projection. *Cell*, 114(5), 545–557.
Kennedy, T. E., Serafini, T., de la Torre, J. R., & Tessier-Lavigne, M. (1994). Netrins are diffusible chemotropic factors for commissural axons in the embryonic spinal cord. *Cell*, 78(3), 425–435.
Long, H., Sabatier, C., Ma, L., Plump, A., Yuan, W., Ornitz, D. M., Tamada, A., Murakami, F., Rao, Y., Lindberg, F. P., & Tessier-Lavigne, M. (2004). Conserved roles for Slit and Robo proteins in midline commissural axon guidance. *Neuron*, 42(2), 213–223.

10.

Gierer, A. (1983). Model for the retino-tectal projection. *Proceedings of the Royal Society of London. Series B. Biological Sciences*, 218(1210), 77–93.
McLaughlin, T., & O’Leary, D. D. (2005). Molecular gradients and development of retinotopic maps. *Annual Review of Neuroscience*, 28, 327–355.
Prestige, M. C., & Willshaw, D. J. (1975). On a role for competition in the formation of patterned neural connexions. *Proceedings of the Royal Society of London. Series B. Biological Sciences*, 190(1098), 77–98.
Sperry, R. W. (1963). Chemoaffinity in the orderly growth of nerve fiber patterns and connections. *Proceedings of the National Academy of Sciences*, 50(4), 703–710.
von der Malsburg, C., & Willshaw, D. J. (1977). How to label nerve cells so that they can interconnect in an ordered fashion. *Proceedings of the National Academy of Sciences*, 74(11), 5176–5178.

11.

Braitenberg, V., & Schüz, A. (1998). *Cortex: Statistics and geometry of neuronal connectivity* (2nd ed.). Springer-Verlag.
Somogyi, P., Tamás, G., Lujan, R., & Buhl, E. H. (1998). Salient features of synaptic organisation in the cerebral cortex. *Brain Research Reviews*, 26(2–3), 113–135.
Südhof, T. C. (2008). Neuroligins and neurexins link synaptic function to cognitive disease. *Nature*, 455(7215), 903–911.
Waites, C. L., Craig, A. M., & Garner, C. C. (2005). Mechanisms of vertebrate synaptogenesis. *Annual Review of Neuroscience*, 28, 251–274.

12.

Feller, M. B., Wellis, D. P., Stellwagen, D., Werblin, F. S., & Shatz, C. J. (1996). Requirement for cholinergic synaptic transmission in the generation of spontaneous retinal waves. *Science*, 272(5265), 1182–1187.
Meister, M., Wong, R. O., Baylor, D. A., & Shatz, C. J. (1991). Synchronous bursts of action potentials in ganglion cells of the developing mammalian retina. *Science*, 252(5008), 939–943.
O’Donovan, M. J., Chub, N., & Wenner, P. (1998). Mechanisms of spontaneous activity in developing spinal networks. *Journal of Neurobiology*, 37(1), 131–145.
Tritsch, N. X., Yi, E., Gale, J. E., Glowatzki, E., & Bergles, D. E. (2007). The origin of spontaneous activity in the developing auditory system. *Nature*, 450(7166), 50–55.

13.

Balice-Gordon, R. J., & Lichtman, J. W. (1994). Long-term synapse loss induced by focal blockade of postsynaptic receptors. *Nature*, 372(6506), 519–524.
Oppenheim, R. W. (1991). Cell death during development of the nervous system. *Annual Review of Neuroscience*, 14(1), 453–501.
Purves, D., & Lichtman, J. W. (1980). Elimination of synapses in the developing nervous system. *Science*, 210(4466), 153–157.
Stevens, B., Allen, N. J., Vazquez, L. E., Howell, G. R., Christopherson, K. S., Nouri, N., Kerr, D., Adaller, A., Welzel, P. E., & Barres, B. A. (2007). The classical complement cascade mediates CNS synapse elimination. *Cell*, 131(6), 1164–1178.

14.

Leslie, K. R., Nelson, S. B., & Turrigiano, G. G. (2001). Postsynaptic depolarization scales quantal amplitude in cortical pyramidal neurons. *Journal of Neuroscience*, 21(20), RC170.
Liu, Z., Golowasch, J., Marder, E., & Abbott, L. F. (1998). A model neuron with activity-dependent conductances regulated by multiple calcium sensors. *Journal of Neuroscience*, 18(7), 2309–2320.
Turrigiano, G. G., Leslie, K. R., Desai, N. S., Rutherford, L. C., & Nelson, S. B. (1998). Activity-dependent scaling of quantal amplitude in neocortical neurons. *Nature*, 391(6670), 892–896.
Turrigiano, G. G., & Nelson, S. B. (2004). Homeostatic plasticity in the developing nervous system. *Nature Reviews Neuroscience*, 5(2), 97–107.

15.

Barres, B. A., & Raff, M. C. (1999). Axonal control of oligodendrocyte development. *Journal of Cell Biology*, 147(6), 1123–1128.
Flechsig, P. (1920). *Anatomie des menschlichen Gehirns und Rückenmarks auf myelogenetischer Grundlage*. Georg Thieme.
Seidl, A. H., Sanchez, J. T., Yamoah, E. N., & Rubel, E. W. (2010). Neural delay lines are adjusted for accurate binaural hearing. *Proceedings of the National Academy of Sciences*, 107(26), 11999–12004.
Waxman, S. G., & Bennett, M. V. (1972). Relative conduction velocities of small myelinated and non-myelinated fibres in the central nervous system. *Nature New Biology*, 238(85), 217–219.