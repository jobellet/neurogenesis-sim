import numpy as np
from typing import Dict, Any, Tuple

from neurogenesis.tissue import Tissue
from neurogenesis.params import Param, resolve, Const, worst_case
from neurogenesis.spatial import CellList
from neurogenesis.stages.base import register_stage

# Mean neighbours per cell assumed by the costs of neighbour interactions (cell-list bins of side the radius).
_MEAN_NEIGHBOURS = 27
# Bytes per neighbour pair at the peak of a cell-list query plus the pair forces (measured, see the tests).
_PAIR_BYTES = 100
# Fixed direction used to separate exactly coincident cells (antisymmetric in the pair order, no random draw).
_TIE_DIRECTION = np.ones(3) / np.sqrt(3.0)


def _neighbour_pairs(pos: np.ndarray, radius: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Ordered pairs (i, j), i != j, closer than `radius` (cell list, O(N k)), their distances and unit vectors i -> j."""
    src, dst, d = CellList(pos, radius).query_radius(pos, radius, return_distances=True)
    keep = src != dst
    src, dst, d = src[keep], dst[keep], d[keep]
    u = pos[dst] - pos[src]
    tie = d < 1e-12
    u[tie] = np.sign(dst[tie] - src[tie])[:, None] * _TIE_DIRECTION
    u[~tie] /= d[~tie, None]
    return src, dst, d, u


def _sum_pair_moves(n: int, src: np.ndarray, f: np.ndarray, u: np.ndarray) -> np.ndarray:
    """Displacement of each cell: sum over its pairs of f * u (f > 0 moves i towards j)."""
    fu = f[:, None] * u
    return np.stack([np.bincount(src, weights=fu[:, k], minlength=n) for k in range(3)], axis=1)


def _sample_field(field_obj: Any, points: np.ndarray) -> np.ndarray:
    """Scalar values of a field at points (first column of multi-column fields, e.g. a layer label)."""
    v = np.asarray(field_obj.values(points) if hasattr(field_obj, "values") else field_obj(points), dtype=np.float64)
    return v[:, 0] if v.ndim == 2 else v


def _field_gradient(field_obj: Any, pos: np.ndarray, h: float) -> np.ndarray:
    """Central-difference gradient (N, 3) of a scalar field, one vectorised evaluation at the 6 N offset points."""
    offsets = np.concatenate([np.eye(3), -np.eye(3)]) * h
    v = _sample_field(field_obj, (pos[None, :, :] + offsets[:, None, :]).reshape(-1, 3)).reshape(6, len(pos))
    return (v[:3] - v[3:]).T / (2.0 * h)


def _unit_rows(v: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(v, axis=1, keepdims=True)
    norms[norms < 1e-12] = 1.0
    return v / norms


@register_stage("migrate")
class MigrateStage:
    """Cell migration, repeated for `steps` sub-steps (all Params; defaults are neutral, i.e. no movement).

    Per sub-step each living cell moves by `speed` along `direction` (or radially away from `target` where `radial`;
    a negative speed moves inwards), plus `chemotaxis` up the gradient of the scalar field named by
    `chemotaxis_field` (unit gradient direction, central differences with step `gradient_step`; a negative
    `chemotaxis` moves down the gradient). A move is refused where `stop_field` (sampled at the new position) is true
    or > 0, or where it leaves the geometry named by `boundary`. Cells whose `layer_field` label (first column, e.g. a
    LayerStackField) equals `target_layer` have arrived and stay. With `min_distance` > 0, living cells closer than
    `min_distance` push each other apart by half their overlap (soft repulsion through the cell list, O(N k)), so
    spacing approaches `min_distance` over the sub-steps.
    Guided radial and tangential migration and chemotactic cues: Marín & Rubenstein 2003, Annu Rev Neurosci.
    """

    def __init__(self):
        pass

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Param]) -> Tuple[int, int]:
        steps = max(1, int(worst_case(params.get("steps"), 1)))
        bytes_cost = N * 8 * 10
        ops_cost = N * 10
        if params.get("chemotaxis_field") is not None:
            bytes_cost += N * 8 * 3 * 6 * 2
            ops_cost += N * 6 * 20
        if float(worst_case(params.get("min_distance"), 0.0)) > 0:
            cl_bytes, cl_ops = CellList.declared_cost(N, N, _MEAN_NEIGHBOURS)
            bytes_cost += N * _MEAN_NEIGHBOURS * _PAIR_BYTES
            ops_cost += cl_ops + N * _MEAN_NEIGHBOURS * 20
        return int(bytes_cost), int(ops_cost * steps)

    def run(self, tissue: Tissue, params: Dict[str, Param], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        N = len(tissue.alive)
        if N == 0:
            return tissue
        steps = int(resolve(params.get("steps", Const(1)), genome, fields))
        chemo_name = params.get("chemotaxis_field")
        chemo_name = resolve(chemo_name, genome, fields) if chemo_name is not None else None
        h = float(resolve(params.get("gradient_step", Const(1e-3)), genome, fields))
        min_d = float(resolve(params.get("min_distance", Const(0.0)), genome, fields))
        layer_name = params.get("layer_field")
        layer_name = resolve(layer_name, genome, fields) if layer_name is not None else None
        for _ in range(steps):
            self._move(tissue, params, genome, fields, chemo_name, h, layer_name)
            if min_d > 0:
                self._repel(tissue, params, genome, fields, min_d)
        return tissue

    def _move(self, tissue, params, genome, fields, chemo_name, h, layer_name):
        N = len(tissue.alive)
        ctx_vars = {
            "generation": tissue.generation,
            "birth_stage": tissue.birth_stage,
            "cell_type": tissue.cell_type,
            "alive": tissue.alive,
            "parent_id": tissue.parent_id,
            "clone_id": tissue.clone_id,
            "cell_id": tissue.cell_id,
            "x": tissue.positions[:, 0],
            "y": tissue.positions[:, 1],
            "z": tissue.positions[:, 2],
            "np": np,
            **(genome if isinstance(genome, dict) else {}),
        }
        speed_param = params.get("speed", Const(0.0))
        speed = resolve(speed_param, genome, fields, tissue.positions, context_vars=ctx_vars)

        radial = params.get("radial", Const(False))
        is_radial = resolve(radial, genome, fields, tissue.positions, context_vars=ctx_vars)

        target_param = params.get("target", Const(np.array([0.0, 0.0, 0.0])))
        target = resolve(target_param, genome, fields, tissue.positions, context_vars=ctx_vars)

        dir_param = params.get("direction", Const(np.array([1.0, 0.0, 0.0])))
        base_directions = np.asarray(resolve(dir_param, genome, fields, tissue.positions, context_vars=ctx_vars), dtype=np.float64)
        if base_directions.shape == (3,):
            base_directions = np.tile(base_directions, (N, 1))

        diff = tissue.positions - target
        norms = np.linalg.norm(diff, axis=1, keepdims=True)
        norms[norms < 1e-9] = 1.0
        radial_directions = diff / norms

        if np.isscalar(is_radial):
            if is_radial:
                directions = radial_directions
            else:
                directions = base_directions
        else:
            if is_radial.ndim == 1:
                is_radial_mask = is_radial[:, np.newaxis]
            else:
                is_radial_mask = is_radial
            directions = np.where(is_radial_mask, radial_directions, base_directions)

        directions = _unit_rows(directions)

        if np.isscalar(speed):
            step = speed * directions
        else:
            if speed.ndim == 1:
                speed = speed[:, np.newaxis]
            step = speed * directions

        if chemo_name is not None:
            gain = resolve(params.get("chemotaxis", Const(0.0)), genome, fields, tissue.positions, context_vars=ctx_vars)
            if np.any(np.asarray(gain) != 0):
                grad = _unit_rows(_field_gradient(fields[chemo_name], tissue.positions, h))
                step = step + np.reshape(gain, (-1, 1)) * grad

        new_positions = tissue.positions + step

        stop_field_param = params.get("stop_field", None)
        boundary_param = params.get("boundary", None)

        mask = tissue.alive.astype(bool)

        if stop_field_param is not None:
            stop_condition = resolve(stop_field_param, genome, fields, new_positions, context_vars=ctx_vars)
            if np.isscalar(stop_condition):
                if stop_condition:
                    mask[:] = False
            else:
                if stop_condition.dtype == bool:
                    mask &= ~stop_condition
                else:
                    mask &= (stop_condition <= 0)

        if boundary_param is not None:
            boundary_name = resolve(boundary_param, genome, fields, tissue.positions, context_vars=ctx_vars)
            if isinstance(boundary_name, str) and boundary_name in fields:
                geom = fields[boundary_name]
                if hasattr(geom, "contains"):
                    mask &= geom.contains(new_positions)

        if layer_name is not None:
            target_layer = resolve(params.get("target_layer", Const(0)), genome, fields, tissue.positions, context_vars=ctx_vars)
            mask &= _sample_field(fields[layer_name], tissue.positions) != target_layer

        tissue.positions = np.where(mask[:, np.newaxis], new_positions, tissue.positions)

    def _repel(self, tissue, params, genome, fields, min_d):
        idx = np.flatnonzero(tissue.alive)
        if len(idx) < 2:
            return
        pos = tissue.positions[idx]
        src, dst, d, u = _neighbour_pairs(pos, min_d)
        new_pos = pos + _sum_pair_moves(len(idx), src, -0.5 * (min_d - d), u)
        boundary_param = params.get("boundary", None)
        if boundary_param is not None:
            boundary_name = resolve(boundary_param, genome, fields, pos)
            geom = fields.get(boundary_name) if isinstance(boundary_name, str) else None
            if hasattr(geom, "contains"):
                new_pos = np.where(geom.contains(new_pos)[:, None], new_pos, pos)
        tissue.positions[idx] = new_pos


@register_stage("sort")
class SortStage:
    """Cell sorting in two modes, both off by default (either or both may be given; rank runs first).

    Rank mode (`axis` or `key` given): cells are re-ordered along `axis` by `key` ("birth_stage", "expression" or a
    per-cell array), keeping their set of projections; e.g. inside-out layering by birth order.
    Differential adhesion (`adhesion` given, a types x types matrix indexed by `cell_type`): for `steps` iterations,
    each pair of living cells closer than `radius` (cell list, O(N k)) interacts. Below `contact` (default radius / 2)
    they push apart by half their overlap (volume exclusion); between `contact` and `radius`, cell i moves towards j
    by `rate` * adhesion[type_i, type_j] * (d - contact) (negative entries repel, e.g. homotypic repulsion).
    Stronger same-type than cross-type adhesion segregates mixed types (Steinberg 1963, Science).
    """

    def __init__(self):
        pass

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Param]) -> Tuple[int, int]:
        bytes_cost = N * 8 * 7
        ops_cost = int(N * np.log2(max(2, N)) + N * 3)
        if params.get("adhesion") is not None:
            steps = max(1, int(worst_case(params.get("steps"), 1)))
            cl_bytes, cl_ops = CellList.declared_cost(N, N, _MEAN_NEIGHBOURS)
            bytes_cost += N * _MEAN_NEIGHBOURS * _PAIR_BYTES
            ops_cost += steps * (cl_ops + N * _MEAN_NEIGHBOURS * 20)
        return int(bytes_cost), int(ops_cost)

    def run(self, tissue: Tissue, params: Dict[str, Param], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        N = len(tissue.alive)
        if N == 0:
            return tissue
        if "axis" in params or "key" in params:
            self._rank(tissue, params, genome, fields)
        if params.get("adhesion") is not None:
            self._adhere(tissue, params, genome, fields)
        return tissue

    def _adhere(self, tissue, params, genome, fields):
        A = np.asarray(resolve(params["adhesion"], genome, fields), dtype=np.float64)
        radius = float(resolve(params.get("radius", Const(0.1)), genome, fields))
        contact = float(resolve(params.get("contact", Const(radius / 2)), genome, fields))
        rate = float(resolve(params.get("rate", Const(0.1)), genome, fields))
        steps = int(resolve(params.get("steps", Const(1)), genome, fields))
        idx = np.flatnonzero(tissue.alive)
        types = tissue.cell_type[idx]
        if A.ndim != 2 or A.shape[0] != A.shape[1] or (len(idx) and (types.min() < 0 or types.max() >= A.shape[0])):
            raise ValueError("adhesion must be a square matrix with a row for every cell_type of the living cells")
        if len(idx) < 2 or radius <= 0:
            return
        pos = tissue.positions[idx].copy()
        for _ in range(steps):
            src, dst, d, u = _neighbour_pairs(pos, radius)
            f = np.where(d < contact, -0.5 * (contact - d), rate * A[types[src], types[dst]] * (d - contact))
            pos += _sum_pair_moves(len(idx), src, f, u)
        tissue.positions[idx] = pos

    def _rank(self, tissue, params, genome, fields):
        N = len(tissue.alive)
        axis_param = params.get("axis", Const(np.array([0.0, 0.0, 1.0])))
        axis = np.asarray(resolve(axis_param, genome, fields, tissue.positions), dtype=np.float64)
        if axis.shape == (3,):
            axis = axis / (np.linalg.norm(axis) + 1e-9)
        else:
            norms = np.linalg.norm(axis, axis=1, keepdims=True)
            norms[norms < 1e-9] = 1.0
            axis = axis / norms

        key_param = params.get("key", Const("birth_stage"))
        key = resolve(key_param, genome, fields, tissue.positions)
        if isinstance(key, np.ndarray) and key.size > 1:
             sort_values = key
        else:
            key_str = str(key)
            if key_str == "birth_stage":
                sort_values = tissue.birth_stage
            elif key_str == "expression":
                if tissue.expression.shape[1] > 0:
                    sort_values = tissue.expression[:, 0]
                else:
                    sort_values = np.zeros(N)
            else:
                sort_values = np.zeros(N)

        sort_idx = np.argsort(sort_values)

        if axis.ndim == 1:
            projections = np.dot(tissue.positions, axis)
        else:
            projections = np.sum(tissue.positions * axis, axis=1)

        sorted_projections = np.sort(projections)

        if axis.ndim == 1:
            positions_no_proj = tissue.positions - np.outer(projections, axis)
            new_positions = positions_no_proj.copy()
            new_positions[sort_idx] += np.outer(sorted_projections, axis)
            tissue.positions = new_positions
        else:
            positions_no_proj = tissue.positions - projections[:, np.newaxis] * axis
            new_positions = positions_no_proj.copy()
            new_positions[sort_idx] += sorted_projections[:, np.newaxis] * axis[sort_idx]
            tissue.positions = new_positions
