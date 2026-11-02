import warnings
from typing import Dict, Any, Tuple
import numpy as np

from neurogenesis.tissue import Tissue
from neurogenesis.stages.base import register_stage
from neurogenesis.params import resolve, param_from_dict, Const, Gene, Fit

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

        if "target" not in params:
            return tissue
        target = resolve(params["target"], genome, fields)
        N = len(tissue.alive)

        # Sum absolute incoming weights per neuron
        in_degrees = np.zeros(N, dtype=np.float32)
        abs_weights = np.abs(tissue.connectivity.weight)
        np.add.at(in_degrees, tissue.connectivity.post, abs_weights)

        # Compute scale factor per post-synaptic neuron
        scale_factors = np.divide(target, in_degrees, out=np.ones(N, dtype=np.float32), where=in_degrees > 0)

        # Apply scaling, maintaining the original sign
        new_weights = tissue.connectivity.weight * scale_factors[tissue.connectivity.post]
        tissue.connectivity.weight = np.round(new_weights).astype(np.int32)
        return tissue


@register_stage("myelinate")
class MyelinateStage:
    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        return E * 4, E * 4

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        if tissue.connectivity is None or len(tissue.connectivity.pre) == 0:
            return tissue

        factor_param = params.get("factor", params.get("delay_factor"))
        if factor_param is None:
            return tissue
        factor = resolve(factor_param, genome, fields)
        
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


from neurogenesis.spiking.plasticity import STDPRule, HebbianRule
from neurogenesis.spiking.jax_backend import tick, init_state, pack
import jax.numpy as jnp
import jax

@register_stage("refine_by_activity")
class RefineByActivityStage:
    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        ticks = params.get("ticks", 100)
        if isinstance(ticks, dict):
            ticks = param_from_dict(ticks)
        if isinstance(ticks, (Gene, Fit)):
            ticks = ticks.hi
        elif isinstance(ticks, Const):
            ticks = ticks.value
        elif not isinstance(ticks, (int, float, np.integer, np.floating)):
            ticks = 100
        ticks = int(ticks)
        bytes_cost = E * 8 + N * 40
        ops_cost = E * ticks * 20
        return bytes_cost, ops_cost

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        rule_param = params.get("rule")
        if rule_param is None or tissue.connectivity is None or len(tissue.connectivity.pre) == 0:
            return tissue

        # 1. Compact / index by id: if there are dead cells, compact first so cell indices and connectivity align
        if not tissue.alive.all():
            tissue.compact()

        ticks = int(resolve(params.get("ticks", 100), genome, fields))
        rule_type = resolve(rule_param, genome, fields)
        
        # Configure drivers:
        # A) Explicit sources / driver cells with Poisson mode
        sources = resolve(params.get("sources", params.get("driver_cells", None)), genome, fields)
        if sources is not None and "waves" not in params:
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

        # B) Spontaneous waves (sources and speed as Params)
        # Generates propagating wave wavefronts across space (e.g. retinal / cortical waves)
        wave_currents = None
        if "waves" in params:
            wave_cfg = params["waves"]
            if isinstance(wave_cfg, dict):
                w_sources = resolve(wave_cfg.get("sources", [0]), genome, fields)
                w_speed = float(resolve(wave_cfg.get("speed", 1.0), genome, fields))
                w_interval = int(resolve(wave_cfg.get("interval", 50), genome, fields))
                w_duration = int(resolve(wave_cfg.get("duration", 4), genome, fields))
                w_amp = int(resolve(wave_cfg.get("amplitude", 3000), genome, fields))
            else:
                w_sources = [0]
                w_speed = 1.0
                w_interval = 50
                w_duration = 4
                w_amp = 3000

            N_cells = len(tissue.alive)
            wave_currents = np.zeros((ticks, N_cells), dtype=np.int32)
            id_to_idx = {int(cid): idx for idx, cid in enumerate(tissue.cell_id)}
            
            src_points = []
            if isinstance(w_sources, (list, tuple, np.ndarray)):
                for s in w_sources:
                    if isinstance(s, (list, tuple, np.ndarray)) and len(s) == 3:
                        src_points.append(np.asarray(s, dtype=np.float64))
                    else:
                        s_int = int(s)
                        idx = id_to_idx.get(s_int, s_int if 0 <= s_int < N_cells else None)
                        if idx is not None:
                            src_points.append(tissue.positions[idx])
            if not src_points and N_cells > 0:
                src_points.append(tissue.positions[0])

            # For each initiation event at each source point
            w_speed = max(1e-6, w_speed)
            init_times = list(range(0, ticks, max(1, w_interval)))
            for t_init in init_times:
                for pt in src_points:
                    dists = np.linalg.norm(tissue.positions - pt, axis=1)
                    t_arrivals = t_init + dists / w_speed
                    for i in range(N_cells):
                        t_arr = int(np.round(t_arrivals[i]))
                        t_start = max(0, t_arr)
                        t_end = min(ticks, t_arr + w_duration)
                        if t_start < t_end:
                            wave_currents[t_start:t_end, i] = np.maximum(wave_currents[t_start:t_end, i], w_amp)

        # C) Motor twitches with sensory feedback
        twitch_cfg = params.get("twitches")
        has_twitches = twitch_cfg is not None
        if has_twitches:
            if isinstance(twitch_cfg, dict):
                motor_cells_param = resolve(twitch_cfg.get("motor_cells", [0]), genome, fields)
                sensory_cells_param = resolve(twitch_cfg.get("sensory_cells", [1]), genome, fields)
                feedback_delay = int(resolve(twitch_cfg.get("delay", 2), genome, fields))
                feedback_gain = int(resolve(twitch_cfg.get("gain", 3000), genome, fields))
                twitch_interval = int(resolve(twitch_cfg.get("interval", 40), genome, fields))
                twitch_amp = int(resolve(twitch_cfg.get("amplitude", 3000), genome, fields))
                twitch_dur = int(resolve(twitch_cfg.get("duration", 2), genome, fields))
            else:
                motor_cells_param = [0]
                sensory_cells_param = [1]
                feedback_delay = 2
                feedback_gain = 3000
                twitch_interval = 40
                twitch_amp = 3000
                twitch_dur = 2

            feedback_delay = max(1, feedback_delay)
            N_cells = len(tissue.alive)
            id_to_idx = {int(cid): idx for idx, cid in enumerate(tissue.cell_id)}

            def _resolve_indices(c_param):
                c_list = c_param if isinstance(c_param, (list, tuple, np.ndarray)) else [c_param]
                idxs = []
                for c in c_list:
                    c_int = int(c)
                    idx = id_to_idx.get(c_int, c_int if 0 <= c_int < N_cells else None)
                    if idx is not None:
                        idxs.append(idx)
                return idxs

            motor_idxs = _resolve_indices(motor_cells_param)
            sensory_idxs = _resolve_indices(sensory_cells_param)

            # Build pre-computed twitch stimulus on motor neurons
            twitch_stim = np.zeros((ticks, N_cells), dtype=np.int32)
            for t_tw in range(0, ticks, max(1, twitch_interval)):
                t_end = min(ticks, t_tw + twitch_dur)
                for m_idx in motor_idxs:
                    twitch_stim[t_tw:t_end, m_idx] = np.maximum(twitch_stim[t_tw:t_end, m_idx], twitch_amp)

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
            base_ext = None
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
                    base_ext = ext_arr
                else:
                    base_ext = np.asarray(ext_current, dtype=np.int32)

            if has_twitches:
                motor_mask_arr = np.zeros(N_cells, dtype=bool)
                if motor_idxs:
                    motor_mask_arr[motor_idxs] = True
                sensory_mask_arr = np.zeros(N_cells, dtype=bool)
                if sensory_idxs:
                    sensory_mask_arr[sensory_idxs] = True
                
                motor_mask_jnp = jnp.asarray(motor_mask_arr)
                sensory_mask_jnp = jnp.asarray(sensory_mask_arr)
                twitch_stim_jnp = jnp.asarray(twitch_stim)
                
                # Feedback ring buffer of length feedback_delay
                # buf stores scalar feedback amount per ring slot
                buf_init = jnp.zeros(feedback_delay, dtype=jnp.int32)
                
                def scan_tick_twitch(carry, t):
                    s, buf = carry
                    curr = twitch_stim_jnp[t]
                    if base_ext is not None:
                        curr = curr + jnp.asarray(base_ext)
                    if wave_currents is not None:
                        curr = curr + jnp.asarray(wave_currents[t])
                    
                    # sensory neurons receive input from buf[0]
                    curr = jnp.where(sensory_mask_jnp, curr + buf[0], curr)
                    
                    s, spikes, arr = tick(packed, s, ext_current=curr)
                    
                    # check if any motor neuron fired
                    motor_fired = jnp.any(spikes & motor_mask_jnp)
                    new_feedback = jnp.where(motor_fired, feedback_gain, 0).astype(jnp.int32)
                    
                    # shift buffer
                    buf_next = jnp.concatenate([buf[1:], jnp.array([new_feedback])])
                    return (s, buf_next), (spikes, arr)
                    
                (final_state, _), (spikes_out, arrivals) = jax.lax.scan(
                    scan_tick_twitch, (state, buf_init), jnp.arange(ticks)
                )
            elif wave_currents is not None:
                wave_jnp = jnp.asarray(wave_currents)
                if base_ext is not None:
                    base_jnp = jnp.asarray(base_ext)
                    def scan_tick_wave(s, t):
                        s, spikes, arr = tick(packed, s, ext_current=wave_jnp[t] + base_jnp)
                        return s, (spikes, arr)
                else:
                    def scan_tick_wave(s, t):
                        s, spikes, arr = tick(packed, s, ext_current=wave_jnp[t])
                        return s, (spikes, arr)
                final_state, (spikes_out, arrivals) = jax.lax.scan(scan_tick_wave, state, jnp.arange(ticks))
            elif base_ext is not None:
                ext_current_jnp = jnp.asarray(base_ext, dtype=jnp.int32)
                def scan_tick(s, _):
                    s, spikes, arr = tick(packed, s, ext_current=ext_current_jnp)
                    return s, (spikes, arr)
                final_state, (spikes_out, arrivals) = jax.lax.scan(scan_tick, state, None, length=ticks)
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

