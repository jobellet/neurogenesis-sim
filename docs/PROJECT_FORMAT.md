# Project Format (Schema Version 1.0.0)

A `Project` in `neurogenesis-sim` represents the entire state of a developmental experiment, including geometry, generated or painted fields, the schedule of developmental stages, the genome, plugins, and metadata.

## File Structure

A project is stored on disk primarily as a JSON file. If the project contains large NumPy arrays (e.g., from dense field data or genome representations), they are extracted and saved into a sidecar `.npz` file to keep the JSON clean and small.

For example, if you save to `my_project.json`, the files created might be:
- `my_project.json`: Contains the JSON representation of the project.
- `my_project.npz` (optional): A compressed numpy archive containing any `np.ndarray` objects found in the project.

### Array Reference Mechanism

When `Project.save()` encounters a NumPy array (`np.ndarray`), it replaces the array in the JSON tree with a dictionary containing a special reference key. The array is then saved into the `.npz` sidecar file using the value of that key as its filename/identifier within the archive.

During `Project.load()`, the JSON file is read first. Then, if the sidecar `.npz` file exists, it is loaded. The loader traverses the JSON structure, and whenever it encounters the special reference dictionary, it replaces it with the corresponding array loaded from the `.npz` file.

## Schema Fields

A valid version 1.0.0 Project dictionary must contain the following keys:

- **`version`** (`str`): The schema version. Currently `"1.0.0"`.
- **`geometry`** (`dict`): Defines the shapes in 2D or 3D, such as primitives, meshes, or voxel masks.
- **`fields`** (`dict`): Hand-made or generated data on the geometry (scalar fields like morphogen gradients, vector fields like orientation, or point sets).
- **`schedule`** (`list`): An ordered list of Stage configuration dictionaries, possibly repeated or looped.
- **`genome`** (`dict`): A nested dictionary of genes, compatible with `neurogenesis.genome`. The optional key
  `"__fit__"` holds fitted values of `Fit` params, `{target: value}` (written by `neurogenesis.fitting`); a `Fit` whose
  target is absent resolves to its `init`, so projects without this key develop exactly as before.
- **`plan`** (`dict`, optional): A legacy `BodyPlan` dictionary, used for backward compatibility.
- **`plugins`** (`list` of `str`): A list of Python module names that register rules, stages, or models to be imported on load.
- **`neuron_model`** (`str`): The neuron model used. Defaults to `"lif_int"`.
- **`metadata`** (`dict`): Any additional user or application metadata.

## Backward Compatibility

The schema includes a migration system. Older project formats (e.g., `"0.1.0"`) which consisted only of a `BodyPlan` will be automatically migrated to `"1.0.0"` by wrapping the old dictionary inside the `"plan"` field and applying defaults to the remaining required fields.
