"""Qortium Dev Monitor P3: Telegram observer plus authorized job control.

The package reuses the existing Workflow v3 job store and CLI. Read-only mode is
the default. Control mode must be explicitly configured by the owner and is
restricted to the authorized private chat. The monitor never opens an inbound
network listener and never implements its own job engine.
"""

from __future__ import annotations

__version__ = "0.3.0-p3"

__all__ = ["__version__"]
