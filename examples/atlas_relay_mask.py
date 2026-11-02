"""Cut a relay-nucleus shape out of an annotation atlas, for examples/retinothalamic.py --relay-mask.

The intended source is the Allen Developing Mouse Brain Reference Atlas at P4 (Thompson et al. 2014, Neuron; data:
developingmouse.brain-map.org, Allen Institute terms of use; cite the atlas when you use it). Its files are not
committed: download the P4 annotation volume and the structure ontology yourself (or with a dataset manifest and
`python -m neurogenesis data fetch`), then:

    python examples/atlas_relay_mask.py --annotation P4_annotation.nrrd --ontology structures.json --find LG
    python examples/atlas_relay_mask.py --annotation P4_annotation.nrrd --ontology structures.json \\
        --structure <acronym> --out relay_mask.npz
    python examples/retinothalamic.py --relay-mask relay_mask.npz --cpu

`--find` lists the structures whose acronym or name contains the text, to choose the one to cut. The shape keeps its
proportions and is scaled into the example's relay box (largest side 60 space units, centred above the retina), so
the rest of the model keeps its units; the atlas sets the shape, not the size.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from neurogenesis.data.atlas import Ontology, fit_to_box, read_volume, structure_geometry  # noqa: E402

RELAY_CENTER_ATLAS = (50.0, 50.0, 60.0)     # relay centre with an atlas shape (taller than the default 20-unit box)
RELAY_EXTENT = 60.0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--annotation", required=True, help="annotation volume (.nrrd, .mhd or .npz)")
    ap.add_argument("--ontology", required=True, help="structure ontology JSON")
    ap.add_argument("--structure", action="append", help="acronym or id to cut (repeatable; descendants included)")
    ap.add_argument("--find", help="list structures whose acronym or name contains this text, then stop")
    ap.add_argument("--out", default="relay_mask.npz")
    args = ap.parse_args()
    onto = Ontology.load(args.ontology)
    if args.find:
        q = args.find.lower()
        for i, a in sorted(onto.acronym.items()):
            if q in a.lower() or q in onto.name.get(i, "").lower():
                print(f"{i:10d}  {a:12s}  {onto.name.get(i, '')}")
        return
    if not args.structure:
        raise SystemExit("give --structure (use --find to list candidates)")
    vol, origin, spacing = read_volume(args.annotation)
    g = structure_geometry(vol, onto, args.structure, origin, spacing)
    lo, hi = g.bounding_box()
    size = np.asarray(hi) - np.asarray(lo)
    print(f"{args.structure}: {int(g.mask.sum())} voxels of {spacing.tolist()}, bounding box {size.round(1).tolist()} "
          f"(atlas units)")
    fit_to_box(g, RELAY_CENTER_ATLAS, RELAY_EXTENT).save_npz(args.out)
    print("wrote", args.out)


if __name__ == "__main__":
    main()
