"""Middleware that ships with the lab. Each is one small class on top of `agentlab.harness.Middleware`."""

from agentlab.middleware.compaction import Compaction
from agentlab.middleware.policy import ProtectPaths
from agentlab.middleware.tracing import Tracer

__all__ = ["Compaction", "ProtectPaths", "Tracer"]
