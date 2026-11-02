"""Builds a relocatable Python with neurogenesis-sim and its dependencies, for embedding in a desktop app.

    python desktop/common/runtime/build_runtime.py --target macos-x86_64 --out build/runtime

Shared by the three apps (macOS, Windows, Linux). The steps:
1. Download a relocatable CPython (python-build-standalone, "install_only_stripped") for the target. The archive name
   and SHA-256 per target are committed in pins.json (never taken from the download site at build time); archives
   are cached in ~/.cache/neurogenesis/runtime.
2. Install the packages of locks/<target>.txt (exact versions and wheel SHA-256s, pip --require-hashes --no-deps),
   then the toolbox wheel built from this checkout (--no-deps). For the build machine's own target, the runtime's pip
   installs them. For another target, the host pip installs that platform's wheels (--platform / --target).
3. Remove test suites and caches; on macOS, keep only the target's slice of universal2 binaries, strip local symbols
   from large extension modules (jaxlib: -110 MB), and re-sign what changed ad hoc (Apple Silicon runs only signed
   code). On native builds, precompile the bytecode (the app's
   first start is then fast) and smoke-test `python -m neurogenesis.bridge`. Write runtime.json (what is inside).
The result is <out>/python/, which runs from any folder. Apps start the bridge with <out>/python/bin/python3
(Windows: <out>/python/python.exe) -m neurogenesis.bridge.

Only the standard library is used, so any Python 3.9+ can run this script.

    python desktop/common/runtime/build_runtime.py --lock      (maintainers: re-pin CPython and re-lock every target)
--lock resolves requirements.in for every target (pip 23.1+ with --report), writes locks/<target>.txt and pins.json
from the pinned RELEASE's SHA256SUMS. Review the diff, then rebuild and test the runtimes.
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

RELEASE = "20261013"            # python-build-standalone release (pinned: change deliberately, then --lock, rebuild, test)
PYTHON = "3.12"                 # minor version: jaxlib must publish wheels for it on every target
BASE_URL = "https://github.com/astral-sh/python-build-standalone/releases/download"
HERE = Path(__file__).resolve().parent
PINS = HERE / "pins.json"       # {"release", "python", "archives": {target: {"name", "sha256"}}}
LOCKS = HERE / "locks"          # <target>.txt: pinned requirements with hashes
REQUIREMENTS = HERE / "requirements.in"

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


def archive_from_sums(triple: str, release: str, python: str) -> tuple[str, str]:
    """Name and SHA-256 of the install_only_stripped archive for this triple, from the release's SHA256SUMS (used only
    by --lock, to pin)."""
    sums = fetch(f"{BASE_URL}/{release}/SHA256SUMS", CACHE / release / "SHA256SUMS").read_text().splitlines()
    for line in sums:
        parts = line.split()
        if len(parts) == 2:
            digest, name = parts
            if name.startswith(f"cpython-{python}.") and name.endswith(f"+{release}-{triple}-install_only_stripped.tar.gz"):
                return name, digest
    raise SystemExit(f"no CPython {python} for {triple} in release {release}")


def pinned_archive(target: str) -> tuple[str, str, str]:
    """(release, archive name, SHA-256) committed for a target in pins.json."""
    pins = json.loads(PINS.read_text())
    if target not in pins["archives"]:
        raise SystemExit(f"{target} is not pinned in {PINS.name}: run --lock")
    a = pins["archives"][target]
    return pins["release"], a["name"], a["sha256"]


def lock() -> None:
    """Pins the CPython archives of RELEASE and locks requirements.in for every target, with hashes."""
    pins = dict(release=RELEASE, python=PYTHON, archives={})
    LOCKS.mkdir(exist_ok=True)
    for target, (triple, tags, _, _) in sorted(TARGETS.items()):
        name, digest = archive_from_sums(triple, RELEASE, PYTHON)
        pins["archives"][target] = dict(name=name, sha256=digest)
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.json"
            plat = [x for t in tags for x in ("--platform", t)]
            run([sys.executable, "-m", "pip", "install", "--dry-run", "--ignore-installed", "--quiet", "--report", report,
                 "--target", Path(tmp) / "t", "--only-binary=:all:", *plat, "--python-version", PYTHON,
                 "--implementation", "cp", "--abi", "cp" + PYTHON.replace(".", ""), "--disable-pip-version-check",
                 "-r", REQUIREMENTS])
            items = json.loads(report.read_text())["install"]
        lines = [f"# {target}: generated by build_runtime.py --lock from requirements.in; do not edit"]
        for it in sorted(items, key=lambda i: i["metadata"]["name"].lower()):
            h = it["download_info"]["archive_info"]["hashes"]["sha256"]
            lines.append(f"{it['metadata']['name']}=={it['metadata']['version']} --hash=sha256:{h}")
        (LOCKS / f"{target}.txt").write_text("\n".join(lines) + "\n")
        print(f"{target}: {name}, {len(items)} packages")
    PINS.write_text(json.dumps(pins, indent=1) + "\n")


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


def macho_files(root: Path):
    """Mach-O files: libraries, extension modules and the interpreter's executables."""
    for f in root.rglob("*"):
        if f.is_file() and not f.is_symlink() and (f.suffix in (".so", ".dylib") or (f.parent.name == "bin" and os.access(f, os.X_OK))):
            with open(f, "rb") as h:
                magic = h.read(4)
            if magic in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"):
                yield f


def thin_and_strip_macos(root: Path, arch: str, min_bytes: int = 1 << 20) -> None:
    """Keeps only the target's slice of universal2 binaries (lipo -thin: some wheels ship both architectures), strips
    local symbols from large ones (strip -x; exported symbols stay), and re-signs every changed file ad hoc (Apple
    Silicon runs only signed code)."""
    for f in macho_files(root):
        changed = False
        archs = subprocess.run(["lipo", "-archs", str(f)], capture_output=True, text=True).stdout.split()
        if len(archs) > 1:
            if arch not in archs:
                raise SystemExit(f"{f}: no {arch} code (has {' '.join(archs)})")
            tmp = f.with_name(f.name + ".thin")
            subprocess.run(["lipo", "-thin", arch, str(f), "-output", str(tmp)], check=True, capture_output=True)
            os.chmod(tmp, f.stat().st_mode)
            tmp.replace(f)
            changed = True
        if f.suffix in (".so", ".dylib") and f.stat().st_size >= min_bytes:
            subprocess.run(["strip", "-x", str(f)], check=True, capture_output=True)
            changed = True
        if changed:
            subprocess.run(["codesign", "--force", "--sign", "-", str(f)], check=True, capture_output=True)


def size(root: Path) -> int:
    return sum(f.stat().st_size for f in root.rglob("*") if f.is_file() and not f.is_symlink())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--target", default=host_target(), choices=sorted(TARGETS))
    ap.add_argument("--out", type=Path)
    ap.add_argument("--toolbox", type=Path, default=Path(__file__).resolve().parents[3], help="neurogenesis-sim checkout")
    ap.add_argument("--lock", action="store_true", help="re-pin CPython and re-lock the packages of every target")
    args = ap.parse_args()
    if args.lock:
        return lock()
    if args.out is None:
        ap.error("--out is required")
    triple, tags, exe, sp = TARGETS[args.target]
    native = args.target == host_target()
    release, name, digest = pinned_archive(args.target)
    python = json.loads(PINS.read_text())["python"]
    lockfile = LOCKS / f"{args.target}.txt"

    archive = fetch(f"{BASE_URL}/{release}/{name.replace('+', '%2B')}", CACHE / release / name)
    if sha256(archive) != digest:
        archive.unlink()
        raise SystemExit(f"{name}: SHA-256 differs from {PINS.name} (download removed)")
    py = extract(archive, args.out.resolve())
    site = py / sp.format(v=python)

    leftovers = [args.toolbox / "build", *args.toolbox.glob("*.egg-info")]
    existed = {p for p in leftovers if p.exists()}
    with tempfile.TemporaryDirectory() as tmp:
        run([sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", tmp, args.toolbox])
        for p in [args.toolbox / "build", *args.toolbox.glob("*.egg-info")]:     # setuptools builds in the checkout
            if p not in existed:
                shutil.rmtree(p, ignore_errors=True)
        wheel = next(Path(tmp).glob("neurogenesis_sim-*.whl"))
        locked = ["--require-hashes", "--no-deps", "--only-binary=:all:", "-r", lockfile]
        if native:
            pip = [py / exe, "-m", "pip", "install", "--no-warn-script-location", "--disable-pip-version-check"]
            run([*pip, *locked])
            run([*pip, "--no-deps", wheel])
        else:
            plat = [x for t in tags for x in ("--platform", t)]
            pip = [sys.executable, "-m", "pip", "install", "--target", site, "--upgrade", *plat, "--python-version", python,
                   "--implementation", "cp", "--abi", "cp" + python.replace(".", ""), "--disable-pip-version-check"]
            run([*pip, *locked])
            run([*pip, "--no-deps", wheel])
    prune(py)
    if args.target.startswith("macos") and platform.system() == "Darwin":
        thin_and_strip_macos(py, "arm64" if args.target.endswith("arm64") else "x86_64")

    manifest = dict(target=args.target, triple=triple, python=name.split("+")[0].removeprefix("cpython-"),
                    release=release, archive=name, sha256=digest, lock=lockfile.name, native_build=native, interpreter=exe)
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
