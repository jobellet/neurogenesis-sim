from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List
from neurogenesis.spiking.network import SNNNetwork, NeuronData, SynapseData

@dataclass
class SparseConnectivity:
    pre: np.ndarray
    post: np.ndarray
    weight: np.ndarray
    delay: np.ndarray
    
    @classmethod
    def empty(cls) -> SparseConnectivity:
        return cls(
            pre=np.zeros(0, dtype=np.int32),
            post=np.zeros(0, dtype=np.int32),
            weight=np.zeros(0, dtype=np.int32),
            delay=np.zeros(0, dtype=np.int32)
        )

@dataclass
class Tissue:
    positions: np.ndarray
    directions: np.ndarray
    lineage_id: np.ndarray
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
    _next_lineage_id: int = 0

    @classmethod
    def empty(cls, K: int = 0) -> Tissue:
        return cls(
            positions=np.zeros((0, 3), dtype=np.float64),
            directions=np.zeros((0, 3), dtype=np.float32),
            lineage_id=np.zeros(0, dtype=np.int32),
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
            poisson_hz=np.zeros(0, dtype=np.float32),
            refractory=np.zeros(0, dtype=np.int32),
            role=np.zeros(0, dtype=np.int32),
            compartment=np.zeros(0, dtype=np.int32),
            threshold=np.zeros(0, dtype=np.int32),
            connectivity=SparseConnectivity.empty(),
            expression_names=[],
            _next_lineage_id=0
        )

    def add_cells(self, N: int, positions: Optional[np.ndarray] = None, K: int = 0, parent_ids: Optional[np.ndarray] = None, **kwargs) -> None:
        """Adds N new cells. Lineage ids are automatically assigned."""
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
        
        lin_id = np.arange(self._next_lineage_id, self._next_lineage_id + N, dtype=np.int32)
        self._next_lineage_id += N
        
        par_id = parent_ids if parent_ids is not None else np.full(N, -1, dtype=np.int32)
        clone_id = kwargs.get("clone_id", lin_id if parent_ids is None else np.where(par_id >= 0, par_id, lin_id))
        birth = kwargs.get("birth_stage", np.zeros(N, dtype=np.int32))
        ctype = kwargs.get("cell_type", np.zeros(N, dtype=np.int32))
        reg = kwargs.get("region", np.zeros(N, dtype=np.int32))
        expr = kwargs.get("expression", np.zeros((N, K), dtype=np.float32))
        sgn = kwargs.get("sign", np.ones(N, dtype=np.int8))
        alv = kwargs.get("alive", np.ones(N, dtype=bool))
        
        # Neuron parameters
        mode = kwargs.get("mode", np.zeros(N, dtype=np.int32))
        shift_v = kwargs.get("shift_v", np.full(N, 5, dtype=np.int32))
        shift_s = kwargs.get("shift_s", np.full(N, 4, dtype=np.int32))
        base_weight = kwargs.get("base_weight", np.full(N, 180, dtype=np.int32))
        conn_radius = kwargs.get("conn_radius", np.full(N, 28.0, dtype=np.float32))
        conn_prob = kwargs.get("conn_prob", np.full(N, 0.38, dtype=np.float32))
        burst_period = kwargs.get("burst_period", np.full(N, 200, dtype=np.int32))
        burst_duty = kwargs.get("burst_duty", np.full(N, 24, dtype=np.int32))
        poisson_hz = kwargs.get("poisson_hz", np.full(N, 25.0, dtype=np.float32))
        refractory = kwargs.get("refractory", np.zeros(N, dtype=np.int32))
        role = kwargs.get("role", np.zeros(N, dtype=np.int32))
        compartment = kwargs.get("compartment", np.full(N, -1, dtype=np.int32))
        threshold = kwargs.get("threshold", np.full(N, 1024, dtype=np.int32))
        
        if self.positions.shape[0] == 0:
            self.expression = np.zeros((0, K), dtype=np.float32)

        self.positions = np.concatenate([self.positions, pos])
        self.directions = np.concatenate([self.directions, dir])
        self.lineage_id = np.concatenate([self.lineage_id, lin_id])
        self.parent_id = np.concatenate([self.parent_id, par_id])
        self.clone_id = np.concatenate([self.clone_id, clone_id])
        self.birth_stage = np.concatenate([self.birth_stage, birth])
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
        self.lineage_id = self.lineage_id[alive_mask]
        self.parent_id = self.parent_id[alive_mask]
        self.birth_stage = self.birth_stage[alive_mask]
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
        
        # Remap synapses
        if len(self.connectivity.pre) > 0:
            pre_valid = (self.connectivity.pre >= 0) & (self.connectivity.pre < N)
            post_valid = (self.connectivity.post >= 0) & (self.connectivity.post < N)
            syn_mask = pre_valid & post_valid
            
            # Additional check: both pre and post must be alive
            pre_alive = np.zeros_like(syn_mask, dtype=bool)
            post_alive = np.zeros_like(syn_mask, dtype=bool)
            pre_alive[syn_mask] = alive_mask[self.connectivity.pre[syn_mask]]
            post_alive[syn_mask] = alive_mask[self.connectivity.post[syn_mask]]
            
            valid_synapses = syn_mask & pre_alive & post_alive
            
            self.connectivity.pre = new_indices[self.connectivity.pre[valid_synapses]]
            self.connectivity.post = new_indices[self.connectivity.post[valid_synapses]]
            self.connectivity.weight = self.connectivity.weight[valid_synapses]
            self.connectivity.delay = self.connectivity.delay[valid_synapses]

    def subset(self, indices: np.ndarray) -> Tissue:
        """Returns a new Tissue with only the given cell indices (assumes connectivity only between subset)."""
        t = Tissue(
            positions=self.positions[indices],
            directions=self.directions[indices],
            lineage_id=self.lineage_id[indices],
            parent_id=self.parent_id[indices],
            clone_id=self.clone_id[indices],
            birth_stage=self.birth_stage[indices],
            cell_type=self.cell_type[indices],
            region=self.region[indices],
            expression=self.expression[indices],
            sign=self.sign[indices],
            alive=self.alive[indices],
            mode=self.mode[indices],
            shift_v=self.shift_v[indices],
            shift_s=self.shift_s[indices],
            base_weight=self.base_weight[indices],
            conn_radius=self.conn_radius[indices],
            conn_prob=self.conn_prob[indices],
            burst_period=self.burst_period[indices],
            burst_duty=self.burst_duty[indices],
            poisson_hz=self.poisson_hz[indices],
            refractory=self.refractory[indices],
            role=self.role[indices],
            compartment=self.compartment[indices],
            threshold=self.threshold[indices],
            connectivity=SparseConnectivity.empty(),
            _next_lineage_id=self._next_lineage_id
        )
        
        if len(self.connectivity.pre) > 0:
            N = len(self.alive)
            inv_map = np.full(N, -1, dtype=np.int32)
            inv_map[indices] = np.arange(len(indices), dtype=np.int32)
            
            pre_valid = (self.connectivity.pre >= 0) & (self.connectivity.pre < N)
            post_valid = (self.connectivity.post >= 0) & (self.connectivity.post < N)
            syn_mask = pre_valid & post_valid
            
            # Map indices
            mapped_pre = np.where(syn_mask, inv_map[self.connectivity.pre], -1)
            mapped_post = np.where(syn_mask, inv_map[self.connectivity.post], -1)
            
            valid = (mapped_pre >= 0) & (mapped_post >= 0)
            
            t.connectivity = SparseConnectivity(
                pre=mapped_pre[valid],
                post=mapped_post[valid],
                weight=self.connectivity.weight[valid],
                delay=self.connectivity.delay[valid]
            )
        
        return t

    @classmethod
    def concatenate(cls, tissues: List[Tissue]) -> Tissue:
        if not tissues:
            return cls.empty()
        
        K = tissues[0].expression.shape[1]
        for t in tissues:
            if t.expression.shape[1] != K:
                raise ValueError("Cannot concatenate Tissues with different expression dimensions")

        offsets = np.cumsum([0] + [len(t.alive) for t in tissues[:-1]])
        
        pre = np.concatenate([t.connectivity.pre + offset for t, offset in zip(tissues, offsets) if len(t.connectivity.pre) > 0] or [np.zeros(0, dtype=np.int32)])
        post = np.concatenate([t.connectivity.post + offset for t, offset in zip(tissues, offsets) if len(t.connectivity.post) > 0] or [np.zeros(0, dtype=np.int32)])
        weight = np.concatenate([t.connectivity.weight for t in tissues if len(t.connectivity.weight) > 0] or [np.zeros(0, dtype=np.int32)])
        delay = np.concatenate([t.connectivity.delay for t in tissues if len(t.connectivity.delay) > 0] or [np.zeros(0, dtype=np.int32)])
        
        return cls(
            positions=np.concatenate([t.positions for t in tissues]),
            directions=np.concatenate([t.directions for t in tissues]),
            lineage_id=np.concatenate([t.lineage_id for t in tissues]),
            parent_id=np.concatenate([t.parent_id for t in tissues]),
            clone_id=np.concatenate([t.clone_id for t in tissues]),
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
            connectivity=SparseConnectivity(pre, post, weight, delay),
            _next_lineage_id=max(t._next_lineage_id for t in tissues)
        )

    def to_network(self) -> SNNNetwork:
        net = SNNNetwork()
        N = len(self.alive)
        net.neurons = [
            NeuronData(
                id=int(i),
                x=float(self.positions[i, 0]),
                y=float(self.positions[i, 1]),
                z=float(self.positions[i, 2]),
                dir_x=float(self.directions[i, 0]),
                dir_y=float(self.directions[i, 1]),
                dir_z=float(self.directions[i, 2]),
                mode=int(self.mode[i]),
                shift_v=int(self.shift_v[i]),
                shift_s=int(self.shift_s[i]),
                base_weight=int(self.base_weight[i]),
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
        
        net.synapses = [
            SynapseData(
                pre=int(pre[i]),
                post=int(post[i]),
                weight=int(weight[i]),
                delay=int(delay[i])
            )
            for i in range(len(pre))
        ]
        
        return net

    @classmethod
    def from_network(cls, net: SNNNetwork) -> Tissue:
        N = net.num_neurons
        t = cls.empty()
        
        if N == 0:
            return t
            
        positions = np.array([[n.x, n.y, n.z] for n in net.neurons], dtype=np.float32)
        directions = np.array([[n.dir_x, n.dir_y, n.dir_z] for n in net.neurons], dtype=np.float32)
        mode = np.array([n.mode for n in net.neurons], dtype=np.int32)
        shift_v = np.array([n.shift_v for n in net.neurons], dtype=np.int32)
        shift_s = np.array([n.shift_s for n in net.neurons], dtype=np.int32)
        base_weight = np.array([n.base_weight for n in net.neurons], dtype=np.int32)
        conn_radius = np.array([n.conn_radius for n in net.neurons], dtype=np.float32)
        conn_prob = np.array([n.conn_prob for n in net.neurons], dtype=np.float32)
        burst_period = np.array([n.burst_period for n in net.neurons], dtype=np.int32)
        burst_duty = np.array([n.burst_duty for n in net.neurons], dtype=np.int32)
        poisson_hz = np.array([n.poisson_hz for n in net.neurons], dtype=np.float32)
        refractory = np.array([n.refractory for n in net.neurons], dtype=np.int32)
        role = np.array([n.role for n in net.neurons], dtype=np.int32)
        compartment = np.array([n.compartment for n in net.neurons], dtype=np.int32)
        threshold = np.array([n.threshold for n in net.neurons], dtype=np.int32)
        sign = np.where(base_weight >= 0, np.ones(N, dtype=np.int8), np.full(N, -1, dtype=np.int8))
        
        t.add_cells(
            N, 
            positions=positions, 
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
            pre = np.array([s.pre for s in net.synapses], dtype=np.int32)
            post = np.array([s.post for s in net.synapses], dtype=np.int32)
            weight = np.array([s.weight for s in net.synapses], dtype=np.int32)
            delay = np.array([s.delay for s in net.synapses], dtype=np.int32)
            t.connectivity = SparseConnectivity(pre, post, weight, delay)
            
        return t

    def memory_bytes(self) -> int:
        """Returns the total number of bytes consumed by all NumPy arrays in this tissue."""
        total = 0
        arrays = [
            self.positions, self.directions, self.lineage_id, self.parent_id,
            self.birth_stage, self.cell_type, self.region, self.expression,
            self.sign, self.alive, self.mode, self.shift_v, self.shift_s,
            self.base_weight, self.conn_radius, self.conn_prob, self.burst_period,
            self.burst_duty, self.poisson_hz, self.refractory, self.role,
            self.compartment, self.threshold
        ]
        
        for arr in arrays:
            if arr is not None:
                total += arr.nbytes
                
        if self.connectivity is not None:
            total += self.connectivity.pre.nbytes
            total += self.connectivity.post.nbytes
            total += self.connectivity.weight.nbytes
            total += self.connectivity.delay.nbytes
            
        return total
