from __future__ import annotations
import jax
import jax.numpy as jnp
from typing import Tuple, Dict, Any, Optional, Union

def _decay_integer(x: jnp.ndarray, shift: int) -> jnp.ndarray:
    """Integer exponential decay for bit-shift kernel (like `_decay` in jax_backend.py).
    x - max(1, x >> shift) for x > 0; x - min(-1, x >> shift) for x < 0.
    """
    sh = jnp.right_shift(x, shift)
    return jnp.where(x > 0, x - jnp.maximum(1, sh), jnp.where(x < 0, x - jnp.minimum(-1, sh), x))

class STDPRule:
    def __init__(self, A_plus: float = 1.0, A_minus: float = 1.0, 
                 tau_plus: float = 20.0, tau_minus: float = 20.0,
                 w_min: float = 0.0, w_max: float = 1000.0,
                 soft_bounds: bool = False, integer_traces: bool = False):
        self.A_plus = A_plus
        self.A_minus = A_minus
        self.tau_plus = tau_plus
        self.tau_minus = tau_minus
        self.w_min = w_min
        self.w_max = w_max
        self.soft_bounds = soft_bounds
        self.integer_traces = integer_traces
        
        self.decay_plus = jnp.exp(-1.0 / tau_plus) if tau_plus > 0 else 0.0
        self.decay_minus = jnp.exp(-1.0 / tau_minus) if tau_minus > 0 else 0.0

    def init_state(self, num_neurons: int, num_synapses: int) -> Tuple[jnp.ndarray, jnp.ndarray]:
        """Returns initial (tr_pre_syn, tr_post_neuron) state for tick-by-tick simulation."""
        if self.integer_traces:
            return jnp.zeros(num_synapses, dtype=jnp.int32), jnp.zeros(num_neurons, dtype=jnp.int32)
        return jnp.zeros(num_synapses, dtype=jnp.float32), jnp.zeros(num_neurons, dtype=jnp.float32)

    def step(self, weights: jnp.ndarray, pre: jnp.ndarray, post: jnp.ndarray,
             spikes_post: jnp.ndarray, arrivals_pre: jnp.ndarray,
             tr_pre_syn: jnp.ndarray, tr_post_neuron: jnp.ndarray,
             original_weights: Optional[jnp.ndarray] = None) -> Tuple[jnp.ndarray, jnp.ndarray, jnp.ndarray]:
        """Tick-by-tick update for online simulation loop (no T x N memory required).
        
        arrivals_pre: (E,) binary / float indicating pre-synaptic spike arrival at each synapse at current tick.
        spikes_post: (N,) binary indicating whether each post-synaptic neuron spiked at current tick.
        """
        N = tr_post_neuron.shape[0]
        spk_post_syn = spikes_post[post]
        
        if self.integer_traces:
            shift_plus = int(jnp.round(jnp.log2(self.tau_plus))) if self.tau_plus > 1 else 1
            shift_minus = int(jnp.round(jnp.log2(self.tau_minus))) if self.tau_minus > 1 else 1
            A_p = int(self.A_plus * 256)
            A_m = int(abs(self.A_minus) * 256)
            
            tr_pre_syn = _decay_integer(tr_pre_syn, shift_plus)
            tr_post_neuron = _decay_integer(tr_post_neuron, shift_minus)
            
            dw = jnp.where(spk_post_syn > 0, A_p * tr_pre_syn, 0) - jnp.where(arrivals_pre > 0, A_m * tr_post_neuron[post], 0)
            
            if original_weights is not None:
                is_exc = original_weights >= 0
                sign = jnp.where(is_exc, 1, -1)
                w_min_mag = jnp.minimum(jnp.abs(self.w_min), jnp.abs(self.w_max))
                w_max_mag = jnp.maximum(jnp.abs(self.w_min), jnp.abs(self.w_max))
                mag = jnp.abs(weights) + (dw // 256)
                mag = jnp.clip(mag, int(w_min_mag), int(w_max_mag))
                weights = sign * mag
            else:
                weights = jnp.clip(weights + (dw // 256), int(self.w_min), int(self.w_max))
            
            tr_pre_syn = tr_pre_syn + (arrivals_pre > 0).astype(jnp.int32) * 256
            tr_post_neuron = tr_post_neuron.at[jnp.arange(N)].add((spikes_post * 256).astype(jnp.int32))
        else:
            tr_pre_syn = tr_pre_syn * self.decay_plus
            tr_post_neuron = tr_post_neuron * self.decay_minus
            A_m = abs(self.A_minus)
            
            if original_weights is not None:
                is_exc = original_weights >= 0
                sign = jnp.where(is_exc, 1.0, -1.0)
                w_min_mag = jnp.minimum(jnp.abs(self.w_min), jnp.abs(self.w_max))
                w_max_mag = jnp.maximum(jnp.abs(self.w_min), jnp.abs(self.w_max))
                mag = jnp.abs(weights)
                
                if self.soft_bounds:
                    dw = spk_post_syn * self.A_plus * tr_pre_syn * (w_max_mag - mag) - \
                         arrivals_pre * A_m * tr_post_neuron[post] * (mag - w_min_mag)
                else:
                    dw = spk_post_syn * self.A_plus * tr_pre_syn - arrivals_pre * A_m * tr_post_neuron[post]
                    
                mag = jnp.clip(mag + dw, w_min_mag, w_max_mag)
                weights = sign * mag
            else:
                if self.soft_bounds:
                    dw = spk_post_syn * self.A_plus * tr_pre_syn * (self.w_max - weights) - \
                         arrivals_pre * A_m * tr_post_neuron[post] * (weights - self.w_min)
                else:
                    dw = spk_post_syn * self.A_plus * tr_pre_syn - arrivals_pre * A_m * tr_post_neuron[post]
                weights = jnp.clip(weights + dw, self.w_min, self.w_max)
            
            tr_pre_syn = tr_pre_syn + arrivals_pre
            tr_post_neuron = tr_post_neuron.at[jnp.arange(N)].add(spikes_post)
            
        return weights, tr_pre_syn, tr_post_neuron

    def apply(self, weights: jnp.ndarray, pre: jnp.ndarray, post: jnp.ndarray, delays: jnp.ndarray,
              spikes: jnp.ndarray, original_weights: jnp.ndarray) -> jnp.ndarray:
        T, N = spikes.shape
        E = weights.shape[0]

        is_exc = original_weights >= 0
        w_min_mag = jnp.minimum(jnp.abs(self.w_min), jnp.abs(self.w_max))
        w_max_mag = jnp.maximum(jnp.abs(self.w_min), jnp.abs(self.w_max))

        if self.integer_traces:
            shift_plus = int(jnp.round(jnp.log2(self.tau_plus))) if self.tau_plus > 1 else 1
            shift_minus = int(jnp.round(jnp.log2(self.tau_minus))) if self.tau_minus > 1 else 1
            A_p = int(self.A_plus * 256)
            A_m = int(abs(self.A_minus) * 256)
            sign = jnp.where(is_exc, 1, -1)

            def step(carry, t):
                mag, tr_pre_syn, tr_post_neuron = carry
                idx_t_minus_d = t - delays
                valid_pre = idx_t_minus_d >= 0
                arr_pre = jnp.where(valid_pre, spikes[idx_t_minus_d, pre], 0).astype(jnp.int32)
                spk_post_now = spikes[t, post].astype(jnp.int32)
                
                tr_pre_syn = _decay_integer(tr_pre_syn, shift_plus)
                tr_post_neuron = _decay_integer(tr_post_neuron, shift_minus)
                
                dw = jnp.where(spk_post_now, A_p * tr_pre_syn, 0) - jnp.where(arr_pre, A_m * tr_post_neuron[post], 0)
                mag = jnp.clip(mag + (dw // 256), int(w_min_mag), int(w_max_mag))
                
                tr_pre_syn = tr_pre_syn + arr_pre * 256
                tr_post_neuron = tr_post_neuron.at[jnp.arange(N)].add((spikes[t] * 256).astype(jnp.int32))
                return (mag, tr_pre_syn, tr_post_neuron), None

            init_carry = (jnp.abs(weights).astype(jnp.int32), jnp.zeros(E, dtype=jnp.int32), jnp.zeros(N, dtype=jnp.int32))
            (final_mag, _, _), _ = jax.lax.scan(step, init_carry, jnp.arange(T))
            final_w = sign * jnp.clip(final_mag, int(w_min_mag), int(w_max_mag))
        else:
            sign = jnp.where(is_exc, 1.0, -1.0)
            A_m = abs(self.A_minus)

            def step(carry, t):
                mag, tr_pre_syn, tr_post_neuron = carry
                idx_t_minus_d = t - delays
                valid_pre = idx_t_minus_d >= 0
                arr_pre = jnp.where(valid_pre, spikes[idx_t_minus_d, pre], 0.0)
                spk_post_now = spikes[t, post].astype(jnp.int32)
                
                tr_pre_syn = tr_pre_syn * self.decay_plus
                tr_post_neuron = tr_post_neuron * self.decay_minus
                
                if self.soft_bounds:
                    dw = spk_post_now * self.A_plus * tr_pre_syn * (w_max_mag - mag) - \
                         arr_pre * A_m * tr_post_neuron[post] * (mag - w_min_mag)
                else:
                    dw = spk_post_now * self.A_plus * tr_pre_syn - arr_pre * A_m * tr_post_neuron[post]
                
                mag = jnp.clip(mag + dw, w_min_mag, w_max_mag)
                tr_pre_syn = tr_pre_syn + arr_pre
                tr_post_neuron = tr_post_neuron.at[jnp.arange(N)].add(spikes[t])
                return (mag, tr_pre_syn, tr_post_neuron), None

            init_carry = (jnp.abs(weights).astype(jnp.float32), jnp.zeros(E, dtype=jnp.float32), jnp.zeros(N, dtype=jnp.float32))
            (final_mag, _, _), _ = jax.lax.scan(step, init_carry, jnp.arange(T))
            final_w = sign * jnp.clip(final_mag, w_min_mag, w_max_mag)

        final_w = jnp.where(is_exc, jnp.maximum(final_w, 0.0), jnp.minimum(final_w, 0.0))
        return final_w

    def declared_cost(self, num_neurons: int, num_synapses: int, ticks: int) -> Tuple[int, int]:
        bytes_cost = num_synapses * 4 + num_neurons * 4
        ops_cost = num_synapses * ticks * 10
        return (bytes_cost, ops_cost)

class HebbianRule:
    def __init__(self, eta: float = 0.01, norm_target: float = 1.0, norm_type: str = "l1_subtractive"):
        self.eta = eta
        self.norm_target = norm_target
        self.norm_type = norm_type

    def step(self, weights: jnp.ndarray, pre: jnp.ndarray, post: jnp.ndarray,
             spikes_post: jnp.ndarray, arrivals_pre: jnp.ndarray,
             num_neurons: int, original_weights: Optional[jnp.ndarray] = None) -> jnp.ndarray:
        """Single tick step update for online simulation loop."""
        arr_pre = arrivals_pre
        spk_post = spikes_post[post]
        
        if self.norm_type == "oja":
            dw = self.eta * spk_post * (arr_pre - spk_post * weights)
        else:
            dw = self.eta * arr_pre * spk_post
            
        w_new = weights + dw
        
        if self.norm_type.startswith("l1"):
            sum_w = jnp.zeros(num_neurons).at[post].add(w_new)
            post_sums = sum_w[post]
            if self.norm_type == "l1_multiplicative":
                scale = jnp.where(post_sums > 0, self.norm_target / post_sums, 1.0)
                w_new = w_new * scale
            elif self.norm_type == "l1_subtractive":
                diff = (post_sums - self.norm_target)
                deg = jnp.zeros(num_neurons).at[post].add(1.0)
                deg_post = deg[post]
                sub = jnp.where(deg_post > 0, diff / deg_post, 0.0)
                w_new = w_new - sub
                
        if original_weights is not None:
            is_exc = original_weights >= 0
            sign = jnp.where(is_exc, 1.0, -1.0)
            w_new = sign * jnp.maximum(0.0, jnp.abs(w_new))
        else:
            w_new = jnp.maximum(0.0, w_new)
            
        return w_new

    def apply(self, weights: jnp.ndarray, pre: jnp.ndarray, post: jnp.ndarray, delays: jnp.ndarray,
              spikes: jnp.ndarray, original_weights: jnp.ndarray) -> jnp.ndarray:
        T, N = spikes.shape
        E = weights.shape[0]

        def step(w, t):
            idx_t_minus_d = t - delays
            valid_pre = idx_t_minus_d >= 0
            arr_pre = jnp.where(valid_pre, spikes[idx_t_minus_d, pre], 0.0)
            return self.step(w, pre, post, spikes[t], arr_pre, N, original_weights), None

        final_w, _ = jax.lax.scan(step, weights.astype(jnp.float32), jnp.arange(T))
        if original_weights is not None:
            is_exc = original_weights >= 0
            sign = jnp.where(is_exc, 1.0, -1.0)
            final_w = sign * jnp.maximum(0.0, jnp.abs(final_w))
        return final_w

    def declared_cost(self, num_neurons: int, num_synapses: int, ticks: int) -> Tuple[int, int]:
        bytes_cost = num_synapses * 4
        ops_cost = num_synapses * ticks * 8
        return (bytes_cost, ops_cost)

class ThreeFactorRule:
    def __init__(self, eta: float = 0.01, tau_e: float = 20.0):
        self.eta = eta
        self.tau_e = tau_e
        self.decay_e = jnp.exp(-1.0 / tau_e) if tau_e > 0 else 0.0

    def init_state(self, num_synapses: int) -> jnp.ndarray:
        return jnp.zeros(num_synapses, dtype=jnp.float32)

    def step(self, weights: jnp.ndarray, pre: jnp.ndarray, post: jnp.ndarray,
             spikes_post: jnp.ndarray, arrivals_pre: jnp.ndarray,
             elig: jnp.ndarray, modulator_val: Union[float, jnp.ndarray],
             original_weights: Optional[jnp.ndarray] = None) -> Tuple[jnp.ndarray, jnp.ndarray]:
        """Single tick step for ThreeFactorRule."""
        spk_post = spikes_post[post]
        elig = elig * self.decay_e + arrivals_pre * spk_post
        mod_post = modulator_val if jnp.ndim(modulator_val) == 0 else modulator_val[post]
        dw = self.eta * elig * mod_post
        weights = weights + dw
        if original_weights is not None:
            is_exc = original_weights >= 0
            weights = jnp.where(is_exc, jnp.maximum(weights, 0), jnp.minimum(weights, 0))
        return weights, elig

    def apply(self, weights: jnp.ndarray, pre: jnp.ndarray, post: jnp.ndarray, delays: jnp.ndarray,
              spikes: jnp.ndarray, modulator: jnp.ndarray, original_weights: jnp.ndarray) -> jnp.ndarray:
        T, N = spikes.shape
        E = weights.shape[0]
        is_global_modulator = modulator.ndim == 1
        
        def step(carry, t):
            w, elig = carry
            idx_t_minus_d = t - delays
            valid_pre = idx_t_minus_d >= 0
            arr_pre = jnp.where(valid_pre, spikes[idx_t_minus_d, pre], 0.0)
            mod_val = modulator[t] if is_global_modulator else modulator[t]
            w, elig = self.step(w, pre, post, spikes[t], arr_pre, elig, mod_val, original_weights)
            return (w, elig), None

        init_carry = (weights.astype(jnp.float32), jnp.zeros(E, dtype=jnp.float32))
        (final_w, _), _ = jax.lax.scan(step, init_carry, jnp.arange(T))
        is_exc = original_weights >= 0
        final_w = jnp.where(is_exc, jnp.maximum(final_w, 0), jnp.minimum(final_w, 0))
        return final_w

    def declared_cost(self, num_neurons: int, num_synapses: int, ticks: int) -> Tuple[int, int]:
        bytes_cost = num_synapses * 4
        ops_cost = num_synapses * ticks * 6
        return (bytes_cost, ops_cost)
