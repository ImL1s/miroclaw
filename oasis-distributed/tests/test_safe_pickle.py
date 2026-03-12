"""Tests for RestrictedUnpickler — safe deserialization."""
import pickle
import pytest
from oasis.network.safe_pickle import restricted_loads


def test_loads_dict():
    """Normal dict payload should work."""
    data = pickle.dumps({"agent_id": 1, "action": "post"})
    result = restricted_loads(data)
    assert result == {"agent_id": 1, "action": "post"}


def test_loads_tuple():
    """Tuple payload (context data) should work."""
    data = pickle.dumps(([1, 2], [3, 4], {"msg": "hi"}))
    result = restricted_loads(data)
    assert result == ([1, 2], [3, 4], {"msg": "hi"})


def test_loads_nested():
    """Nested structures should work."""
    data = pickle.dumps({"agents": [1, 2, 3], "meta": {"round": 5, "done": True}})
    result = restricted_loads(data)
    assert result["agents"] == [1, 2, 3]
    assert result["meta"]["round"] == 5


def test_blocks_os_system():
    """Should block os.system() payload."""
    class Malicious:
        def __reduce__(self):
            import os
            return (os.system, ("echo pwned",))
    malicious = pickle.dumps(Malicious())
    with pytest.raises(pickle.UnpicklingError, match="Blocked unsafe"):
        restricted_loads(malicious)


def test_blocks_subprocess():
    """Should block subprocess.Popen payload."""
    class Malicious:
        def __reduce__(self):
            import subprocess
            return (subprocess.Popen, (["echo", "pwned"],))
    malicious = pickle.dumps(Malicious())
    with pytest.raises(pickle.UnpicklingError, match="Blocked unsafe"):
        restricted_loads(malicious)
