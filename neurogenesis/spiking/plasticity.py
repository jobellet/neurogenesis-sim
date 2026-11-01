import jax
import jax.numpy as jnp
from typing import Tuple, Dict, Any, Optional

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
        
        # Precompute constants for float traces
        self.decay_plus = jnp.exp(-1.0 / tau_plus) if tau_plus > 0 else 0.0
        self.decay_minus = jnp.exp(-1.0 / tau_minus) if tau_minus > 0 else 0.0

    def apply(self, weights: jnp.ndarray, pre: jnp.ndarray, post: jnp.ndarray, delays: jnp.ndarray,
              spikes: jnp.ndarray, original_weights: jnp.ndarray) -> jnp.ndarray:
        """
        weights: (E,) Current weights
        pre: (E,) Pre-synaptic neuron indices
        post: (E,) Post-synaptic neuron indices
        delays: (E,) Axonal delays
        spikes: (T, N) Spike history (1 if spike, 0 otherwise)
        original_weights: (E,) Used to check Dale's law signs.
        """
        # Spikes shape: T = time steps, N = number of neurons
        T, N = spikes.shape
        E = weights.shape[0]

        # The STDP applies weight updates at spike times.
        # A pre-synaptic spike at time t arrives at the synapse at t + delay.
        # So we can track pre_trace at the synapse, and post_trace at the post-synaptic neuron.

        if self.integer_traces:
            # integer traces (scaled by 256 for precision, bit-shift tau representation)
            # A_plus and A_minus should be scaled as integers, tau is shift
            shift_plus = int(jnp.round(jnp.log2(self.tau_plus))) if self.tau_plus > 1 else 1
            shift_minus = int(jnp.round(jnp.log2(self.tau_minus))) if self.tau_minus > 1 else 1
            
            A_p = int(self.A_plus * 256)
            A_m = int(self.A_minus * 256)

            def step(carry, t):
                w, tr_pre_syn, tr_post_neuron = carry
                
                # pre_spikes arriving at synapse at time t
                # We need spikes at t - delay. So a spike fired at t-delay arrives now.
                # However, spikes array gives spikes[t]. Let's say we process forward in time.
                spk_pre_now = spikes[t, pre] # But wait, delay means it arrives at t + delay.
                # Actually it's easier to check if t >= delay and use spikes[t - delay, pre]
                # To vectorize: we just access spikes[t - delays, pre] safely
                idx_t_minus_d = t - delays
                valid_pre = idx_t_minus_d >= 0
                arr_pre = jnp.where(valid_pre, spikes[idx_t_minus_d, pre], 0).astype(jnp.int32)
                
                spk_post_now = spikes[t, post].astype(jnp.int32)
                
                # decay
                tr_pre_syn = _decay_integer(tr_pre_syn, shift_plus)
                tr_post_neuron = _decay_integer(tr_post_neuron, shift_minus)
                
                # apply STDP updates
                # When post spikes: delta w = + A_plus * tr_pre_syn
                # When pre arrives: delta w = - A_minus * tr_post_neuron
                
                dw = jnp.where(spk_post_now, A_p * tr_pre_syn, 0) - jnp.where(arr_pre, A_m * tr_post_neuron[post], 0)
                # Convert back to regular weight scale (divide by 256)
                # Soft bounds would be slightly more complex with ints. Using hard bounds for now.
                w = w + (dw // 256)
                
                # update traces (add 256 for a spike of size 1)
                tr_pre_syn = tr_pre_syn + arr_pre * 256
                tr_post_neuron = tr_post_neuron.at[jnp.arange(N)].add((spikes[t] * 256).astype(jnp.int32))
                
                return (w, tr_pre_syn, tr_post_neuron), None

            init_carry = (weights.astype(jnp.int32), jnp.zeros(E, dtype=jnp.int32), jnp.zeros(N, dtype=jnp.int32))
            
        else:
            # Float traces
            def step(carry, t):
                w, tr_pre_syn, tr_post_neuron = carry
                
                idx_t_minus_d = t - delays
                valid_pre = idx_t_minus_d >= 0
                arr_pre = jnp.where(valid_pre, spikes[idx_t_minus_d, pre], 0.0)
                spk_post_now = spikes[t, post].astype(jnp.int32)
                
                tr_pre_syn = tr_pre_syn * self.decay_plus
                tr_post_neuron = tr_post_neuron * self.decay_minus
                
                # dw
                if self.soft_bounds:
                    dw = spk_post_now * self.A_plus * tr_pre_syn * (self.w_max - w) - \
                         arr_pre * self.A_minus * tr_post_neuron[post] * (w - self.w_min)
                else:
                    dw = spk_post_now * self.A_plus * tr_pre_syn - arr_pre * self.A_minus * tr_post_neuron[post]
                
                w = w + dw
                
                # hard bounds
                w = jnp.clip(w, self.w_min, self.w_max)
                
                # update traces
                tr_pre_syn = tr_pre_syn + arr_pre
                tr_post_neuron = tr_post_neuron.at[jnp.arange(N)].add(spikes[t])
                
                return (w, tr_pre_syn, tr_post_neuron), None

            init_carry = (weights, jnp.zeros(E, dtype=jnp.float32), jnp.zeros(N, dtype=jnp.float32))

        (final_w, _, _), _ = jax.lax.scan(step, init_carry, jnp.arange(T))
        
        # Apply Dale's law and bounds again
        if not self.soft_bounds and not self.integer_traces:
             final_w = jnp.clip(final_w, self.w_min, self.w_max)
        elif self.integer_traces:
             final_w = jnp.clip(final_w, int(self.w_min), int(self.w_max))

        is_exc = original_weights >= 0
        final_w = jnp.where(is_exc, jnp.maximum(final_w, 0), jnp.minimum(final_w, 0))
        return final_w

    def declared_cost(self, num_neurons: int, num_synapses: int, ticks: int) -> Tuple[int, int]:
        # Bytes: traces for synapses and neurons
        bytes_cost = num_synapses * 4 + num_neurons * 4
        # Ops: roughly 10 ops per synapse per tick
        ops_cost = num_synapses * ticks * 10
        return (bytes_cost, ops_cost)

class HebbianRule:
    def __init__(self, eta: float = 0.01, norm_target: float = 1.0, norm_type: str = "l1_subtractive"):
        self.eta = eta
        self.norm_target = norm_target
        self.norm_type = norm_type # "l1_subtractive", "l1_multiplicative", "oja"

    def apply(self, weights: jnp.ndarray, pre: jnp.ndarray, post: jnp.ndarray, delays: jnp.ndarray,
              spikes: jnp.ndarray, original_weights: jnp.ndarray) -> jnp.ndarray:
        T, N = spikes.shape
        E = weights.shape[0]

        def step(w, t):
            # purely correlational: pre * post
            idx_t_minus_d = t - delays
            valid_pre = idx_t_minus_d >= 0
            arr_pre = jnp.where(valid_pre, spikes[idx_t_minus_d, pre], 0.0)
            spk_post = spikes[t, post]
            
            dw = self.eta * arr_pre * spk_post
            
            if self.norm_type == "oja":
                # dw = eta * post * (pre - post * w)
                dw = self.eta * spk_post * (arr_pre - spk_post * w)
            
            w_new = w + dw
            
            # Normalization per post neuron
            if self.norm_type.startswith("l1"):
                # sum of weights per post neuron
                # Need a quick scatter_add
                sum_w = jnp.zeros(N).at[post].add(w_new)
                post_sums = sum_w[post]
                
                if self.norm_type == "l1_multiplicative":
                    scale = jnp.where(post_sums > 0, self.norm_target / post_sums, 1.0)
                    w_new = w_new * scale
                elif self.norm_type == "l1_subtractive":
                    diff = (post_sums - self.norm_target)
                    # count incoming synapses per post
                    deg = jnp.zeros(N).at[post].add(1.0)
                    deg_post = deg[post]
                    sub = jnp.where(deg_post > 0, diff / deg_post, 0.0)
                    w_new = jnp.maximum(0.0, w_new - sub)
            
            return w_new, None

        final_w, _ = jax.lax.scan(step, weights.astype(jnp.float32), jnp.arange(T))
        
        # Dale's law
        is_exc = original_weights >= 0
        final_w = jnp.where(is_exc, jnp.maximum(final_w, 0), jnp.minimum(final_w, 0))
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

    def apply(self, weights: jnp.ndarray, pre: jnp.ndarray, post: jnp.ndarray, delays: jnp.ndarray,
              spikes: jnp.ndarray, modulator: jnp.ndarray, original_weights: jnp.ndarray) -> jnp.ndarray:
        """
        modulator: (T,) or (T, N) global or per-region scalar signal. We'll broadcast to (T, N) internally if needed.
        """
        T, N = spikes.shape
        E = weights.shape[0]

        is_global_modulator = modulator.ndim == 1
        
        def step(carry, t):
            w, elig = carry
            
            idx_t_minus_d = t - delays
            valid_pre = idx_t_minus_d >= 0
            arr_pre = jnp.where(valid_pre, spikes[idx_t_minus_d, pre], 0.0)
            spk_post = spikes[t, post]
            
            # e_ij update: e_ij = e_ij * decay + pre * post
            elig = elig * self.decay_e + arr_pre * spk_post
            
            mod_val = modulator[t] if is_global_modulator else modulator[t, post]
            
            dw = self.eta * elig * mod_val
            w = w + dw
            
            return (w, elig), None

        init_carry = (weights.astype(jnp.float32), jnp.zeros(E, dtype=jnp.float32))
        (final_w, _), _ = jax.lax.scan(step, init_carry, jnp.arange(T))
        
        # Dale's law
        is_exc = original_weights >= 0
        final_w = jnp.where(is_exc, jnp.maximum(final_w, 0), jnp.minimum(final_w, 0))
        return final_w

    def declared_cost(self, num_neurons: int, num_synapses: int, ticks: int) -> Tuple[int, int]:
        bytes_cost = num_synapses * 4
        ops_cost = num_synapses * ticks * 6
        return (bytes_cost, ops_cost)
