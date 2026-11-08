"""The front-page playground: its JavaScript port (docs/_static/ngjs/ng-core.js) equals the Python toolbox where it
claims to (lif_int spikes, gene coding, seeds_of, coactivity, competitive elimination), is deterministic, and its
evolution improves the founder within a few generations; the Python example of the front page runs (needs node)."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from neurogenesis.evolution.islands import seeds_of
from neurogenesis.genome.genes import from_unit, to_unit
from neurogenesis.spiking import SNNNetwork
from neurogenesis.spiking.morphology import MorphogeneticEngine
from neurogenesis.spiking.reference import IntegerSNNSimulator
from neurogenesis.stages.base import STAGE_REGISTRY
from neurogenesis.stages.refinement import coactivity
from neurogenesis.tissue import SparseConnectivity, Tissue

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scripts" / "js" / "check_ngjs.cjs"
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def _js(cmd, spec, tmp_path, *args):
    f = tmp_path / f"{cmd}.json"
    f.write_text(json.dumps(spec))
    out = subprocess.run(["node", str(HARNESS), cmd, str(f), *map(str, args)], capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def _network(seed, long_delays):
    net = MorphogeneticEngine.generate_cortical_column(150, seed=seed, weight_scale=0.25, refractory=3)
    rng = np.random.default_rng(seed)
    for n in net.neurons:
        n.threshold = int(rng.integers(500, 1900))
    for n in net.neurons[:6]:
        n.mode, n.burst_period, n.burst_duty = 2, int(rng.integers(30, 90)), 12
    if long_delays:
        for s in net.synapses[::7]:
            s.delay = int(rng.integers(32, 120))
    return net


@needs_node
@pytest.mark.parametrize("seed, long_delays", [(8, False), (11, True)])
def test_js_kernel_equals_reference(tmp_path, seed, long_delays):
    """Same spikes, tick by tick, as IntegerSNNSimulator (Poisson drivers, bursters, refractory, multi-word delays)."""
    f = tmp_path / "net.json"
    _network(seed, long_delays).save_json(f)
    sim = IntegerSNNSimulator(SNNNetwork.load_json(f))
    sim.run(300)
    assert len(sim.spike_history) > 50 and (sim.W > 1) == long_delays
    py = "\n".join(f"{t} {i}" for t, i in sim.spike_history)
    out = subprocess.run(["node", str(HARNESS), "kernel", str(f), "300"], capture_output=True, text=True, cwd=ROOT)
    assert out.stdout.strip() == py


@needs_node
def test_js_gene_coding_equals_python(tmp_path):
    genome = {"count": {"map": 10}, "guidance": {"B": [[0.0, 0.0], [0.0, 0.0]], "sigma": 0.1}, "w": 5.0}
    genes = [(("count", "map"), 0, 100), (("guidance", "B", 0, 1), -2.0, 2.0), (("guidance", "sigma"), 0.02, 0.5),
             (("w",), 0.0, 10.0)]
    u = [0.333, 0.75, 1.2, -0.1]
    py = from_unit(genome, genes, u)
    js = json.loads(_js("genes", {"genome": genome, "genes": [[list(p), lo, hi] for p, lo, hi in genes], "u": u}, tmp_path))
    assert js["genome"]["count"]["map"] == py["count"]["map"] == 33
    assert np.allclose(js["genome"]["guidance"]["B"], np.asarray(py["guidance"]["B"]))
    assert js["genome"]["guidance"]["sigma"] == pytest.approx(py["guidance"]["sigma"])
    assert js["genome"]["w"] == pytest.approx(py["w"])
    assert np.allclose(js["unit"], to_unit(py, genes))


@needs_node
def test_js_seeds_of_equals_python(tmp_path):
    for island, gen, n in [(0, 0, 2), (3, 17, 4)]:
        assert json.loads(_js("seeds", {"island": island, "generation": gen, "n": n}, tmp_path)) == list(
            seeds_of(island, gen, n))


@needs_node
def test_js_coactivity_and_competition_equal_python(tmp_path):
    rng = np.random.default_rng(5)
    T, N = 80, 8
    spikes = (rng.random((T, N)) < 0.15).astype(np.uint8)
    pairs = [(i, j) for i in range(N) for j in range(N) if i != j and rng.random() < 0.45]
    pre = np.array([p for p, _ in pairs], np.int32)
    post = np.array([q for _, q in pairs], np.int32)
    delay = rng.integers(1, 6, len(pairs)).astype(np.int32)
    js = json.loads(_js("coact", {"spikes": spikes.tolist(), "pre": pre.tolist(), "post": post.tolist(),
                                  "delay": delay.tolist(), "window": 4, "fraction": 0.6}, tmp_path))
    assert js["score"] == coactivity(spikes, pre, post, delay, 4).tolist()
    t = Tissue.empty()
    t.add_cells(N, positions=np.zeros((N, 3)))
    t.connectivity = SparseConnectivity(pre, post, np.full(len(pre), 50, np.int32), delay)
    out = STAGE_REGISTRY["competitive_elimination"]().run(
        t, {"spikes": spikes, "fraction": 0.6, "window": 4, "remove": True}, {}, {}, np.random.default_rng(0))
    kept_py = set(zip(out.connectivity.pre.tolist(), out.connectivity.post.tolist()))
    kept_js = {pairs[s] for s, lost in enumerate(js["lose"]) if not lost}
    assert 0 < len(kept_js) < len(pairs) and kept_js == kept_py


@needs_node
def test_js_evolution_is_deterministic_and_improves_in_few_generations(tmp_path):
    """Best-offspring selection lifts the held-out fitness of the founder (about 0.01) within ten generations."""
    r = json.loads(_js("evolve", {"island": 0, "generations": 10, "lambda": 10}, tmp_path))
    assert r["identical"]
    val = [h["validation"] for h in r["history"]]
    assert r["founder"] < 0.05
    assert max(val[-5:]) > 0.2 and np.mean(val[-5:]) > r["founder"] + 0.1


def test_front_page_python_example_runs():
    """The Python example of docs/index.md runs and its evolution reduces the decoding error."""
    text = (ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    code = re.search(r"## The same idea in Python.*?```python\n(.*?)```", text, re.S).group(1)
    ns = {}
    exec(compile(code, "docs/index.md", "exec"), ns)
    best = [h["best"] for h in ns["history"]]
    assert max(best[1:]) > best[0]
