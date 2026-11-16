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
    retino   retinothalamic_development.webp   selected development milestones + WT / EphA knockout
             with RETINO_RELAY_MASK=<mask.npz> (examples/atlas_relay_mask.py): the relay grown in that shape, written
             to retinothalamic_development_p4_atlas.webp (or $RETINO_WEBP)

The browser viewer captures are made by docs/_scripts/viewer_capture.py.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("JAX_PLATFORMS", "cpu")

import matplotlib  # noqa: E402
import matplotlib.ticker  # noqa: E402

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


def save_webp(frames, name, durations, quality=78):
    """Write a compact animated WebP with a per-frame duration list."""
    path = OUT / name
    frames[0].save(path, format="WEBP", save_all=True, append_images=frames[1:], duration=durations,
                   loop=0, quality=quality, method=6)
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


def make_retino():
    """Retina -> relay development (examples/retinothalamic.py, WT, seed 0): one frame per checkpoint, then a turn
    around the final network. Retinal axons and relay cells are coloured by the retinal x position they come from
    (relay cells: weighted mean over their retinal inputs), so a topographic map shows as a colour gradient.
    $RETINO_RELAY_MASK, if set, is a relay shape (.npz from examples/atlas_relay_mask.py) used instead of the box."""
    print("retino: examples/retinothalamic.py run_schedule(checkpoints=True)")
    from examples.retinothalamic import RET_C, RET_S, RGC, OTHER, RELAY, INTER, build_project, relay_frame
    from neurogenesis.stages import run_schedule
    mask = os.environ.get("RETINO_RELAY_MASK") or None
    animation = os.environ.get("RETINO_WEBP") or ("retinothalamic_development_p4_atlas.webp" if mask
                                                  else "retinothalamic_development.webp")
    rel_lo, rel_size = relay_frame(mask)
    z_top = max(55.0, float(rel_lo[2] + rel_size[2]) + 5.0)
    shape = " (atlas-shaped)" if mask else ""
    p = build_project("WT", 0, relay_mask=mask)
    d = p.to_dict()
    cps = run_schedule(d, p.genome, 0, checkpoints=True)
    labels = [(st["name"], rep, st.get("repeat", 1)) for st in d["schedule"] for rep in range(st.get("repeat", 1))]
    cmap = plt.get_cmap("viridis")
    lo = RET_C - RET_S / 2

    def draw(t, title, azim):
        fig = plt.figure(figsize=(8.6, 5.0))
        ax = fig.add_axes([-0.06, -0.06, 0.78, 1.0], projection="3d")
        ax2 = fig.add_axes([0.70, 0.30, 0.27, 0.42])
        pos, ct = t.positions, t.cell_type
        ux = np.clip((pos[:, 0] - lo[0]) / RET_S[0], 0, 1)
        c = t.connectivity
        retinal = (ct[c.pre] == RGC) & np.isin(ct[c.post], (RELAY, INTER)) & (c.weight != 0) if len(c.pre) else np.zeros(0, bool)
        relay_col = np.full(len(ct), np.nan)
        if retinal.any():
            pre, post, w = c.pre[retinal], c.post[retinal], np.abs(c.weight[retinal]).astype(float)
            wsum = np.bincount(post, w, len(ct))
            relay_col = np.where(wsum > 0, np.bincount(post, w * ux[pre], len(ct)) / np.maximum(wsum, 1e-12), np.nan)
            rgc_w = np.bincount(pre, w, len(ct))
            u_rel = (pos[:, :2] - rel_lo[:2]) / rel_size[:2]
            has = np.flatnonzero((ct == RGC) & (rgc_w > 0))
            for k, (colour, axis) in enumerate((("#0072B2", "x"), ("#D55E00", "y"))):
                u_ret = np.clip((pos[has, k] - lo[k]) / RET_S[k], 0, 1)
                cen = np.bincount(pre, w * u_rel[post, k], len(ct))[has] / rgc_w[has]
                r = np.corrcoef(u_ret, cen)[0, 1] if len(has) > 2 else np.nan
                ax2.scatter(u_ret, cen, s=7, c=colour, label=f"{axis}: r = {r:.2f}")
            ax2.legend(fontsize=7, loc="upper left", frameon=False)
            pick = np.random.default_rng(0).choice(len(pre), size=min(len(pre), 350), replace=False)
            for a, b in zip(pre[pick], post[pick]):
                ax.plot(*np.stack([pos[a], pos[b]]).T, color=cmap(ux[a]), lw=0.35, alpha=0.35)
        prog = ~np.isin(ct, (RGC, OTHER, RELAY, INTER))
        ax.scatter(*pos[prog].T, s=10, c="#999999", depthshade=False)
        ax.scatter(*pos[ct == OTHER].T, s=8, c="#cccccc", depthshade=False)
        ax.scatter(*pos[ct == RGC].T, s=22, c=cmap(ux[ct == RGC]), depthshade=False, edgecolors="black", linewidths=0.3)
        rel = ct == RELAY
        col = np.array([cmap(v) if np.isfinite(v) else (0.73, 0.73, 0.73, 1.0) for v in relay_col[rel]]).reshape(-1, 4)
        ax.scatter(*pos[rel].T, s=16, c=col, marker="s", depthshade=False, edgecolors="black", linewidths=0.2)
        ax.scatter(*pos[ct == INTER].T, s=26, c="#D55E00", marker="^", depthshade=False)
        ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.set_zlim(-5, z_top)
        ax.view_init(elev=18, azim=azim)
        ax.set_xticklabels([]); ax.set_yticklabels([]); ax.set_zticklabels([])
        ax.set_xlabel("x (EphA axis)", fontsize=8, labelpad=-10); ax.set_ylabel("y (EphB axis)", fontsize=8, labelpad=-10)
        ax2.set_xlim(0, 1); ax2.set_ylim(-0.1, 1.1)
        ax2.set_xlabel("RGC position in the retina", fontsize=8)
        ax2.set_ylabel("mean position of its relay targets", fontsize=8)
        ax2.tick_params(labelsize=7)
        ax2.set_title("map (each dot one RGC)", fontsize=8)
        ax.set_title(title, fontsize=9, x=0.62)
        return fig_to_image(fig, dpi=72)

    milestones = (
        ("seed_relay", "1 · Seed retina and relay progenitors"),
        ("proliferate", "2 · Expand the retinal population"),
        ("differentiate", "3 · Differentiate retinal and relay cells"),
        ("grow_axons", "4 · Grow retinal projections"),
        ("apoptosis", "5 · Keep relay cells with retinal input"),
        ("refine_3", "6 · Refine the map with activity"),
        ("freeze", "7 · Final wild-type network"),
    )
    selected = []
    for name, title in milestones:
        candidates = [i for i, (stage, _, _) in enumerate(labels) if stage == name]
        if candidates:
            i = candidates[-1]
            selected.append((i, title))
    frames, dur = [], []
    for number, (i, title) in enumerate(selected, 1):
        t = cps[i]
        n_ret = int(np.sum(np.isin(t.cell_type, (RELAY, INTER)) == False))  # noqa: E712
        caption = (f"{title}\n{n_ret} retinal cells, {int(np.sum(t.cell_type == RELAY))} relay cells, "
                 f"{len(t.connectivity.pre)} synapses; colour = retinal x")
        frames.append(draw(t, caption, -38))
        dur.append(1100)
    final = cps[-1]
    frames.append(draw(final, f"Final wild type: retina below, relay{shape} above\ncolour follows retinal x",
                       -38))
    dur.append(1800)
    pk = build_project("EphAKO", 0, relay_mask=mask)
    ko = run_schedule(pk.to_dict(), pk.genome, 0)
    frames.append(draw(ko, "EphA knockout, same seed\nx map lost; y map remains",
                       -38))
    dur.append(2400)
    save_webp(frames, animation, dur)

    # Export individual stage checkpoint frames for the interactive tutorial carousel
    step_indices = [4, 10, 11, 12, 13, 14, 15, 19, 23, 25, 26, 28]
    prefix = "retino_stage_p4_" if mask else "retino_stage_"
    for step_num, idx in enumerate(step_indices, 1):
        if idx < len(frames):
            frames[idx].save(OUT / f"{prefix}{step_num:02d}.png")


# --------------------------------------------------------------------------------------------------------------------
# 9. Geometry and fields gallery + migration with stop field
def make_fields():
    print("fields: geometry & field gallery + migrate stop_field GIF")
    from neurogenesis.fields import AnalyticField, LayerStackField, find_pinwheels, pinwheel_map
    from neurogenesis.geometry import Box, CurvedSheet, Difference, Sphere
    from neurogenesis.stages import run_schedule

    fig = plt.figure(figsize=(12.2, 3.9))
    ax1 = fig.add_subplot(1, 3, 1, projection="3d")
    shell = Difference(Box([0, 0, 0], [2, 2, 2]), Sphere([0, 0, 0], 0.55))
    pts = shell.sample_points(3000, np.random.default_rng(0))
    cut = pts[pts[:, 0] > -0.05]
    r = np.linalg.norm(cut, axis=1)
    ax1.scatter(*cut.T, c=r, cmap="viridis", s=5, alpha=0.85, depthshade=False)
    ax1.view_init(elev=22, azim=20)
    ax1.set_xlim(-1.05, 1.05); ax1.set_ylim(-1.05, 1.05); ax1.set_zlim(-1.05, 1.05)
    ax1.set_xlabel("x"); ax1.set_ylabel("y"); ax1.set_zlabel("z")
    ax1.set_title("CSG: Difference(Box, Sphere)\n(cutaway x > -0.05)", fontsize=9.5)

    ax2 = fig.add_subplot(1, 3, 2, projection="3d")
    sheet = CurvedSheet("2*u - 1", "2*v - 1", "0.35*np.sin(np.pi*u)*np.sin(np.pi*v)", thickness=0.6)
    spts = sheet.sample_points(2200, np.random.default_rng(1))
    layers = LayerStackField(AnalyticField("z + 0.32"), thicknesses=[0.33, 0.33, 0.34], labels=[0, 1, 2])
    lab = layers.values(spts)[:, 0].astype(int)
    for k, col, name in ((0, "#0072B2", "layer 0"), (1, "#009E73", "layer 1"), (2, "#D55E00", "layer 2")):
        m = lab == k
        ax2.scatter(*spts[m].T, c=col, s=5, alpha=0.85, depthshade=False, label=name)
    ax2.legend(fontsize=7.5, loc="upper right", frameon=False)
    ax2.view_init(elev=24, azim=-45)
    ax2.set_xlabel("x"); ax2.set_ylabel("y"); ax2.set_zlabel("z")
    ax2.set_title("LayerStackField on CurvedSheet", fontsize=9.5)

    ax3 = fig.add_subplot(1, 3, 3)
    centres = np.asarray([[3.0, 3.0], [7.0, 7.0], [3.0, 7.0], [7.0, 3.0]])
    charges = np.asarray([0.5, 0.5, -0.5, -0.5])
    _, angles, _ = pinwheel_map((np.zeros(2), np.full(2, 10.0)), 0.1, centres, charges)
    found, ch = find_pinwheels(angles, [0.0, 0.0], 0.1)
    ax3.imshow(angles.T, origin="lower", extent=[0, 10, 0, 10], cmap="hsv", vmin=0.0, vmax=np.pi)
    pos_c = found[ch > 0]
    neg_c = found[ch < 0]
    ax3.scatter(pos_c[:, 0], pos_c[:, 1], s=75, c="white", edgecolors="black", linewidths=1.2, label="+1/2 pinwheel")
    ax3.scatter(neg_c[:, 0], neg_c[:, 1], s=75, c="black", marker="^", edgecolors="white", linewidths=1.0, label="-1/2 pinwheel")
    ax3.legend(fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2, frameon=False)
    ax3.set_xlabel("x"); ax3.set_ylabel("y")
    ax3.set_title("PinwheelField + find_pinwheels", fontsize=9.5)
    fig.tight_layout()
    save_png(fig, "fields_geometry_gallery.png", dpi=115)

    project = dict(
        geometry={
            "box": {"type": "Box", "center": [5.0, 5.0, 5.0], "size": [10.0, 10.0, 10.0]},
            "seed_zone": {"type": "Box", "center": [5.0, 5.0, 1.0], "size": [8.4, 8.4, 1.0]},
        },
        fields={"stop": {"type": "AnalyticField", "expr": "z - (0.4 * x + 2.8)"}},
        schedule=[
            {"name": "seed", "operator": "seed_cells", "params": {"N": 90, "geometry": "seed_zone"}},
            {"name": "migrate", "operator": "migrate", "repeat": 16,
             "params": {"direction": [0.0, 0.0, 1.0], "speed": 0.4,
                        "stop_field": {"type": "Field", "name": "stop"}, "boundary": "box"}},
        ],
    )
    cps = run_schedule(project, {}, seed=0, checkpoints=True)
    stop_fn = AnalyticField("z - (0.4 * x + 2.8)")
    xs = np.linspace(0.0, 10.0, 100)
    zs_stop = 0.4 * xs + 2.8
    frames, dur = [], []
    for k, t in enumerate(cps):
        fig, ax = plt.subplots(figsize=(5.8, 4.2))
        ax.plot(xs, zs_stop, ls="--", c="#D55E00", lw=1.6, label="stop_field = 0 (z = 0.4x + 2.8)")
        ax.fill_between(xs, zs_stop, 10.0, color="#D55E00", alpha=0.08)
        stopped = stop_fn.values(t.positions + np.array([0.0, 0.0, 0.4])) > 0
        ax.scatter(t.positions[~stopped, 0], t.positions[~stopped, 2], s=28, c="#0072B2", edgecolors="white",
                   linewidths=0.4, label="migrating")
        ax.scatter(t.positions[stopped, 0], t.positions[stopped, 2], s=28, c="#009E73", edgecolors="white",
                   linewidths=0.4, label="stopped")
        ax.set_xlim(0, 10); ax.set_ylim(0, 8.5)
        ax.set_xlabel("x"); ax.set_ylabel("z")
        ax.legend(fontsize=8, loc="upper left", frameon=False)
        ax.set_title(f"migrate + stop_field: step {k}/{len(cps) - 1} ({int(stopped.sum())}/{len(t.alive)} stopped)",
                     fontsize=10, loc="left")
        fig.tight_layout()
        frames.append(fig_to_image(fig, dpi=80))
        dur.append(280 if k < len(cps) - 1 else 2000)
    save_gif(frames, "migrate_stop_field.gif", dur, colours=64)


# --------------------------------------------------------------------------------------------------------------------
# 10. Synaptic plasticity: measured STDP curve + wave refinement + RF sharpening GIF
def make_plasticity():
    print("plasticity: STDPRule window + refine_by_activity waves + RF sharpening GIF")
    import jax.numpy as jnp
    from neurogenesis.spiking.plasticity import STDPRule
    from neurogenesis.stages import run_schedule

    # 1. Measure STDP curve across dt in [-60, 60] ms in a single batched apply() call
    rule = STDPRule(A_plus=1.0, A_minus=1.05, tau_plus=20.0, tau_minus=20.0, w_min=0.0, w_max=1000.0)
    dts = np.arange(-60, 61, 1)
    dts = dts[dts != 0]
    E = len(dts)
    T = 160
    spikes = np.zeros((T, 2 * E), dtype=np.float32)
    t_pre = 80
    for k, dt in enumerate(dts):
        spikes[t_pre, 2 * k] = 1.0
        spikes[t_pre + int(dt), 2 * k + 1] = 1.0
    w0 = jnp.full(E, 500.0, dtype=jnp.float32)
    pre = jnp.arange(0, 2 * E, 2, dtype=jnp.int32)
    post = jnp.arange(1, 2 * E, 2, dtype=jnp.int32)
    delays = jnp.zeros(E, dtype=jnp.int32)
    dw = np.asarray(rule.apply(w0, pre, post, delays, jnp.asarray(spikes), w0)) - 500.0

    # 2. Wave-driven refine_by_activity on a 1D topographic sensor -> map tissue
    n_src, n_dst = 30, 80
    src_pos = np.column_stack([np.linspace(1.0, 29.0, n_src), np.full(n_src, 15.0), np.zeros(n_src)])
    dst_pos = np.column_stack([np.linspace(1.0, 29.0, n_dst), np.full(n_dst, 15.0), np.full(n_dst, 10.0)])
    base_proj = dict(
        schedule=[
            {"name": "src", "operator": "place_by_hand", "params": {"positions": src_pos.tolist(), "region": 0, "sign": 1}},
            {"name": "dst", "operator": "place_by_hand", "params": {"positions": dst_pos.tolist(), "region": 1, "sign": 1}},
            {"name": "axons", "operator": "grow_axons", "params": {
                "projections": ["0->1"], "exact": True, "conduction_velocity": 5.0,
                "guidance": {"0->1": {"B": [[1.0, 0, 0], [0, 0, 0], [0, 0, 0]], "c": [0, 0, 0],
                                      "sigma": 0.35, "p0": 0.85, "w": 220.0}}}},
        ]
    )
    t_init = run_schedule(base_proj, {}, seed=0)
    w_before = np.abs(t_init.connectivity.weight.copy())

    refine_stage = {
        "name": "waves", "operator": "refine_by_activity",
        "params": {
            "rule": "stdp", "ticks": 220, "A_plus": 35.0, "A_minus": 38.0, "tau_plus": 20.0, "tau_minus": 20.0,
            "w_min": 0.0, "w_max": 600.0, "restore_modes": True,
            "waves": {"sources": [[0.0, 15.0, 0.0], [30.0, 15.0, 0.0]], "speed": 0.3, "interval": 110,
                      "duration": 4, "amplitude": 1500, "cells": {"region": [0]}},
        },
    }
    n_waves = 8
    wave_sched = {"schedule": base_proj["schedule"] + [dict(refine_stage, name=f"waves_{k}") for k in range(n_waves)]}
    cps = run_schedule(wave_sched, {}, seed=0, checkpoints=True)
    # checkpoints[2] is right after grow_axons; checkpoints[3:] are after each refine_by_activity step
    rf_cps = cps[2:]
    w_after = np.abs(rf_cps[-1].connectivity.weight.copy())

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 4.0))
    pos_m = dts > 0
    neg_m = dts < 0
    ax1.axhline(0, c="#888888", lw=0.8)
    ax1.axvline(0, c="#888888", lw=0.8)
    ax1.plot(dts[pos_m], dw[pos_m], c="#009E73", lw=2.2, label="LTP (post after pre)")
    ax1.plot(dts[neg_m], dw[neg_m], c="#D55E00", lw=2.2, label="LTD (post before pre)")
    ax1.set_xlabel(r"$\Delta t = t_{\mathrm{post}} - t_{\mathrm{pre}}$ (ms)")
    ax1.set_ylabel(r"Measured $\Delta w$ (weight units)")
    ax1.set_title("STDP window measured from STDPRule.apply", fontsize=10)
    ax1.legend(fontsize=8, frameon=False)

    bins = np.linspace(0, 600, 25)
    ax2.hist(w_before, bins=bins, alpha=0.55, color="#999999", edgecolor="white", label=f"before (mean {w_before.mean():.0f})")
    ax2.hist(w_after, bins=bins, alpha=0.65, color="#0072B2", edgecolor="white", label=f"after {n_waves} wave epochs (mean {w_after.mean():.0f})")
    ax2.set_xlabel("Synaptic weight |w|")
    ax2.set_ylabel("Number of synapses")
    ax2.set_title("Weight distribution before vs. after wave refinement", fontsize=10)
    ax2.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    save_png(fig, "plasticity_stdp_waves.png", dpi=115)

    frames, dur = [], []
    for k, t in enumerate(rf_cps):
        c = t.connectivity
        xs_pre = t.positions[c.pre, 0]
        xs_post = t.positions[c.post, 0]
        w = np.abs(c.weight).astype(float)
        # Weighted RF width (std of pre x per post neuron with weight > 0)
        stds = []
        for idx in np.flatnonzero(t.region == 1):
            m = c.post == idx
            if m.any() and w[m].sum() > 0:
                wm = w[m] / w[m].sum()
                mu = (wm * xs_pre[m]).sum()
                stds.append(np.sqrt((wm * (xs_pre[m] - mu) ** 2).sum()))
        rf_w = float(np.mean(stds)) if stds else 0.0
        fig, ax = plt.subplots(figsize=(5.4, 4.6))
        ax.plot([0, 30], [0, 30], ls="--", c="#bbbbbb", lw=0.9)
        order = np.argsort(w)
        sc = ax.scatter(xs_pre[order], xs_post[order], c=w[order], s=4 + 28 * (w[order] / 600.0),
                        cmap="viridis", vmin=0, vmax=600, alpha=0.85)
        ax.set_xlim(0, 30); ax.set_ylim(0, 30); ax.set_aspect("equal")
        ax.set_xlabel("sensor x position"); ax.set_ylabel("target x position")
        ax.set_title(f"Wave-driven STDP refinement: epoch {k}/{n_waves}\nmean RF width = {rf_w:.2f} space units", fontsize=9.5)
        fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.04, label="|w|")
        fig.tight_layout()
        frames.append(fig_to_image(fig, dpi=80))
        dur.append(450 if k < len(rf_cps) - 1 else 2200)
    save_gif(frames, "plasticity_rf_sharpening.gif", dur, colours=96)
    print(f"  STDP max LTP={dw[pos_m].max():.3f}, max LTD={dw[neg_m].min():.3f}; "
          f"mean |w| {w_before.mean():.1f} -> {w_after.mean():.1f}")


# --------------------------------------------------------------------------------------------------------------------
# 11. Layered sheet from progenitors (examples/layered_sheet.py)
def make_layered():
    print("layered: examples/layered_sheet.py checkpoints GIF")
    import importlib.util
    from neurogenesis.stages import run_schedule

    spec = importlib.util.spec_from_file_location("layered_sheet", ROOT / "examples" / "layered_sheet.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    proj = mod.build_project()
    d = proj.to_dict()
    cps = run_schedule(d, proj.genome, seed=42, checkpoints=True)
    labels = [(st["name"], st["operator"]) for st in d["schedule"] for _ in range(st.get("repeat", 1))]

    # Select key milestones to keep GIF crisp and concise
    pick = [0, 3, 6, 9, 10, 11, 12, 13, 14]
    type_colors = {0: "#0072B2", 1: "#009E73", 2: "#56B4E9", 3: "#D55E00"}
    type_names = {0: "deep exc", 1: "mid exc", 2: "sup exc", 3: "sup inh"}
    frames, dur = [], []
    for frame_k, idx in enumerate(pick):
        t = cps[idx]
        name, op = labels[idx]
        fig = plt.figure(figsize=(6.2, 5.0))
        ax = fig.add_axes([0.04, 0.06, 0.92, 0.82], projection="3d")
        pos, ct = t.positions, t.cell_type
        if t.connectivity is not None and len(t.connectivity.pre) > 0:
            c = t.connectivity
            rng = np.random.default_rng(0)
            s_idx = rng.choice(len(c.pre), size=min(len(c.pre), 250), replace=False)
            for a, b, w in zip(c.pre[s_idx], c.post[s_idx], c.weight[s_idx]):
                col = "#0072B2" if w > 0 else "#D55E00"
                ax.plot(*np.stack([pos[a], pos[b]]).T, color=col, lw=0.4, alpha=0.28)
        for tid in range(4):
            m = ct == tid
            if m.any():
                marker = "^" if tid == 3 else "o"
                ax.scatter(*pos[m].T, s=26 if tid == 3 else 20, c=type_colors[tid], marker=marker,
                           edgecolors="white", linewidths=0.3, depthshade=False, label=f"{type_names[tid]} ({int(m.sum())})")
        for z_b in (8.0, 16.0, 24.0):
            ax.plot([0, 40, 40, 0, 0], [0, 0, 40, 40, 0], [z_b] * 5, c="#cccccc", ls="--", lw=0.6)
        ax.set_xlim(0, 40); ax.set_ylim(0, 40); ax.set_zlim(-1, 25)
        ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_zlabel("z (layer)")
        ax.view_init(elev=18, azim=-40 + 5 * frame_k)
        ax.legend(fontsize=7.5, loc="upper left", frameon=False)
        n_syn = len(t.connectivity.pre) if t.connectivity is not None else 0
        ax.set_title(f"{frame_k + 1}/{len(pick)}: {name} ({op})\n{int(t.alive.sum())} cells, {n_syn} synapses",
                     fontsize=9.5, loc="left")
        frames.append(fig_to_image(fig, dpi=78))
        dur.append(1000 if idx < pick[-1] else 2500)
    save_gif(frames, "layered_sheet_stages.gif", dur, colours=96)


# --------------------------------------------------------------------------------------------------------------------
# 12. Connectome-constrained optic lobe comparison (examples/optic_lobe_column.py)
def make_optic():
    print("optic: examples/optic_lobe_column.py connectome vs fitted circuit")
    import importlib.util
    import neurogenesis.data.catalogue as cat
    from neurogenesis.data.importer import import_connectome
    from neurogenesis.data.targets import compare_type_statistics, extract_fitting_targets
    from neurogenesis.fitting import fit
    from neurogenesis.stages import run_schedule

    spec = importlib.util.spec_from_file_location("optic_lobe_column", ROOT / "examples" / "optic_lobe_column.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    WORK.mkdir(parents=True, exist_ok=True)
    target_dir = WORK / "mock_optic"
    hex_centres = mod.setup_mock_dataset(target_dir)
    orig_sha = cat.sha256
    cat.sha256 = lambda p: "mock1" if "neurons" in str(p) else "mock2"
    try:
        manifest_dict = json.loads((target_dir / "manifest.json").read_text())
        t_baseline, info = import_connectome(
            manifest_dict, directory=target_dir,
            transmitter_signs={"ACh": 1, "Glu": -1, "GABA": -1}, log=lambda s: None
        )
    finally:
        cat.sha256 = orig_sha

    targets = extract_fitting_targets(t_baseline, columns=hex_centres, min_synapses=1)
    fit_targets = [t for t in targets if t["metric"] != "cell_count"]
    project = mod.create_project(hex_centres, t_baseline, info)
    fit_res = fit(project, fit_targets, seeds=(0, 1), iterations=30, popsize=10)
    t_grown = run_schedule(project, fit_res.genome, seed=2)
    stats = compare_type_statistics(t_grown, t_baseline)

    type_names = info["type_names"]
    nt = len(type_names)

    def _mat(t):
        m = np.zeros((nt, nt), dtype=int)
        c = t.connectivity
        if c is not None and len(c.pre) > 0:
            for a, b in zip(t.cell_type[c.pre], t.cell_type[c.post]):
                m[a, b] += 1
        return m

    m_base = _mat(t_baseline)
    m_grown = _mat(t_grown)
    vmax = max(int(m_base.max()), int(m_grown.max()), 1)

    fig, axs = plt.subplots(1, 3, figsize=(12.0, 3.9))
    cols = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00")
    for k, name in enumerate(type_names):
        sel = t_baseline.cell_type == k
        axs[0].scatter(t_baseline.positions[sel, 0], t_baseline.positions[sel, 1], s=32 if name == "T4" else 18,
                       marker="^" if name == "T4" else "o", c=cols[k % len(cols)], label=f"{name} ({int(sel.sum())})")
    axs[0].legend(fontsize=7.5, loc="upper right", frameon=False)
    axs[0].set_aspect("equal")
    axs[0].set_xlabel("x (um)"); axs[0].set_ylabel("y (um)")
    axs[0].set_title(f"7 hexagonal columns\n({len(t_baseline.alive)} cells, {len(t_baseline.connectivity.pre)} edges)", fontsize=9.5)

    for ax, mat, title in ((axs[1], m_base, "Connectome type matrix"),
                           (axs[2], m_grown, f"Fitted grown matrix (seed 2)\ncos sim={stats['matrix_cosine_similarity']:.3f}, deg err={stats['degree_mean_rel_error']:.3f}")):
        ax.imshow(mat, cmap="Blues", vmin=0, vmax=vmax)
        ax.set_xticks(range(nt)); ax.set_xticklabels(type_names, fontsize=8)
        ax.set_yticks(range(nt)); ax.set_yticklabels(type_names, fontsize=8)
        ax.set_xlabel("post type"); ax.set_ylabel("pre type")
        ax.set_title(title, fontsize=9.5)
        for i in range(nt):
            for j in range(nt):
                v = mat[i, j]
                ax.text(j, i, str(v), ha="center", va="center", fontsize=8,
                        color="white" if v > 0.55 * vmax else "#222222")
    fig.tight_layout()
    save_png(fig, "optic_lobe_comparison.png", dpi=115)
    print(f"  optic stats: {stats}")
    print(f"  baseline edges={len(t_baseline.connectivity.pre)}, grown edges={len(t_grown.connectivity.pre)}")


# --------------------------------------------------------------------------------------------------------------------
# 13. Developmental knockouts on topographic_map across 50 held-out seeds
def make_knockouts():
    print("knockouts: 50 held-out seeds on examples/topographic_map.py")
    import copy
    from neurogenesis.development import grow, knockout, region_of

    make_plan, make_genome = topographic_example()
    plan = make_plan()
    base = make_genome()
    seeds = range(1000, 1050)

    def _conds():
        wt = copy.deepcopy(base)
        ko_x = copy.deepcopy(base); ko_x["guidance"][("sensor", "map")]["B"][0, 0] = 0.0
        ko_y = copy.deepcopy(base); ko_y["guidance"][("sensor", "map")]["B"][1, 1] = 0.0
        ko_xy = copy.deepcopy(base); ko_xy["guidance"][("sensor", "map")]["B"] = np.zeros((3, 3))
        broad = copy.deepcopy(base); broad["guidance"][("sensor", "map")]["sigma"] = 0.50
        return [("WT", wt), ("B[0,0]=0\n(x cue KO)", ko_x), ("B[1,1]=0\n(y cue KO)", ko_y),
                ("B=0\n(double KO)", ko_xy), ("sigma=0.50\n(broad arbor)", broad)]

    results = {}
    for label, g in _conds():
        rxs, rys = [], []
        for s in seeds:
            net = grow(plan, g, seed=s)
            src, tgt, _ = topography(net, region_of(net, plan, "sensor"), region_of(net, plan, "map"))
            rx = float(np.corrcoef(src[:, 0], tgt[:, 0])[0, 1]) if len(src) > 2 else 0.0
            ry = float(np.corrcoef(src[:, 1], tgt[:, 1])[0, 1]) if len(src) > 2 else 0.0
            rxs.append(rx); rys.append(ry)
        results[label] = (np.asarray(rxs), np.asarray(rys))
        print(f"  {label.replace(chr(10), ' ')}: r_x={np.mean(rxs):.3f}+-{np.std(rxs):.3f}, r_y={np.mean(rys):.3f}+-{np.std(rys):.3f}")

    # Verify structural projection knockout gives 0 synapses
    ko_proj = knockout(base, projections=[("sensor", "map")])
    assert grow(plan, ko_proj, seed=1000).num_synapses == 0

    fig, ax = plt.subplots(figsize=(8.6, 4.2))
    labels = list(results.keys())
    x = np.arange(len(labels))
    w = 0.34
    rx_m = [results[k][0].mean() for k in labels]
    rx_s = [results[k][0].std() for k in labels]
    ry_m = [results[k][1].mean() for k in labels]
    ry_s = [results[k][1].std() for k in labels]
    ax.bar(x - w / 2, rx_m, w, yerr=rx_s, capsize=3, color="#0072B2", alpha=0.85, label="r_x (horizontal axis)")
    ax.bar(x + w / 2, ry_m, w, yerr=ry_s, capsize=3, color="#D55E00", alpha=0.85, label="r_y (vertical axis)")
    rng = np.random.default_rng(0)
    for i, k in enumerate(labels):
        jx = rng.uniform(-0.07, 0.07, len(seeds))
        ax.scatter(x[i] - w / 2 + jx, results[k][0], s=8, c="#003f63", alpha=0.35, zorder=4)
        ax.scatter(x[i] + w / 2 + jx, results[k][1], s=8, c="#7a3200", alpha=0.35, zorder=4)
    ax.axhline(0, c="#777777", lw=0.8)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8.5)
    ax.set_ylim(-0.4, 1.12)
    ax.set_ylabel("Topographic Pearson correlation r")
    ax.set_title("Genetic knockouts across 50 held-out developmental seeds (1000–1049)", fontsize=10)
    ax.legend(fontsize=8.5, frameon=False, loc="upper right")
    fig.tight_layout()
    save_png(fig, "topographic_knockouts.png", dpi=115)


# --------------------------------------------------------------------------------------------------------------------
# 14. Shared ON/OFF module + composition with topographic map
def make_modules_demo():
    print("modules_demo: ON/OFF module + compose with topographic map")
    from neurogenesis.development import BodyPlan, FixedPlacement, Region, grow, region_of
    from neurogenesis.evolution.robust import audit
    from neurogenesis.modules import Module, compose
    from neurogenesis.spiking.batch import simulate_counts
    from neurogenesis.validation import validate_module

    pos_1d = [[(i + 0.5) / 12, 0.5, 0.5] for i in range(12)]
    on_off_plan = BodyPlan(
        name="on_off_sensory",
        regions=[
            Region("receptor", (0, 0, 0), (10, 30, 5), FixedPlacement(pos_1d), role=1),
            Region("inter", (15, 0, 0), (10, 30, 5), FixedPlacement(pos_1d), role=0),
            Region("on_out", (30, 0, 0), (10, 30, 5), FixedPlacement(pos_1d), role=2),
            Region("off_out", (30, 10, 0), (10, 30, 5), FixedPlacement(pos_1d), role=2),
        ],
        projections=[("receptor", "on_out"), ("receptor", "inter"), ("inter", "on_out"), ("receptor", "off_out")],
    )
    on_off_genome = dict(
        count={}, inh_weight_factor=2.0, w_clip=2047,
        inhibitory=dict(receptor=dict(a0=-8.0, a=np.zeros(3)), inter=dict(a0=8.0, a=np.zeros(3)),
                        on_out=dict(a0=-8.0, a=np.zeros(3)), off_out=dict(a0=-8.0, a=np.zeros(3))),
        tonic=dict(off_out=35.0),
        guidance={
            ("receptor", "on_out"): dict(B=np.eye(3) * 2.0, c=np.zeros(3), sigma=0.06, p0=1.0, w=900.0),
            ("receptor", "inter"): dict(B=np.eye(3) * 2.0, c=np.zeros(3), sigma=0.06, p0=1.0, w=900.0),
            ("inter", "on_out"): dict(B=np.eye(3) * 2.0, c=np.zeros(3), sigma=0.08, p0=1.0, w=500.0),
            ("receptor", "off_out"): dict(B=np.eye(3) * 2.0, c=np.zeros(3), sigma=0.06, p0=1.0, w=900.0,
                                          receptor="inverting"),
        },
    )
    assays = [
        {"name": "on_responds_to_step", "ticks": 80, "blank": 20, "seeds": [1000, 1001, 1002, 1003, 1004],
         "stimuli": [{}, {"receptor": 80}], "readout": {"region": "on_out", "measure": "rate"},
         "metric": "difference", "gate": {"min": 20.0}, "pass_fraction": 1.0},
        {"name": "off_suppressed_by_step", "ticks": 80, "blank": 20, "seeds": [1000, 1001, 1002, 1003, 1004],
         "stimuli": [{}, {"receptor": 80}], "readout": {"region": "off_out", "measure": "rate"},
         "metric": "difference", "gate": {"max": -20.0}, "pass_fraction": 1.0},
    ]
    on_off_mod = Module(
        "on_off_sensory", on_off_plan, on_off_genome,
        inputs=["receptor"], outputs=["on_out", "off_out"],
        description="12-channel sensory module: ON output excited by input, OFF output suppressed by inverting receptors.",
        validation={"assays": assays},
    )
    val_res = validate_module(on_off_mod)
    assert all(r["ok"] for r in val_res), val_res

    def eval_one(g, seeds):
        nets, exts, on_idx, off_idx = [], [], [], []
        for s in seeds:
            net = grow(on_off_plan, g, s)
            base = np.zeros(net.num_neurons, np.int32)
            base[region_of(net, on_off_plan, "off_out")] = 35
            ext = np.tile(base, (3, 1))
            ext[1, region_of(net, on_off_plan, "receptor")] += 80
            nets.append(net); exts.append(ext)
            on_idx.append(region_of(net, on_off_plan, "on_out"))
            off_idx.append(region_of(net, on_off_plan, "off_out"))
        cnts = simulate_counts(nets, exts, ticks=80, blank=20)
        on_r = [c[:, idx].mean(1) * 1000.0 / 80 for c, idx in zip(cnts, on_idx)]
        off_r = [c[:, idx].mean(1) * 1000.0 / 80 for c, idx in zip(cnts, off_idx)]
        score = np.array([(r_on[1] - r_on[0]) + (r_off[0] - r_off[1]) for r_on, r_off in zip(on_r, off_r)])
        return dict(score=score, passed=score > 50.0, on_rates=on_r, off_rates=off_r)

    aud = audit(eval_one, on_off_genome, seeds=range(1000, 1010), keep=("on_rates", "off_rates"))
    on_r_arr = np.asarray(aud["on_rates"])   # (10, 3)
    off_r_arr = np.asarray(aud["off_rates"]) # (10, 3)

    make_topo_plan, make_topo_genome = topographic_example()
    topo_mod = Module("topographic_map", make_topo_plan(), make_topo_genome(), inputs=["sensor"], outputs=["map"])
    brain = compose(
        "sensory+map", {"eye": on_off_mod, "cortex": topo_mod},
        offsets={"cortex": (60.0, 0.0, 0.0)},
        links=[("eye.on_out", "cortex.sensor", dict(B=np.eye(3) * 2.0, c=np.zeros(3), sigma=0.15, p0=0.9, w=800.0))],
    )
    cnet = brain.grow(seed=0)
    rec = region_of(cnet, brain.plan, "eye.receptor")
    cmap = region_of(cnet, brain.plan, "cortex.map")
    u_map = np.asarray([(cnet.neurons[i].x - 110.0) / 30.0 for i in cmap])
    ext_c = np.zeros((2, cnet.num_neurons), np.int32)
    ext_c[0, rec[:4]] = 90
    ext_c[1, rec[-4:]] = 90
    c_cnt = simulate_counts([cnet], [ext_c], ticks=80, blank=20)[0][:, cmap]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 4.0))
    epochs = np.arange(3)
    ax1.errorbar(epochs, on_r_arr.mean(0), yerr=on_r_arr.std(0), marker="o", lw=2, c="#0072B2", capsize=3, label="on_out rate")
    ax1.errorbar(epochs, off_r_arr.mean(0), yerr=off_r_arr.std(0), marker="s", lw=2, c="#D55E00", capsize=3, label="off_out rate")
    ax1.set_xticks(epochs); ax1.set_xticklabels(["1. Baseline\n(I=0)", "2. Step ON\n(I=80)", "3. Step OFF\n(I=0)"])
    ax1.set_ylabel("Mean population rate (Hz)")
    ax1.set_title(f"ON/OFF module across 10 held-out seeds\n(audit pass fraction = {aud['pass_fraction']:.2f})", fontsize=9.5)
    ax1.legend(fontsize=8.5, frameon=False)

    bins = np.linspace(0, 1, 11)
    centres = 0.5 * (bins[:-1] + bins[1:])
    for k, col, lab in ((0, "#0072B2", "stimulate low receptors (0..3)"), (1, "#D55E00", "stimulate high receptors (8..11)")):
        rates = np.zeros(len(centres))
        for b in range(len(centres)):
            m = (u_map >= bins[b]) & (u_map <= bins[b + 1])
            rates[b] = c_cnt[k, m].mean() * 1000.0 / 80 if m.any() else 0.0
        ax2.plot(centres, rates, marker="o", lw=2, c=col, label=lab)
    ax2.set_xlabel("Normalized cortex.map x position (u)")
    ax2.set_ylabel("Mean map firing rate (Hz)")
    ax2.set_title("Composed eye.on_out -> cortex.sensor -> cortex.map", fontsize=9.5)
    ax2.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    save_png(fig, "shared_module_composition.png", dpi=115)
    print(f"  ON rates: {on_r_arr.mean(0).round(1).tolist()}, OFF rates: {off_r_arr.mean(0).round(1).tolist()}")
    print(f"  assay results: {[(r['name'], r['pass_fraction']) for r in val_res]}")


# --------------------------------------------------------------------------------------------------------------------
# 15. Quantitative 100-seed topographic map study
def make_topo_study():
    print("topo_study: 100-seed sweep over sigma, N_map, and activity refinement")
    import copy
    import jax
    import jax.numpy as jnp
    from neurogenesis.development import grow, region_of
    from neurogenesis.spiking import jax_backend
    from neurogenesis.spiking.batch import stack
    from neurogenesis.stages.refinement import coactivity

    make_plan, make_genome = topographic_example()
    plan = make_plan()
    base = make_genome()
    seeds = range(100)
    sigmas = [0.05, 0.08, 0.12, 0.18, 0.25, 0.35, 0.50]

    def _mean_r(nets):
        rs = []
        for net in nets:
            src, tgt, _ = topography(net, region_of(net, plan, "sensor"), region_of(net, plan, "map"))
            if len(src) > 2:
                rs.append(0.5 * (np.corrcoef(src[:, 0], tgt[:, 0])[0, 1] + np.corrcoef(src[:, 1], tgt[:, 1])[0, 1]))
            else:
                rs.append(0.0)
        return np.asarray(rs)

    _jit_wave = {}

    def _refine_batch(nets, ticks=120):
        # Simulate travelling sweeps across sensor sheet in one batched JAX call per bucket, then filter via coactivity
        arr, N_pad = stack(nets)
        T = ticks
        ext = np.zeros((len(nets), T, N_pad), dtype=np.int32)
        s_idx = region_of(nets[0], plan, "sensor")
        for b, net in enumerate(nets):
            xs = np.array([net.neurons[i].x for i in s_idx]) / 30.0
            ys = np.array([net.neurons[i].y for i in s_idx]) / 30.0
            for t in range(T):
                phase = (t % 60) / 60.0
                active = (np.abs(xs - phase) < 0.12) if t < 60 else (np.abs(ys - phase) < 0.12)
                ext[b, t, s_idx[active]] = 180

        def run_one(a, ext_seq, seed):
            st = jax_backend.init_state(a, seed)

            def step(s, e):
                s, spk, _ = jax_backend.tick(a, s, e)
                return s, spk
            _, spk_all = jax.lax.scan(step, st, ext_seq)
            return spk_all

        if T not in _jit_wave:
            _jit_wave[T] = jax.jit(jax.vmap(run_one))
        spikes_batch = np.asarray(_jit_wave[T](arr, jnp.asarray(ext), jnp.arange(len(nets), dtype=jnp.uint32)))
        refined_rs = []
        for b, net in enumerate(nets):
            n_real = net.num_neurons
            spk = spikes_batch[b, :, :n_real]
            pre = np.array([s.pre for s in net.synapses], dtype=np.int32)
            post = np.array([s.post for s in net.synapses], dtype=np.int32)
            dly = np.array([s.delay for s in net.synapses], dtype=np.int32)
            co = coactivity(spk, pre, post, dly, window=10).astype(float)
            # Keep synapses whose coactivity is at least the mean coactivity of that presynaptic sensor
            keep = np.zeros(len(pre), dtype=bool)
            for si in s_idx:
                m = pre == si
                if m.any():
                    thr = max(1.0, float(np.mean(co[m])))
                    keep[m] = co[m] >= thr
            if keep.any():
                xy = np.asarray([[n.x, n.y] for n in net.neurons])
                src_xy, tgt_xy = [], []
                for si in s_idx:
                    m = (pre == si) & keep
                    if m.any():
                        t_idx = post[m]
                        wm = np.maximum(co[m], 1.0)
                        src_xy.append(xy[si] / 30.0)
                        tgt_xy.append(((xy[t_idx] - [50.0, 0.0]) / 30.0 * wm[:, None]).sum(0) / wm.sum())
                if len(src_xy) > 2:
                    s_a, t_a = np.asarray(src_xy), np.asarray(tgt_xy)
                    refined_rs.append(0.5 * (np.corrcoef(s_a[:, 0], t_a[:, 0])[0, 1] + np.corrcoef(s_a[:, 1], t_a[:, 1])[0, 1]))
                else:
                    refined_rs.append(0.0)
            else:
                refined_rs.append(0.0)
        return np.asarray(refined_rs)

    r_raw_m, r_raw_s, r_ref_m, r_ref_s = [], [], [], []
    for sig in sigmas:
        g = copy.deepcopy(base)
        g["guidance"][("sensor", "map")]["sigma"] = sig
        nets = [grow(plan, g, seed=s) for s in seeds]
        rr = _mean_r(nets)
        rf = _refine_batch(nets)
        r_raw_m.append(rr.mean()); r_raw_s.append(rr.std())
        r_ref_m.append(rf.mean()); r_ref_s.append(rf.std())
        print(f"  sigma={sig:.2f}: raw r={rr.mean():.3f}+-{rr.std():.3f}, refined r={rf.mean():.3f}+-{rf.std():.3f}")

    counts = [50, 100, 200, 400]
    cnt_m, cnt_s = [], []
    for nc in counts:
        g = copy.deepcopy(base)
        g["count"]["map"] = nc
        nets = [grow(plan, g, seed=s) for s in seeds]
        rr = _mean_r(nets)
        cnt_m.append(rr.mean()); cnt_s.append(rr.std())
        print(f"  N_map={nc}: r={rr.mean():.3f}+-{rr.std():.3f}")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 4.0))
    ax1.errorbar(sigmas, r_raw_m, yerr=r_raw_s, marker="o", lw=2, c="#0072B2", capsize=3, label="chemoaffinity alone")
    ax1.errorbar(sigmas, r_ref_m, yerr=r_ref_s, marker="s", lw=2, c="#009E73", capsize=3, label="after STDP wave refinement + prune")
    ax1.set_xlabel(r"Arbor spread $\sigma$")
    ax1.set_ylabel("Topographic Pearson r (mean ± SD, 100 seeds)")
    ax1.set_ylim(0.55, 1.02)
    ax1.set_title("Precision vs. arbor spread (N_map = 200)", fontsize=10)
    ax1.legend(fontsize=8.5, frameon=False, loc="lower left")

    ax2.errorbar(counts, cnt_m, yerr=cnt_s, marker="o", lw=2, c="#D55E00", capsize=3)
    ax2.set_xlabel("Number of map cells N_map")
    ax2.set_ylabel("Topographic Pearson r (mean ± SD, 100 seeds)")
    ax2.set_ylim(0.85, 1.01)
    ax2.set_xscale("log"); ax2.set_xticks(counts); ax2.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax2.set_title("Precision vs. target population size (sigma = 0.12)", fontsize=10)
    fig.tight_layout()
    save_png(fig, "topographic_study_100seeds.png", dpi=115)


TASKS = dict(cli=make_cli, topo=make_topo, models=make_models, fi=make_fi, cost=make_cost, evo=make_evo,
             stages=make_stages, retino=make_retino, fields=make_fields, plasticity=make_plasticity,
             layered=make_layered, optic=make_optic, knockouts=make_knockouts,
             modules_demo=make_modules_demo, topo_study=make_topo_study)

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name in (sys.argv[1:] or TASKS):
        TASKS[name]()
