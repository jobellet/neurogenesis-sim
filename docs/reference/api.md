# Python API

Generated from the docstrings of the installed package.

## Development
```{eval-rst}
.. automodule:: neurogenesis.development
   :members: BodyPlan, Region, FixedPlacement, grow, region_of, knockout, tonic_current, register

.. automodule:: neurogenesis.development.parallel
   :members: set_workers, map_calls, grow_many

.. automodule:: neurogenesis.development.legacy_compiler
   :members: compile_plan_to_schedule, compile_plan_to_project
```

## Projects, Params and stages
```{eval-rst}
.. automodule:: neurogenesis.project.io
   :members: Project

.. automodule:: neurogenesis.project.schema
   :members: validate, migrate

.. automodule:: neurogenesis.params
   :members: Const, Gene, Field, Fit, Expr, param_from_dict, param_to_dict, resolve, collect_genes

.. automodule:: neurogenesis.stages.base
   :members: register_stage, Stage, run_schedule, schedule_cost

.. automodule:: neurogenesis.tissue
   :members: Tissue, SparseConnectivity
```

## Geometry and fields
```{eval-rst}
.. automodule:: neurogenesis.geometry
   :members: Box, Sphere, Ellipsoid, Cylinder, Sheet2D, CurvedSheet, Union, Difference, geometry_from_dict, register_geometry

.. automodule:: neurogenesis.fields.core
   :members: GridField, AnalyticField, LayerStackField, field_from_dict, register_field

.. automodule:: neurogenesis.fields.maps
   :members:
```

## Genomes, evolution, modules
```{eval-rst}
.. automodule:: neurogenesis.genome
   :members: get_gene, set_gene, to_unit, from_unit, to_json, from_json, guidance_genes, body_genes, field_genes, differentiation_genes, identity_genes, typed_guidance_genes

.. automodule:: neurogenesis.evolution
   :members: evolve, choose, audit, robust_value, seeds_of

.. automodule:: neurogenesis.modules
   :members: Module, compose
```

## Spiking
```{eval-rst}
.. automodule:: neurogenesis.spiking.network
   :members: SNNNetwork, NeuronData, SynapseData

.. automodule:: neurogenesis.spiking.batch
   :members: simulate_counts

.. automodule:: neurogenesis.spiking.models
   :members: register_model

.. automodule:: neurogenesis.spiking.plasticity
   :members: STDPRule, HebbianRule, ThreeFactorRule
```

## Cost and analysis
```{eval-rst}
.. automodule:: neurogenesis.cost
   :members: estimate, check, calibrate, memory_bytes, available_memory, CostError

.. automodule:: neurogenesis.analysis
   :members: fi_curve, nearest_neighbour_regularity
```

## Interoperability
```{eval-rst}
.. automodule:: neurogenesis.interop.core
   :members: export_network, import_network, formats, register_format, ExportReport

.. automodule:: neurogenesis.interop.dynamics
   :members: tau_ms, shift_from_tau, delay_ms, delay_ticks, lif_params, LIFParams

.. automodule:: neurogenesis.interop.sonata
   :members: export_sonata, import_sonata
```

## Bridge
```{eval-rst}
.. automodule:: neurogenesis.bridge.ngb
   :members:
```
