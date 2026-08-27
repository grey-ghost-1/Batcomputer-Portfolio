"""Alfred Assistant: a local-first, typed FastAPI household-manager service.

The package is intentionally offline by default. Desktop actions are disabled
until explicitly enabled and every mutating action flows through an auditable
propose -> approve -> execute lifecycle bound to an authenticated local caller.
"""

__version__ = "1.0.0"
