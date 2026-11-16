# Citing neurogenesis-sim

If you use the toolbox in published work, please cite the software and the references of the mechanisms you used
(listed in {doc}`development/third-party`, {doc}`background/literature`, and module docstrings). The repository's
`CITATION.cff` gives the software citation; GitHub shows it under **Cite this repository**.

```bibtex
@software{neurogenesis_sim,
  author  = {Bellet, Joachim and contributors},
  title   = {neurogenesis-sim: growing spiking neural networks through development},
  url     = {https://github.com/jobellet/neurogenesis-sim},
  year    = {2026},
  version = {0.1.0},
  license = {MIT}
}
```

To generate a provenance report listing which biological parameter profiles, sources, and DOIs a project relies on,
run:

```bash
python -m neurogenesis profile report project.json
```

Datasets have their own licences and citations (for example, the FlyEM male CNS connectome is CC-BY 4.0); cite them
when you use them. For the BibTeX entries of the literature referenced in the documentation, download
{download}`references.bib <_static/references.bib>`.
