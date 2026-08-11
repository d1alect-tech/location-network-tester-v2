"""Долговечное состояние фоновых задач LNT."""

from lnt.runtime.store import IllegalJobTransitionError, JobStore

__all__ = ["IllegalJobTransitionError", "JobStore"]
