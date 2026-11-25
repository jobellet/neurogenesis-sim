# Cues released by cells, two-phase growth and target recognition (C27)

How an axon finds its partners is split, in the toolbox as in the developing brain, into steps that use different
molecules: **(1)** a long-range trip to a target region, steered by diffusible cues that cells release and that the growth
cone reads through its receptors; **(2)** arrival: the axon stops elongating and arborises in the target region (and the
target's dendrites elaborate where afferents arrive); **(3)** contact: among the cells within reach, synapses form
preferentially between partners that express matching recognition molecules. This page explains how each step is
implemented and why, against the literature. Stages: `secrete_cue` and the `CueField` (new), `grow_arbors` (extended),
`arbor_synapses`, `partner_select` / `bilinear_select` (existing).

```{admonition} Note on references
:class: note
Compiled with the help of an AI assistant (2026-11-25). Titles, journals and pages of the starred references were checked
in an online search on that day; the others are well-known publications. Check each reference against the publisher's
record before citing it.
```

## Step 1. Cues released by cells, read through receptors

**Biology.** Long-range guidance cues (netrins, Slits, class-3 semaphorins) are secreted by intermediate and final targets
and form gradients along the path of the growth cone; membrane-bound cues (ephrins, Sema6) act at short range and at
choice points (Tessier-Lavigne & Goodman 1996). The direction of the response is set by the **receptor**, not by the cue:
netrin-1 attracts through DCC and repels when UNC5 is co-expressed (Hong et al. 1999); "the receptor, or receptor complex,
on the growth cone surface determines the direction of growth" (Bashaw & Klein 2010\*). Class-3 semaphorins repel axons
yet attract apical dendrites of cortical neurons (Sema3A, through cGMP; Polleux et al. 2000\*). Dopaminergic axons are
steered on their way to the striatum by netrin-1/DCC, Slit/Robo, semaphorins and ephrins (Lin & Isacson 2006), and
the striatum's own secretions make it permissive for them (Nolz1: Soleilhavoup et al. 2020\*).

**Implementation.**
- `secrete_cue` makes any selected cells sources of a named cue. Selection by region, cell type, or **expression of a
  ligand gene** (`expressing` channel above a threshold), so that which cells secrete is itself an output of the
  regulatory network (`express`, C6) and can be switched off by a gene (expression 0 = absent).
- The concentration is a `CueField`: c(x) = Σ_i a_i exp(−|x − p_i| / λ). A molecule that diffuses (D) and is
  degraded or captured (k) settles to a profile with decay length λ = √(D/k) (Crick 1970); λ sets how far a target can
  be "seen" (Goodhill 1998). The 3D point-source steady state is exp(−r/λ)/r; the 1/r factor, singular at a source the
  size of a soma, is dropped. A membrane-bound cue is λ ≈ one cell diameter. Sources beyond 5 λ are ignored and the
  field is evaluated through the cell list, so the cost stays O(N).
- In `grow_arbors`, `guidance` lists any number of cues, each with a **per-cell gain**: a `Param`, or
  {"expression": k, "scale": s}, the cell's expression level of receptor channel k. Its sign is attraction or
  repulsion, so one cue can attract one cell type and repel another, as with DCC versus UNC5, or axons versus
  dendrites for Sema3A.
- `sensing: "relative"` uses ∇c / (c + K): growth cones detect a fractional change of concentration across their
  width, a few percent at best, and lose sensitivity far above the receptor's dissociation constant K (Goodhill &
  Urbach 1999; Rosoff et al. 2004). `"unit"` (the default) keeps only the gradient's direction, as the older single
  `attractor_field`.
- Cues released by **arbors** (`source: "terminals"` or `"nodes"`) model afferent- or target-derived signals that only
  exist once the first axons have arrived. The same field can stand for a neuromodulator released along an axonal
  arbor (volume transmission): most dopaminergic terminals are non-synaptic (Ducrot et al. 2021\*), and release comes from
  sparse active-zone-like sites in about 30 % of the varicosities (Liu et al. 2018\*).

**Not modelled.** Receptor switching at choice points is the separate `choice_point` stage (C17); local protein
synthesis, adaptation of the growth cone (desensitisation) and the time course of secretion are not modelled. Cues are
static after `secrete_cue` (call it again to update them after cells move or grow).

## Step 2. Arrival: shaft, then arbor

**Biology.** Retinal ganglion cell axons extend largely unbranched along the optic tract and arborise in the tectum,
where target-derived BDNF increases branch addition (Cohen-Cory & Fraser 1995\*); in mammals they first overshoot their
termination zone and add interstitial branches at the right position later (Yates et al. 2001). Target neurons give a
contact-mediated stop signal to afferent growth cones (Baird et al. 1992\*), and branches tend to arise where the growth
cone paused. Dendrites of the target in turn elaborate through activity and neurotrophins provided by their afferents
(McAllister, Lo & Katz 1995; Cline 2001).

**Implementation (`grow_arbors`, keys `target_field`, `target_threshold`, `arbor_*`).**
- Each growth cone carries a phase. In the **pathfinding** phase it uses the usual parameters (typically
  `branch_prob` 0: an unbranched shaft) and the `guidance` cues.
- When it reaches a point where `target_field` ≥ `target_threshold`, it switches to the **arbor** phase, with its own
  branching (`arbor_branch_prob`), step length, turning noise and cues (`arbor_guidance`, default none: local
  exploration). Its branches inherit the phase.
- With `confine_to_target` (default), a step that would leave the target region stops the tip: arbors stay in their
  termination zone.
- The target field is typically a cue released by the target cells (step 1). For dendrites it is a cue released by
  the afferents' terminals, so dendrites arborise where axons arrived.

**Not modelled.** Overshoot followed by interstitial branching, and the retraction of mistargeted branches (partly
covered by `refine_by_activity`, `competitive_elimination` and `prune`); arbors grow in one pass rather than through
growth-retraction dynamics.

## Step 3. Contact and partner recognition (existing stages)

**Biology.** Proximity alone does not decide synapses (a deviation from Peters' rule; Peters & Feldman 1976). Synaptic
partners are matched by combinations of recognition molecules (immunoglobulin superfamily, cadherins, leucine-rich
repeat proteins, teneurins; Sanes & Zipursky 2020\*). Homophilic matching: Dscam, DscamL, Sidekick-1 and -2 direct
lamina-specific connections in the retina (Yamagata & Sanes 2008\*); teneurins match olfactory receptor neuron axons to
projection neuron dendrites (Hong, Mosca & Luo 2012\*). Heterophilic pairs such as neurexin–neuroligin isoforms bias
excitatory versus inhibitory synapses (Südhof 2008).

**Implementation.** `arbor_synapses` (N3) lists the contacts between axonal and dendritic nodes (Peters' rule).
`partner_select` (C18, a compatibility matrix of pre × post recognition channels) or `bilinear_select` (C25, a low-rank
rule on graded expression profiles, homophilic when A = B) keeps each contact with the probability that the partners'
expressed molecules allow. With the steps above, a schedule is:
`express` → `secrete_cue` (targets) → `grow_arbors` (axons: guidance then arbor) → `secrete_cue` (afferent terminals) →
`grow_arbors` (dendrites: arbor where afferents arrived) → `arbor_synapses` → `partner_select` / `bilinear_select` →
`refine_by_activity` → `competitive_elimination` / `prune`.

## References
- Baird DH et al. (1992). Cerebellar target neurons provide a stop signal for afferent neurite extension in vitro.
  *J Neurosci* 12:619–634. doi:10.1523/JNEUROSCI.12-02-00619.1992 \*
- Bashaw GJ, Klein R (2010). Signaling from axon guidance receptors. *Cold Spring Harb Perspect Biol* 2:a001941. \*
- Cline HT (2001). Dendritic arbor development and synaptogenesis. *Curr Opin Neurobiol* 11:118–126.
- Cohen-Cory S, Fraser SE (1995). Effects of brain-derived neurotrophic factor on optic axon branching and remodelling
  in vivo. *Nature* 378:192–196. \*
- Crick F (1970). Diffusion in embryogenesis. *Nature* 225:420–422.
- Ducrot C et al. (2021). Dopaminergic neurons establish a distinctive axonal arbor with a majority of non-synaptic
  terminals. PubMed 34320240. \*
- Goodhill GJ (1998). Mathematical guidance for axons. *Trends Neurosci* 21:226–231.
- Goodhill GJ, Urbach JS (1999). Theoretical analysis of gradient detection by growth cones. *J Neurobiol* 41:230–241.
- Hong K et al. (1999). A ligand-gated association between cytoplasmic domains of UNC5 and DCC family receptors converts
  netrin-induced growth cone attraction to repulsion. *Cell* 97:927–941.
- Hong W, Mosca TJ, Luo L (2012). Teneurins instruct synaptic partner matching in an olfactory map. *Nature* 484:201–207. \*
- Lin L, Isacson O (2006). Axonal growth regulation of fetal and embryonic stem cell-derived dopaminergic neurons by
  Netrin-1 and Slits. *Stem Cells* 24:2504–2513. (PMC2613222)
- Liu C, Kershberg L, Wang J, Schneeberger S, Kaeser PS (2018). Dopamine secretion is mediated by sparse active
  zone-like release sites. *Cell* 172:706–718. (PMC5807134) \*
- McAllister AK, Lo DC, Katz LC (1995). Neurotrophins regulate dendritic growth in developing visual cortex. *Neuron*
  15:791–803.
- Peters A, Feldman ML (1976). The projection of the lateral geniculate nucleus to area 17 of the rat cerebral cortex.
  *J Neurocytol* 5:63–84.
- Polleux F, Morrow T, Ghosh A (2000). Semaphorin 3A is a chemoattractant for cortical apical dendrites. *Nature*
  404:567–573. \*
- Rosoff WJ et al. (2004). A new chemotaxis assay shows the extreme sensitivity of axons to molecular gradients.
  *Nat Neurosci* 7:678–682.
- Sanes JR, Zipursky SL (2020). Synaptic specificity, recognition molecules, and assembly of neural circuits. *Cell*
  181:536–556. \*
- Soleilhavoup C et al. (2020). Nolz1 expression is required in dopaminergic axon guidance and striatal innervation.
  *Nat Commun* 11:3111. doi:10.1038/s41467-020-16947-6 \*
- Südhof TC (2008). Neuroligins and neurexins link synaptic function to cognitive disease. *Nature* 455:903–911.
- Tessier-Lavigne M, Goodman CS (1996). The molecular biology of axon guidance. *Science* 274:1123–1133.
- Yamagata M, Sanes JR (2008). Dscam and Sidekick proteins direct lamina-specific synaptic connections in vertebrate
  retina. *Nature* 451:465–469. \*
- Yates PA et al. (2001). Topographic-specific axon branching controlled by ephrin-As is the critical event in
  retinotectal map development. *J Neurosci* 21:8548–8563.
