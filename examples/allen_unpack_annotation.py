"""Unpack an Allen Developing Mouse Brain annotation zip (e.g. P4_DevMouse2012_annotation.zip) next to itself.

The download server ships the 3D annotation as a zip of annotation.mhd + annotation.raw; neurogenesis.data.atlas reads
the .mhd. Fetch the files first with the manifest examples/datasets/allen-devmouse-p4.json:

    python -m neurogenesis data fetch examples/datasets/allen-devmouse-p4.json --yes
    python examples/allen_unpack_annotation.py ~/.cache/neurogenesis/data/allen-devmouse-p4/P4_DevMouse2012_annotation.zip

Only the members annotation.mhd and annotation.raw are written (no other paths from the archive).
"""
import argparse
import shutil
import zipfile
from pathlib import Path

MEMBERS = ("annotation.mhd", "annotation.raw")


def unpack(zip_path, out_dir=None):
    """Writes annotation.mhd and annotation.raw from zip_path into out_dir (default: the zip's folder); returns the
    path of the .mhd."""
    zip_path = Path(zip_path)
    out = Path(out_dir) if out_dir else zip_path.parent
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        names = set(z.namelist())
        missing = [m for m in MEMBERS if m not in names]
        if missing:
            raise SystemExit(f"{zip_path} has no {missing} (members: {sorted(names)})")
        for m in MEMBERS:
            with z.open(m) as src, open(out / m, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
    return out / MEMBERS[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("zip", help="annotation zip from the Allen download server")
    ap.add_argument("--out", help="output folder (default: the zip's folder)")
    args = ap.parse_args()
    print("wrote", unpack(args.zip, args.out))


if __name__ == "__main__":
    main()
