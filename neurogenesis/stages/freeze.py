"""End of development (C13): validate a tissue and compile it to an `SNNNetwork`."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from neurogenesis.params import resolve
from neurogenesis.spiking.network import SNNNetwork
from neurogenesis.stages.base import register_stage, run_schedule
from neurogenesis.tissue import Tissue

MAX_DELAY = 31          # ticks, kernel limit of the 32-bit spike history
MAX_WEIGHT = 32767      # int16 range of the weights in the NGB1 format and the kernels


class FreezeError(ValueError):
    """The tissue cannot be compiled to a valid network (the message lists every problem)."""


def validate(tissue: Tissue, dale: bool = False) -> List[str]:
    """Problems that prevent compiling the tissue: non-finite positions, synapse indices out of range, delays outside
    [1, 31] ticks, weights outside the int16 range and, with `dale`, outgoing weights whose sign differs from the
    presynaptic cell's sign. An empty list means the tissue is valid. O(N + E)."""
    problems = []
    N = len(tissue.alive)
    c = tissue.connectivity
    if not np.all(np.isfinite(tissue.positions)):
        problems.append(f"{int(np.sum(~np.isfinite(tissue.positions).all(axis=1)))} cells have non-finite positions")
    lengths = {len(c.pre), len(c.post), len(c.weight), len(c.delay)}
    if len(lengths) != 1:
        return problems + [f"connectivity arrays have different lengths {sorted(lengths)}"]
    try:
        c._sync()
    except ValueError as e:
        return problems + [str(e)]
    bad = (c.pre < 0) | (c.pre >= N) | (c.post < 0) | (c.post >= N)
    if bad.any():
        problems.append(f"{int(bad.sum())} synapses have indices outside [0, {N})")
    bad_d = (c.delay < 1) | (c.delay > MAX_DELAY)
    if bad_d.any():
        problems.append(f"{int(bad_d.sum())} synapses have delays outside [1, {MAX_DELAY}] ticks")
    bad_w = np.abs(c.weight.astype(np.int64)) > MAX_WEIGHT
    if bad_w.any():
        problems.append(f"{int(bad_w.sum())} synapses have |weight| > {MAX_WEIGHT}")
    if dale and not bad.any() and len(c.pre):
        wrong = ((tissue.sign[c.pre] < 0) & (c.weight > 0)) | ((tissue.sign[c.pre] > 0) & (c.weight < 0))
        if wrong.any():
            problems.append(f"{int(wrong.sum())} synapses break Dale's principle (weight sign != presynaptic sign)")
    return problems


def freeze(tissue: Tissue, dale: bool = False) -> SNNNetwork:
    """Validates the tissue (`validate`) and compiles its living cells to an `SNNNetwork` (synapses of dead cells are
    dropped). Raises `FreezeError` listing every problem."""
    problems = validate(tissue, dale)
    if problems:
        raise FreezeError("freeze: " + "; ".join(problems))
    return tissue.to_network()


def develop(project: Dict[str, Any], genome: Dict[str, Any], seed: int, dale: bool = False) -> SNNNetwork:
    """Runs a Project's schedule (`run_schedule`) and freezes the final tissue."""
    return freeze(run_schedule(project, genome, seed), dale=dale)


@register_stage("freeze")
class FreezeStage:
    """Validates the tissue and compiles it (end of development or a checkpoint); the tissue itself is unchanged.

    Params: `dale` (False; also check that synapse signs follow the presynaptic sign) and `path` (none; write the
    network there: NGB1 binary for a `.ngb` suffix, else JSON). Raises `FreezeError` on an invalid tissue.
    """

    @classmethod
    def cost(cls, N: int, E: int, params: Dict[str, Any]) -> Tuple[int, int]:
        # validation masks plus the SNNNetwork objects (about 400 bytes per neuron and 120 per synapse in Python)
        return int(N * 400 + E * 140), int(N * 50 + E * 30)

    def run(self, tissue: Tissue, params: Dict[str, Any], genome: Dict[str, Any], fields: Dict[str, Any],
            rng: np.random.Generator) -> Tissue:
        dale = bool(resolve(params.get("dale", False), genome, fields))
        problems = validate(tissue, dale)
        if problems:
            raise FreezeError("freeze: " + "; ".join(problems))
        path = params.get("path")
        if path is not None:
            path = Path(str(resolve(path, genome, fields)))
            net = tissue.to_network()
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix == ".ngb":
                from neurogenesis.bridge.ngb import write_network
                write_network(net, path)
            else:
                net.save_json(path)
        return tissue
