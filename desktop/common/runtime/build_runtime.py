"""Builds a relocatable Python with neurogenesis-sim and its dependencies, for embedding in a desktop app.

    python desktop/common/runtime/build_runtime.py --target macos-x86_64 --out build/runtime

Shared by the three apps (macOS, Windows, Linux). The steps:
1. Download a relocatable CPython (python-build-standalone, "install_only_stripped") for the target. The release is
   pinned, and the archive is checked against the release's SHA256SUMS and cached in ~/.cache/neurogenesis/runtime.
2. Build the toolbox wheel from this checkout and install it, with numpy, jax, jaxlib and matplotlib, into that
   Python. For the build machine's own target, the runtime's pip installs them. For another target, the host pip
   installs binary wheels for that platform (--platform / --target).
3. Remove test suites and caches; on macOS, strip local symbols from large extension modules (jaxlib: -110 MB) and
   re-sign them ad hoc (Apple Silicon runs only signed code). On native builds, precompile the bytecode (the app's
   first start is then fast) and smoke-test `python -m neurogenesis.bridge`. Write runtime.json (what is inside).
The result is <out>/python/, which runs from any folder. Apps start the bridge with <out>/python/bin/python3
(Windows: <out>/python/python.exe) -m neurogenesis.bridge.

Only the standard library is used, so any Python 3.9+ can run this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

RELEASE = "20261013"            # python-build-standalone release (pinned: change deliberately, then rebuild and test)
PYTHON = "3.12"                 # minor version: jaxlib must publish wheels for it on every target
BASE_URL = "https://github.com/astral-sh/python-build-standalone/releases/download"
PACKAGES = ["jaxlib"]           # the toolbox wheel brings numpy, jax and matplotlib; jax needs jaxlib to run

TARGETS = {
    # name: (python-build-standalone triple, pip platform tags, interpreter path inside python/, site-packages)
    "macos-x86_64": ("x86_64-apple-darwin", ["macosx_14_0_x86_64"], "bin/python3", "lib/python{v}/site-packages"),
    "macos-arm64": ("aarch64-apple-darwin", ["macosx_14_0_arm64"], "bin/python3", "lib/python{v}/site-packages"),
    "linux-x86_64": ("x86_64-unknown-linux-gnu", ["manylinux_2_28_x86_64", "manylinux_2_17_x86_64", "manylinux2014_x86_64"],
                     "bin/python3", "lib/python{v}/site-packages"),
    "linux-arm64": ("aarch64-unknown-linux-gnu", ["manylinux_2_28_aarch64", "manylinux_2_17_aarch64", "manylinux2014_aarch64"],
                    "bin/python3", "lib/python{v}/site-packages"),
    "windows-x86_64": ("x86_64-pc-windows-msvc", ["win_amd64"], "python.exe", "Lib/site-packages"),
}
CACHE = Path(os.environ.get("NEUROGENESIS_CACHE", Path.home() / ".cache" / "neurogenesis")) / "runtime"
PRUNE_DIRS = {"tests", "test", "__pycache__", "idle_test"}


def host_target() -> str:
    system = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(platform.system(), "?")
    machine = platform.machine().lower()
    arch = {"x86_64": "x86_64", "amd64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}.get(machine, machine)
    return f"{system}-{arch}"


def fetch(url: str, dest: Path) -> Path:
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {url}")
        tmp = dest.with_suffix(dest.suffix + ".part")
        with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        tmp.replace(dest)
    return dest


def locate_archive(triple: str, release: str, python: str) -> tuple[str, str]:
    """Name and SHA-256 of the install_only_stripped archive for this triple and Python minor version."""
    sums = fetch(f"{BASE_URL}/{release}/SHA256SUMS", CACHE / release / "SHA256SUMS").read_text().splitlines()
    for line in sums:
        digest, _, name = line.strip().partition("  ")
        name = name.strip() or line.split()[-1]
        if (name.startswith(f"cpython-{python}.") and name.endswith(f"+{release}-{triple}-install_only_stripped.tar.gz")):
            return name, digest.split()[0]
    raise SystemExit(f"no CPython {python} for {triple} in release {release}")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract(archive: Path, out: Path) -> Path:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    with tarfile.open(archive) as t:
        members = [m for m in t.getmembers() if not (m.name.startswith("/") or ".." in Path(m.name).parts)]
        if sys.version_info >= (3, 12):
            t.extractall(out, members=members, filter="tar")
        else:
            t.extractall(out, members=members)
    return out / "python"


def run(cmd, **kw):
    print("+", " ".join(map(str, cmd)))
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def prune(root: Path) -> None:
    """Removes test suites and caches of the installed packages, and the standard library's own test suite."""
    for d in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if not d.is_dir():
            continue
        in_packages = "site-packages" in d.parts and d.name in PRUNE_DIRS
        stdlib_tests = d.name == "test" and d.parent.name.lower().startswith(("python3", "lib"))
        if in_packages or stdlib_tests:
            shutil.rmtree(d, ignore_errors=True)


def strip_macos(root: Path, min_bytes: int = 1 << 20) -> None:
    """strip -x (local symbols only; exported ones stay) and an ad-hoc signature on large Mach-O libraries."""
    for f in list(root.rglob("*.so")) + list(root.rglob("*.dylib")):
        if f.is_file() and not f.is_symlink() and f.stat().st_size >= min_bytes:
            subprocess.run(["strip", "-x", str(f)], check=True, capture_output=True)
            subprocess.run(["codesign", "--force", "--sign", "-", str(f)], check=True, capture_output=True)


def size(root: Path) -> int:
    return sum(f.stat().st_size for f in root.rglob("*") if f.is_file() and not f.is_symlink())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--target", default=host_target(), choices=sorted(TARGETS))
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--release", default=RELEASE)
    ap.add_argument("--python", default=PYTHON)
    ap.add_argument("--toolbox", type=Path, default=Path(__file__).resolve().parents[3], help="neurogenesis-sim checkout")
    args = ap.parse_args()
    triple, tags, exe, sp = TARGETS[args.target]
    native = args.target == host_target()

    name, digest = locate_archive(triple, args.release, args.python)
    archive = fetch(f"{BASE_URL}/{args.release}/{name.replace('+', '%2B')}", CACHE / args.release / name)
    if sha256(archive) != digest:
        archive.unlink()
        raise SystemExit(f"{name}: SHA-256 mismatch (download removed; try again)")
    py = extract(archive, args.out.resolve())
    site = py / sp.format(v=args.python)

    leftovers = [args.toolbox / "build", *args.toolbox.glob("*.egg-info")]
    existed = {p for p in leftovers if p.exists()}
    with tempfile.TemporaryDirectory() as tmp:
        run([sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", tmp, args.toolbox])
        for p in [args.toolbox / "build", *args.toolbox.glob("*.egg-info")]:     # setuptools builds in the checkout
            if p not in existed:
                shutil.rmtree(p, ignore_errors=True)
        wheel = next(Path(tmp).glob("neurogenesis_sim-*.whl"))
        if native:
            run([py / exe, "-m", "pip", "install", "--no-warn-script-location", "--disable-pip-version-check", wheel, *PACKAGES])
        else:
            plat = [x for t in tags for x in ("--platform", t)]
            run([sys.executable, "-m", "pip", "install", "--target", site, "--upgrade", "--only-binary=:all:", *plat,
                 "--python-version", args.python, "--implementation", "cp", "--disable-pip-version-check", wheel, *PACKAGES])
    prune(py)
    if args.target.startswith("macos") and platform.system() == "Darwin":
        strip_macos(py)

    manifest = dict(target=args.target, triple=triple, python=name.split("+")[0].removeprefix("cpython-"),
                    release=args.release, archive=name, sha256=digest, native_build=native, interpreter=exe)
    if native:
        run([py / exe, "-m", "compileall", "-q", "-j", "0", py / ("Lib" if exe.endswith(".exe") else "lib")], stdout=subprocess.DEVNULL)
        env = {**os.environ, "JAX_PLATFORMS": "cpu", "PYTHONNOUSERSITE": "1"}
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        r = subprocess.run([str(py / exe), "-m", "neurogenesis.bridge"], input='{"id": 1, "method": "ping"}\n',
                           capture_output=True, text=True, env=env, timeout=600, cwd=tempfile.gettempdir())
        if '"result": "pong"' not in r.stdout:
            raise SystemExit(f"bridge smoke test failed:\n{r.stdout}\n{r.stderr[-3000:]}")
        freeze = subprocess.run([str(py / exe), "-m", "pip", "list", "--format=json", "--disable-pip-version-check"],
                                capture_output=True, text=True, env=env, check=True).stdout
        manifest["packages"] = {p["name"]: p["version"] for p in json.loads(freeze)}
    else:
        manifest["packages"] = {d.name.split("-")[0]: d.name.split("-")[1].removesuffix(".dist-info")
                                for d in site.glob("*.dist-info")}
    manifest["bytes"] = size(py)
    (args.out / "runtime.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"runtime for {args.target}: {py} ({manifest['bytes'] / 2**20:.0f} MB), python {manifest['python']}, "
          f"jax {manifest['packages'].get('jax', '?')}, numpy {manifest['packages'].get('numpy', '?')}")


if __name__ == "__main__":
    main()
