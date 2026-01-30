"""Multi-agent architecture for BRD generation and verification."""

from .base import BaseAgent, AgentMessage, AgentRole
from .brd_generator_agent import BRDGeneratorAgent
from .brd_verifier_agent import BRDVerifierAgent

__all__ = [
    "BaseAgent",
    "AgentMessage",
    "AgentRole",
    "BRDGeneratorAgent",
    "BRDVerifierAgent",
]
