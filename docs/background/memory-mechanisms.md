# Medium-term memory: sparse indexing, one-shot binding, consolidation (C28)

Three mechanisms proposed for how the hippocampal formation stores memories that last minutes to days and can be
recalled from a part, implemented as general tools. They are building blocks; how they are combined (and whether
evolution uses them) is up to the project that grows a network.

```{admonition} Note on references
:class: note
Compiled with the help of an AI assistant (2026-11-26); the linked references were checked in an online search on that
day. Check each reference against the publisher's record before citing it.
```

## Sparse random expansion: an index of the situation (`random_projection`)
**Evidence.** The hippocampus is proposed to store an *index* of the cortical patterns of an experience, which a partial
cue reactivates (indexing theory: Teyler & DiScenna 1986; [Teyler & Rudy 2007](https://experts.colorado.edu/display/pubid_53637);
[review](https://pmc.ncbi.nlm.nih.gov/articles/PMC7486247)); engram cells are sparse ensembles active at learning and
reactivated at recall ([Josselyn & Tonegawa 2020](https://dspace.mit.edu/bitstream/1721.1/126261/2/Submitted%20Version_aaw4325_CombinedPDF_v1.pdf)).
The dentate gyrus expands entorhinal input into a sparse code that separates similar patterns, and CA3's recurrent
synapses complete stored patterns from a part (Marr 1971; Treves & Rolls 1994;
[Rolls 2015](https://www.oxcns.org/papers/555%20Rolls%202015%20Hippocampal%20pattern%20completion%20and%20separation.pdf);
Leutgeb et al. 2007; Nakazawa et al. 2002; [Neunuebel & Knierim 2014 and review](https://pmc.ncbi.nlm.nih.gov/articles/PMC3904133)).
The same motif in the fly mushroom body (each Kenyon cell samples ~6 of 50 inputs, then strong inhibition keeps the
most active) implements a variant of locality-sensitive hashing
([Dasgupta, Stevens & Navlakha 2017](https://www.its.caltech.edu/~jkenny/nb250c/papers/Dasgupta-2017.pdf)); the hashing
reading of the dentate gyrus is a modelling proposal ([arXiv 1910.04590](https://arxiv.org/pdf/1910.04590)).
**Implementation.** `random_projection`: each target samples `fan_in` distinct sources at random. The sparsity comes from
inhibition among the targets, grown or wired separately.

## One-shot binding over seconds (`BTSPRule`)
**Evidence.** A dendritic plateau potential in a CA1 cell potentiates the inputs active seconds before or after it and
creates a place field in one trial ([Bittner et al. 2017](https://www.its.caltech.edu/~jkenny/nb250c/papers/Bittner-2017.pdf));
the change depends on the current weight (weak inputs grow, strong ones shrink), which moves fields
([Milstein et al. 2021](https://elifesciences.org/articles/73046)).
**Implementation.** Presynaptic eligibility trace x postsynaptic instructive signal (both decaying over ~1 s), times
k+ (w_max - w) - k- w. The plateau events are given by the caller.

## Keeping memories: fast and slow components (`ConsolidationRule`)
**Evidence.** Early potentiation tags a synapse and lasts only if plasticity-related products are captured
(Frey & Morris 1997; [review](https://www.nature.com/articles/nrn2963)); synapses with variables at several time scales
keep many more memories (Fusi, Drew & Abbott 2005; [Benna & Fusi 2016](https://www.proquest.com/docview/1855418478));
a fast hippocampal store and a slow cortical learner complement each other
([Kumaran, Hassabis & McClelland 2016](https://web.stanford.edu/~jlmcc/papers/KumaranHassabisMcClelland16FinalMS.pdf)).
**Implementation.** Every change from another rule goes to a fast component that decays; a gated fraction moves to a
slow component; the weight is their sum.

## Related models (not implemented here)
Context-dependent "clones" of an observation ([George et al. 2021](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8062558/));
structure (entorhinal) separated from content (hippocampal binding), with generalisation
([Whittington et al. 2020](https://pmc.ncbi.nlm.nih.gov/articles/PMC7707106)); their relation to transformers
([Whittington, Warren & Behrens 2022](https://arxiv.org/abs/2112.04035)).
