import warnings
from typing import Dict, Any, Optional, Tuple
import numpy as np

from neurogenesis.tissue import Tissue
from neurogenesis.stages.base import register_stage
from neurogenesis.params import resolve, param_from_dict, Const, Gene, Fit, worst_case


# Largest (ticks x synapses) block evaluated at once by `coactivity`.
_COACT_CHUNK = 1 << 22


def simulate_tissue(tissue: Tissue, ticks: int, seed: int, ext_current: Optional[np.ndarray] = None) -> np.ndarray:
    """(ticks, N) uint8 spike raster of a compacted tissue run with the JAX `lif_int` kernel; ext_current (N,) int32 is
    added every tick. The kernel seed is mapped to [1, 2^32 - 1] (xorshift32 never leaves the state 0)."""
    seed = int(seed) % 0xFFFFFFFF + 1
    from neurogenesis.spiking.jax_backend import tick, init_state, pack
    import jax
    import jax.numpy as jnp
    packed = pack(tissue.to_network())
    ext = None if ext_current is None else jnp.asarray(ext_current, dtype=jnp.int32)

    def f(s, _):
        s, spk, _ = tick(packed, s, ext_current=ext)
        return s, spk
    _, spikes = jax.lax.scan(f, init_state(packed, seed=seed), None, length=int(ticks))
    return np.asarray(spikes)[:, :len(tissue.alive)]


def coactivity(spikes: np.ndarray, pre: np.ndarray, post: np.ndarray, delay: np.ndarray, window: int) -> np.ndarray:
    """Per synapse: number of pre spikes, arriving after `delay` ticks, followed by a post spike within `window` ticks
    (arrival tick included). O(T x E) operations in blocks of at most 2^22 (tick, synapse) pairs."""
    spikes = np.asarray(spikes, dtype=np.int32)
    T = spikes.shape[0]
    E = len(pre)
    out = np.zeros(E, dtype=np.int64)
    if T == 0 or E == 0:
        return out
    c = np.concatenate([np.zeros((1, spikes.shape[1]), np.int32), np.cumsum(spikes, axis=0)])
    hi = np.minimum(np.arange(T) + max(1, int(window)), T)
    post_window = (c[hi] - c[np.arange(T)]) > 0                                 # (T, N): post spikes in [t, t + window)
    t = np.arange(T)[:, None]
    step = max(1, _COACT_CHUNK // T)
    for a in range(0, E, step):
        b = min(E, a + step)
        src_t = t - delay[None, a:b]
        arr = np.where(src_t >= 0, spikes[np.maximum(src_t, 0), pre[None, a:b]], 0)
        out[a:b] = np.sum(arr * post_window[:, post[a:b]], axis=0)
    return out


def _activity(tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any],
              rng: np.random.Generator) -> np.ndarray:
    """Spike raster for an activity criterion: `spikes` (a given (T, N) raster) or a simulation of `ticks` (default
    100) with an optional constant `ext_current` per cell."""
    if params.get("spikes") is not None:
        return np.asarray(resolve(params["spikes"], genome, fields))
    ticks = int(resolve(params.get("ticks", 100), genome, fields))
    ext = params.get("ext_current")
    ext = None if ext is None else np.broadcast_to(np.asarray(resolve(ext, genome, fields), dtype=np.int32), (len(tissue.alive),))
    return simulate_tissue(tissue, ticks, int(rng.integers(0, 1_000_000)), ext)


def _activity_cost(N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
    ticks = int(worst_case(params.get("ticks"), 100))
    return N * 40 + E * 24 + ticks * N * 5, ticks * (E * 20 + N * 30)

@register_stage("prune")
class PruneStage:
    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        b, ops = E * 4, E * 4
        if params.get("min_coactivity") is not None:
            ab, aops = _activity_cost(N, E, params)
            b, ops = b + ab, ops + aops
        return b, ops

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        if tissue.connectivity is None or len(tissue.connectivity.pre) == 0:
            return tissue

        # Resolve threshold param, default to 0 if not provided
        threshold = resolve(params.get("threshold", 0), genome, fields)
        
        abs_weights = np.abs(tissue.connectivity.weight)
        keep_mask = abs_weights >= threshold

        if params.get("min_coactivity") is not None:
            # Activity criterion ("use it or lose it"): keep synapses whose arriving pre spikes were followed by a post
            # spike within `window` ticks at least `min_coactivity` times (Katz & Shatz 1996, Science).
            if not tissue.alive.all():
                tissue.compact()
                abs_weights = np.abs(tissue.connectivity.weight)
                keep_mask = abs_weights >= threshold
            spikes = _activity(tissue, params, genome, fields, rng)
            window = int(resolve(params.get("window", 5), genome, fields))
            coact = coactivity(spikes, tissue.connectivity.pre, tissue.connectivity.post, tissue.connectivity.delay, window)
            keep_mask &= coact >= float(resolve(params["min_coactivity"], genome, fields))

        if tissue.connectivity.plastic is not None:
            keep_mask |= ~tissue.connectivity.plastic              # non-plastic synapses are never pruned (K6)
        tissue.connectivity = tissue.connectivity.take(keep_mask)

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
        if params.get("rate") is not None:
            # Partial step towards the target (synaptic scaling with a time constant: Turrigiano et al. 1998, Nature)
            rate = float(resolve(params["rate"], genome, fields))
            scale_factors = 1.0 + rate * (scale_factors - 1.0)

        # Apply scaling, maintaining the original sign
        new_weights = np.round(tissue.connectivity.weight * scale_factors[tissue.connectivity.post]).astype(np.int32)
        if tissue.connectivity.plastic is not None:
            # Non-plastic synapses keep their weight; factors still use every incoming synapse (K6)
            new_weights = np.where(tissue.connectivity.plastic, new_weights, tissue.connectivity.weight).astype(np.int32)
        tissue.connectivity.weight = new_weights
        return tissue


@register_stage("myelinate")
class MyelinateStage:
    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        b, ops = E * 4, E * 4
        if params.get("min_rate") is not None:
            ab, aops = _activity_cost(N, E, params)
            b, ops = b + ab, ops + aops
        return b, ops

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any], rng: np.random.Generator) -> Tissue:
        if tissue.connectivity is None or len(tissue.connectivity.pre) == 0:
            return tissue

        factor_param = params.get("factor", params.get("delay_factor"))
        if factor_param is None:
            return tissue
        factor = resolve(factor_param, genome, fields)
        sel = self._selected(tissue, params, genome, fields, rng)

        # Scale delays down, clipping to [1, 31]
        raw_delays = np.where(sel, np.round(tissue.connectivity.delay * factor), tissue.connectivity.delay).astype(np.int32)
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

    @staticmethod
    def _selected(tissue, params, genome, fields, rng) -> np.ndarray:
        """Synapses to myelinate: all, or those passing every given criterion: `min_delay` (long projections, ticks),
        `pre_region` / `post_region` (lists of region ids), `min_rate` (active presynaptic cells, Hz, measured by a
        simulation of `ticks`; activity-dependent myelination: Gibson et al. 2014, Science)."""
        c = tissue.connectivity
        sel = np.ones(len(c.pre), dtype=bool)
        if params.get("min_delay") is not None:
            sel &= c.delay >= float(resolve(params["min_delay"], genome, fields))
        for key, idx in (("pre_region", c.pre), ("post_region", c.post)):
            if params.get(key) is not None:
                sel &= np.isin(tissue.region[idx], np.asarray(resolve(params[key], genome, fields)).ravel())
        if params.get("min_rate") is not None:
            if not tissue.alive.all():
                raise ValueError("myelinate: 'min_rate' needs a compacted tissue (run apoptosis / refine first)")
            spikes = _activity(tissue, params, genome, fields, rng)
            rate_hz = spikes.sum(0) * 1000.0 / max(1, spikes.shape[0])
            sel &= rate_hz[c.pre] >= float(resolve(params["min_rate"], genome, fields))
        return sel


from neurogenesis.spiking.plasticity import STDPRule, HebbianRule, ThreeFactorRule
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
                    t_arr = np.round(t_init + dists / w_speed).astype(np.int64)
                    cols = np.arange(N_cells)
                    for k in range(max(0, w_duration)):              # vectorised over cells
                        rows = t_arr + k
                        ok = (rows >= 0) & (rows < ticks)
                        wave_currents[rows[ok], cols[ok]] = np.maximum(wave_currents[rows[ok], cols[ok]], w_amp)

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
            
        elif rule_type == "three_factor":
            # Eligibility trace x neuromodulator (Izhikevich 2007, Cereb Cortex; Fremaux & Gerstner 2016, Front Neural
            # Circuits): `modulator` is a constant, a (ticks,) series or a (ticks, N) per-cell array; with
            # `modulator_cells` it is the number of spikes of those cells at each tick times `modulator_gain`.
            eta = float(resolve(params.get("eta", 0.01), genome, fields))
            tau_e = float(resolve(params.get("tau_e", 20.0), genome, fields))
            T = int(np.shape(spikes_out)[0])
            if params.get("modulator_cells") is not None:
                ids = np.asarray(resolve(params["modulator_cells"], genome, fields)).ravel().astype(int)
                id_to_idx = {int(cid): idx for idx, cid in enumerate(tissue.cell_id)}
                idx = np.asarray([id_to_idx[i] for i in ids if i in id_to_idx], dtype=int)
                gain = float(resolve(params.get("modulator_gain", 1.0), genome, fields))
                mod = gain * np.asarray(spikes_out)[:, idx].sum(axis=1).astype(np.float32)
            else:
                mod = np.asarray(resolve(params.get("modulator", 1.0), genome, fields), dtype=np.float32)
                if mod.ndim == 0:
                    mod = np.full(T, float(mod), dtype=np.float32)
                elif mod.ndim == 2 and mod.shape[1] < packed["mode"].shape[0]:
                    mod = np.pad(mod, ((0, 0), (0, packed["mode"].shape[0] - mod.shape[1])))
            rule = ThreeFactorRule(eta=eta, tau_e=tau_e)
            new_weights = rule.apply(weight.astype(jnp.float32), pre, post, delay, jnp.asarray(spikes_out, jnp.float32),
                                     jnp.asarray(mod), weight.astype(jnp.float32))

        else:
            raise ValueError(f"Unknown plasticity rule: {rule_type}")
            
        # Update tissue weights
        valid = packed["valid"]
        valid_idx = np.where(valid)[0]
        
        new_w = np.array(new_weights)[valid_idx].astype(np.int32)
        if tissue.connectivity.plastic is not None:
            new_w = np.where(tissue.connectivity.plastic, new_w, tissue.connectivity.weight).astype(np.int32)  # K6
        tissue.connectivity.weight = new_w

        return tissue

