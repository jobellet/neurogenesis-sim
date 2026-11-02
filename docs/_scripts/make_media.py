"""Generate the figures and animations of the documentation site from real runs of the toolbox.

Run from the repository root (CPU only, deterministic seeds, about 2-5 minutes in total):

    JAX_PLATFORMS=cpu python docs/_scripts/make_media.py            # every figure
    JAX_PLATFORMS=cpu python docs/_scripts/make_media.py fi cost    # only some of them

Figures (written to docs/_static/media/):
    cli      cli_raster.png                    `python -m neurogenesis generate` then `simulate --raster` (CLI's own plot)
    topo     topographic_map_growth.png/.gif   examples/topographic_map.py plan + genome, grow(seed=0)
             topographic_precision.png         sensor position vs mean position of its targets in the map
             (also writes docs/_scripts/_work/topographic_network.json for the viewer capture)
    models   raster_models.png                 the same grown network, lif_int / two_compartment / hh, same input
    fi       fi_curves.png                     neurogenesis.analysis.fi_curve for the three models
    cost     cost_estimate.png                 neurogenesis.cost.estimate vs number of neurons
    evo      evolution_progress.png            neurogenesis.evolution.evolve on a toy topography fitness
    stages   development_stages.gif            neurogenesis.stages.run_schedule(checkpoints=True)

The browser viewer captures are made by docs/_scripts/viewer_capture.py.
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("JAX_PLATFORMS", "cpu")

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "_static" / "media"
WORK = ROOT / "docs" / "_scripts" / "_work"
sys.path.insert(0, str(ROOT))

# One fixed colour per region and per model, used in every figure (Okabe-Ito, colour-blind safe; always direct-labelled).
REGION_COLOURS = {"sensor": "#D55E00", "map": "#0072B2"}
MODEL_COLOURS = {"lif_int": "#009E73", "two_compartment": "#CC79A7", "hh": "#E69F00"}
MODELS = ("lif_int", "two_compartment", "hh")

plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 10, "axes.titlesize": 11,
    "axes.labelcolor": "#333333", "xtick.color": "#555555", "ytick.color": "#555555",
})


def save_png(fig, name, dpi=110):
    """Save a figure as a palette PNG (small files) and report its size."""
    buf = io.BytesIO()
    fig.savefig(buf, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    im = Image.open(buf).convert("RGB").quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    path = OUT / name
    im.save(path, optimize=True)
    print(f"  wrote {path.relative_to(ROOT)} ({path.stat().st_size / 1024:.0f} KB)")


def fig_to_image(fig, dpi=80):
    buf = io.BytesIO()
    fig.savefig(buf, dpi=dpi)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def save_gif(frames, name, durations, colours=96):
    """Frames share one adaptive palette (computed from all frames), no dithering, so the GIF stays small."""
    w, h = frames[0].size
    strip = Image.new("RGB", (w, h * min(len(frames), 8)))
    pick = np.linspace(0, len(frames) - 1, min(len(frames), 8)).astype(int)
    for k, i in enumerate(pick):
        strip.paste(frames[i], (0, h * k))
    pal = strip.quantize(colors=colours, method=Image.Quantize.MEDIANCUT)
    q = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    path = OUT / name
    q[0].save(path, save_all=True, append_images=q[1:], duration=durations, loop=0, optimize=True, disposal=1)
    print(f"  wrote {path.relative_to(ROOT)} ({path.stat().st_size / 1024:.0f} KB, {len(frames)} frames)")


# --------------------------------------------------------------------------------------------------------------------
# 1. CLI raster
def make_cli():
    print("cli: generate + simulate --raster")
    WORK.mkdir(parents=True, exist_ok=True)
    net = WORK / "cli_column_500.json"
    py = sys.executable
    cmds = [[py, "-m", "neurogenesis", "generate", "--neurons", "500", "--morphology", "column", "--weight-scale", "0.2",
             "--refractory", "3", "--seed", "42", "--out", str(net)],
            [py, "-m", "neurogenesis", "simulate", "--network", str(net), "--ticks", "500", "--seed", "12345",
             "--raster", str(WORK / "cli_raster_full.png")]]
    for c in cmds:
        print("  $", " ".join(["python"] + c[1:]).replace(str(ROOT) + "/", ""))
        r = subprocess.run(c, cwd=ROOT, capture_output=True, text=True, check=True)
        print("   ", r.stdout.strip().replace("\n", "\n    "))
    im = Image.open(WORK / "cli_raster_full.png").convert("RGB")
    im = im.resize((im.width // 2, im.height // 2), Image.LANCZOS)        # the CLI writes 200 dpi; halve for the web
    path = OUT / "cli_raster.png"
    im.quantize(colors=128, dither=Image.Dither.NONE).save(path, optimize=True)
    print(f"  wrote {path.relative_to(ROOT)} ({path.stat().st_size / 1024:.0f} KB)")


# --------------------------------------------------------------------------------------------------------------------
# 2-4. The topographic map example
def topographic_example():
    """make_plan / make_genome of examples/topographic_map.py (imported, not copied)."""
    import importlib.util
    argv, sys.argv = sys.argv, ["topographic_map.py", "--cpu"]
    try:
        spec = importlib.util.spec_from_file_location("topographic_map", ROOT / "examples" / "topographic_map.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.argv = argv
    return mod.make_plan, mod.make_genome


def grown_topographic(seed=0):
    from neurogenesis.development import grow, region_of
    make_plan, make_genome = topographic_example()
    plan, genome = make_plan(), make_genome()
    net = grow(plan, genome, seed=seed)
    return plan, genome, net, region_of(net, plan, "sensor"), region_of(net, plan, "map")


def topography(net, sensor, mp):
    """Per sensor neuron: local (u, v) of the sensor on its sheet and mean local (u, v) of its targets in the map."""
    xy = np.asarray([[n.x, n.y] for n in net.neurons])
    loc = np.empty_like(xy)
    loc[sensor] = xy[sensor] / 30.0
    loc[mp] = (xy[mp] - [50.0, 0.0]) / 30.0
    pre = np.asarray([s.pre for s in net.synapses])
    post = np.asarray([s.post for s in net.synapses])
    src, tgt, n_t = [], [], []
    for i in sensor:
        t = post[pre == i]
        t = t[np.isin(t, mp)]
        if len(t):
            src.append(loc[i])
            tgt.append(loc[t].mean(0))
            n_t.append(len(t))
    return np.asarray(src), np.asarray(tgt), np.asarray(n_t)


def draw_topo_frame(ax, net, sensor, mp, syn_idx, title, show_map=True):
    xy = np.asarray([[n.x, n.y] for n in net.neurons])
    if len(syn_idx):
        from matplotlib.collections import LineCollection
        tt = np.linspace(0, 1, 16)[:, None]
        segs = []
        for k in syn_idx:                                   # gentle arcs, so axons do not hide behind other sensors
            a, b = xy[net.synapses[k].pre], xy[net.synapses[k].post]
            c = (a + b) / 2 + [0.0, 4.0]
            segs.append((1 - tt) ** 2 * a + 2 * (1 - tt) * tt * c + tt ** 2 * b)
        u = np.asarray([xy[net.synapses[k].pre][0] / 30.0 for k in syn_idx])
        lc = LineCollection(segs, colors=plt.cm.viridis(0.85 * u), linewidths=0.7, alpha=0.6, zorder=1)
        ax.add_collection(lc)
    ax.scatter(*xy[sensor].T, s=28, c=REGION_COLOURS["sensor"], edgecolors="white", linewidths=0.6, zorder=3)
    if show_map:
        ax.scatter(*xy[mp].T, s=12, c=REGION_COLOURS["map"], edgecolors="white", linewidths=0.4, zorder=3)
    ax.add_patch(plt.Rectangle((0, 0), 30, 30, fill=False, ec=REGION_COLOURS["sensor"], lw=0.8, ls="--", zorder=0))
    ax.add_patch(plt.Rectangle((50, 0), 30, 30, fill=False, ec=REGION_COLOURS["map"], lw=0.8, ls="--", zorder=0))
    ax.text(15, 32, "sensor (36, fixed sheet)", ha="center", color=REGION_COLOURS["sensor"], fontsize=9)
    ax.text(65, 32, "map (200, grown)", ha="center", color=REGION_COLOURS["map"], fontsize=9)
    ax.set_xlim(-3, 83)
    ax.set_ylim(-3, 36)
    ax.set_aspect("equal")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_title(title, fontsize=10, loc="left")


def make_topo():
    print("topo: examples/topographic_map.py plan + genome, grow(seed=0)")
    plan, genome, net, sensor, mp = grown_topographic(0)
    E = net.num_synapses
    print(f"  {net.num_neurons} neurons, {E} synapses")
    WORK.mkdir(parents=True, exist_ok=True)
    net.save_json(WORK / "topographic_network.json")

    # Synapses in the order grow() creates them (by presynaptic sensor index = row-major position on the sheet).
    order = np.arange(E)
    pre = np.asarray([s.pre for s in net.synapses])

    fig, ax = plt.subplots(figsize=(8, 4))
    draw_topo_frame(ax, net, sensor, mp, order,
                    f"Grown topographic map (seed 0): {E} sensor→map synapses, coloured by the sensor's x position\n"
                    "top view; plan and genome of examples/topographic_map.py")
    save_png(fig, "topographic_map_growth.png", dpi=120)

    n_inh = sum(n.base_weight < 0 for n in net.neurons)
    frames, dur = [], []
    f, ax = plt.subplots(figsize=(8, 4))
    draw_topo_frame(ax, net, sensor, mp, [], "1. placement: 36 sensor neurons on a fixed 6×6 sheet", show_map=False)
    frames.append(fig_to_image(f)); dur.append(1200)
    f, ax = plt.subplots(figsize=(8, 4))
    draw_topo_frame(ax, net, sensor, mp, [], "1. placement: 200 map neurons at random positions (genome migration)")
    frames.append(fig_to_image(f)); dur.append(1200)
    f, ax = plt.subplots(figsize=(8, 4))
    draw_topo_frame(ax, net, sensor, mp, [], f"2. sign and differentiation: {n_inh} inhibitory neurons, no differentiation genes\n"
                    "(the network does not change at this step)")
    frames.append(fig_to_image(f)); dur.append(1200)
    n_src = len(sensor)
    for k in range(1, n_src + 1, 3):
        upto = min(k + 2, n_src)
        idx = order[pre < sensor[upto - 1] + 1]
        f, ax = plt.subplots(figsize=(8, 4))
        draw_topo_frame(ax, net, sensor, mp, idx, f"3. axon growth: synapses of sensors 1–{upto} of {n_src} "
                        f"({len(idx)} of {E} synapses)\n(drawn in the order grow() creates them)")
        frames.append(fig_to_image(f)); dur.append(350)
    dur[-1] = 2500
    save_gif(frames, "topographic_map_growth.gif", dur)

    src, tgt, n_t = topography(net, sensor, mp)
    r = [np.corrcoef(src[:, d], tgt[:, d])[0, 1] for d in (0, 1)]
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.6))
    for d, (ax, lab) in enumerate(zip(axs[:2], ("x", "y"))):
        ax.plot([0, 1], [0, 1], ls="--", c="#999999", lw=0.8)
        ax.scatter(src[:, d], tgt[:, d], s=22, c=REGION_COLOURS["sensor"], edgecolors="white", linewidths=0.5)
        ax.set_xlabel(f"sensor {lab} position (sheet, 0–1)")
        ax.set_ylabel(f"mean {lab} of its targets (map, 0–1)")
        ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_aspect("equal")
        ax.set_title(f"{lab}: Pearson r = {r[d]:.2f} ({len(src)} sensors)", fontsize=10)
    ax = axs[2]
    ax.quiver(src[:, 0], src[:, 1], tgt[:, 0] - src[:, 0], tgt[:, 1] - src[:, 1], angles="xy", scale_units="xy",
              scale=1, color="#555555", width=0.005)
    ax.scatter(*src.T, s=18, c=REGION_COLOURS["sensor"], zorder=3, label="sensor position")
    ax.scatter(*tgt.T, s=18, c=REGION_COLOURS["map"], zorder=3, label="mean target position")
    ax.set_xlim(-0.05, 1.05); ax.set_ylim(-0.05, 1.05); ax.set_aspect("equal")
    ax.set_xlabel("x (normalised)"); ax.set_ylabel("y (normalised)")
    ax.legend(fontsize=8, loc="upper left", bbox_to_anchor=(1.0, 1.0), frameon=False)
    ax.set_title("sensor → centroid of its targets", fontsize=10)
    fig.suptitle(f"Topographic precision of the grown sensor→map projection (seed 0; {n_t.mean():.1f} targets per sensor "
                 "on average; dashed: identity)", fontsize=11)
    fig.tight_layout()
    save_png(fig, "topographic_precision.png")
    print(f"  topography r_x = {r[0]:.3f}, r_y = {r[1]:.3f}")


# --------------------------------------------------------------------------------------------------------------------
# 4. Rasters of the same network with three neuron models
def spike_raster(net, ext_seq, model, seed=0):
    """(T, N) spikes, one row per tick, driving models.<model>.tick directly (ext_seq: (T, N) int32 currents)."""
    import jax
    import jax.numpy as jnp
    from neurogenesis.spiking.jax_backend import pack
    from neurogenesis.spiking.models import get_model
    m = get_model(model)
    a = pack(net)
    st = m.init_state(a, seed)
    n_pad = np.shape(a["mode"])[-1]
    ext = np.zeros((len(ext_seq), n_pad), np.int32)
    ext[:, :net.num_neurons] = ext_seq

    def f(s, e):
        s, spk, _ = m.tick(a, s, e)
        return s, spk.astype(jnp.uint8)
    _, spikes = jax.jit(lambda s, e: jax.lax.scan(f, s, e))(st, jnp.asarray(ext))
    return np.asarray(spikes)[:, :net.num_neurons]


def make_models():
    print("models: the grown topographic map with lif_int / two_compartment / hh")
    from neurogenesis.spiking.batch import simulate_counts
    plan, genome, net, sensor, mp = grown_topographic(0)
    xs = np.asarray([net.neurons[i].x for i in sensor])
    cols = np.unique(np.round(xs, 3))
    T_on, T_off, amp = 40, 20, 40
    ext = []
    for c in cols:                                                  # a bar sweeping the sheet along x, one column at a time
        e = np.zeros(net.num_neurons, np.int32)
        e[sensor[np.isclose(xs, c)]] = amp
        ext += [np.zeros(net.num_neurons, np.int32)] * T_off + [e] * T_on
    ext = np.asarray(ext)
    T = len(ext)
    # order neurons: sensors then map, each by x position
    order = np.concatenate([sensor[np.argsort(xs, kind="stable")],
                            mp[np.argsort([net.neurons[i].x for i in mp], kind="stable")]])
    fig, axs = plt.subplots(3, 1, figsize=(9, 7.5), sharex=True)
    for ax, model in zip(axs, MODELS):
        spk = spike_raster(net, ext, model)
        # cross-check against the batched API on the first stimulus (after T_off blank ticks)
        ref = simulate_counts([net], [ext[T_off:T_off + 1]], ticks=T_on, blank=T_off, model=model)[0][0, :net.num_neurons]
        assert np.array_equal(ref, spk[T_off:T_off + T_on].sum(0)), model
        sp = spk[:, order]
        t, row = np.nonzero(sp)
        is_s = row < len(sensor)
        ax.scatter(t[is_s], row[is_s], s=2.5, c=REGION_COLOURS["sensor"], marker="|", linewidths=0.8)
        ax.scatter(t[~is_s], row[~is_s], s=2.5, c=REGION_COLOURS["map"], marker="|", linewidths=0.8)
        for k in range(len(cols)):
            ax.axvspan(k * (T_on + T_off) + T_off, (k + 1) * (T_on + T_off), color="#f0f0f0", zorder=0, lw=0)
        ax.axhline(len(sensor) - 0.5, c="#bbbbbb", lw=0.6)
        ax.set_ylim(-1, net.num_neurons)
        ax.set_ylabel("neuron (sorted by x)")
        ns, nm = sp[:, :len(sensor)].sum(), sp[:, len(sensor):].sum()
        ax.set_title(f"{model}: {ns} sensor spikes, {nm} map spikes", color="#222222", fontsize=10, loc="left")
        ax.text(1.005, 0.5, model, transform=ax.transAxes, rotation=90, va="center", color=MODEL_COLOURS[model],
                fontsize=11, fontweight="bold")
        print(f"  {model}: sensor spikes {ns}, map spikes {nm}")
    axs[0].text(2, len(sensor) * 0.5, "sensor", color=REGION_COLOURS["sensor"], fontsize=8, va="center")
    axs[0].text(2, len(sensor) + len(mp) * 0.5, "map", color=REGION_COLOURS["map"], fontsize=8, va="center")
    axs[-1].set_xlabel("time (ticks of 1 ms)")
    fig.suptitle(f"Same grown network (topographic map, seed 0), same input, three neuron models\n"
                 f"input: current {amp} to one column of the 6×6 sensor sheet for {T_on} ticks (grey), "
                 f"sweeping x from 0 to 30, {T_off} silent ticks between", fontsize=10)
    fig.tight_layout()
    save_png(fig, "raster_models.png")


# --------------------------------------------------------------------------------------------------------------------
# 5. F-I curves
def make_fi():
    print("fi: neurogenesis.analysis.fi_curve")
    from neurogenesis.analysis import fi_curve
    from neurogenesis.spiking.models.base import RHEOBASE_UNITS
    cur = np.concatenate([np.arange(0, 20), np.arange(20, 121, 4)])
    fig, ax = plt.subplots(figsize=(6.5, 4))
    for m in MODELS:
        f = fi_curve(cur, model=m, ticks=1000) * 1000
        ax.plot(cur, f, c=MODEL_COLOURS[m], lw=2, marker="o", ms=3)
        ax.text(cur[-1] + 2, f[-1] + {"lif_int": -7, "two_compartment": 7, "hh": 0}[m], m, color=MODEL_COLOURS[m],
                va="center", fontsize=9)
        print(f"  {m}: onset at {cur[np.argmax(f > 0)]} units, {f[-1]:.0f} Hz at {cur[-1]}")
    ax.axvline(RHEOBASE_UNITS, c="#999999", ls="--", lw=0.8)
    ax.text(RHEOBASE_UNITS + 1, ax.get_ylim()[1] * 0.95, f"integer rheobase\n{RHEOBASE_UNITS} units", fontsize=8,
            color="#666666", va="top")
    ax.set_xlim(0, cur[-1] + 22)
    ax.set_xlabel("constant external current (toolbox units)")
    ax.set_ylabel("firing rate (Hz)")
    ax.set_title("Frequency–current curves, one isolated default neuron\n"
                 "(threshold 1024, shift_v 5, shift_s 4, refractory 3; 1000 ticks from rest per current)", fontsize=10)
    save_png(fig, "fi_curves.png")


# --------------------------------------------------------------------------------------------------------------------
# 6. Cost estimates
def make_cost():
    print("cost: neurogenesis.cost.estimate")
    from neurogenesis import cost
    syn_per = 1000
    N = np.logspace(3, 9, 25)
    t0 = time.time()
    calibrated = True
    try:
        for m in MODELS:
            cost.calibrate(m)                     # cached in ~/.cache/neurogenesis after the first run
    except Exception as e:                        # pragma: no cover
        print("  calibration failed:", e)
        calibrated = False
    print(f"  calibration (or cache) took {time.time() - t0:.1f} s")
    fig, axs = plt.subplots(1, 2, figsize=(10, 4.2))
    avail = None
    for spn, ls in ((syn_per, "-"), (10, "--")):
        for m in MODELS:
            es = [cost.estimate(m, int(n), int(n * spn), 1000, calibrated=calibrated) for n in N]
            avail = es[0]["available_bytes"]
            axs[0].loglog(N, [e["memory_bytes"] for e in es], c=MODEL_COLOURS[m], lw=2 if ls == "-" else 1.5, ls=ls)
            if "seconds_total" in es[0]:
                axs[1].loglog(N, [e["seconds_total"] for e in es], c=MODEL_COLOURS[m], lw=2 if ls == "-" else 1.5, ls=ls,
                              label=f"{m}" if ls == "-" else None)
    axs[1].plot([], [], c="#444444", ls="-", label=f"{syn_per} synapses / neuron")
    axs[1].plot([], [], c="#444444", ls="--", label="10 synapses / neuron")
    if avail:
        axs[0].axhline(avail, c="#444444", ls=":", lw=0.9)
        axs[0].text(N[0], avail * 1.6, f"this machine: {avail / 1e9:.0f} GB RAM", fontsize=8, color="#444444")
    axs[0].set_xlabel("neurons"); axs[0].set_ylabel("memory (bytes)")
    axs[0].set_title("Estimated memory\n(a simulation is refused above 80% of it)", fontsize=10)
    axs[0].text(0.98, 0.04, "memory: the three models overlap\n(synapse arrays dominate)",
                transform=axs[0].transAxes, ha="right", fontsize=8, color="#666666")
    axs[1].set_xlabel("neurons"); axs[1].set_ylabel("wall time per simulated second (s)")
    axs[1].set_title("Estimated time, linear extrapolation\nof a short calibration on this CPU", fontsize=10)
    axs[1].legend(frameon=False, fontsize=8)
    for y, lab in ((60, "1 min"), (3600, "1 h"), (86400, "1 day")):
        axs[1].axhline(y, c="#dddddd", lw=0.7, zorder=0)
        axs[1].text(N[0], y * 1.2, lab, fontsize=7, color="#888888")
    fig.suptitle("neurogenesis.cost.estimate for 1 simulated second (1000 ticks), JAX on this CPU", fontsize=11)
    fig.tight_layout()
    save_png(fig, "cost_estimate.png")


# --------------------------------------------------------------------------------------------------------------------
# 7. Evolution
def make_evo():
    print("evo: neurogenesis.evolution.evolve on a toy topography fitness")
    from neurogenesis.development import grow, region_of
    from neurogenesis.evolution import evolve, robust_value
    make_plan, make_genome = topographic_example()
    plan = make_plan()
    base = make_genome()
    k = ("sensor", "map")
    base["guidance"][k]["B"] = np.diag([0.2, 0.2, 0.0])            # weak topography to start from
    base["guidance"][k]["sigma"] = 0.4
    base["count"]["map"] = 80
    genes = [(("guidance", k, "B", 0, 0), -2.0, 4.0), (("guidance", k, "B", 1, 1), -2.0, 4.0),
             (("guidance", k, "B", 0, 1), -2.0, 2.0), (("guidance", k, "sigma"), 0.03, 0.5)]

    def score(net):
        src, tgt, _ = topography(net, region_of(net, plan, "sensor"), region_of(net, plan, "map"))
        if len(src) < 10:
            return -1.0
        r = [np.corrcoef(src[:, d], tgt[:, d])[0, 1] for d in (0, 1)]
        return float(np.nan_to_num(np.mean(r), nan=-1.0))

    def evaluate(genomes, seeds):
        fit, info = [], []
        for g in genomes:
            s = np.asarray([score(grow(plan, g, seed=sd)) for sd in seeds])
            fit.append(robust_value(dict(score=s, cost=0.0)))
            info.append(dict(scores=s.tolist()))
        return fit, info
    t0 = time.time()
    gens, pop = 15, 12
    P, hist = evolve(base, genes, evaluate, island=0, pop=pop, gens=gens, seeds_per_gen=3, elite=2, parents=4, sigma=0.15)
    print(f"  {gens} generations x {pop} genomes x 3 seeds in {time.time() - t0:.0f} s; "
          f"best {hist[0]['best']:.3f} -> {hist[-1]['best']:.3f}")
    g = [h["generation"] for h in hist]
    fig, ax = plt.subplots(figsize=(6.5, 4))
    ax.plot(g, [h["best"] for h in hist], c="#0072B2", lw=2, marker="o", ms=4)
    ax.plot(g, [h["median"] for h in hist], c="#999999", lw=1.5, marker="o", ms=3)
    ax.text(g[-1] + 0.3, hist[-1]["best"], "best", color="#0072B2", va="center")
    ax.text(g[-1] + 0.3, hist[-1]["median"], "median", color="#777777", va="center")
    ax.set_xlim(-0.5, gens + 1.5)
    ax.set_xlabel("generation")
    ax.set_ylabel("fitness = worst + 0.25 × mean score")
    ax.set_title(f"Island evolution (pop {pop}, 3 fresh development seeds per generation)\n"
                 "toy score: topographic correlation of the sensor→map projection; "
                 "genes: B[0,0], B[1,1], B[0,1], sigma", fontsize=9)
    save_png(fig, "evolution_progress.png")


# --------------------------------------------------------------------------------------------------------------------
# 8. Developmental stages
STAGES_PROJECT_DOC = """seed_cells (12 founders in a sphere of radius 10) -> proliferate x5 (p=0.6, jitter 1.5)
-> apoptosis (p=0.15) -> apoptosis (crowding: > 4 neighbours within 1.5) -> differentiate (clone % 3 == 0: inhibitory)
-> migrate x3 (radial, speed 2)"""


def make_stages():
    print("stages: run_schedule(checkpoints=True)")
    from neurogenesis.geometry.primitives import Sphere
    from neurogenesis.stages import run_schedule
    # The geometry is passed as an object in the stage params, not in project["fields"]: with a geometry in the fields,
    # the differentiate stage crashes (it calls geometry.sample(positions)).
    project = dict(schedule=[
        dict(name="seed", operator="seed_cells", params=dict(N=12, geometry=Sphere(np.zeros(3), 10.0))),
        dict(name="divide", operator="proliferate", params=dict(prob=0.6, jitter=1.5), repeat=5),
        dict(name="death", operator="apoptosis", params=dict(prob=0.15)),
        dict(name="crowding", operator="apoptosis", params=dict(density_radius=1.5, max_density=4)),
        dict(name="fate", operator="differentiate",
             params=dict(types=[dict(type_id=1, condition="clone % 3 == 0", sign=-1)])),
        dict(name="spread", operator="migrate", params=dict(speed=2.0, radial=True, target=[0.0, 0.0, 0.0]), repeat=3),
    ])
    cps = run_schedule(project, {}, seed=0, checkpoints=True)
    labels = []
    for st in project["schedule"]:
        for rep in range(st.get("repeat", 1)):
            labels.append((st["name"], st["operator"], rep, st.get("repeat", 1)))
    clones = sorted(set(np.concatenate([t.clone_id for t in cps]).tolist()))
    cmap = plt.get_cmap("tab20")
    col = {c: cmap((2 * k) % 20 + (k // 10)) for k, c in enumerate(clones)}
    lim = max(np.percentile(np.abs(t.positions), 99) for t in cps) * 1.05
    frames, dur = [], []
    prev = 0
    for k, (t, (name, op, rep, nrep)) in enumerate(zip(cps, labels)):
        fig = plt.figure(figsize=(5.6, 5.2))
        ax = fig.add_axes([-0.08, -0.08, 1.16, 1.0], projection="3d")
        c = [col[x] for x in t.clone_id]
        inh = t.sign < 0
        ax.scatter(*t.positions[~inh].T, c=[ci for ci, i in zip(c, inh) if not i], s=40, marker="o", depthshade=False,
                   edgecolors="white", linewidths=0.3)
        if inh.any():
            ax.scatter(*t.positions[inh].T, c=[ci for ci, i in zip(c, inh) if i], s=55, marker="^", depthshade=False,
                       edgecolors="black", linewidths=0.4)
        for s in (ax.set_xlim, ax.set_ylim, ax.set_zlim):
            s(-lim, lim)
        ax.view_init(elev=20, azim=30 + 4 * k)
        ax.set_xticklabels([]); ax.set_yticklabels([]); ax.set_zticklabels([])
        rep_s = f" {rep + 1}/{nrep}" if nrep > 1 else ""
        n = len(t.alive)
        delta = f"{n - prev:+d} cells" if k else ""
        ax.set_title(f"checkpoint {k + 1}/{len(cps)}: stage '{name}' ({op}{rep_s})\n"
                     f"{n} cells{(' (' + delta + ')') if delta else ''}, {len(set(t.clone_id.tolist()))} clones; "
                     f"colour = clone; ▲ = inhibitory ({int(inh.sum())})", fontsize=9)
        prev = n
        frames.append(fig_to_image(fig, dpi=72))
        dur.append(900)
    dur[-1] = 2500
    save_gif(frames, "development_stages.gif", dur, colours=128)
    print("  checkpoints:", [len(t.alive) for t in cps])


TASKS = dict(cli=make_cli, topo=make_topo, models=make_models, fi=make_fi, cost=make_cost, evo=make_evo,
             stages=make_stages)

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name in (sys.argv[1:] or TASKS):
        TASKS[name]()
