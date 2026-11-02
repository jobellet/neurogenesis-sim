# Related work and literature

neurogenesis-sim sits between four lines of work: models of neural development, developmental (indirect) encodings
in neuroevolution, spiking network simulators, and connectome-constrained modelling. This page lists the work the
toolbox builds on or should be compared with.

```{admonition} Note on references
:class: note
This list was compiled with the help of an AI assistant from well-known publications. Check each reference
(authors, year, volume, pages) against the publisher's record before citing it.
```

## How the toolbox relates to existing tools

| Tool | Focus | Difference from neurogenesis-sim |
|---|---|---|
| Cx3D / BioDynaMo | physics of growing cells and neurites, agent-based | detailed mechanics; no evolution of genomes for function, no spiking kernel tied to development |
| NETMORPH, TREES toolbox | statistical or optimal-wiring growth of neuronal morphologies | morphology-centred; networks are not grown from evolvable genomes for a task |
| NEST, Brian 2, NEURON, GeNN | simulating spiking networks | networks are specified, not developed; neurogenesis-sim can export to them |
| NEAT, HyperNEAT, ES-HyperNEAT, NDPs | evolving networks through (indirect) encodings | abstract encodings; no biological geometry, cell types, stages or spiking biophysics |
| Connectome-constrained models | simulating measured wiring diagrams | wiring taken as given; neurogenesis-sim asks how development could produce its statistics |

## Models of neural development
- Turing AM (1952). The chemical basis of morphogenesis. *Philosophical Transactions of the Royal Society B* 237:37–72.
- Wolpert L (1969). Positional information and the spatial pattern of cellular differentiation. *Journal of
  Theoretical Biology* 25:1–47.
- Gierer A, Meinhardt H (1972). A theory of biological pattern formation. *Kybernetik* 12:30–39.
- Sperry RW (1963). Chemoaffinity in the orderly growth of nerve fiber patterns and connections. *PNAS* 50:703–710.
- Willshaw DJ, von der Malsburg C (1976). How patterned neural connections can be set up by self-organization.
  *Proceedings of the Royal Society B* 194:431–445.
- Swindale NV (1996). The development of topography in the visual cortex: a review of models. *Network* 7:161–247.
- Collier JR, Monk NAM, Maini PK, Lewis JH (1996). Pattern formation by lateral inhibition with feedback: a
  mathematical model of Delta–Notch intercellular signalling. *Journal of Theoretical Biology* 183:429–446.
- McLaughlin T, O'Leary DDM (2005). Molecular gradients and development of retinotopic maps. *Annual Review of
  Neuroscience* 28:327–355.
- Simpson HD, Mortimer D, Goodhill GJ (2009). Theoretical models of neural circuit development. *Current Topics in
  Developmental Biology* 87:1–51.
- van Ooyen A (2011). Using theoretical models to analyse neural development. *Nature Reviews Neuroscience*
  12:311–326.
- Goodhill GJ (2016). Can molecular gradients wire the brain? *Trends in Neurosciences* 39:202–211.

## Developmental and growth simulators
- Zubler F, Douglas R (2009). A framework for modeling the growth and development of neurons and networks.
  *Frontiers in Computational Neuroscience* 3:25. (Cx3D)
- Koene RA, Tijms B, van Hees P, et al. (2009). NETMORPH: a framework for the stochastic generation of large scale
  neuronal networks with realistic neuron morphologies. *Neuroinformatics* 7:195–210.
- Cuntz H, Forstner F, Borst A, Häusser M (2010). One rule to grow them all: a general theory of neuronal branching
  and its practical application. *PLoS Computational Biology* 6:e1000877. (TREES toolbox)
- Breitwieser L, Hesam A, de Montigny J, et al. (2022). BioDynaMo: a modular platform for high-performance
  agent-based simulation. *Bioinformatics* 38:453–460.

## Activity-dependent development
- Wong ROL (1999). Retinal waves and visual system development. *Annual Review of Neuroscience* 22:29–47.
- Ben-Ari Y (2002). Excitatory actions of GABA during development: the nature of the nurture. *Nature Reviews
  Neuroscience* 3:728–739.
- Khazipov R, Sirota A, Leinekugel X, et al. (2004). Early motor activity drives spindle bursts in the developing
  somatosensory cortex. *Nature* 432:758–761.
- Bi GQ, Poo MM (1998). Synaptic modifications in cultured hippocampal neurons: dependence on spike timing, synaptic
  strength, and postsynaptic cell type. *Journal of Neuroscience* 18:10464–10472.
- Frémaux N, Gerstner W (2016). Neuromodulated spike-timing-dependent plasticity, and theory of three-factor learning
  rules. *Frontiers in Neural Circuits* 9:85.

## Developmental encodings and neuroevolution
- Kitano H (1990). Designing neural networks using genetic algorithms with graph generation system. *Complex Systems*
  4:461–476.
- Gruau F (1994). *Neural network synthesis using cellular encoding and the genetic algorithm.* PhD thesis, École
  Normale Supérieure de Lyon.
- Whitley D, Rana S, Heckendorn RB (1999). The island model genetic algorithm: on separability, population size and
  convergence. *Journal of Computing and Information Technology* 7:33–47.
- Stanley KO, Miikkulainen R (2002). Evolving neural networks through augmenting topologies. *Evolutionary
  Computation* 10:99–127.
- Stanley KO (2007). Compositional pattern producing networks: a novel abstraction of development. *Genetic
  Programming and Evolvable Machines* 8:131–162.
- Stanley KO, D'Ambrosio DB, Gauci J (2009). A hypercube-based encoding for evolving large-scale neural networks.
  *Artificial Life* 15:185–212.
- Risi S, Stanley KO (2012). An enhanced hypercube-based encoding for evolving the placement, density, and
  connectivity of neurons. *Artificial Life* 18:331–363.
- Zador AM (2019). A critique of pure learning and what artificial neural networks can learn from animal brains.
  *Nature Communications* 10:3770.
- Najarro E, Sudhakaran S, Risi S (2023). Towards self-assembling artificial neural networks through neural
  developmental programs. *Proceedings of the Artificial Life Conference (ALIFE 2023)*.
- Shuvaev S, Lachi D, Koulakov A, Zador A (2024). Encoding innate ability through a genomic bottleneck. *PNAS*
  121:e2409160121.

## Neuron models and spiking simulators
- Lapicque L (1907). Recherches quantitatives sur l'excitation électrique des nerfs traitée comme une polarisation.
  *Journal de Physiologie et de Pathologie Générale* 9:620–635.
- Hodgkin AL, Huxley AF (1952). A quantitative description of membrane current and its application to conduction and
  excitation in nerve. *Journal of Physiology* 117:500–544.
- Izhikevich EM (2003). Simple model of spiking neurons. *IEEE Transactions on Neural Networks* 14:1569–1572.
- Gerstner W, Kistler WM, Naud R, Paninski L (2014). *Neuronal Dynamics.* Cambridge University Press.
- Hines ML, Carnevale NT (1997). The NEURON simulation environment. *Neural Computation* 9:1179–1209.
- Gewaltig MO, Diesmann M (2007). NEST (NEural Simulation Tool). *Scholarpedia* 2:1430.
- Davison AP, Brüderle D, Eppler J, et al. (2009). PyNN: a common interface for neuronal network simulators.
  *Frontiers in Neuroinformatics* 2:11.
- Gleeson P, Crook S, Cannon RC, et al. (2010). NeuroML: a language for describing data driven models of neurons and
  networks with a high degree of biological detail. *PLoS Computational Biology* 6:e1000815.
- Yavuz E, Turner J, Nowotny T (2016). GeNN: a code generation framework for accelerated brain simulations.
  *Scientific Reports* 6:18854.
- Stimberg M, Brette R, Goodman DFM (2019). Brian 2, an intuitive and efficient neural simulator. *eLife* 8:e47314.
- Dai K, Hernando J, Billeh YN, et al. (2020). The SONATA data format for efficient description of large-scale
  network models. *PLoS Computational Biology* 16:e1007696.
- Eshraghian JK, Ward M, Neftci EO, et al. (2023). Training spiking neural networks using lessons from deep learning.
  *Proceedings of the IEEE* 111:1016–1054.

## Connectomes and connectome-constrained models
- Peters A, Feldman ML (1976). The projection of the lateral geniculate nucleus to area 17 of the rat cerebral
  cortex. I. General description. *Journal of Neurocytology* 5:63–84. (origin of "Peters' rule")
- Hill SL, Wang Y, Riachi I, Schürmann F, Markram H (2012). Statistical connectivity provides a sufficient foundation
  for specific functional connectivity in neocortical neural microcircuits. *PNAS* 109:E2885–E2894.
- Markram H, Muller E, Ramaswamy S, et al. (2015). Reconstruction and simulation of neocortical microcircuitry.
  *Cell* 163:456–492.
- Billeh YN, Cai B, Gratiy SL, et al. (2020). Systematic integration of structural and functional data into
  multi-scale models of mouse primary visual cortex. *Neuron* 106:388–403.
- Scheffer LK, Xu CS, Januszewski M, et al. (2020). A connectome and analysis of the adult *Drosophila* central
  brain. *eLife* 9:e57443.
- Dorkenwald S, Matsliah A, Sterling AR, et al. (2024). Neuronal wiring diagram of an adult brain. *Nature*
  634:124–138.
- Schlegel P, Yin Y, Bates AS, et al. (2024). Whole-brain annotation and multi-connectome cell typing of *Drosophila*.
  *Nature* 634:139–152.
- Lappalainen JK, Tschopp FD, Prakhya S, et al. (2024). Connectome-constrained networks predict neural activity across
  the fly visual system. *Nature* 634:1132–1140.
- Shiu PK, Sterne GR, Spiller N, et al. (2024). A *Drosophila* computational brain model reveals sensorimotor
  processing. *Nature* 634:210–219.
- FlyEM / Janelia: male *Drosophila* central nervous system connectome v1.0 (2026), *Cell*; preprint bioRxiv
  10.1101/2025.10.09.680999. Data under CC-BY 4.0.

```{admonition} PLACEHOLDER
:class: placeholder
A comparison table with measured numbers (time to grow and simulate a reference circuit) against Cx3D / BioDynaMo,
Brian 2 and NEST; a BibTeX file of all references; and short summaries of how each listed model maps onto toolbox
stages and Params.
```
