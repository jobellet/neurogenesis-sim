"""Bridge between the toolbox and its clients (the desktop apps): a JSON-lines server and the NGB1 network format.

    python -m neurogenesis.bridge          serve requests on stdin / stdout (desktop/common/PROTOCOL.md)
"""
from .ngb import NGB_VERSION, read_extensions, read_network, write_network
from .server import METHODS, PROTOCOL_VERSION, ResourceError, handle, main

__all__ = ["METHODS", "NGB_VERSION", "PROTOCOL_VERSION", "ResourceError", "handle", "main", "read_extensions", "read_network", "write_network"]
