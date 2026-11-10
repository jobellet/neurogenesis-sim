"""Format registry and export reports shared by every importer and exporter (roadmap task J1).

A format module registers itself with `register_format(name, export=..., import_=..., extra=...)`. Exporters return an
`ExportReport` saying which network fields were written exactly, which were approximated (and how), and which were
dropped, so that a user always knows what the file in another simulator's format still means.
"""
from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

from ..spiking.network import SNNNetwork

_FORMATS: Dict[str, dict] = {}
_BUILTIN = {
    "sonata": "neurogenesis.interop.sonata",
    "nir": "neurogenesis.interop.nir",
}


@dataclass
class ExportReport:
    """What an export kept. `approximated` and `dropped` map a field to an explanation."""
    format: str
    path: str
    exact: List[str] = field(default_factory=list)
    approximated: Dict[str, str] = field(default_factory=dict)
    dropped: Dict[str, str] = field(default_factory=dict)
    counts: Dict[str, int] = field(default_factory=dict)

    @property
    def lossless(self) -> bool:
        return not self.approximated and not self.dropped

    def to_dict(self) -> dict:
        return dict(format=self.format, path=self.path, lossless=self.lossless, exact=self.exact,
                    approximated=self.approximated, dropped=self.dropped, counts=self.counts)

    def __str__(self) -> str:
        return json.dumps(self.to_dict(), indent=1)


def register_format(name: str, export: Optional[Callable] = None, import_: Optional[Callable] = None,
                    extra: Optional[str] = None, description: str = "") -> None:
    """Register a format. `export(net, path, **opts) -> ExportReport`, `import_(path, **opts) -> SNNNetwork`;
    `extra` names the optional dependency group (`pip install "neurogenesis-sim[extra]"`)."""
    _FORMATS[name] = dict(export=export, import_=import_, extra=extra, description=description)


def _format(name: str) -> dict:
    if name not in _FORMATS and name in _BUILTIN:
        importlib.import_module(_BUILTIN[name])
    if name not in _FORMATS:
        raise ValueError(f"unknown format {name!r}; available: {', '.join(formats())}")
    return _FORMATS[name]


def formats() -> List[str]:
    """Names of the registered and built-in formats."""
    return sorted(set(_FORMATS) | set(_BUILTIN))


def as_network(net: Union[SNNNetwork, str, Path]) -> SNNNetwork:
    """An SNNNetwork from an object, a network JSON file or an NGB1 file."""
    if isinstance(net, SNNNetwork):
        return net
    path = Path(net)
    if path.suffix.lower() == ".ngb":
        from ..bridge.ngb import read_network
        return read_network(path)
    return SNNNetwork.load_json(path)


def export_network(net: Union[SNNNetwork, str, Path], fmt: str, path: Union[str, Path], **opts) -> ExportReport:
    """Write a network in format `fmt` to `path`; returns what was kept, approximated and dropped."""
    f = _format(fmt)
    if f["export"] is None:
        raise ValueError(f"format {fmt!r} cannot be written")
    return f["export"](as_network(net), Path(path), **opts)


def import_network(fmt: str, path: Union[str, Path], **opts) -> SNNNetwork:
    """Read a network written in format `fmt`."""
    f = _format(fmt)
    if f["import_"] is None:
        raise ValueError(f"format {fmt!r} cannot be read")
    return f["import_"](Path(path), **opts)


def require(module: str, extra: str):
    """Import an optional dependency, or explain which extra installs it."""
    try:
        return importlib.import_module(module)
    except ImportError as e:
        raise ImportError(f"this format needs the optional package {module!r}: "
                          f'pip install "neurogenesis-sim[{extra}]"') from e
