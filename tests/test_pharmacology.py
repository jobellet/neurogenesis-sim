"""P1 profiles as data, P2 transmitters and receptor assignment, P3 compilation in developmental contexts."""
import json
from pathlib import Path

import numpy as np
import pytest

import neurogenesis.stages  # noqa: F401
from neurogenesis.pharmacology import DEFAULT, Profile, Receptor, compile_weights, load_profile
from neurogenesis.stages.base import STAGE_REGISTRY, run_schedule
from neurogenesis.tissue import SparseConnectivity, Tissue

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "profiles" / "example_receptors.json"


def _run(op, t, params, seed=0):
    return STAGE_REGISTRY[op]().run(t, params, {}, {}, np.random.default_rng(seed))


def _tissue():
    """Cell 0 releases glutamate, cell 1 GABA, cell 2 both (co-transmission); cell 3 receives everything."""
    t = Tissue.empty()
    t.add_cells(4, positions=np.zeros((4, 3)), cell_type=np.array([0, 1, 2, 3]), sign=np.array([1, -1, 1, 1]))
    t.connectivity = SparseConnectivity(np.array([0, 1, 2, 2], np.int32), np.array([3, 3, 3, 3], np.int32),
                                        np.array([100, -100, 100, 100], np.int32), np.array([1, 1, 1, 1], np.int32))
    return t


def test_default_profile_keeps_every_weight():
    t = _tissue()
    before = t.connectivity.weight.copy()
    r = compile_weights(t, DEFAULT)
    np.testing.assert_array_equal(t.connectivity.weight, before)
    assert r == dict(changed=0, silenced=0)


def test_default_profile_keeps_a_grown_network_bit_for_bit():
    from test_development import fp, sheet_plan, toy_genome
    from neurogenesis.development import grow
    net = grow(sheet_plan(), toy_genome(), 3)
    t = Tissue.from_network(net)
    compile_weights(t, DEFAULT)
    assert fp(t.to_network()) == fp(net)


def test_profile_json_round_trip_and_validation(tmp_path, monkeypatch):
    p = load_profile(str(EXAMPLE))
    assert p.receptors[0].sign == "pre" and p.receptor_index("gaba_a") == 4
    q = Profile.from_dict(json.loads(json.dumps(p.to_dict())))
    assert q.to_dict() == p.to_dict()
    (tmp_path / "mine.json").write_text(json.dumps(p.to_dict()))
    monkeypatch.setenv("NEUROGENESIS_PROFILES", str(tmp_path))
    assert load_profile("mine").id == "example_receptors"
    with pytest.raises(ValueError, match="unknown transmitter"):
        Profile("bad", transmitters=["a"], receptors=[Receptor("x", transmitter="b")])
    with pytest.raises(FileNotFoundError):
        load_profile("does_not_exist")


def test_transmitters_receptors_and_context_switch():
    profile = load_profile(str(EXAMPLE))
    t = _tissue()
    t = _run("set_transmitters", t, {"profile": str(EXAMPLE), "rules": [
        {"condition": "cell_type == 0", "transmitters": ["glutamate"]},
        {"condition": "cell_type == 1", "transmitters": ["gaba"]},
        {"condition": "cell_type == 2", "transmitters": ["glutamate", "gaba"]}]})
    g, a = profile.bit("glutamate"), profile.bit("gaba")
    assert t.transmitter.tolist() == [g, a, g | a, 0]
    t = _run("express_receptors", t, {"profile": str(EXAMPLE), "rules": [
        {"condition": "cell_type == 3", "receptor": "glutamate_gated_chloride", "level": 1.0},
        {"condition": "cell_type == 3", "receptor": "gaba_a", "level": 3.0}]})
    assert t.receptor_expression.shape == (4, len(profile.receptors))
    t = _run("assign_receptors", t, {"profile": str(EXAMPLE), "mode": "max"})
    rc = t.connectivity.receptor_class.tolist()
    assert rc == [2, 4, 4, 4]           # glutamate -> the only glutamate receptor expressed; GABA -> GABA-A (most expressed)
    t = _run("pharmacology", t, {"profile": str(EXAMPLE), "context": "immature"})
    assert t.connectivity.weight.tolist() == [-100, 100, 100, 100]     # GluCl inhibits; immature GABA-A depolarises
    t = _run("pharmacology", t, {"profile": str(EXAMPLE), "context": "mature"})
    assert t.connectivity.weight.tolist() == [-100, -100, -100, -100]


def test_missing_transmitter_silences_and_sampling_is_deterministic():
    profile = load_profile(str(EXAMPLE))
    t = _tissue()
    t.connectivity.receptor_class = np.array([1, 1, 1, 1], np.uint8)    # ionotropic glutamate everywhere
    t.transmitter[:] = [profile.bit("glutamate"), profile.bit("gaba"), 0, 0]
    r = compile_weights(t, profile)
    assert t.connectivity.weight.tolist() == [100, 0, 0, 0] and r["silenced"] == 3

    def sampled(seed):
        t = Tissue.empty()
        n = 200
        t.add_cells(n, positions=np.zeros((n, 3)), transmitter=np.full(n, profile.bit("glutamate")))
        t.connectivity = SparseConnectivity(np.arange(n - 1, dtype=np.int32), np.arange(1, n, dtype=np.int32),
                                            np.full(n - 1, 50, np.int32), np.ones(n - 1, np.int32))
        t = _run("express_receptors", t, {"profile": str(EXAMPLE), "rules": [
            {"receptor": "ionotropic_glutamate", "level": 3.0}, {"receptor": "glutamate_gated_chloride", "level": 1.0}]})
        return _run("assign_receptors", t, {"profile": str(EXAMPLE)}, seed=seed).connectivity.receptor_class
    a, b = sampled(1), sampled(1)
    np.testing.assert_array_equal(a, b)
    assert 0.6 < np.mean(a == 1) < 0.9 and set(np.unique(a)) == {1, 2}  # in proportion 3 : 1


def test_pharmacology_stages_are_neutral_without_params_and_in_a_schedule():
    project = {"schedule": [
        {"name": "cells", "operator": "place_by_hand", "params": {"positions": [[0, 0, 0], [1, 0, 0]]}},
        {"name": "wire", "operator": "connect_by_hand", "params": {"pre": [0], "post": [1], "weight": 40}},
        {"name": "tx", "operator": "set_transmitters", "params": {"profile": str(EXAMPLE), "rules": [{"transmitters": ["gaba"]}]}},
        {"name": "rx", "operator": "express_receptors", "params": {"profile": str(EXAMPLE), "rules": [{"receptor": "gaba_a", "level": 1}]}},
        {"name": "assign", "operator": "assign_receptors", "params": {"profile": str(EXAMPLE)}},
        {"name": "compile", "operator": "pharmacology", "params": {"profile": str(EXAMPLE)}}]}
    t = run_schedule(project, {}, 0)
    assert t.connectivity.weight.tolist() == [-40]
