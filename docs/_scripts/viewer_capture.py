"""Screenshots and a short GIF of the browser viewer (viz/) with exported networks loaded, captured headless.

Needs Playwright for Python and its Chromium (pip install playwright && python -m playwright install chromium) and
Node 20 with viz/node_modules installed. Run from the repository root, after make_media.py (which writes the network
JSON files into docs/_scripts/_work/):

    python docs/_scripts/viewer_capture.py

Starts the viewer's Vite dev server (viz/, port 5199), opens http://localhost:5199/?no-modal in headless Chromium with
software WebGL (SwiftShader), loads networks through the viewer's own import function (window.__snn.importNetwork, the
same function as the "Import" button and drag-and-drop), and writes to docs/_static/media/:
    viewer_network.png  the grown topographic map (examples/topographic_map.py, seed 0)
    viewer_raster.png   the CLI column (generate --neurons 500 --weight-scale 0.2 --refractory 3 --seed 42) running
    viewer_rotate.gif   the same column running while the camera orbits around it (about 4 s)
The viewer's own simulation runs in the browser (integer kernel, Poisson drivers of the network); nothing is injected.
"""
from __future__ import annotations

import io
import json
import math
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "_static" / "media"
WORK = ROOT / "docs" / "_scripts" / "_work"
PORT = 5199
URL = f"http://localhost:{PORT}/?no-modal"


def node_env():
    env = dict(os.environ)
    nvm = Path.home() / ".nvm" / "versions" / "node"
    if shutil.which("npx", path=env.get("PATH")) is None and nvm.exists():
        env["PATH"] = str(sorted(nvm.iterdir())[-1] / "bin") + os.pathsep + env["PATH"]
    return env


def wait_http(url, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"viewer did not start at {url}")


def load(page, path):
    net = json.loads(Path(path).read_text())
    page.evaluate("net => window.__snn.importNetwork(net)", net)
    return net


def set_camera(page, target, pos):
    page.evaluate("""([t, p]) => { const sm = window.__snn.sceneManager;
        sm.controls.target.set(t[0], t[1], t[2]); sm.camera.position.set(p[0], p[1], p[2]);
        sm.camera.lookAt(t[0], t[1], t[2]); sm.controls.update(); }""", [target, pos])


def shot(page, clip=None):
    return Image.open(io.BytesIO(page.screenshot(clip=clip))).convert("RGB")


def save_png(im, name, colours=160):
    path = OUT / name
    im.quantize(colors=colours, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)
    print(f"  wrote {path.relative_to(ROOT)} ({path.stat().st_size / 1024:.0f} KB)")


def main():
    print("starting the viewer dev server", flush=True)
    for f in ("topographic_network.json", "cli_column_500.json"):
        if not (WORK / f).exists():
            sys.exit(f"missing {WORK / f}: run docs/_scripts/make_media.py cli topo first")
    server = subprocess.Popen(["npx", "vite", "--port", str(PORT), "--strictPort"], cwd=ROOT / "viz", env=node_env(),
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_http(f"http://localhost:{PORT}/")
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--use-angle=swiftshader", "--use-gl=angle", "--enable-unsafe-swiftshader",
                                              "--ignore-gpu-blocklist"])
            page = browser.new_page(viewport={"width": 1100, "height": 720})
            page.on("console", lambda m: m.type == "error" and print("  [browser error]", m.text))
            page.goto(URL)
            page.wait_for_function("window.__snn !== undefined", timeout=60000)
            page.wait_for_timeout(1500)

            # 1. the grown topographic map (sensor sheet x 0-30, map x 50-80)
            load(page, WORK / "topographic_network.json")
            page.check("#check-global-syn")                         # draw every synapse
            set_camera(page, [70, 15, 5], [70, -60, 110])
            page.wait_for_timeout(2500)
            save_png(shot(page), "viewer_network.png")

            # 2. a CLI-generated column with Poisson drivers, running in the viewer
            net = load(page, WORK / "cli_column_500.json")
            ys = [n["y"] for n in net["neurons"]]
            cy = (min(ys) + max(ys)) / 2
            page.uncheck("#check-global-syn")
            set_camera(page, [90, cy, 0], [90, cy + 40, 330])
            page.wait_for_timeout(20000)                      # let the scrolling raster fill its width
            save_png(shot(page), "viewer_raster.png")

            # 3. orbit while it runs
            frames = []
            n_fr = 30
            clip = dict(x=0, y=150, width=730, height=390)       # the 3D view only, left of the inspector panel
            t0 = time.time()
            for k in range(n_fr):
                a = 2 * math.pi * k / n_fr
                set_camera(page, [0, cy, 0], [300 * math.sin(a), cy + 40, 300 * math.cos(a)])
                page.wait_for_timeout(40)
                im = shot(page, clip)
                frames.append(im.resize((im.width * 3 // 4, im.height * 3 // 4), Image.LANCZOS))
                print(f"  frame {k + 1}/{n_fr} ({time.time() - t0:.0f} s)", flush=True)
            browser.close()
        pal = frames[0].quantize(colors=96, method=Image.Quantize.MEDIANCUT)
        q = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
        path = OUT / "viewer_rotate.gif"
        q[0].save(path, save_all=True, append_images=q[1:], duration=130, loop=0, optimize=True)
        print(f"  wrote {path.relative_to(ROOT)} ({path.stat().st_size / 1024:.0f} KB, {len(q)} frames)")
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    main()
