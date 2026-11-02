from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List
from neurogenesis.spiking.network import SNNNetwork, NeuronData, SynapseData

# Optional per-synapse morphology and conductance arrays (K2, P4) and the value of a synapse that has none.
_SYNAPSE_OPTIONAL = {"pre_node": (np.int32, -1), "post_node": (np.int32, -1),
                     "path_length": (np.float32, np.nan), "dendritic_distance": (np.float32, np.nan),
                     "e_rev": (np.float32, np.nan), "tau_decay": (np.float32, np.nan)}


@dataclass
class SparseConnectivity:
    """Synapses as struct of arrays. `receptor_class` (E,) uint8 (0 = the classic signed synapse) always exists; the
    morphology arrays `pre_node`, `post_node` (arbor node indices, -1 = soma / none), `path_length` and
    `dendritic_distance` (space units, NaN = unknown) and conductance arrays `e_rev` (mV), `tau_decay` (ms) are None
    until a stage sets them. Use `take` and `concat` to filter or join synapses so that every array stays aligned."""
    pre: np.ndarray
    post: np.ndarray
    weight: np.ndarray
    delay: np.ndarray
    receptor_class: Optional[np.ndarray] = None
    pre_node: Optional[np.ndarray] = None
    post_node: Optional[np.ndarray] = None
    path_length: Optional[np.ndarray] = None
    dendritic_distance: Optional[np.ndarray] = None
    e_rev: Optional[np.ndarray] = None
    tau_decay: Optional[np.ndarray] = None

    def __post_init__(self) -> None:
        if self.receptor_class is None or len(self.receptor_class) != len(self.pre):
            if self.receptor_class is not None and len(self.receptor_class):
                raise ValueError("receptor_class must have one entry per synapse")
            self.receptor_class = np.zeros(len(self.pre), dtype=np.uint8)

    @classmethod
    def empty(cls) -> SparseConnectivity:
        return cls(
            pre=np.zeros(0, dtype=np.int32),
            post=np.zeros(0, dtype=np.int32),
            weight=np.zeros(0, dtype=np.int32),
            delay=np.zeros(0, dtype=np.int32)
        )

    def _sync(self) -> None:
        """A default (all-zero) receptor_class follows the core arrays when code replaced them directly; any other
        length mismatch is an error."""
        E = len(self.pre)
        if len(self.receptor_class) != E:
            if np.any(self.receptor_class):
                raise ValueError(f"receptor_class has {len(self.receptor_class)} entries for {E} synapses")
            self.receptor_class = np.zeros(E, dtype=np.uint8)
        for k in _SYNAPSE_OPTIONAL:
            v = getattr(self, k)
            if v is not None and len(v) != E:
                raise ValueError(f"{k} has {len(v)} entries for {E} synapses")

    def _arrays(self):
        self._sync()
        out = {k: getattr(self, k) for k in ("pre", "post", "weight", "delay", "receptor_class")}
        out.update({k: getattr(self, k) for k in _SYNAPSE_OPTIONAL if getattr(self, k) is not None})
        return out

    def take(self, sel: np.ndarray, pre: Optional[np.ndarray] = None, post: Optional[np.ndarray] = None) -> SparseConnectivity:
        """Synapses selected by a boolean mask or index array (every array kept aligned); `pre` / `post` replace the
        selected indices (e.g. after re-indexing cells)."""
        d = {k: v[sel] for k, v in self._arrays().items()}
        if pre is not None:
            d["pre"] = pre
        if post is not None:
            d["post"] = post
        return SparseConnectivity(**d)

    @classmethod
    def concat(cls, parts: List[SparseConnectivity]) -> SparseConnectivity:
        """Synapses of several stores; optional arrays present in any part are filled with their default elsewhere."""
        parts = [p for p in parts if p is not None]
        if not parts:
            return cls.empty()
        for p in parts:
            p._sync()
        d = {k: np.concatenate([getattr(p, k) for p in parts]) for k in ("pre", "post", "weight", "delay", "receptor_class")}
        for k, (dt, fill) in _SYNAPSE_OPTIONAL.items():
            if any(getattr(p, k) is not None for p in parts):
                d[k] = np.concatenate([getattr(p, k) if getattr(p, k) is not None else np.full(len(p.pre), fill, dt)
                                       for p in parts]).astype(dt)
        return cls(**d)

    def append(self, pre, post, weight, delay, **extra) -> SparseConnectivity:
        """This store plus new synapses (int32 core arrays; `extra` per-synapse arrays such as receptor_class)."""
        new = SparseConnectivity(np.asarray(pre, np.int32), np.asarray(post, np.int32), np.asarray(weight, np.int32),
                                 np.asarray(delay, np.int32), **extra)
        out = SparseConnectivity.concat([self, new])
        for k in ("pre", "post", "weight", "delay"):
            setattr(out, k, getattr(out, k).astype(np.int32))
        return out

    def nbytes(self) -> int:
        return int(sum(v.nbytes for v in self._arrays().values()))

def _concat_morphology(tissues, offsets):
    """Arbors of concatenated tissues, cell indices shifted by each tissue's offset (None if no tissue has arbors)."""
    if all(t.morphology is None for t in tissues):
        return None
    from neurogenesis.arbors import ArborStore
    parts = []
    for t, off in zip(tissues, offsets):
        if t.morphology is not None:
            m = t.morphology
            parts.append(ArborStore(m.xyz, m.radius, m.parent, m.compartment, m.cell + int(off), dict(m.labels)))
    return ArborStore.concatenate(parts)


@dataclass
class Tissue:
    positions: np.ndarray
    directions: np.ndarray
    cell_id: np.ndarray
    parent_id: np.ndarray
    clone_id: np.ndarray
    birth_stage: np.ndarray
    cell_type: np.ndarray
    region: np.ndarray
    expression: np.ndarray
    sign: np.ndarray
    alive: np.ndarray
    mode: np.ndarray
    shift_v: np.ndarray
    shift_s: np.ndarray
    base_weight: np.ndarray
    conn_radius: np.ndarray
    conn_prob: np.ndarray
    burst_period: np.ndarray
    burst_duty: np.ndarray
    poisson_hz: np.ndarray
    refractory: np.ndarray
    role: np.ndarray
    compartment: np.ndarray
    threshold: np.ndarray
    connectivity: SparseConnectivity
    expression_names: List[str] = field(default_factory=list)
    _next_cell_id: int = 0
    generation: Optional[np.ndarray] = None  # (N,) int32 divisions since the founder; zeros when omitted
    transmitter: Optional[np.ndarray] = None  # (N,) int8 bitmask of transmitters released (0 = classic sign only)
    receptor_expression: Optional[np.ndarray] = None  # (N, R) float32 receptor levels; (N, 0) when omitted
    morphology: Optional[object] = None  # optional ArborStore (neurogenesis.morphology), arbors of the cells

    def __post_init__(self) -> None:
        if self.generation is None:
            self.generation = np.zeros(len(self.alive), dtype=np.int32)
        if self.transmitter is None:
            self.transmitter = np.zeros(len(self.alive), dtype=np.int8)
        if self.receptor_expression is None:
            self.receptor_expression = np.zeros((len(self.alive), 0), dtype=np.float32)

    @property
    def lineage_id(self) -> np.ndarray:
        """Alias for backward compatibility."""
        return self.cell_id

    @lineage_id.setter
    def lineage_id(self, val: np.ndarray) -> None:
        self.cell_id = val

    @classmethod
    def empty(cls, K: int = 0) -> Tissue:
        return cls(
            positions=np.zeros((0, 3), dtype=np.float64),
            directions=np.zeros((0, 3), dtype=np.float32),
            cell_id=np.zeros(0, dtype=np.int32),
            parent_id=np.zeros(0, dtype=np.int32),
            clone_id=np.zeros(0, dtype=np.int32),
            birth_stage=np.zeros(0, dtype=np.int32),
            cell_type=np.zeros(0, dtype=np.int32),
            region=np.zeros(0, dtype=np.int32),
            expression=np.zeros((0, K), dtype=np.float32),
            sign=np.zeros(0, dtype=np.int8),
            alive=np.zeros(0, dtype=bool),
            mode=np.zeros(0, dtype=np.int32),
            shift_v=np.zeros(0, dtype=np.int32),
            shift_s=np.zeros(0, dtype=np.int32),
            base_weight=np.zeros(0, dtype=np.int32),
            conn_radius=np.zeros(0, dtype=np.float32),
            conn_prob=np.zeros(0, dtype=np.float32),
            burst_period=np.zeros(0, dtype=np.int32),
            burst_duty=np.zeros(0, dtype=np.int32),
            poisson_hz=np.zeros(0, dtype=np.float64),
            refractory=np.zeros(0, dtype=np.int32),
            role=np.zeros(0, dtype=np.int32),
            compartment=np.zeros(0, dtype=np.int32),
            threshold=np.zeros(0, dtype=np.int32),
            connectivity=SparseConnectivity.empty(),
            expression_names=[],
            _next_cell_id=0
        )

    def add_cells(self, N: int, positions: Optional[np.ndarray] = None, K: int = 0, parent_ids: Optional[np.ndarray] = None, **kwargs) -> None:
        """Adds N new cells. cell_ids are automatically assigned."""
        if N == 0:
            return
        
        K = K if K > 0 else self.expression.shape[1] if self.expression.shape[1] > 0 else K
        if self.expression.shape[1] > 0 and K > 0 and self.expression.shape[1] != K:
            raise ValueError(f"Expression dimension K={K} does not match existing K={self.expression.shape[1]}")

        # Arrays for new cells
        pos = positions.astype(np.float64) if positions is not None else np.zeros((N, 3), dtype=np.float64)
        dir = kwargs.get("directions", np.zeros((N, 3), dtype=np.float32))
        if "directions" not in kwargs:
            dir[:, 0] = 1.0  # Default to (1, 0, 0)
        
        if "cell_id" in kwargs:
            c_id = np.asarray(kwargs["cell_id"], dtype=np.int32)
            if len(c_id) > 0:
                self._next_cell_id = max(self._next_cell_id, int(np.max(c_id)) + 1)
        else:
            c_id = np.arange(self._next_cell_id, self._next_cell_id + N, dtype=np.int32)
            self._next_cell_id += N
        
        par_id = parent_ids if parent_ids is not None else np.full(N, -1, dtype=np.int32)
        
        # Proper clone_id resolution:
        # If explicitly passed in kwargs, use it.
        # Otherwise: for founder cells (par_id == -1), clone_id = c_id.
        # For child cells, lookup parent's clone_id in self.clone_id!
        if "clone_id" in kwargs:
            c_clone_id = np.asarray(kwargs["clone_id"], dtype=np.int32)
        else:
            c_clone_id = np.array(c_id, dtype=np.int32)
            if len(self.cell_id) > 0:
                # Parent's clone_id among existing cells (the last cell with that cell_id), by binary search
                order = np.argsort(self.cell_id, kind="stable")
                ids = self.cell_id[order]
                pid = np.asarray(par_id)
                at = np.searchsorted(ids, pid, side="right") - 1
                found = (at >= 0) & (ids[np.maximum(at, 0)] == pid) & (pid != -1)
                c_clone_id[found] = self.clone_id[order[at[found]]]

        birth = kwargs.get("birth_stage", np.zeros(N, dtype=np.int32))
        gen = np.asarray(kwargs.get("generation", np.zeros(N, dtype=np.int32)), dtype=np.int32)
        ctype = kwargs.get("cell_type", np.zeros(N, dtype=np.int32))
        reg = kwargs.get("region", np.zeros(N, dtype=np.int32))
        expr = kwargs.get("expression", np.zeros((N, K), dtype=np.float32))
        
        # Single source of truth for sign:
        # sign is +1 (exc) or -1 (inh)
        sgn = kwargs.get("sign", np.ones(N, dtype=np.int8))
        sgn = np.asarray(sgn, dtype=np.int8)
        alv = kwargs.get("alive", np.ones(N, dtype=bool))
        
        # Neuron parameters - aligned with grow.py defaults
        mode = kwargs.get("mode", np.zeros(N, dtype=np.int32))
        shift_v = kwargs.get("shift_v", np.full(N, 5, dtype=np.int32))
        shift_s = kwargs.get("shift_s", np.full(N, 4, dtype=np.int32))
        
        # base_weight: magnitude is 1 by default (or abs of provided base_weight), signed by sgn
        if "base_weight" in kwargs:
            raw_bw = np.asarray(kwargs["base_weight"], dtype=np.int32)
            base_weight = (np.abs(raw_bw) * np.where(sgn >= 0, 1, -1)).astype(np.int32)
        else:
            base_weight = np.where(sgn >= 0, 1, -1).astype(np.int32)

        conn_radius = kwargs.get("conn_radius", np.zeros(N, dtype=np.float32))
        conn_prob = kwargs.get("conn_prob", np.zeros(N, dtype=np.float32))
        burst_period = kwargs.get("burst_period", np.full(N, 200, dtype=np.int32))
        burst_duty = kwargs.get("burst_duty", np.full(N, 24, dtype=np.int32))
        poisson_hz = kwargs.get("poisson_hz", np.full(N, 25.0, dtype=np.float64))
        refractory = kwargs.get("refractory", np.zeros(N, dtype=np.int32))
        role = kwargs.get("role", np.zeros(N, dtype=np.int32))
        compartment = kwargs.get("compartment", np.full(N, -1, dtype=np.int32))
        threshold = kwargs.get("threshold", np.full(N, 1024, dtype=np.int32))
        
        if self.positions.shape[0] == 0:
            self.expression = np.zeros((0, K), dtype=np.float32)

        self.positions = np.concatenate([self.positions, pos])
        self.directions = np.concatenate([self.directions, dir])
        self.cell_id = np.concatenate([self.cell_id, c_id])
        self.parent_id = np.concatenate([self.parent_id, par_id])
        self.clone_id = np.concatenate([self.clone_id, c_clone_id])
        self.birth_stage = np.concatenate([self.birth_stage, birth])
        self.generation = np.concatenate([self.generation, gen])
        self.cell_type = np.concatenate([self.cell_type, ctype])
        self.region = np.concatenate([self.region, reg])
        self.expression = np.concatenate([self.expression, expr])
        self.sign = np.concatenate([self.sign, sgn])
        self.alive = np.concatenate([self.alive, alv])
        
        self.mode = np.concatenate([self.mode, mode])
        self.shift_v = np.concatenate([self.shift_v, shift_v])
        self.shift_s = np.concatenate([self.shift_s, shift_s])
        self.base_weight = np.concatenate([self.base_weight, base_weight])
        self.conn_radius = np.concatenate([self.conn_radius, conn_radius])
        self.conn_prob = np.concatenate([self.conn_prob, conn_prob])
        self.burst_period = np.concatenate([self.burst_period, burst_period])
        self.burst_duty = np.concatenate([self.burst_duty, burst_duty])
        self.poisson_hz = np.concatenate([self.poisson_hz, poisson_hz])
        self.refractory = np.concatenate([self.refractory, refractory])
        self.role = np.concatenate([self.role, role])
        self.compartment = np.concatenate([self.compartment, compartment])
        self.threshold = np.concatenate([self.threshold, threshold])
        self.transmitter = np.concatenate([self.transmitter, np.asarray(kwargs.get("transmitter", np.zeros(N)), dtype=np.int8)])
        R = self.receptor_expression.shape[1]
        rex = kwargs.get("receptor_expression")
        if rex is None:
            rex = np.zeros((N, R), dtype=np.float32)
        rex = np.asarray(rex, dtype=np.float32).reshape(N, -1)
        if R and rex.shape[1] != R:
            raise ValueError(f"receptor_expression has {rex.shape[1]} receptors, the tissue has {R}")
        if R == 0 and rex.shape[1] > 0:
            self.receptor_expression = np.zeros((len(self.alive) - N, rex.shape[1]), dtype=np.float32)
        self.receptor_expression = np.concatenate([self.receptor_expression, rex])

    def kill(self, mask: np.ndarray) -> None:
        """Sets alive=False for cells where mask is True."""
        self.alive[mask] = False

    def compact(self) -> None:
        """Removes dead cells, remaps connectivity indices, dropping synapses attached to dead cells."""
        alive_mask = self.alive
        if alive_mask.all():
            return
            
        N = len(self.alive)
        new_indices = np.full(N, -1, dtype=np.int32)
        new_indices[alive_mask] = np.arange(np.sum(alive_mask), dtype=np.int32)

        # Subset arrays
        self.positions = self.positions[alive_mask]
        self.directions = self.directions[alive_mask]
        self.cell_id = self.cell_id[alive_mask]
        self.parent_id = self.parent_id[alive_mask]
        self.clone_id = self.clone_id[alive_mask]
        self.birth_stage = self.birth_stage[alive_mask]
        self.generation = self.generation[alive_mask]
        self.cell_type = self.cell_type[alive_mask]
        self.region = self.region[alive_mask]
        self.expression = self.expression[alive_mask]
        self.sign = self.sign[alive_mask]
        self.alive = self.alive[alive_mask]
        
        self.mode = self.mode[alive_mask]
        self.shift_v = self.shift_v[alive_mask]
        self.shift_s = self.shift_s[alive_mask]
        self.base_weight = self.base_weight[alive_mask]
        self.conn_radius = self.conn_radius[alive_mask]
        self.conn_prob = self.conn_prob[alive_mask]
        self.burst_period = self.burst_period[alive_mask]
        self.burst_duty = self.burst_duty[alive_mask]
        self.poisson_hz = self.poisson_hz[alive_mask]
        self.refractory = self.refractory[alive_mask]
        self.role = self.role[alive_mask]
        self.compartment = self.compartment[alive_mask]
        self.threshold = self.threshold[alive_mask]
        self.transmitter = self.transmitter[alive_mask]
        self.receptor_expression = self.receptor_expression[alive_mask]
        if self.morphology is not None:
            self.morphology = self.morphology.select_cells(np.flatnonzero(alive_mask), renumber=new_indices)
        
        # Remap synapses
        if len(self.connectivity.pre) > 0:
            pre_valid = (self.connectivity.pre >= 0) & (self.connectivity.pre < N)
            post_valid = (self.connectivity.post >= 0) & (self.connectivity.post < N)
            syn_mask = pre_valid & post_valid
            
            pre_alive = np.zeros_like(syn_mask, dtype=bool)
            post_alive = np.zeros_like(syn_mask, dtype=bool)
            pre_alive[syn_mask] = alive_mask[self.connectivity.pre[syn_mask]]
            post_alive[syn_mask] = alive_mask[self.connectivity.post[syn_mask]]
            
            valid_synapses = syn_mask & pre_alive & post_alive
            
            c = self.connectivity
            self.connectivity = c.take(valid_synapses, pre=new_indices[c.pre[valid_synapses]],
                                       post=new_indices[c.post[valid_synapses]])

    def subset(self, indices: np.ndarray) -> Tissue:
        """Returns a new Tissue with only the given cell indices (assumes connectivity only between subset)."""
        t = Tissue(
            positions=self.positions[indices].copy(),
            directions=self.directions[indices].copy(),
            cell_id=self.cell_id[indices].copy(),
            parent_id=self.parent_id[indices].copy(),
            clone_id=self.clone_id[indices].copy(),
            birth_stage=self.birth_stage[indices].copy(),
            cell_type=self.cell_type[indices].copy(),
            region=self.region[indices].copy(),
            expression=self.expression[indices].copy(),
            sign=self.sign[indices].copy(),
            alive=self.alive[indices].copy(),
            mode=self.mode[indices].copy(),
            shift_v=self.shift_v[indices].copy(),
            shift_s=self.shift_s[indices].copy(),
            base_weight=self.base_weight[indices].copy(),
            conn_radius=self.conn_radius[indices].copy(),
            conn_prob=self.conn_prob[indices].copy(),
            burst_period=self.burst_period[indices].copy(),
            burst_duty=self.burst_duty[indices].copy(),
            poisson_hz=self.poisson_hz[indices].copy(),
            refractory=self.refractory[indices].copy(),
            role=self.role[indices].copy(),
            compartment=self.compartment[indices].copy(),
            threshold=self.threshold[indices].copy(),
            connectivity=SparseConnectivity.empty(),
            expression_names=list(self.expression_names),
            _next_cell_id=self._next_cell_id,
            generation=self.generation[indices].copy(),
            transmitter=self.transmitter[indices].copy(),
            receptor_expression=self.receptor_expression[indices].copy(),
        )
        if self.morphology is not None:
            renumber = np.full(len(self.alive), -1, dtype=np.int32)
            renumber[indices] = np.arange(len(indices), dtype=np.int32)
            t.morphology = self.morphology.select_cells(indices, renumber=renumber)
        
        if len(self.connectivity.pre) > 0:
            N = len(self.alive)
            inv_map = np.full(N, -1, dtype=np.int32)
            inv_map[indices] = np.arange(len(indices), dtype=np.int32)
            
            pre_valid = (self.connectivity.pre >= 0) & (self.connectivity.pre < N)
            post_valid = (self.connectivity.post >= 0) & (self.connectivity.post < N)
            syn_mask = pre_valid & post_valid
            
            mapped_pre = np.where(syn_mask, inv_map[self.connectivity.pre], -1)
            mapped_post = np.where(syn_mask, inv_map[self.connectivity.post], -1)
            
            valid = (mapped_pre >= 0) & (mapped_post >= 0)
            
            t.connectivity = self.connectivity.take(valid, pre=mapped_pre[valid], post=mapped_post[valid])
        
        return t

    @classmethod
    def concatenate(cls, tissues: List[Tissue]) -> Tissue:
        if not tissues:
            return cls.empty()
        
        K = tissues[0].expression.shape[1]
        for t in tissues:
            if t.expression.shape[1] != K:
                raise ValueError("Cannot concatenate Tissues with different expression dimensions")

        # Preserve expression names
        expr_names = list(tissues[0].expression_names)
        for t in tissues[1:]:
            if not expr_names and t.expression_names:
                expr_names = list(t.expression_names)

        offsets = np.cumsum([0] + [len(t.alive) for t in tissues[:-1]])
        
        # Ensure unique cell_id, parent_id, clone_id across concatenated tissues:
        # Shift cell_ids, parent_ids, and clone_ids by distinct ID offsets
        id_offsets = [0]
        cur_id_offset = 0
        for t in tissues[:-1]:
            # Each tissue may have max id = max(cell_id, clone_id, _next_cell_id)
            max_id = max(
                t._next_cell_id,
                int(np.max(t.cell_id)) + 1 if len(t.cell_id) > 0 else 0,
                int(np.max(t.clone_id)) + 1 if len(t.clone_id) > 0 else 0
            )
            cur_id_offset += max_id
            id_offsets.append(cur_id_offset)

        shifted_cell_ids = []
        shifted_parent_ids = []
        shifted_clone_ids = []
        for t, id_off in zip(tissues, id_offsets):
            shifted_cell_ids.append(t.cell_id + id_off)
            shifted_parent_ids.append(np.where(t.parent_id >= 0, t.parent_id + id_off, -1))
            shifted_clone_ids.append(t.clone_id + id_off)

        conn = SparseConnectivity.concat([t.connectivity.take(slice(None), pre=t.connectivity.pre + off,
                                                              post=t.connectivity.post + off)
                                          for t, off in zip(tissues, offsets)])
        R = max(t.receptor_expression.shape[1] for t in tissues)
        if any(t.receptor_expression.shape[1] not in (0, R) for t in tissues):
            raise ValueError("Cannot concatenate Tissues with different receptor dimensions")
        rex = np.concatenate([t.receptor_expression if t.receptor_expression.shape[1] == R
                              else np.zeros((len(t.alive), R), np.float32) for t in tissues])
        
        total_next_id = cur_id_offset + max(
            tissues[-1]._next_cell_id,
            int(np.max(tissues[-1].cell_id)) + 1 if len(tissues[-1].cell_id) > 0 else 0
        )

        return cls(
            positions=np.concatenate([t.positions for t in tissues]),
            directions=np.concatenate([t.directions for t in tissues]),
            cell_id=np.concatenate(shifted_cell_ids),
            parent_id=np.concatenate(shifted_parent_ids),
            clone_id=np.concatenate(shifted_clone_ids),
            birth_stage=np.concatenate([t.birth_stage for t in tissues]),
            cell_type=np.concatenate([t.cell_type for t in tissues]),
            region=np.concatenate([t.region for t in tissues]),
            expression=np.concatenate([t.expression for t in tissues]),
            sign=np.concatenate([t.sign for t in tissues]),
            alive=np.concatenate([t.alive for t in tissues]),
            mode=np.concatenate([t.mode for t in tissues]),
            shift_v=np.concatenate([t.shift_v for t in tissues]),
            shift_s=np.concatenate([t.shift_s for t in tissues]),
            base_weight=np.concatenate([t.base_weight for t in tissues]),
            conn_radius=np.concatenate([t.conn_radius for t in tissues]),
            conn_prob=np.concatenate([t.conn_prob for t in tissues]),
            burst_period=np.concatenate([t.burst_period for t in tissues]),
            burst_duty=np.concatenate([t.burst_duty for t in tissues]),
            poisson_hz=np.concatenate([t.poisson_hz for t in tissues]),
            refractory=np.concatenate([t.refractory for t in tissues]),
            role=np.concatenate([t.role for t in tissues]),
            compartment=np.concatenate([t.compartment for t in tissues]),
            threshold=np.concatenate([t.threshold for t in tissues]),
            connectivity=conn,
            expression_names=expr_names,
            _next_cell_id=total_next_id,
            generation=np.concatenate([t.generation for t in tissues]),
            transmitter=np.concatenate([t.transmitter for t in tissues]),
            receptor_expression=rex,
            morphology=_concat_morphology(tissues, offsets),
        )

    def to_network(self) -> SNNNetwork:
        net = SNNNetwork()
        N = len(self.alive)
        
        # Single source of truth for polarity: sign (+1 or -1) governs the sign of base_weight
        # base_weight in SNNNetwork = abs(self.base_weight) * (1 if sign >= 0 else -1)
        net.neurons = [
            NeuronData(
                id=int(self.cell_id[i]),
                x=float(self.positions[i, 0]),
                y=float(self.positions[i, 1]),
                z=float(self.positions[i, 2]),
                dir_x=float(self.directions[i, 0]),
                dir_y=float(self.directions[i, 1]),
                dir_z=float(self.directions[i, 2]),
                mode=int(self.mode[i]),
                shift_v=int(self.shift_v[i]),
                shift_s=int(self.shift_s[i]),
                base_weight=int(abs(int(self.base_weight[i])) * (1 if self.sign[i] >= 0 else -1)),
                conn_radius=float(self.conn_radius[i]),
                conn_prob=float(self.conn_prob[i]),
                burst_period=int(self.burst_period[i]),
                burst_duty=int(self.burst_duty[i]),
                poisson_hz=float(self.poisson_hz[i]),
                refractory=int(self.refractory[i]),
                role=int(self.role[i]),
                compartment=int(self.compartment[i]),
                threshold=int(self.threshold[i])
            )
            for i in range(N) if self.alive[i]
        ]
        
        # Remap synapses if some cells are dead
        if self.alive.all():
            valid_synapses = np.ones(len(self.connectivity.pre), dtype=bool)
            new_indices = np.arange(N, dtype=np.int32)
        else:
            new_indices = np.full(N, -1, dtype=np.int32)
            new_indices[self.alive] = np.arange(np.sum(self.alive), dtype=np.int32)
            pre_valid = (self.connectivity.pre >= 0) & (self.connectivity.pre < N)
            post_valid = (self.connectivity.post >= 0) & (self.connectivity.post < N)
            syn_mask = pre_valid & post_valid
            
            pre_alive = np.zeros_like(syn_mask, dtype=bool)
            post_alive = np.zeros_like(syn_mask, dtype=bool)
            pre_alive[syn_mask] = self.alive[self.connectivity.pre[syn_mask]]
            post_alive[syn_mask] = self.alive[self.connectivity.post[syn_mask]]
            valid_synapses = syn_mask & pre_alive & post_alive
            
        pre = new_indices[self.connectivity.pre[valid_synapses]]
        post = new_indices[self.connectivity.post[valid_synapses]]
        weight = self.connectivity.weight[valid_synapses]
        delay = self.connectivity.delay[valid_synapses]
        
        syn_arrays = {
            "pre": pre.astype(np.uint32),
            "post": post.astype(np.uint32),
            "weight": weight.astype(np.int16),
            "delay": delay.astype(np.uint8),
        }
        for key in ("e_rev", "tau_decay"):
            val = getattr(self.connectivity, key, None)
            if val is not None:
                syn_arrays[key] = np.asarray(val[valid_synapses], dtype=np.float32)
        return SNNNetwork.from_arrays(
            version="1.0.0",
            morphology="Custom",
            neurons=net.neurons,
            synapse_arrays=syn_arrays,
        )

    @classmethod
    def from_network(cls, net: SNNNetwork) -> Tissue:
        N = net.num_neurons
        t = cls.empty()
        
        if N == 0:
            return t
            
        # Float64 for positions and float64 for poisson_hz for bit-for-bit fidelity
        positions = np.array([[n.x, n.y, n.z] for n in net.neurons], dtype=np.float64)
        directions = np.array([[n.dir_x, n.dir_y, n.dir_z] for n in net.neurons], dtype=np.float32)
        mode = np.array([n.mode for n in net.neurons], dtype=np.int32)
        shift_v = np.array([n.shift_v for n in net.neurons], dtype=np.int32)
        shift_s = np.array([n.shift_s for n in net.neurons], dtype=np.int32)
        base_weight = np.array([n.base_weight for n in net.neurons], dtype=np.int32)
        conn_radius = np.array([n.conn_radius for n in net.neurons], dtype=np.float32)
        conn_prob = np.array([n.conn_prob for n in net.neurons], dtype=np.float32)
        burst_period = np.array([n.burst_period for n in net.neurons], dtype=np.int32)
        burst_duty = np.array([n.burst_duty for n in net.neurons], dtype=np.int32)
        poisson_hz = np.array([n.poisson_hz for n in net.neurons], dtype=np.float64)
        refractory = np.array([n.refractory for n in net.neurons], dtype=np.int32)
        role = np.array([n.role for n in net.neurons], dtype=np.int32)
        compartment = np.array([n.compartment for n in net.neurons], dtype=np.int32)
        threshold = np.array([n.threshold for n in net.neurons], dtype=np.int32)
        
        # Single source of truth: sign matches base_weight polarity
        sign = np.where(base_weight >= 0, np.ones(N, dtype=np.int8), np.full(N, -1, dtype=np.int8))
        
        cell_id = np.array([n.id for n in net.neurons], dtype=np.int32)
        t.add_cells(
            N, 
            positions=positions, 
            cell_id=cell_id,
            directions=directions,
            mode=mode,
            shift_v=shift_v,
            shift_s=shift_s,
            base_weight=base_weight,
            conn_radius=conn_radius,
            conn_prob=conn_prob,
            burst_period=burst_period,
            burst_duty=burst_duty,
            poisson_hz=poisson_hz,
            refractory=refractory,
            role=role,
            compartment=compartment,
            threshold=threshold,
            sign=sign
        )
        
        M = net.num_synapses
        if M > 0:
            extra = {}
            if net.synapse_arrays is not None:
                pre = net.synapse_arrays["pre"].astype(np.int32)
                post = net.synapse_arrays["post"].astype(np.int32)
                weight = net.synapse_arrays["weight"].astype(np.int32)
                delay = net.synapse_arrays["delay"].astype(np.int32)
                for key in ("e_rev", "tau_decay"):
                    if key in net.synapse_arrays:
                        extra[key] = np.asarray(net.synapse_arrays[key], dtype=np.float32)
            else:
                pre = np.array([s.pre for s in net.synapses], dtype=np.int32)
                post = np.array([s.post for s in net.synapses], dtype=np.int32)
                weight = np.array([s.weight for s in net.synapses], dtype=np.int32)
                delay = np.array([s.delay for s in net.synapses], dtype=np.int32)
            t.connectivity = SparseConnectivity(pre, post, weight, delay, **extra)
            
        return t

    def memory_bytes(self) -> int:
        """Returns the total number of bytes consumed by all NumPy arrays in this tissue."""
        total = 0
        arrays = [
            self.positions, self.directions, self.cell_id, self.parent_id, self.clone_id,
            self.birth_stage, self.generation, self.cell_type, self.region, self.expression,
            self.sign, self.alive, self.mode, self.shift_v, self.shift_s,
            self.base_weight, self.conn_radius, self.conn_prob, self.burst_period,
            self.burst_duty, self.poisson_hz, self.refractory, self.role,
            self.compartment, self.threshold, self.transmitter, self.receptor_expression
        ]
        
        for arr in arrays:
            if arr is not None:
                total += arr.nbytes
                
        if self.connectivity is not None:
            total += self.connectivity.nbytes()
        if self.morphology is not None:
            total += self.morphology.nbytes()

        return total
