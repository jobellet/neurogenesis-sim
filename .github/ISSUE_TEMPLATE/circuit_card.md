---
name: Circuit Card Submission
about: Submit a new evolved or hand-crafted microcircuit card to the community catalogue
title: '[CARD]: <Circuit Name>'
labels: ['catalogue', 'circuit-card']
assignees: ''
---

## 1. Circuit Metadata
- **Circuit ID**: `kebab-case-id`
- **Version**: `1.0.0`
- **Title**: Circuit Title
- **Summary**: Concise biological and functional description (1-3 sentences)

## 2. Provenance & Attribution
- **Authors**:
  - Name: `Author Name`, ORCID: `0000-0000-0000-0000`
- **Associated Publication / Preprint**:
  - DOI: `10.xxxx/...` (optional)
- **License**: `CC-BY-4.0` / `MIT`

## 3. Objective & Target Metrics
- **Target Metrics Achieved**:
  - Metric: `<metric_name>`, Target Value: `<value>`, Achieved: `<value>`

## 4. Resource Footprint (Low-Compute Compliance)
- **Neurons (N)**: 
- **Synapses (E)**: 
- **Memory Footprint**: `compute_cost.memory_bytes`
- **Ops per Tick**: `compute_cost.ops_per_tick`
- **Cost Verdict**: 

## 5. Reproduction & Verification
- **Validation Seeds**: `[1000, 1001, 1002]`
- **Validation Scores per Seed**:
  - Seed 1000:
  - Seed 1001:
  - Seed 1002:

## 6. Verification Checklist
- [ ] Card validated via `neurogenesis.data.catalogue.validate_card()`
- [ ] Valid author ORCID matching `^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$`
- [ ] Valid paper DOI matching `^10\.\d{4,9}/[-._;()/:A-Za-z0-9]+$` (if provided)
- [ ] Re-growing on seeds `[1000, 1001, 1002]` reproduces targets within numerical tolerance
- [ ] Card JSON placed in `catalogue/<circuit-id>.json`
