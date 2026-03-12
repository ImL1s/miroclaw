"""
Custom errors for the OASIS distributed simulation.
"""


class SimulationAbortError(Exception):
    """Raised when simulation integrity is compromised beyond recovery.
    
    Examples:
        - Orphaned agent ratio exceeds threshold
        - All workers disconnected
        - Platform DB corrupted
    """
    pass
