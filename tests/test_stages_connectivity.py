import json

import numpy as np
import pytest

from neurogenesis.tissue import Tissue
from neurogenesis.stages.base import Stage
from neurogenesis.params import Const, Gene
from neurogenesis.stages.base import run_schedule

def test_connectivity_hand_remap():
    t = Tissue.empty()
    # add cells
    stage_place = Stage(name="p", operator="place_by_hand", params={"positions": Const([[0,0,0], [1,1,1], [2,2,2]])})
    t = stage_place.run(t, {}, {}, np.random.default_rng(0))
    assert len(t.alive) == 3
    
    stage_conn = Stage(name="c", operator="connect_by_hand", params={"pre": Const([0, 1]), "post": Const([1, 2]), "weight": Const(100), "delay": Const(2)})
    t = stage_conn.run(t, {}, {}, np.random.default_rng(0))
    
    assert len(t.connectivity.pre) == 2
    assert t.connectivity.pre[0] == 0
    assert t.connectivity.post[0] == 1
    
    # kill middle cell
    t.kill(np.array([False, True, False]))
    t.compact()
    
    assert len(t.alive) == 2
    # Only synapse should be dead
    assert len(t.connectivity.pre) == 0

def test_cost_declarations():
    stage = Stage(name="p", operator="place_by_hand", params={})
    assert stage.cost(10, 0)[0] > 0
    
    stage2 = Stage(name="g", operator="grow_axons", params={})
    assert stage2.cost(10, 5)[0] > 0

GUIDANCE = {"0->1": {"c": [0, 0, 0], "B": np.eye(3).tolist(), "sigma": 0.2, "p0": 0.8,
                     "w": Gene(("axon", "w"), lo=10.0, hi=100.0), "wc": 100, "inh": 1.0}}
GENOME = {"axon": {"w": 50.0}}


def _two_regions(pos):
    t = Tissue.empty()
    t.add_cells(10, positions=pos, region=np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1]))
    return t


def test_determinism_grow_axons():
    rng = np.random.default_rng(42)
    pos = rng.uniform(0.0, 0.2, (10, 3))
    stage = Stage(name="g", operator="grow_axons", params={"guidance": Const(GUIDANCE)})

    res1 = stage.run(_two_regions(pos), GENOME, {}, np.random.default_rng(42))
    res2 = stage.run(_two_regions(pos), GENOME, {}, np.random.default_rng(42))
    assert len(res1.connectivity.pre) > 0
    assert np.array_equal(res1.connectivity.pre, res2.connectivity.pre)
    assert np.array_equal(res1.connectivity.weight, res2.connectivity.weight)
    assert np.all(np.abs(res1.connectivity.weight) >= 45) and np.all(np.abs(res1.connectivity.weight) <= 55)

    res3 = stage.run(_two_regions(pos), GENOME, {}, np.random.default_rng(43))
    assert not np.array_equal(res1.connectivity.pre, res3.connectivity.pre) or not np.array_equal(res1.connectivity.weight, res3.connectivity.weight)

    # the Gene is read from the genome
    res4 = stage.run(_two_regions(pos), {"axon": {"w": 20.0}}, {}, np.random.default_rng(42))
    assert np.array_equal(res1.connectivity.pre, res4.connectivity.pre)
    assert np.all(np.abs(res4.connectivity.weight) <= 22)


def test_grow_axons_list_guidance_and_region_names_match_dict_form():
    pos = np.random.default_rng(1).uniform(0.0, 0.2, (10, 3))
    gd = {**GUIDANCE["0->1"], "sigma": 0.5, "p0": 1.0}
    as_list = [{"src": "a", "dst": "b", **gd}]
    a = Stage(name="g", operator="grow_axons", params={"guidance": Const({"0->1": gd})})
    b = Stage(name="g", operator="grow_axons", params={"guidance": Const(as_list), "region_map": Const({"a": 0, "b": 1})})
    ra = a.run(_two_regions(pos), GENOME, {}, np.random.default_rng(3))
    rb = b.run(_two_regions(pos), GENOME, {}, np.random.default_rng(3))
    assert len(ra.connectivity.pre) > 0
    assert np.array_equal(ra.connectivity.pre, rb.connectivity.pre)
    assert np.array_equal(ra.connectivity.weight, rb.connectivity.weight)


def _project():
    w_gene = {"type": "Gene", "path": ["axon", "w"], "lo": 10.0, "hi": 100.0}
    return {
        "version": "1.0.0",
        "fields": {
            "src_box": {"type": "Box", "center": [0, 0, 0], "size": [10, 10, 10]},
            "dst_box": {"type": "Box", "center": [20, 0, 0], "size": [10, 10, 10]},
        },
        "schedule": [
            {"name": "seed_src", "operator": "seed_cells", "params": {"N": 20, "geometry": "src_box", "region": 0}},
            {"name": "seed_dst", "operator": "seed_cells", "params": {"N": 20, "geometry": "dst_box", "region": 1}},
            {"name": "axons", "operator": "grow_axons", "params": {
                "guidance": {"0->1": {"B": np.eye(3).tolist(), "c": [0, 0, 0], "sigma": 0.3, "p0": 0.9, "w": w_gene}},
                "conduction_velocity": 2.0}},
        ],
    }


def test_grow_axons_project_json_round_trip():
    project = _project()
    reloaded = json.loads(json.dumps(project))
    t1 = run_schedule(project, GENOME, seed=7)
    t2 = run_schedule(reloaded, GENOME, seed=7)
    assert len(t1.connectivity.pre) > 0
    for k in ("pre", "post", "weight", "delay"):
        assert np.array_equal(getattr(t1.connectivity, k), getattr(t2.connectivity, k))
    assert np.all(t1.region[t1.connectivity.pre] == 0) and np.all(t1.region[t1.connectivity.post] == 1)
    assert np.all((np.abs(t1.connectivity.weight) >= 45) & (np.abs(t1.connectivity.weight) <= 55))


def test_grow_axons_explicit_empty_projections_is_noop():
    pos = np.random.default_rng(1).uniform(0.0, 0.2, (10, 3))
    for params in ({"projections": Const([])}, {"projections": Const([]), "guidance": Const(GUIDANCE)}):
        t = Stage(name="g", operator="grow_axons", params=params).run(_two_regions(pos), GENOME, {}, np.random.default_rng(0))
        assert len(t.connectivity.pre) == 0


def test_grow_axons_empty_population_is_noop():
    t = Tissue.empty()
    t.add_cells(5, positions=np.zeros((5, 3)), region=np.zeros(5, dtype=int))   # region 1 has no cells
    stage = Stage(name="g", operator="grow_axons", params={"guidance": Const(GUIDANCE)})
    assert len(stage.run(t, GENOME, {}, np.random.default_rng(0)).connectivity.pre) == 0


def test_grow_axons_errors():
    pos = np.random.default_rng(1).uniform(0.0, 0.2, (10, 3))

    def run(params, genome=GENOME):
        return Stage(name="g", operator="grow_axons", params=params).run(_two_regions(pos), genome, {}, np.random.default_rng(0))

    with pytest.raises(ValueError, match="no projections given"):
        run({})
    with pytest.raises(ValueError, match="no projections given"):
        run({}, genome={"guidance": {(0, 1): GUIDANCE["0->1"]}})   # genome["guidance"] is not read by this stage
    with pytest.raises(ValueError, match="no guidance dict for projection '1'->'0'"):
        run({"projections": Const(["0->1", "1->0"]), "guidance": Const(GUIDANCE)})
    with pytest.raises(ValueError, match="no guidance dict for projection '0'->'1'"):
        run({"projections": Const(["0->1"])})
    with pytest.raises(ValueError, match="cannot parse projection"):
        run({"projections": Const(["0 to 1"]), "guidance": Const(GUIDANCE)})
    with pytest.raises(ValueError, match="needs 'src' and 'dst'"):
        run({"guidance": Const([{"src": 0, "p0": 0.5}])})
    with pytest.raises(ValueError, match="'region_map'"):
        run({"projections": Const(["a->b"]), "guidance": Const({"a->b": GUIDANCE["0->1"]})})


def _grow(n_src, n_dst, pos, gd, rng=0, **params):
    t = Tissue.empty()
    t.add_cells(n_src + n_dst, positions=pos, region=np.repeat([0, 1], [n_src, n_dst]))
    params = {"guidance": Const({"0->1": gd}), **{k: Const(v) for k, v in params.items()}}
    return Stage(name="g", operator="grow_axons", params=params).run(t, {}, {}, np.random.default_rng(rng)).connectivity


def _edges(c):
    order = np.lexsort((c.post, c.pre))
    return np.stack([c.pre[order], c.post[order], c.weight[order], c.delay[order]])


def test_grow_axons_dense_and_sparse_paths_agree():
    # Every axon aims at the box centre (B = 0); one destination cell sits there, the others at the far corners:
    # p is exactly p0 = 1 at the centre and underflows to 0 elsewhere, so both paths form the same synapses.
    rng = np.random.default_rng(5)
    src = rng.uniform(0.0, 4.0, (30, 3))
    corners = np.array([[i, j, k] for i in (0, 4) for j in (0, 4) for k in (0, 4)], float)
    pos = np.vstack([src, corners + 10.0, [[12.0, 12.0, 12.0]]])
    gd = {"B": np.zeros((3, 3)).tolist(), "sigma": 0.01, "p0": 1.0, "w": 1.0}
    dense = _grow(30, 9, pos, gd, exact=True)
    sparse = _grow(30, 9, pos, gd, exact=False)
    auto = _grow(30, 9, pos, gd)
    assert len(dense.pre) == 30 and np.all(dense.post == 38)
    assert np.array_equal(_edges(dense), _edges(sparse))
    # below the threshold the default is the dense path, draw for draw
    gd2 = {"sigma": 0.2, "p0": 0.5, "w": 10.0}
    pos2 = rng.uniform(0.0, 1.0, (60, 3))
    assert np.array_equal(_edges(_grow(30, 30, pos2, gd2, rng=1)), _edges(_grow(30, 30, pos2, gd2, rng=1, exact=True)))
    assert np.array_equal(_edges(auto), _edges(dense))


def test_grow_axons_large_populations_stay_sparse():
    import tracemalloc
    from neurogenesis.stages.connectivity import DENSE_MAX_CELLS, EXACT_MAX_PAIRS
    n = DENSE_MAX_CELLS + 952  # 3000 per side: a dense float64 Ns x Nd array would take 72 MB
    pos = np.random.default_rng(2).uniform(0.0, 1.0, (2 * n, 3))
    gd = {"sigma": 0.01, "p0": 0.5, "w": 10.0}
    tracemalloc.start()
    try:
        c = _grow(n, n, pos, gd)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert len(c.pre) > 0
    assert peak < n * n * 8 / 8
    big = int(np.sqrt(EXACT_MAX_PAIRS)) + 1
    t = Tissue.empty()
    t.add_cells(2 * big, positions=np.zeros((2 * big, 3)), region=np.repeat([0, 1], big))
    stage = Stage(name="g", operator="grow_axons", params={"guidance": Const({"0->1": gd}), "exact": Const(True)})
    with pytest.raises(ValueError, match="exact=True"):
        stage.run(t, {}, {}, np.random.default_rng(0))
