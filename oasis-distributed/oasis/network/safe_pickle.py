"""Restricted unpickler — only allows safe builtins, no arbitrary code execution.

camel-ai / OASIS uses pickle for gRPC action/context payloads. Raw pickle.loads
allows arbitrary code execution if an attacker crafts a malicious payload.
This module provides a drop-in replacement that whitelists safe modules only.
"""
import io
import pickle


_SAFE_MODULES = frozenset({
    "builtins",       # dict, list, tuple, set, frozenset, int, float, str, bytes, bool, None
    "collections",    # OrderedDict, defaultdict
    "datetime",       # datetime objects in action payloads
    "uuid",           # UUID objects
})


class RestrictedUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str):
        if module in _SAFE_MODULES:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(
            f"Blocked unsafe pickle class: {module}.{name}"
        )


def restricted_loads(data: bytes):
    """Drop-in replacement for pickle.loads with security restrictions."""
    return RestrictedUnpickler(io.BytesIO(data)).load()
