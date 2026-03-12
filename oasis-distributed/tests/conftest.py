"""
conftest.py — Stub heavy ML/NLP dependencies before any oasis module is imported.

Uses a custom MetaPathFinder so that ANY submodule of a stubbed top-level
package (e.g. camel.prompts, camel.toolkits.foo) is automatically stubbed
without needing to list them exhaustively.
"""
import sys
import types
import importlib.abc
import importlib.machinery


class _StubModule(types.ModuleType):
    """A module stub that returns MagicMock for any attribute access."""
    def __getattr__(self, name):
        from unittest.mock import MagicMock
        attr = MagicMock()
        setattr(self, name, attr)
        return attr

    def __call__(self, *args, **kwargs):
        from unittest.mock import MagicMock
        return MagicMock()


class _StubFinder(importlib.abc.MetaPathFinder):
    """Intercept imports for any module whose top-level name is in _STUB_PACKAGES."""

    def __init__(self, packages):
        self._packages = set(packages)

    def find_module(self, fullname, path=None):
        top = fullname.split(".")[0]
        if top in self._packages:
            return self
        return None

    def load_module(self, fullname):
        if fullname in sys.modules:
            return sys.modules[fullname]
        mod = _StubModule(fullname)
        mod.__path__ = []
        mod.__file__ = f"<stub:{fullname}>"
        mod.__loader__ = self
        mod.__spec__ = importlib.machinery.ModuleSpec(fullname, self)
        mod.__package__ = fullname
        sys.modules[fullname] = mod
        return mod


# ---- Top-level packages to stub ----
_STUB_PACKAGES = [
    # ML / NLP
    "camel",
    "sentence_transformers",
    "torch",
    "transformers",
    # SciPy / Sklearn / Numpy
    "numpy",
    "scipy",
    "sklearn",
    # Graph / Network
    "igraph",
    "neo4j",
    # Data / Other
    "pandas",
    "PIL",
    "cv2",
    "openai",
    "tiktoken",
    # Misc deps needed by oasis
    "tqdm",
    "cairocffi",
    "unstructured",
    "slack_sdk",
    "requests_oauthlib",
    "prance",
    "openapi_spec_validator",
    # NOTE: do NOT stub 'google' — google.protobuf is required by gRPC
]

# Install the finder at the front of sys.meta_path
sys.meta_path.insert(0, _StubFinder(_STUB_PACKAGES))
