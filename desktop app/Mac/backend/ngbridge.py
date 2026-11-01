"""Bridge between the Neurogenesis desktop app and the neurogenesis toolbox: JSON lines over stdin / stdout.

Request  {"id": 7, "method": "grow", "params": {...}}
Reply    {"id": 7, "result": {...}}  or  {"id": 7, "error": "message", "trace": "..."}
Event    {"event": "progress", "job": 7, "data": {...}}       (long jobs: evolution)

Networks travel as binary files (format NGB1, see write_network) in a temporary directory, not as JSON, so that large
networks load in milliseconds. Every feature of the roadmap is probed at run time (method "capabilities"): what other
contributors merge lights up in the app without changing it. Library prints go to stderr; stdout carries only replies.

The toolbox is imported from NEUROGENESIS_REPO (set by the app; default: the checkout this file lives in).
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import json
import os
import struct
import sys
import tempfile
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(os.environ.get("NEUROGENESIS_REPO") or Path(__file__).resolve().parents[3])
sys.path.insert(0, str(REPO))
os.environ.setdefault("JAX_PLATFORMS", "cpu")

_OUT = sys.stdout
sys.stdout = sys.stderr
_LOCK = threading.Lock()
TMP = Path(tempfile.mkdtemp(prefix="ngbridge-"))
_COUNTER = [0]

import numpy as np  # noqa: E402

NEURON_I32 = ("mode", "shift_v", "shift_s", "base_weight", "burst_period", "burst_duty", "refractory", "role",
              "compartment", "threshold")
NEURON_F64 = ("poisson_hz", "conn_radius", "conn_prob")


def send(obj):
    line = json.dumps(obj, default=_json_default)
    with _LOCK:
        _OUT.write(line + "\n")
        _OUT.flush()


def _json_default(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, (tuple, set)):
        return list(o)
    if isinstance(o, Path):
        return str(o)
    return repr(o)


def _jsonable(x):
    return json.loads(json.dumps(x, default=_json_default))


def _tmpfile(suffix):
    _COUNTER[0] += 1
    return TMP / f"n{_COUNTER[0]}{suffix}"


# ---------------------------------------------------------------------------------------------------------- networks
def write_network(net, path=None, extra=None):
    """NGB1: magic, N, E, 0 (int32); positions (N, 3) f64; directions (N, 3) f64; NEURON_I32 fields (N,) i32 each;
    NEURON_F64 fields (N,) f64 each; pre, post, weight, delay (E,) i32 each. Little endian. Float64 keeps the Poisson
    thresholds and distances exactly as in Python."""
    path = Path(path or _tmpfile(".ngb"))
    ns, ss = net.neurons, net.synapses
    N, E = len(ns), len(ss)
    with open(path, "wb") as f:
        f.write(b"NGB1" + struct.pack("<iii", N, E, 0))
        f.write(np.asarray([(n.x, n.y, n.z) for n in ns], "<f8").reshape(N, 3).tobytes())
        f.write(np.asarray([(n.dir_x, n.dir_y, n.dir_z) for n in ns], "<f8").reshape(N, 3).tobytes())
        for a in NEURON_I32:
            f.write(np.asarray([getattr(n, a) for n in ns], "<i4").tobytes())
        for a in NEURON_F64:
            f.write(np.asarray([getattr(n, a) for n in ns], "<f8").tobytes())
        for a in ("pre", "post", "weight", "delay"):
            f.write(np.asarray([getattr(s, a) for s in ss], "<i4").tobytes())
    out = dict(path=str(path), neurons=N, synapses=E, morphology=net.morphology)
    if extra:
        out.update(extra)
    return out


def read_network(path):
    from neurogenesis.spiking.network import NeuronData, SNNNetwork, SynapseData
    b = Path(path).read_bytes()
    assert b[:4] == b"NGB1", "not an NGB1 network file"
    N, E, _ = struct.unpack("<iii", b[4:16])
    o = 16

    def take(dt, n):
        nonlocal o
        a = np.frombuffer(b, dt, n, o)
        o += a.nbytes
        return a
    pos = take("<f8", 3 * N).reshape(N, 3)
    dirs = take("<f8", 3 * N).reshape(N, 3)
    ints = {a: take("<i4", N) for a in NEURON_I32}
    flts = {a: take("<f8", N) for a in NEURON_F64}
    syn = {a: take("<i4", E) for a in ("pre", "post", "weight", "delay")}
    neurons = [NeuronData(id=i, x=float(pos[i, 0]), y=float(pos[i, 1]), z=float(pos[i, 2]), dir_x=float(dirs[i, 0]),
                          dir_y=float(dirs[i, 1]), dir_z=float(dirs[i, 2]),
                          **{a: int(ints[a][i]) for a in NEURON_I32}, **{a: float(flts[a][i]) for a in NEURON_F64})
               for i in range(N)]
    synapses = [SynapseData(int(p), int(q), int(w), int(d)) for p, q, w, d in zip(syn["pre"], syn["post"], syn["weight"], syn["delay"])]
    return SNNNetwork(morphology="Desktop", neurons=neurons, synapses=synapses)


# ---------------------------------------------------------------------------------------------------- capabilities
def _has(module, attr=None):
    try:
        if importlib.util.find_spec(module) is None:
            return False
        m = importlib.import_module(module)
        return attr is None or hasattr(m, attr)
    except Exception:
        return False


def _any(*mods):
    return any(_has(*m) if isinstance(m, tuple) else _has(m) for m in mods)


def stage_registry():
    """The registered developmental stages (task A4), as {name: object}, or None while A4 is not merged."""
    for mod in ("neurogenesis.stages", "neurogenesis.stages.base"):
        if not _has(mod):
            continue
        m = importlib.import_module(mod)
        for attr in ("STAGES", "REGISTRY", "STAGE_REGISTRY", "_STAGE_REGISTRY", "_REGISTRY", "stage_registry", "registry"):
            reg = getattr(m, attr, None)
            if callable(reg) and not isinstance(reg, dict):
                try:
                    reg = reg()
                except Exception:
                    reg = None
            if isinstance(reg, dict):
                return reg
    return None


STAGE_TASKS = [("C1", "seed_cells"), ("C2", "proliferate"), ("C3", "apoptosis"), ("C4", "migrate"), ("C5", "sort"),
               ("C5", "mosaic"), ("C6", "express"), ("C7", "differentiate"), ("C8", "grow_axons"), ("C9", "place_by_hand"),
               ("C9", "connect_by_hand"), ("C10", "prune"), ("C10", "scale"), ("C11", "refine_by_activity"),
               ("C12", "myelinate"), ("C13", "freeze")]


def m_capabilities(p):
    """Every roadmap task with whether its code is present in this checkout."""
    reg = stage_registry()
    stages = set(reg or {})
    T = [
        ("A1", "Project schema and I/O", _has("neurogenesis.project.io", "Project")),
        ("A2", "Tissue state", _has("neurogenesis.tissue", "Tissue")),
        ("A3", "Param sources", _has("neurogenesis.params")),
        ("A4", "Stages and scheduler", reg is not None),
        ("A5", "Legacy compiler", _any("neurogenesis.stages.legacy", "neurogenesis.development.legacy", "neurogenesis.compiler")),
        ("B1", "Geometry primitives", _has("neurogenesis.geometry", "Box")),
        ("B2", "Meshes and voxel masks", _any("neurogenesis.geometry.mesh", "neurogenesis.geometry.meshes", "neurogenesis.geometry.voxel")),
        ("B3", "Scalar, vector, label fields", _has("neurogenesis.fields")),
        ("B4", "Point patterns and maps", _any("neurogenesis.fields.patterns", "neurogenesis.fields.points", "neurogenesis.fields.maps")),
        ("B5", "Field operations", _any("neurogenesis.fields.ops", "neurogenesis.fields.operations")),
    ]
    for task, name in STAGE_TASKS:
        T.append((task, f"Stage {name}", name in stages))
    T += [
        ("D1", "Cell lists / spatial hash", _has("neurogenesis.spatial", "CellList")),
        ("D2", "Sparse guidance", _any("neurogenesis.development.sparse", ("neurogenesis.development.grow", "sparse_guidance"))),
        ("D3", "Development cost model", _any(("neurogenesis.cost", "estimate_project"), ("neurogenesis.cost", "stage_cost"),
                                              ("neurogenesis.stages.base", "schedule_cost"))),
        ("D4", "Chunked growth", _any("neurogenesis.development.chunked", "neurogenesis.chunked")),
        ("E1", "Plasticity", _has("neurogenesis.spiking.plasticity", "STDPRule")),
        ("E2", "Supervised fitting", _any("neurogenesis.fitting", "neurogenesis.fit", "neurogenesis.optim")),
        ("E3", "Semi-supervised workflows", _any("neurogenesis.evolution.semi", "neurogenesis.evolution.pareto")),
        ("E4", "Validation harness", _any("neurogenesis.validation", "neurogenesis.validate")),
        ("F7", "Bridge server", _any("neurogenesis.serve", "neurogenesis.server")),
        ("G1", "Module registry", _any("neurogenesis.modules.registry", "neurogenesis.registry")),
        ("core", "Spiking kernel and models", _has("neurogenesis.spiking.models", "MODELS")),
        ("core", "Body plans and growth", _has("neurogenesis.development", "grow")),
        ("core", "Evolution", _has("neurogenesis.evolution", "evolve")),
        ("core", "Modules", _has("neurogenesis.modules", "Module")),
        ("core", "Cost estimates", _has("neurogenesis.cost", "estimate")),
    ]
    import platform
    return dict(tasks=[dict(task=t, name=n, available=bool(a)) for t, n, a in T], python=sys.version.split()[0],
                executable=sys.executable, repo=str(REPO), platform=platform.platform())


# ------------------------------------------------------------------------------------------------ network sources
def m_load_network(p):
    from neurogenesis.spiking.network import SNNNetwork
    return write_network(SNNNetwork.load_json(p["path"]))


def m_save_network(p):
    net = read_network(p["ngb"])
    net.morphology = p.get("morphology", net.morphology)
    net.save_json(p["path"])
    return dict(path=p["path"])


def m_generate(p):
    from neurogenesis.spiking.morphology import MorphogeneticEngine as M
    kind = p.get("morphology", "column")
    n, seed = int(p.get("neurons", 500)), int(p.get("seed", 42))
    cv = float(p.get("conduction_velocity", 4.0))
    if kind == "layered":
        net = M.generate_layered_network(num_neurons=n, num_layers=int(p.get("layers", 4)), conduction_velocity=cv, seed=seed)
    elif kind == "microcircuit":
        net = M.generate_microcircuit(num_neurons=n, conduction_velocity=cv, seed=seed)
    else:
        net = M.generate_cortical_column(num_neurons=n, radius=float(p.get("radius", 30)), height=float(p.get("height", 150)),
                                         exc_ratio=float(p.get("exc_ratio", 0.8)), pace_ratio=float(p.get("pace_ratio", 0.05)),
                                         conduction_velocity=cv, seed=seed, weight_scale=float(p.get("weight_scale", 1.0)),
                                         inh_scale=float(p.get("inh_scale", 1.0)), refractory=int(p.get("refractory", 0)))
    return write_network(net)


def m_wire(p):
    """Rewire a network by distance (MorphogeneticEngine.wire_network: each neuron's radius, probability, weight)."""
    from neurogenesis.spiking.morphology import MorphogeneticEngine as M
    net = read_network(p["ngb"])
    sig = inspect.signature(M.wire_network).parameters
    kw = {k: v for k, v in dict(seed=int(p.get("seed", 0)), conduction_velocity=float(p.get("conduction_velocity", 4.0))).items()
          if k in sig}
    out = M.wire_network(net, **kw)
    return write_network(out if out is not None else net)


def m_stats(p):
    return _jsonable(read_network(p["ngb"]).compute_statistics())


# --------------------------------------------------------------------------------------------- plans and genomes
def _plan(d):
    from neurogenesis.development import BodyPlan
    return BodyPlan.from_dict(d)


def _genome(d):
    from neurogenesis.genome.io import from_json
    return from_json(d or {})


def m_plan_defaults(p):
    """Genome completed with neutral defaults for every region and projection of the plan (existing genes kept)."""
    from neurogenesis.genome.io import to_json
    plan, g = _plan(p["plan"]), _genome(p.get("genome"))
    g.setdefault("inh_weight_factor", 2.0)
    for r in plan.regions:
        if r.grown:
            g.setdefault("count", {}).setdefault(r.name, 60)
            g.setdefault("migration", {}).setdefault(r.name, dict(mean=np.full(3, 0.5), spread=0.3))
            g.setdefault("inhibitory", {}).setdefault(r.name, dict(a0=-1.4, a=np.zeros(3)))
            g.setdefault("excitability", {}).setdefault(r.name, dict(shift_v=5, shift_s=4))
    for pr in plan.projections:
        g.setdefault("guidance", {}).setdefault(tuple(pr), dict(B=np.eye(3), c=np.zeros(3), sigma=0.3, p0=0.5, w=100.0))
    return dict(genome=to_json(g))


def _network_extra(plan):
    names = {v: k for k, v in plan.ids.items()}
    return dict(regions=[names.get(i, str(i)) for i in range(max(plan.ids.values(), default=-1) + 1)])


def m_grow(p):
    from neurogenesis.development import grow
    plan, g = _plan(p["plan"]), _genome(p.get("genome"))
    prs = [tuple(x) for x in p["projections"]] if p.get("projections") is not None else None
    net = grow(plan, g, int(p.get("seed", 0)), projections=prs)
    net.morphology = plan.name
    return write_network(net, extra=_network_extra(plan))


def m_grow_steps(p):
    """Development checkpoints of the legacy growth (until A4 checkpoints exist): placement, signs, differentiation and
    identity first, then one checkpoint per projection in growth order. The single random stream is consumed in this
    order, so each checkpoint is exactly the network grown so far (a prefix of the final synapses)."""
    from neurogenesis.development import grow
    plan, g, seed = _plan(p["plan"]), _genome(p.get("genome")), int(p.get("seed", 0))
    steps = [("placement, sign, differentiation, identity", [])]
    for k, pr in enumerate(plan.projections):
        steps.append((f"axon growth {pr[0]} → {pr[1]}", plan.projections[:k + 1]))
    out = []
    for label, prs in steps:
        net = grow(plan, g, seed, projections=prs)
        net.morphology = plan.name
        out.append(dict(label=label, **write_network(net, extra=_network_extra(plan))))
    return dict(steps=out, source="legacy grow()")


def m_plan_load(p):
    from neurogenesis.development import BodyPlan
    return dict(plan=BodyPlan.load(p["path"]).to_dict())


def m_plan_save(p):
    _plan(p["plan"]).save(p["path"])
    return dict(path=p["path"])


def m_rules(p):
    from neurogenesis.development.rules import RULES
    return {phase: sorted(v) for phase, v in RULES.items()}


# ----------------------------------------------------------------------------------------------------- projects
def _project(d):
    from neurogenesis.project.io import Project
    known = set(inspect.signature(Project).parameters)
    return Project(**{k: v for k, v in dict(d).items() if k in known})


def m_project_new(p):
    from neurogenesis.project.io import Project
    return dict(project=_jsonable(Project().to_dict()))


def m_project_load(p):
    from neurogenesis.project.io import Project
    return dict(project=_jsonable(Project.load(p["path"]).to_dict()))


def m_project_save(p):
    _project(p["project"]).save(p["path"])
    return dict(path=p["path"])


def m_project_validate(p):
    from neurogenesis.project import schema
    try:
        schema.validate(p["project"])
        return dict(ok=True, message=f"valid (schema {schema.SCHEMA_VERSION})")
    except Exception as e:
        return dict(ok=False, message=str(e))


# ----------------------------------------------------------------------------------------------------- geometry
def _kind(name, ann):
    a = str(ann)
    if name in ("a", "b") or "Geometry" in a:
        return "geometry"
    if "ndarray" in a or name in ("center", "size", "radii", "p0", "p1", "u_vec", "v_vec", "origin"):
        return "vec3"
    if "str" in a or name.endswith("_expr"):
        return "string"
    return "float"


def _safe_sample(geo, n, rng, probes=4096):
    """geo.sample, refusing empty shapes first: rejection sampling of an empty union or difference never returns
    (B1), which would block the bridge. Probes the bounding box with its own generator, so `rng` is untouched."""
    lo, hi = (np.asarray(x, float) for x in geo.bounding_box())
    pts = lo + (hi - lo) * np.random.default_rng(0).random((probes, 3))
    if not np.any(geo.contains(pts)):
        raise ValueError(f"the shape looks empty: none of {probes} probes of its bounding box is inside it")
    return geo.sample(n, rng)


def m_geometry_types(p):
    from neurogenesis.geometry import primitives
    reg = getattr(primitives, "_GEOMETRY_REGISTRY", {})
    out, seen = [], set()
    for name, cls in reg.items():
        if cls in seen:
            continue
        seen.add(cls)
        params = [dict(name=k, kind=_kind(k, prm.annotation),
                       default=None if prm.default is inspect.Parameter.empty else _jsonable(prm.default))
                  for k, prm in inspect.signature(cls.__init__).parameters.items() if k != "self"]
        out.append(dict(type=cls.__name__, params=params, doc=(cls.__doc__ or "").strip().split("\n")[0]))
    return dict(types=out)


def m_geometry_preview(p):
    """Sample points (for display) and bounding box of one geometry."""
    from neurogenesis.geometry import geometry_from_dict
    geo = geometry_from_dict(p["geometry"])
    pts = np.asarray(_safe_sample(geo, int(p.get("n", 1500)), np.random.default_rng(int(p.get("seed", 0)))), np.float32)
    lo, hi = geo.bounding_box()
    return dict(points=pts.round(3).tolist(), lo=np.asarray(lo).tolist(), hi=np.asarray(hi).tolist())


def m_geometry_cells(p):
    """A network of unconnected LIF neurons sampled in a geometry (supervised seeding until stage C1 exists)."""
    from neurogenesis.geometry import geometry_from_dict
    from neurogenesis.spiking.network import NeuronData, SNNNetwork
    geo = geometry_from_dict(p["geometry"])
    seed = int(p.get("seed", 0))
    pts = np.asarray(_safe_sample(geo, int(p["n"]), np.random.default_rng(seed)))
    inh = np.random.default_rng([seed, 1]).random(len(pts)) < float(p.get("inh_fraction", 0.2))
    w = int(p.get("weight", 180))
    ns = [NeuronData(id=i, x=float(x), y=float(y), z=float(z), dir_x=0.0, dir_y=1.0, dir_z=0.0, mode=0,
                     base_weight=-w if inh[i] else w, conn_radius=float(p.get("conn_radius", 28.0)),
                     conn_prob=float(p.get("conn_prob", 0.3)), refractory=int(p.get("refractory", 3)),
                     role=int(p.get("role", 0)), compartment=int(p.get("compartment", -1)))
          for i, (x, y, z) in enumerate(pts)]
    return write_network(SNNNetwork(morphology="geometry", neurons=ns, synapses=[]))


# ------------------------------------------------------------------------------------------------------- stages
def _describe_stage(name, obj):
    d = dict(name=name, doc=(getattr(obj, "__doc__", "") or "").strip().split("\n")[0], params=[])
    for attr in ("params", "PARAMS", "param_spec", "parameters", "defaults"):
        spec = getattr(obj, attr, None)
        if isinstance(spec, dict):
            d["params"] = [dict(name=k, default=None if callable(v) else _jsonable(getattr(v, "value", v))) for k, v in spec.items()]
            break
    else:
        fn = getattr(obj, "operator", obj)
        try:
            for k, prm in inspect.signature(fn).parameters.items():
                if k in ("tissue", "rng", "self", "params", "ctx", "genome", "fields"):
                    continue
                d["params"].append(dict(name=k, default=None if prm.default is inspect.Parameter.empty else _jsonable(prm.default)))
        except (TypeError, ValueError):
            pass
    d["has_cost"] = callable(getattr(obj, "cost", None))
    return d


def m_stages(p):
    """The roadmap's stage catalogue merged with the registered stages (A4 registry): registered ones are available."""
    reg = stage_registry()
    names = {n: t for t, n in STAGE_TASKS}
    out = [dict(_describe_stage(n, o), task=names.get(n, "plugin"), available=True) for n, o in sorted((reg or {}).items())]
    out += [dict(name=n, task=t, available=False, doc="", params=[]) for t, n in STAGE_TASKS if n not in (reg or {})]
    return dict(available=reg is not None, stages=out)


PARAM_TYPES = ("Const", "Gene", "Field", "Fit", "Expr")


def _param(d):
    """A schedule parameter as an A3 Param: {"type": "Const" | "Gene" | "Field" | "Fit" | "Expr", ...fields}."""
    if not isinstance(d, dict):
        return d
    params = importlib.import_module("neurogenesis.params")
    kind = d.get("type") or str(d.get("source", "const")).capitalize()
    if kind not in PARAM_TYPES:
        return d
    cls = getattr(params, kind)
    known = set(inspect.signature(cls).parameters)
    kw = {k: v for k, v in d.items() if k in known}
    if kind == "Gene" and isinstance(kw.get("path"), list):
        kw["path"] = ".".join(map(str, kw["path"]))
    return cls(**kw)


def _schedule(project):
    """Schedule entries in the A4 form {name, operator, params (Param objects), when, repeat}."""
    out = []
    for k, st in enumerate(project.get("schedule", [])):
        st = dict(st)
        st["operator"] = st.get("operator") or st.pop("stage", None)
        st.setdefault("name", f"{k + 1}_{st['operator']}")
        st["params"] = {n: _param(v) for n, v in (st.get("params") or {}).items()}
        out.append(st)
    return out


def m_run_schedule(p):
    """Run a Project's schedule through A4's run_schedule, keeping the tissue after every stage."""
    if stage_registry() is None:
        raise RuntimeError("the stage scheduler (task A4) is not merged yet; use 'Develop step by step' meanwhile")
    mod = importlib.import_module("neurogenesis.stages")
    d = dict(p["project"])
    d["schedule"] = _schedule(d)
    unknown = [s["operator"] for s in d["schedule"] if s["operator"] not in stage_registry()]
    if unknown:
        raise RuntimeError(f"stages not implemented yet: {', '.join(unknown)} (tasks C1–C13 in progress)")
    kw = {"checkpoints": True} if "checkpoints" in inspect.signature(mod.run_schedule).parameters else {}
    res = mod.run_schedule(d, _genome(d.get("genome")), int(p.get("seed", 0)), **kw)
    tissues = list(res) if isinstance(res, (list, tuple)) else [res]
    labels = [f"{s['name']} ({r + 1}/{s.get('repeat', 1)})" if s.get("repeat", 1) > 1 else s["name"]
              for s in d["schedule"] for r in range(int(s.get("repeat", 1)))]
    steps = []
    for k, t in enumerate(tissues):
        net = t.to_network() if hasattr(t, "to_network") else t
        steps.append(dict(label=labels[k] if k < len(labels) else f"stage {k + 1}", **write_network(net)))
    return dict(steps=steps, source="schedule (A4 run_schedule)")


def m_schedule_info(p):
    """Genes the schedule uses (A3 collect_genes) and its declared cost (A4 schedule_cost) for N cells and E synapses."""
    d = dict(p["project"])
    sched = _schedule(d)
    out = {}
    if _has("neurogenesis.params", "collect_genes"):
        out["genes"] = importlib.import_module("neurogenesis.params").collect_genes(sched)
    if _has("neurogenesis.stages.base", "schedule_cost"):
        try:
            b, o = importlib.import_module("neurogenesis.stages.base").schedule_cost({**d, "schedule": sched}, int(p.get("N", 1000)), int(p.get("E", 100000)))
            out["cost"] = dict(bytes=int(b), ops=int(o))
        except Exception as e:
            out["cost_error"] = str(e)
    return out


# --------------------------------------------------------------------------------------------------- simulation
def m_models(p):
    from neurogenesis.spiking.models import MODELS
    return dict(models=[dict(name=m.name, description=m.description, substeps=m.substeps, state_bytes=m.state_bytes,
                             flops=m.flops) for m in MODELS.values()])


def m_simulate(p):
    """Spike times of any registered neuron model (JAX), for models the app does not run natively."""
    import jax
    import jax.numpy as jnp
    from neurogenesis.cost import check
    from neurogenesis.spiking import jax_backend
    from neurogenesis.spiking.models import get_model
    net = read_network(p["ngb"])
    mdl = get_model(p.get("model", "lif_int"))
    ticks = int(p.get("ticks", 500))
    check(mdl.name, net.num_neurons, net.num_synapses, ticks, force=bool(p.get("force", False)))
    a = jax_backend.pack(net)
    ext = np.zeros(net.num_neurons, np.int32)
    for i, c in (p.get("ext") or {}).items():
        ext[int(i)] = int(c)
    st = mdl.init_state(a, int(p.get("seed", 12345)))

    def f(s, _):
        s, spk, _ = mdl.tick(a, s, jnp.asarray(ext))
        return s, spk
    _, spikes = jax.lax.scan(f, st, None, length=ticks)
    t, i = np.nonzero(np.asarray(spikes))
    return dict(ticks=ticks, t=t.astype(int).tolist(), i=i.astype(int).tolist(), model=mdl.name)


def m_estimate(p):
    from neurogenesis.cost import estimate
    from neurogenesis.spiking.models import MODELS
    models = p.get("models") or list(MODELS)
    return dict(estimates=[_jsonable(estimate(m, int(p["neurons"]), int(p["synapses"]), int(p.get("ticks", 1000)),
                                              calibrated=bool(p.get("calibrate", False)))) for m in models])


def m_fi_curve(p):
    from neurogenesis.analysis import fi_curve
    cur = list(range(int(p.get("lo", 0)), int(p.get("hi", 40)) + 1, max(1, int(p.get("step", 2)))))
    r = fi_curve(cur, shift_v=int(p.get("shift_v", 5)), shift_s=int(p.get("shift_s", 4)),
                 threshold=int(p.get("threshold", 1024)), refractory=int(p.get("refractory", 3)),
                 ticks=int(p.get("ticks", 1000)), model=p.get("model", "lif_int"))
    return dict(currents=cur, rate_hz=(np.asarray(r) * 1000).tolist())


def m_regularity(p):
    from neurogenesis.analysis import nearest_neighbour_regularity
    net = read_network(p["ngb"])
    idx = p.get("indices") or list(range(net.num_neurons))
    if len(idx) > 2048:
        raise ValueError("regularity uses a dense distance matrix: at most 2048 cells")
    xy = [(net.neurons[i].x, net.neurons[i].y) for i in idx]
    return dict(regularity=nearest_neighbour_regularity(xy), cells=len(idx))


# --------------------------------------------------------------------------------------------------- plasticity
def m_plasticity_rules(p):
    if not _has("neurogenesis.spiking.plasticity", "STDPRule"):
        return dict(available=False, rules=[])
    pl = importlib.import_module("neurogenesis.spiking.plasticity")
    out = []
    for name, cls in inspect.getmembers(pl, inspect.isclass):
        if cls.__module__ == pl.__name__ and hasattr(cls, "apply"):
            out.append(dict(name=name, params=[dict(name=k, default=_jsonable(v.default)) for k, v in
                                               inspect.signature(cls.__init__).parameters.items()
                                               if k != "self" and v.default is not inspect.Parameter.empty]))
    return dict(available=True, rules=out)


def m_plasticity(p):
    """Apply a plasticity rule (task E1) to a network given the spikes the app recorded. Returns the new weights."""
    if not _has("neurogenesis.spiking.plasticity", "STDPRule"):
        raise RuntimeError("plasticity (task E1) is not merged yet")
    import jax.numpy as jnp
    pl = importlib.import_module("neurogenesis.spiking.plasticity")
    net = read_network(p["ngb"])
    cls = getattr(pl, p.get("rule", "STDPRule"))
    kw = {k: v for k, v in (p.get("params") or {}).items() if k in inspect.signature(cls.__init__).parameters}
    rule = cls(**kw)
    N, T = net.num_neurons, int(p["ticks"])
    spikes = np.zeros((T, N), np.int32)
    t, i = np.asarray(p["t"], int), np.asarray(p["i"], int)
    ok = (t >= 0) & (t < T) & (i < N)
    spikes[t[ok], i[ok]] = 1
    w = np.asarray([s.weight for s in net.synapses], np.float32)
    args = dict(weights=jnp.asarray(w), pre=jnp.asarray([s.pre for s in net.synapses], jnp.int32),
                post=jnp.asarray([s.post for s in net.synapses], jnp.int32),
                delays=jnp.asarray([s.delay for s in net.synapses], jnp.int32),
                spikes=jnp.asarray(spikes), original_weights=jnp.asarray(w))
    sig = inspect.signature(rule.apply).parameters
    for k in ("modulator", "modulation", "reward"):
        if k in sig:
            args[k] = jnp.ones(T, jnp.float32) * float(p.get("modulator", 1.0))
    new = np.asarray(rule.apply(**{k: v for k, v in args.items() if k in sig}))
    return dict(weights=np.round(new).astype(int).tolist(), mean_change=float(np.abs(new - w).mean()) if len(w) else 0.0)


# ---------------------------------------------------------------------------------------------------- evolution
def m_genes(p):
    """Numeric gene paths of a genome (leaves and array entries), with values: candidates for evolution."""
    out = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, path + [k])
        elif isinstance(node, list) and node and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in node):
            for j, x in enumerate(node):
                out.append(dict(path=path + [j], value=x))
        elif isinstance(node, list):
            for j, x in enumerate(node):
                walk(x, path + [j])
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            out.append(dict(path=path, value=node))
    walk(p.get("genome") or {}, [])
    return dict(genes=out)


def _gene_path(path):
    return tuple(tuple(k.split("->")) if isinstance(k, str) and "->" in k else k for k in path)


def m_evolve(p, job=None):
    """Island evolution towards a target mean firing rate (a generic toy objective; projects define their own)."""
    from neurogenesis.development import grow
    from neurogenesis.evolution import evolve
    from neurogenesis.genome.genes import from_unit
    from neurogenesis.genome.io import to_json
    from neurogenesis.spiking.batch import simulate_counts
    plan, base = _plan(p["plan"]), _genome(p["genome"])
    genes = [(_gene_path(g["path"]), float(g["lo"]), float(g["hi"])) for g in p["genes"]]
    target, ticks, current = float(p.get("target_hz", 10.0)), int(p.get("ticks", 200)), int(p.get("input_current", 60))

    def evaluate(genomes, seeds):
        fit, info = [], []
        for g in genomes:
            nets = [grow(plan, g, s) for s in seeds]
            ext = [np.asarray([[current if n.role == 1 else 0 for n in net.neurons]], np.int32) for net in nets]
            c = simulate_counts(nets, ext, ticks=ticks, check_cost=False)
            hz = [float(c[k, 0, :nets[k].num_neurons].sum()) / max(nets[k].num_neurons, 1) / (ticks / 1000) for k in range(len(nets))]
            err = [abs(h - target) for h in hz]
            fit.append(-(max(err) + 0.25 * float(np.mean(err))))
            info.append(dict(rate_hz=float(np.mean(hz))))
        return np.asarray(fit), info

    def log(h):
        if job is not None:
            send(dict(event="progress", job=job, data=h))
    P, hist = evolve(base, genes, evaluate, pop=int(p.get("pop", 12)), gens=int(p.get("gens", 10)),
                     seeds_per_gen=int(p.get("seeds", 2)), elite=2, parents=4, sigma=float(p.get("sigma", 0.1)), log=log)
    return dict(history=hist, genome=to_json(from_unit(base, genes, P[0])))


# ------------------------------------------------------------------------------------------------------ modules
def m_module_load(p):
    from neurogenesis.genome.io import to_json
    from neurogenesis.modules import Module
    m = Module.load(p["path"])
    net = m.grow(int(p.get("seed", 0)))
    return dict(name=m.name, plan=m.plan.to_dict(), genome=to_json(m.genome), inputs=m.inputs, outputs=m.outputs,
                description=m.description, neuron_model=m.neuron_model, validation=_jsonable(m.validation),
                network=write_network(net, extra=_network_extra(m.plan)))


def m_module_save(p):
    from neurogenesis.modules import Module
    Module(p["name"], _plan(p["plan"]), _genome(p["genome"]), inputs=p.get("inputs", []), outputs=p.get("outputs", []),
           description=p.get("description", ""), neuron_model=p.get("neuron_model", "lif_int")).save(p["path"])
    return dict(path=p["path"])


def m_module_compose(p):
    from neurogenesis.genome.io import to_json
    from neurogenesis.modules import Module, compose
    mods = [Module.load(x) for x in p["paths"]]
    m = compose(p.get("name", "composite"), mods, links=[tuple(x) for x in p.get("links", [])])
    net = m.grow(int(p.get("seed", 0)))
    return dict(name=m.name, plan=m.plan.to_dict(), genome=to_json(m.genome),
                network=write_network(net, extra=_network_extra(m.plan)))


# ----------------------------------------------------------------------------------------------------- dispatch
LONG = {"evolve"}
METHODS = {k[2:]: v for k, v in list(globals().items()) if k.startswith("m_") and callable(v)}
_POOL = ThreadPoolExecutor(max_workers=1)          # requests run one at a time, in order
_LONG_POOL = ThreadPoolExecutor(max_workers=1)     # long jobs do not block the others


def warm_up():
    """Import the heavy modules once, in the main thread (concurrent first imports of jax are not safe)."""
    import jax  # noqa: F401
    import jax.numpy  # noqa: F401
    for m in ("neurogenesis.spiking.batch", "neurogenesis.spiking.models", "neurogenesis.development", "neurogenesis.cost",
              "neurogenesis.spiking.morphology"):
        try:
            importlib.import_module(m)
        except Exception:
            traceback.print_exc()


def handle(req):
    rid, method, params = req.get("id"), req.get("method"), req.get("params") or {}
    try:
        fn = METHODS[method]
        res = fn(params, job=rid) if method in LONG else fn(params)
        send(dict(id=rid, result=res))
    except Exception as e:
        send(dict(id=rid, error=f"{type(e).__name__}: {e}", trace=traceback.format_exc()))


def main():
    warm_up()
    send(dict(event="ready", data=dict(python=sys.version.split()[0], repo=str(REPO))))
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            send(dict(id=None, error=f"bad request: {e}"))
            continue
        if req.get("method") == "ping":
            send(dict(id=req.get("id"), result="pong"))
            continue
        (_LONG_POOL if req.get("method") in LONG else _POOL).submit(handle, req)


if __name__ == "__main__":
    main()
