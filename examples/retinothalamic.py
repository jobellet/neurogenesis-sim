"""Retina -> thalamic relay development, a toy after the mouse retina -> dLGN projection (E14-P14), in four conditions.

Pipeline (docs/STAGES.md; hypotheses written beforehand in docs/hypotheses/2026-11-02-retinothalamic.md):
  1. seed_cells + proliferate retinal progenitors; express one fate gene with lateral inhibition (Delta-Notch-like,
     Collier et al. 1996, J Theor Biol) and two graded genes read from analytic x / y gradient fields (EphA-like and
     EphB-like, McLaughlin & O'Leary 2005, Annu Rev Neurosci); differentiate RGCs (high fate gene), other retinal cells
     (another region, no projection), relay cells and relay interneurons.
  2. migrate (soft repulsion), mosaic (homotypic exclusion of RGCs; Galli-Resta et al. 1997, J Neurosci).
  3. grow_axons: an exuberant retina -> relay projection (broad sigma) whose target map gain per axis is the
     chemoaffinity gain (x: EphA / ephrin-A, y: EphB / ephrin-B); local interneuron -> relay projection.
  4. apoptosis: neurotrophic death of relay cells with too few retinal inputs.
  5. set_transmitters / express_receptors / assign_receptors / pharmacology in context "immature" (depolarising
     GABA-A, Ben-Ari 2002, Nat Rev Neurosci).
  6. refine_by_activity: stage-II-like propagating waves (Meister et al. 1991, Science) + STDP, several wave origins.
  7. pharmacology "mature", prune, scale (Turrigiano et al. 1998, Nature), myelinate, freeze.

Conditions: WT; b2KO (no waves, uncorrelated Poisson RGC firing; after McLaughlin et al. 2003, Neuron); TTX (no
spikes during refinement); EphAKO (x chemoaffinity gain 0; Feldheim et al. 2000, Neuron). Results hold in this
simulation only.

`--map-source expression` (hypotheses in docs/hypotheses/2026-11-03-retinothalamic-expression.md): the retina -> relay
target map is read from the EphA / EphB expression by the `expression_gradient` target rule instead of the matrix B
(B = 0 on x and y), and EphAKO sets the EphA gene to 0 in every cell (`express` knockout) instead of the gain.

    python examples/retinothalamic.py [--seeds 10] [--cpu] [--out example_out] [--small] [--map-source B|expression]
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

CONDITIONS = ("WT", "b2KO", "TTX", "EphAKO")
RET_C, RET_S = np.array([50.0, 50.0, 0.0]), np.array([100.0, 100.0, 2.0])      # retina box (space units)
REL_C, REL_S = np.array([50.0, 50.0, 40.0]), np.array([60.0, 60.0, 20.0])      # relay box, above the retina
RGC, OTHER, RELAY, INTER = 1, 2, 3, 4                                           # cell types
PROFILE = {
    "id": "retinothalamic",
    "transmitters": ["glutamate", "gaba"],
    "receptors": [
        {"name": "classic", "sign": "pre"},
        {"name": "ampa", "transmitter": "glutamate", "sign": 1},
        {"name": "gaba_a", "transmitter": "gaba", "sign": -1, "contexts": {"immature": {"sign": 1}}},
    ],
}


def condition_genome(cond, wave_ticks=300):
    """Genome of a condition: chemoaffinity gains per axis, wave and Poisson activity during refinement (b2KO: one
    spike per RGC per refinement window on average, as one wave gives, but uncorrelated)."""
    g = dict(epha_gain=1.0, ephb_gain=1.0, wave_amp=600.0, poisson_hz=0.0, activity=1.0)
    if cond == "EphAKO":
        g["epha_gain"] = 0.0
    elif cond == "b2KO":
        g.update(wave_amp=0.0, poisson_hz=1000.0 / wave_ticks)
    elif cond == "TTX":
        g.update(wave_amp=0.0, activity=0.0)
    elif cond != "WT":
        raise ValueError(cond)
    return g


def relay_frame(relay_mask=None):
    """(lower corner, size) of the relay's local box: the default box, or the bounding box of an atlas mask."""
    if relay_mask is None:
        return REL_C - REL_S / 2, REL_S
    from neurogenesis.geometry.voxel import VoxelMaskGeometry
    lo, hi = VoxelMaskGeometry.from_npz(str(relay_mask)).bounding_box()
    return np.asarray(lo, float), np.asarray(hi, float) - np.asarray(lo, float)


def volume_matched_box(relay_mask):
    """Return a box frame with the atlas mask's volume and the mask's bounding-box aspect ratio."""
    from neurogenesis.geometry.voxel import VoxelMaskGeometry
    geom = VoxelMaskGeometry.from_npz(str(relay_mask))
    lo, hi = geom.bounding_box()
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    size = hi - lo
    occupied = int(np.count_nonzero(geom.mask))
    if occupied == 0:
        raise ValueError("relay mask is empty")
    fraction = float(occupied) / geom.mask.size
    return (lo + hi) / 2, size * fraction ** (1.0 / 3.0)


MAP_SOURCES = ("B", "expression")


def build_project(cond="WT", seed=0, n_prog=60, n_relay=200, n_waves=4, wave_ticks=300, relay_mask=None,
                  relay_box=None, map_source="B"):
    """Project dict of one condition. Wave origins are drawn from `seed` here (example-level, deterministic).
    `relay_mask`: an .npz voxel geometry (examples/atlas_relay_mask.py) used as the relay's shape instead of the box.
    `map_source`: "B" (the gains in B carry the map) or "expression" (the `expression_gradient` rule reads the EphA /
    EphB genes; EphAKO knocks the EphA gene out)."""
    if map_source not in MAP_SOURCES:
        raise ValueError(map_source)
    if relay_mask is not None and relay_box is not None:
        raise ValueError("relay_mask and relay_box are mutually exclusive")
    rel_lo, rel_size = relay_frame(relay_mask) if relay_box is None else (
        np.asarray(relay_box["center"], float) - np.asarray(relay_box["size"], float) / 2,
        np.asarray(relay_box["size"], float))
    from neurogenesis.project.io import Project
    g = condition_genome(cond, wave_ticks)
    from_expr = map_source == "expression"
    if from_expr:
        g["epha_gain"] = 1.0                                   # the gene is expressed as in WT, then knocked out
    expr_names = dict(names=["fate", "EphA", "EphB"], knockout=["EphA"] if cond == "EphAKO" else []) if from_expr else {}
    if from_expr:
        retinal = dict(B=np.zeros((3, 3)).tolist(), rules_target=["expression_gradient"],
                       expression_gradient=[dict(gene="EphA", axis=0, gain=2.0), dict(gene="EphB", axis=1, gain=2.0)])
    else:
        retinal = dict(B=np.diag([2.0 * g["epha_gain"], 2.0 * g["ephb_gain"], 0.0]).tolist())
    gene = lambda name, hi: {"type": "Gene", "path": name, "lo": 0.0, "hi": hi}
    one = {"type": "Field", "name": "one"}
    sched = [
        dict(name="seed_retina", operator="seed_cells", params=dict(geometry="retina", N=n_prog, region=0)),
        dict(name="seed_relay", operator="seed_cells", params=dict(geometry="relay", N=n_relay, region=1, cell_type=RELAY)),
        dict(name="express_init", operator="express", params=dict(K=3, decay=1.0)),
        dict(name="proliferate", operator="proliferate", repeat=2,
             params=dict(prob={"type": "Expr", "formula": "1.0 * (region == 0)"}, jitter=3.0,
                         expression_noise=0.2)),
        # lateral inhibition on gene 0 (fate) + graded EphA (x) / EphB (y) genes from the analytic fields
        dict(name="express_fate", operator="express", repeat=6, params=dict(
            K=3, decay=1.0, dt=1.0, radius=12.0,
            weights=[[6.0, 0, 0], [0, 0, 0], [0, 0, 0]],
            neighbor_weights=[[-1.5, 0, 0], [0, 0, 0], [0, 0, 0]],
            morphogens=[{"field": one, "weights": [0.0, -3.0, -3.0]},
                        {"field": {"type": "Field", "name": "grad_x"}, "weights": [0.0, gene("epha_gain", 2.0), 0.0]},
                        {"field": {"type": "Field", "name": "grad_y"}, "weights": [0.0, 0.0, gene("ephb_gain", 2.0)]}],
            **expr_names)),
        dict(name="differentiate", operator="differentiate", params=dict(types=[
            dict(type_id=OTHER, condition="(region == 0) & (expr[0] <= 0.5)", region=2, sign=1, base_weight=300),
            dict(type_id=RGC, condition="(region == 0) & (expr[0] > 0.5)", sign=1, base_weight=300),
            dict(type_id=RELAY, condition="region == 1", sign=1, base_weight=300, refractory=5),
            dict(type_id=INTER, condition="(region == 1) & (cell_id % 5 == 0)", sign=-1, base_weight=300, refractory=5),
        ])),
        dict(name="migrate", operator="migrate", params=dict(steps=5, min_distance=2.0)),
        dict(name="mosaic", operator="mosaic", params=dict(radius=12.0, steps=60, rate=0.5, types=[RGC])),
        dict(name="grow_axons", operator="grow_axons", params=dict(
            projections=["0->1", "1->1"], conduction_velocity=8.0, w_clip=2047, exact=True,
            bounds_min={"0": (RET_C - RET_S / 2).tolist(), "1": rel_lo.tolist()},
            bounds_size={"0": RET_S.tolist(), "1": rel_size.tolist()},
            rules_probability=["no_autapse"],
            guidance={
                "0->1": dict(retinal, sigma=0.3, p0=0.6, w=250.0),
                "1->1": dict(B=np.diag([2.0, 2.0, 0.0]).tolist(), sigma=0.1, p0=0.3, w=60.0, source="inh",
                             rules_probability=["no_autapse", "source_sign"])})),
        dict(name="apoptosis", operator="apoptosis", params=dict(min_inputs={"type": "Field", "name": "trophic_need"})),
        dict(name="set_transmitters", operator="set_transmitters", params=dict(profile=PROFILE, rules=[
            dict(condition="sign > 0", transmitters=["glutamate"]), dict(condition="sign < 0", transmitters=["gaba"])])),
        dict(name="express_receptors", operator="express_receptors", params=dict(profile=PROFILE, rules=[
            dict(condition="region == 1", receptor="ampa", level=1.0),
            dict(condition="region == 1", receptor="gaba_a", level=1.0)])),
        dict(name="assign_receptors", operator="assign_receptors", params=dict(profile=PROFILE, mode="max")),
        dict(name="gaba_immature", operator="pharmacology", params=dict(profile=PROFILE, context="immature")),
    ]
    if g["activity"] > 0:
        rng = np.random.default_rng([seed, 2026])
        for k in range(n_waves):
            origin = (RET_C + (rng.random(3) - 0.5) * RET_S * np.array([1, 1, 0])).tolist()
            refine = dict(rule="stdp", ticks=wave_ticks, A_plus=20.0, A_minus=21.0, w_min=0.0, w_max=1000.0,
                          restore_modes=True)
            if g["wave_amp"] > 0:
                refine["waves"] = dict(sources=[origin], speed=0.4, interval=wave_ticks, duration=1,
                                       amplitude=gene("wave_amp", 2000.0), cells={"region": [0]})   # retina only
            else:
                ids = list(range(n_prog)) + list(range(n_prog + n_relay, n_prog + n_relay + 4 * n_prog))   # retinal ids
                refine.update(sources=ids, poisson_hz=gene("poisson_hz", 100.0))
            sched.append(dict(name=f"refine_{k}", operator="refine_by_activity", params=refine))
    sched += [
        dict(name="gaba_mature", operator="pharmacology", params=dict(profile=PROFILE, context="mature")),
        dict(name="scale", operator="scale", params=dict(target=1500.0)),
        dict(name="prune", operator="prune", params=dict(threshold=150)),
        dict(name="myelinate", operator="myelinate", params=dict(factor=0.5, pre_region=[0])),
        dict(name="freeze", operator="freeze", params=dict(dale=True)),
    ]
    fields = {
        "one": {"type": "AnalyticField", "expr": "1.0 + 0.0 * x"},
        "grad_x": {"type": "AnalyticField", "expr": f"(x - {RET_C[0] - RET_S[0] / 2}) / {RET_S[0]}"},
        "grad_y": {"type": "AnalyticField", "expr": f"(y - {RET_C[1] - RET_S[1] / 2}) / {RET_S[1]}"},
        "trophic_need": {"type": "AnalyticField", "expr": "3.0 * (z > 20.0)"},
    }
    geometry = {"retina": {"type": "Box", "center": RET_C.tolist(), "size": RET_S.tolist()},
                "relay": ({"type": "Box", "center": REL_C.tolist(), "size": REL_S.tolist()} if relay_mask is None
                          else {"type": "voxel_mask", "npz": str(relay_mask)})}
    if relay_box is not None:
        geometry["relay"] = {"type": "Box", "center": list(relay_box["center"]), "size": list(relay_box["size"])}
    return Project(geometry=geometry, fields=fields, genome=g, schedule=sched, pharmacology=PROFILE,
                   metadata=dict(name=f"retinothalamic {cond}", description="toy retina -> relay development"))


def _pearson(a, b):
    a, b = a - a.mean(), b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else 0.0


def measure(tissue, n_stim_ticks=50, relay_mask=None, relay_box=None):
    """Metrics of one grown tissue (vectorised over synapses): mosaic regularity, map correlations and error, and the
    evoked separation of two opposite retinal corners in the relay (1 - cosine similarity of relay spike counts)."""
    from neurogenesis.analysis import nearest_neighbour_regularity
    from neurogenesis.spiking.batch import simulate_counts
    ct, pos = tissue.cell_type, tissue.positions
    rgc, relay = np.flatnonzero(ct == RGC), np.flatnonzero(ct == RELAY)
    u_ret = (pos[:, :2] - (RET_C - RET_S / 2)[:2]) / RET_S[:2]
    if relay_box is None:
        rel_lo, rel_size = relay_frame(relay_mask)
    else:
        rel_lo = np.asarray(relay_box["center"], float) - np.asarray(relay_box["size"], float) / 2
        rel_size = np.asarray(relay_box["size"], float)
    u_rel = (pos[:, :2] - rel_lo[:2]) / rel_size[:2]
    c = tissue.connectivity
    m = (ct[c.pre] == RGC) & (ct[c.post] == RELAY) & (c.weight != 0)
    pre, post, w = c.pre[m], c.post[m], np.abs(c.weight[m]).astype(float)
    N = len(ct)
    wsum = np.bincount(pre, w, N)
    cen = np.stack([np.bincount(pre, w * u_rel[post, k], N) for k in (0, 1)], 1) / np.maximum(wsum, 1e-12)[:, None]
    has = rgc[wsum[rgc] > 0]
    ideal = 1.0 / (1.0 + np.exp(-4.0 * (u_ret[has] - 0.5) * 2.0))                # WT chemoaffinity target point
    err = float(np.linalg.norm(cen[has] - ideal, axis=1).mean()) if len(has) else float("nan")
    if relay_mask is None:
        feasible = ideal
    else:
        from neurogenesis.geometry.voxel import VoxelMaskGeometry
        geom = VoxelMaskGeometry.from_npz(str(relay_mask))
        occupied_xy = np.argwhere(np.any(geom.mask, axis=2))
        # Use the projection of occupied voxel centres: a target is compared with the closest
        # 2D location available anywhere through the relay's depth.
        attainable = (occupied_xy + 0.5) / np.asarray(geom.mask.shape[:2], float)
        feasible = np.empty_like(ideal)
        for start in range(0, len(ideal), 64):
            target = ideal[start:start + 64]
            d2 = ((target[:, None, :] - attainable[None, :, :]) ** 2).sum(axis=2)
            feasible[start:start + len(target)] = attainable[np.argmin(d2, axis=1)]
    feasible_err = float(np.linalg.norm(cen[has] - feasible, axis=1).mean()) if len(has) else float("nan")
    net = tissue.to_network()
    for n in net.neurons:
        n.mode = 0                                                             # b2KO Poisson drivers off for the test
    ext = np.zeros((2, N), np.int32)
    ext[0, rgc[(u_ret[rgc] < 0.25).all(1)]] = 400
    ext[1, rgc[(u_ret[rgc] > 0.75).all(1)]] = 400
    counts = simulate_counts([net], [ext], ticks=n_stim_ticks, blank=40)[0][:, relay].astype(float)
    nrm = np.linalg.norm(counts, axis=1)
    sep = float(1.0 - counts[0] @ counts[1] / (nrm[0] * nrm[1])) if nrm.min() > 0 else float("nan")
    return dict(mosaic_nnri=nearest_neighbour_regularity(pos[rgc, :2]), r_x=_pearson(u_ret[has, 0], cen[has, 0]),
                r_y=_pearson(u_ret[has, 1], cen[has, 1]), topo_error=err, topo_error_feasible=feasible_err,
                separation=sep, n_rgc=int(len(rgc)),
                n_relay=int(len(relay)), n_retinal_synapses=int(m.sum()), relay_spikes=counts.sum(1).tolist())



STEP_MAP = {
    "proliferate": ["seed_retina", "seed_relay", "express_init", "proliferate"],
    "express": ["express_fate"],
    "differentiate": ["differentiate"],
    "migrate": ["migrate"],
    "mosaic": ["mosaic"],
    "grow_axons": ["grow_axons"],
    "apoptosis": ["apoptosis"],
    "pharmacology_immature": ["set_transmitters", "express_receptors", "assign_receptors", "gaba_immature"],
    "refine_by_activity": ["refine_0", "refine_1", "refine_2", "refine_3"],
    "scale": ["gaba_mature", "scale"],
    "prune": ["prune"],
    "freeze": ["myelinate", "freeze"],
}
STEP_ORDER = [
    "start",
    "proliferate",
    "express",
    "differentiate",
    "migrate",
    "mosaic",
    "grow_axons",
    "apoptosis",
    "pharmacology_immature",
    "refine_by_activity",
    "scale",
    "prune",
    "freeze",
]


def save_checkpoint(tissue, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if str(path).endswith(".json"):
        net = tissue.to_network()
        net.save_json(path)
        return
    from neurogenesis.bridge.ngb import write_network
    net = tissue.to_network()
    exts = {}
    N = len(tissue.alive)
    if getattr(tissue, "cell_type", None) is not None and len(tissue.cell_type) == N:
        exts["cell_type"] = ("neuron", np.asarray(tissue.cell_type, dtype="<i4"))
    if getattr(tissue, "region", None) is not None and len(tissue.region) == N:
        exts["region"] = ("neuron", np.asarray(tissue.region, dtype="<i4"))
    if getattr(tissue, "sign", None) is not None and len(tissue.sign) == N:
        exts["sign"] = ("neuron", np.asarray(tissue.sign, dtype="<i1"))
    if getattr(tissue, "expression", None) is not None and len(tissue.expression) == N:
        exts["expression"] = ("neuron", np.asarray(tissue.expression, dtype="<f4"))
    write_network(net, path, extensions=exts)


def load_checkpoint(path):
    path = Path(path)
    if str(path).endswith(".json"):
        from neurogenesis.spiking.network import SNNNetwork
        from neurogenesis.tissue import Tissue
        net = SNNNetwork.load_json(path)
        return Tissue.from_network(net)
    from neurogenesis.bridge.ngb import read_network, read_extensions
    from neurogenesis.tissue import Tissue
    net = read_network(path)
    exts = read_extensions(path)
    t = Tissue.from_network(net)
    for name, (axis, arr) in exts.items():
        setattr(t, name, np.array(arr, copy=True))
    return t


def run_stages_slice(p, seed, tissue=None, from_stage=None, until_stage=None):
    import zlib
    from neurogenesis.stages.base import Stage, _instantiate_fields
    from neurogenesis.params import param_from_dict
    from neurogenesis.fields import Field
    from neurogenesis.tissue import Tissue

    sched = p.to_dict()["schedule"]
    raw_geoms = p.to_dict().get("geometry", {})
    raw_fields = p.to_dict().get("fields", {})
    fields = _instantiate_fields({**raw_geoms, **raw_fields})
    fields = {k: (v.bind(p.genome) if isinstance(v, Field) else v) for k, v in fields.items()}

    from_idx = STEP_ORDER.index(from_stage) if from_stage in STEP_ORDER else 0
    until_idx = STEP_ORDER.index(until_stage) if until_stage in STEP_ORDER else len(STEP_ORDER) - 1

    active_stage_names = []
    for s_idx in range(from_idx + 1, until_idx + 1):
        step_name = STEP_ORDER[s_idx]
        active_stage_names.extend(STEP_MAP.get(step_name, [step_name]))

    if tissue is None:
        tissue = Tissue.empty()

    for config in sched:
        st_name = config["name"]
        if st_name not in active_stage_names:
            continue
        name_salt = zlib.crc32(st_name.encode("utf-8")) & 0xFFFFFFFF
        params = {k: (param_from_dict(v) if isinstance(v, dict) else v) for k, v in config.get("params", {}).items()}
        st = Stage(name=st_name, operator=config["operator"], params=params, repeat=config.get("repeat", 1))
        for rep in range(st.repeat):
            rng = np.random.default_rng([seed, name_salt, rep])
            tissue = st.run(tissue, p.genome, fields, rng, rep=rep)
    return tissue


def run(seeds, small=False, conditions=CONDITIONS, relay_mask=None, relay_box=None, map_source="B"):
    from neurogenesis.stages.base import run_schedule
    kw = dict(n_prog=45, n_relay=100, n_waves=2, wave_ticks=250) if small else {}
    out = {}
    for cond in conditions:
        rows = []
        for s in seeds:
            p = build_project(cond, s, relay_mask=relay_mask, relay_box=relay_box, map_source=map_source, **kw)
            rows.append(measure(run_schedule(p.to_dict(), p.genome, s), relay_mask=relay_mask, relay_box=relay_box))
        out[cond] = rows
    return out


def summary(results):
    keys = ("mosaic_nnri", "r_x", "r_y", "topo_error", "topo_error_feasible", "separation")
    return {c: {k: [float(np.mean([r[k] for r in rows])), float(np.std([r[k] for r in rows], ddof=1)) if len(rows) > 1
                    else 0.0] for k in keys} for c, rows in results.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0, help="single seed for stage slice execution")
    ap.add_argument("--condition", default="WT", choices=CONDITIONS)
    ap.add_argument("--out", default="example_out")
    ap.add_argument("--cpu", action="store_true")
    ap.add_argument("--small", action="store_true", help="small tissue for tests")
    ap.add_argument("--relay-mask", help="relay shape from an atlas (.npz from examples/atlas_relay_mask.py)")
    ap.add_argument("--compare-matched-box", action="store_true",
                    help="also run a box with the atlas mask's volume and bounding-box aspect ratio")
    ap.add_argument("--map-source", choices=MAP_SOURCES, default="B",
                    help="B: target map from the gains in B (runs 1-4); expression: from the EphA / EphB expression")
    ap.add_argument("--from-stage", help="start stage for stage slicing")
    ap.add_argument("--until-stage", help="end stage for stage slicing")
    ap.add_argument("--in", dest="in_file", help="input checkpoint file (.ngb or .json)")
    args = ap.parse_args()
    if args.cpu:
        os.environ["JAX_PLATFORMS"] = "cpu"

    if args.until_stage is not None or args.from_stage is not None:
        p = build_project(args.condition, args.seed, relay_mask=args.relay_mask, map_source=args.map_source,
                          **({"n_prog": 45, "n_relay": 100, "n_waves": 2, "wave_ticks": 250} if args.small else {}))
        tissue = load_checkpoint(args.in_file) if args.in_file else None
        tissue = run_stages_slice(p, args.seed, tissue=tissue, from_stage=args.from_stage, until_stage=args.until_stage)
        save_checkpoint(tissue, args.out)
        print(f"saved checkpoint {args.out} (from {args.from_stage} to {args.until_stage}): {len(tissue.alive)} cells, {len(tissue.connectivity.pre)} synapses")
        return

    res = run(range(args.seeds), small=args.small, relay_mask=args.relay_mask, map_source=args.map_source)
    summ = summary(res)
    print(f"{'condition':9s} " + " ".join(f"{k:>18s}" for k in next(iter(summ.values()))))
    for c, row in summ.items():
        print(f"{c:9s} " + " ".join(f"{m:8.3f} +- {s:6.3f}" for m, s in row.values()))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    p = build_project("WT", 0, relay_mask=args.relay_mask, map_source=args.map_source)
    p.save(out / "project.json")
    stats = dict(seeds=args.seeds, small=args.small, map_source=args.map_source, summary=summ, per_seed=res)
    if args.compare_matched_box:
        if not args.relay_mask:
            ap.error("--compare-matched-box requires --relay-mask")
        center, size = volume_matched_box(args.relay_mask)
        box = dict(center=center.tolist(), size=size.tolist())
        box_results = run(range(args.seeds), small=args.small, relay_box=box, map_source=args.map_source)
        stats["matched_box"] = dict(center=box["center"], size=box["size"],
                                    summary=summary(box_results), per_seed=box_results)
    (out / "stats.json").write_text(json.dumps(stats, indent=1))
    print("wrote", out / "stats.json")


if __name__ == "__main__":
    main()
