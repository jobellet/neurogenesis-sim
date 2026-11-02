"""Import and export of networks in other simulators' formats (roadmap phase J).

    from neurogenesis.interop import export_network, import_network, formats
    report = export_network(net, "sonata", "out/circuit")      # what was exact, approximated, dropped
    net2 = import_network("sonata", "out/circuit")

Each format is a module of this package with its dependencies as an optional extra; see docs/ROADMAP.md, phase J.
"""
from .core import ExportReport, export_network, formats, import_network, register_format
from .dynamics import LIFParams, delay_ms, delay_ticks, lif_params, shift_from_tau, tau_ms

__all__ = ["ExportReport", "export_network", "import_network", "formats", "register_format", "LIFParams",
           "lif_params", "tau_ms", "shift_from_tau", "delay_ms", "delay_ticks"]
