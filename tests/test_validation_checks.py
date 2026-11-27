"""Order check, reset, matched control and random lesions in validation assays (E4)."""
import numpy as np
import pytest

from neurogenesis.validation import _lesion, run_assay
from test_development import sheet_plan, toy_genome


def _module():
    from neurogenesis.modules import Module
    return Module(name="toy", plan=sheet_plan(), genome=toy_genome(), inputs=["sheet"], outputs=["out"],
                  validation={"assays": []}, version="1.0.0", toolbox=">=0.1, <1.0")


DRIVE = {"name": "drive", "ticks": 60, "seeds": [1000, 1001], "stimuli": [{}, {"sheet": 4000}],
         "readout": {"region": "map", "measure": "rate"}, "metric": "difference", "gate": {"min": 1.0}}


def test_new_options_are_off_by_default():
    r = run_assay(_module(), DRIVE)
    assert set(r) == {"name", "seeds", "values", "passed", "pass_fraction", "ok"}
    assert run_assay(_module(), dict(DRIVE, lesion={"fraction": 0.0})) ["values"] == r["values"]


def test_reset_makes_each_stimulus_start_from_rest_and_order_check_measures_carry_over():
    m = _module()
    carry = dict(DRIVE, stimuli=[{"sheet": 4000}, {}], metric="stimulus:1", gate={}, blank=0)
    r = run_assay(m, dict(carry, order_check={"tolerance": 0.0}))
    reset = run_assay(m, dict(carry, reset=True, order_check={"tolerance": 0.0}))
    assert reset["order_max_diff"] == 0.0 and reset["order_ok"] and reset["ok"]
    assert reset["values"] == run_assay(m, dict(carry, stimuli=[{}], metric="stimulus:0", gate={}))["values"]
    assert r["order_max_diff"] >= 0.0 and r["ok"] == r["order_ok"]


def test_matched_control_reports_the_effect_of_the_mechanism():
    ctrl = dict(DRIVE, control={"knockout": {"projections": [["sheet", "map"]]}, "gate": {"min": 1.0}})
    r = run_assay(_module(), ctrl)
    assert r["control_values"] == [0.0, 0.0]
    assert r["effect"] == r["values"] and r["effect_mean"] > 1.0 and r["ok"]
    assert not run_assay(_module(), dict(ctrl, control=dict(ctrl["control"], gate={"min": 1e9})))["ok"]


def test_lesions_reduce_the_response_and_are_deterministic():
    m = _module()
    full = run_assay(m, dict(DRIVE, gate={}))
    les = dict(DRIVE, gate={}, lesion={"fraction": 0.5, "seed": 3})
    a, b = run_assay(m, les), run_assay(m, les)
    assert a == b
    assert np.mean(a["values"]) < np.mean(full["values"])
    assert run_assay(m, dict(DRIVE, gate={}, lesion={"fraction": 1.0}))["values"] == [0.0, 0.0]


def test_lesion_helper_keeps_indices_and_silences_synapses():
    from neurogenesis.development import grow
    net = grow(sheet_plan(), toy_genome(), 1000)
    n, e = net.num_neurons, net.num_synapses
    dead = _lesion(net, {"fraction": 0.2, "target": "cells", "seed": 1}, 1000)
    assert net.num_neurons == n and net.num_synapses == e and dead.sum() == round(0.2 * n)
    arrays = net.synapse_arrays
    pre = np.asarray(arrays["pre"]) if arrays is not None else np.array([s.pre for s in net.synapses])
    w = np.asarray(arrays["weight"]) if arrays is not None else np.array([s.weight for s in net.synapses])
    assert np.all(w[dead[pre]] == 0)
    def weights(nt):
        a = nt.synapse_arrays
        return np.asarray(a["weight"]).copy() if a is not None else np.array([s.weight for s in nt.synapses])
    net2 = grow(sheet_plan(), toy_genome(), 1000)
    w0 = weights(net2)
    dead2 = _lesion(net2, {"fraction": 0.25, "target": "synapses"}, 1000)
    w2 = weights(net2)
    changed = w0 != w2
    assert not dead2.any() and np.all(w2[changed] == 0)
    assert int(np.sum(w2 == 0) - np.sum(w0 == 0)) <= round(0.25 * e) and int(np.sum(changed)) > 0
    with pytest.raises(ValueError):
        _lesion(net2, {"fraction": 0.1, "target": "axons"}, 1000)
