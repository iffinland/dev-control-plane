"""Workflow v3 development job engine.

The package is intentionally standard-library only. It stores durable job state
outside the repository, runs OpenCode through the existing execution guard and
never signals any process it did not create.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "3.1.1"
