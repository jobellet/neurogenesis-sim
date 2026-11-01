import warnings
from typing import Dict, Any, Tuple
import numpy as np

from neurogenesis.tissue import Tissue
from neurogenesis.stages.base import register_stage
from neurogenesis.params import resolve

@register_stage("prune")
class PruneStage:
    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        return E * 4, E * 4

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        if tissue.connectivity is None or len(tissue.connectivity.pre) == 0:
            return tissue

        # Resolve threshold param, default to 0 if not provided
        threshold = resolve(params.get("threshold", 0), genome, fields)
        
        abs_weights = np.abs(tissue.connectivity.weight)
        keep_mask = abs_weights >= threshold

        tissue.connectivity.pre = tissue.connectivity.pre[keep_mask]
        tissue.connectivity.post = tissue.connectivity.post[keep_mask]
        tissue.connectivity.weight = tissue.connectivity.weight[keep_mask]
        tissue.connectivity.delay = tissue.connectivity.delay[keep_mask]

        return tissue

@register_stage("scale")
class ScaleStage:
    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        return E * 8, E * 10

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        if tissue.connectivity is None or len(tissue.connectivity.pre) == 0:
            return tissue

        target = resolve(params.get("target", 1000), genome, fields)
        N = len(tissue.alive)

        # Sum absolute incoming weights per neuron
        in_degrees = np.zeros(N, dtype=np.float32)
        abs_weights = np.abs(tissue.connectivity.weight)
        np.add.at(in_degrees, tissue.connectivity.post, abs_weights)

        # Compute scale factor per post-synaptic neuron
        scale_factors = np.where(in_degrees > 0, target / in_degrees, 1.0)

        # Apply scaling, maintaining the original sign
        new_weights = tissue.connectivity.weight * scale_factors[tissue.connectivity.post]
        tissue.connectivity.weight = np.round(new_weights).astype(np.int32)
        
        # Ensure that weights do not flip signs if they round to zero
        sign = np.sign(tissue.connectivity.weight)
        # Assuming all weights > 0 are exc and < 0 are inh
        # We can just leave them as is, because scaling doesn't change sign.
        # But if we want to ensure non-zero? Let's just leave it as rounded.
        
        return tissue


@register_stage("myelinate")
class MyelinateStage:
    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        return E * 4, E * 4

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        if tissue.connectivity is None or len(tissue.connectivity.pre) == 0:
            return tissue

        factor = resolve(params.get("factor", params.get("delay_factor", 0.5)), genome, fields)
        
        # Scale delays down, clipping to [1, 31]
        raw_delays = np.round(tissue.connectivity.delay * factor).astype(np.int32)
        n_clipped = int(np.sum(raw_delays > 31))
        if n_clipped > 0:
            warnings.warn(
                f"myelinate: {n_clipped} synapses clipped to maximum delay 31 ticks (kernel limit)",
                UserWarning,
                stacklevel=2
            )
        new_delays = np.clip(raw_delays, 1, 31).astype(np.int32)
        tissue.connectivity.delay = new_delays

        return tissue


from neurogenesis.spiking.plasticity import STDPRule, HebbianRule, ThreeFactorRule
from neurogenesis.spiking.jax_backend import tick, init_state, pack
import jax.numpy as jnp
import jax

@register_stage("refine_by_activity")
class RefineByActivityStage:
    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        ticks = params.get("ticks", 100)
        ticks = ticks.value if hasattr(ticks, 'value') else ticks
        if isinstance(ticks, dict):
            ticks = ticks.get("value", 100)
            
        bytes_cost = E * 8 + N * 40
        ops_cost = E * ticks * 20
        return bytes_cost, ops_cost

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        if tissue.connectivity is None or len(tissue.connectivity.pre) == 0:
            return tissue

        # 1. Compact / index by id: if there are dead cells, compact first so cell indices and connectivity align
        if not tissue.alive.all():
            tissue.compact()

        ticks = int(resolve(params.get("ticks", 100), genome, fields))
        rule_type = params.get("rule", "stdp")
        rule_type = resolve(rule_type, genome, fields)
        
        # Configure sources / driver cells by ID if specified
        sources = resolve(params.get("sources", params.get("driver_cells", None)), genome, fields)
        if sources is not None:
            id_to_idx = {int(cid): idx for idx, cid in enumerate(tissue.cell_id)}
            src_list = sources if isinstance(sources, (list, tuple, np.ndarray)) else [sources]
            poisson_hz = float(resolve(params.get("poisson_hz", 1000.0), genome, fields))
            for s in src_list:
                s_int = int(s)
                if s_int in id_to_idx:
                    idx = id_to_idx[s_int]
                elif 0 <= s_int < len(tissue.alive):
                    idx = s_int
                else:
                    continue
                tissue.mode[idx] = 1
                tissue.poisson_hz[idx] = poisson_hz

        # Build network and pack
        net = tissue.to_network()
        # We need N, E pad just like pack does
        packed = pack(net)
        
        injected_spikes = resolve(params.get("spikes", None), genome, fields)
        if injected_spikes is not None:
            spikes_out = jnp.asarray(injected_spikes, dtype=jnp.uint8)
        else:
            # Run simulation to get spikes
            state = init_state(packed, seed=int(rng.integers(0, 1000000)))
            
            ext_current = resolve(params.get("ext_current", None), genome, fields)
            if ext_current is not None:
                if isinstance(ext_current, dict):
                    id_to_idx = {int(cid): idx for idx, cid in enumerate(tissue.cell_id)}
                    ext_arr = np.zeros(len(tissue.alive), dtype=np.int32)
                    for k, v in ext_current.items():
                        k_int = int(k)
                        if k_int in id_to_idx:
                            ext_arr[id_to_idx[k_int]] = int(v)
                        elif 0 <= k_int < len(tissue.alive):
                            ext_arr[k_int] = int(v)
                    ext_current_jnp = jnp.asarray(ext_arr)
                else:
                    ext_current_jnp = jnp.asarray(ext_current, dtype=jnp.int32)
                def scan_tick(s, _):
                    s, spikes, arr = tick(packed, s, ext_current=ext_current_jnp)
                    return s, (spikes, arr)
            else:
                def scan_tick(s, _):
                    s, spikes, arr = tick(packed, s)
                    return s, (spikes, arr)
                
            final_state, (spikes_out, arrivals) = jax.lax.scan(scan_tick, state, None, length=ticks)
        
        # Extract pre, post, weight, delay
        pre = packed["pre"]
        post = packed["post"]
        weight = packed["weight"]
        delay = packed["delay"]
        
        # Select rule
        if rule_type == "stdp":
            A_plus = float(resolve(params.get("A_plus", 1.0), genome, fields))
            A_minus = float(resolve(params.get("A_minus", 1.0), genome, fields))
            tau_plus = float(resolve(params.get("tau_plus", 20.0), genome, fields))
            tau_minus = float(resolve(params.get("tau_minus", 20.0), genome, fields))
            w_min = float(resolve(params.get("w_min", 0.0), genome, fields))
            w_max = float(resolve(params.get("w_max", 1000.0), genome, fields))
            
            rule = STDPRule(A_plus=A_plus, A_minus=A_minus, tau_plus=tau_plus, tau_minus=tau_minus, w_min=w_min, w_max=w_max)
            new_weights = rule.apply(weight.astype(jnp.float32), pre, post, delay, spikes_out, weight.astype(jnp.float32))
            
        elif rule_type == "hebbian":
            eta = float(resolve(params.get("eta", 0.01), genome, fields))
            norm_target = float(resolve(params.get("norm_target", 1000.0), genome, fields))
            norm_type = str(resolve(params.get("norm_type", "l1_subtractive"), genome, fields))
            
            rule = HebbianRule(eta=eta, norm_target=norm_target, norm_type=norm_type)
            new_weights = rule.apply(weight.astype(jnp.float32), pre, post, delay, spikes_out, weight.astype(jnp.float32))
            
        else:
            raise ValueError(f"Unknown plasticity rule: {rule_type}")
            
        # Update tissue weights
        valid = packed["valid"]
        valid_idx = np.where(valid)[0]
        
        tissue.connectivity.weight = np.array(new_weights)[valid_idx].astype(np.int32)

        return tissue

