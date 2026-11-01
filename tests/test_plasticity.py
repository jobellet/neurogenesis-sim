import jax.numpy as jnp
import numpy as np
import pytest

from neurogenesis.spiking.plasticity import STDPRule, HebbianRule, ThreeFactorRule

def test_stdp_asymmetric_curve():
    # Two neurons, one synapse
    pre = jnp.array([0])
    post = jnp.array([1])
    delays = jnp.array([1])
    original_weights = jnp.array([10.0])
    
    A_plus = 1.0
    A_minus = 1.0
    tau_p = 20.0
    tau_m = 20.0
    rule = STDPRule(A_plus=A_plus, A_minus=A_minus, tau_plus=tau_p, tau_minus=tau_m, w_min=0.0, w_max=100.0)

    # test t_post - t_pre from -50 to +50
    dt_vals = np.arange(-50, 51)
    dw_vals = []
    
    for dt in dt_vals:
        T = 150
        spikes = np.zeros((T, 2))
        
        t_pre = 50
        # pre arrives at t_pre + delay = 51
        # t_post - (t_pre + delay) = dt => t_post = dt + 51
        t_post = dt + 51
        
        if 0 <= t_post < T:
            spikes[t_pre, 0] = 1.0
            spikes[t_post, 1] = 1.0
            
        spikes_jnp = jnp.array(spikes)
        weights = jnp.array([10.0])
        
        final_w = rule.apply(weights, pre, post, delays, spikes_jnp, original_weights)
        dw_vals.append(final_w[0] - 10.0)
        
    dw_vals = np.array(dw_vals)
    
    # Check that for dt > 0, dw > 0
    assert np.all(dw_vals[dt_vals > 0] > 0)
    # Check that for dt < 0, dw < 0
    assert np.all(dw_vals[dt_vals < 0] < 0)
    # Check exponential decay
    assert dw_vals[dt_vals == 1][0] > dw_vals[dt_vals == 20][0]
    assert dw_vals[dt_vals == -1][0] < dw_vals[dt_vals == -20][0]

def test_stdp_bounds_and_dale():
    pre = jnp.array([0, 0])
    post = jnp.array([1, 2])
    delays = jnp.array([0, 0])
    original_weights = jnp.array([10.0, -10.0])
    weights = jnp.array([10.0, -10.0])
    
    rule = STDPRule(w_min=-5.0, w_max=15.0)
    
    T = 10
    spikes = jnp.zeros((T, 3))
    spikes = spikes.at[1, 0].set(1.0)
    spikes = spikes.at[2, 1].set(1.0) # Potentiation for exc synapse
    spikes = spikes.at[2, 2].set(1.0) # Potentiation for inh synapse
    
    final_w = rule.apply(weights, pre, post, delays, spikes, original_weights)
    
    # Final weight for exc shouldn't exceed 15
    assert final_w[0] <= 15.0
    # Final weight for inh should stay <= 0
    assert final_w[1] <= 0.0

def test_three_factor_modulator():
    pre = jnp.array([0])
    post = jnp.array([1])
    delays = jnp.array([0])
    original_weights = jnp.array([10.0])
    weights = jnp.array([10.0])
    
    rule = ThreeFactorRule(eta=1.0, tau_e=20.0)
    
    T = 10
    spikes = jnp.zeros((T, 2))
    spikes = spikes.at[1, 0].set(1.0)
    spikes = spikes.at[1, 1].set(1.0)
    
    # M(t) == 0
    mod_zero = jnp.zeros(T)
    w_zero = rule.apply(weights, pre, post, delays, spikes, mod_zero, original_weights)
    assert jnp.allclose(w_zero, 10.0)
    
    # M(t) > 0
    mod_pos = jnp.ones(T)
    w_pos = rule.apply(weights, pre, post, delays, spikes, mod_pos, original_weights)
    assert w_pos[0] > 10.0
    
    # M(t) < 0
    mod_neg = -jnp.ones(T)
    w_neg = rule.apply(weights, pre, post, delays, spikes, mod_neg, original_weights)
    assert w_neg[0] < 10.0

def test_stdp_no_op():
    pre = jnp.array([0])
    post = jnp.array([1])
    delays = jnp.array([1])
    original_weights = jnp.array([10.0])
    weights = jnp.array([10.0])
    
    rule = STDPRule(A_plus=0.0, A_minus=0.0)
    
    T = 10
    spikes = jnp.ones((T, 2))
    
    final_w = rule.apply(weights, pre, post, delays, spikes, original_weights)
    assert jnp.allclose(final_w, 10.0)


def test_stdp_integer_traces():
    pre = jnp.array([0])
    post = jnp.array([1])
    delays = jnp.array([1])
    original_weights = jnp.array([1000])
    weights = jnp.array([1000])
    
    # integer STDP, shift ~ tau
    rule = STDPRule(A_plus=1.0, A_minus=1.0, tau_plus=16.0, tau_minus=16.0, w_min=0, w_max=2000, integer_traces=True)
    
    T = 20
    spikes = jnp.zeros((T, 2))
    # Pre spikes at 5, arrives at 6.
    spikes = spikes.at[5, 0].set(1.0)
    # Post spikes at 8. dt = t_post - t_arr = 8 - 6 = +2 => potentiation
    spikes = spikes.at[8, 1].set(1.0)
    
    final_w = rule.apply(weights, pre, post, delays, spikes, original_weights)
    assert final_w[0] > 1000

def test_hebbian_norm():
    pre = jnp.array([0, 1])
    post = jnp.array([2, 2])
    delays = jnp.array([0, 0])
    original_weights = jnp.array([10.0, 10.0])
    weights = jnp.array([10.0, 10.0])
    
    rule = HebbianRule(eta=0.1, norm_target=20.0, norm_type="l1_subtractive")
    
    T = 10
    spikes = jnp.ones((T, 3))
    
    final_w = rule.apply(weights, pre, post, delays, spikes, original_weights)
    assert jnp.allclose(final_w[0] + final_w[1], 20.0)

