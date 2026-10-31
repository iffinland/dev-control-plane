"""Qortium Dev Monitor P1: read-only Telegram observer for Workflow v3.

The package reuses the existing Workflow v3 job store and CLI. It never creates
or mutates jobs in Phase 1 and never opens an inbound network listener.
"""

from __future__ import annotations

__version__ = "0.1.0-p1"

__all__ = ["__version__"]
