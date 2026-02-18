"""Multi-agent architecture for BRD generation and verification."""

from .base import BaseAgent, AgentMessage, AgentRole
from .brd_generator_agent import BRDGeneratorAgent
from .brd_verifier_agent import BRDVerifierAgent
from .brd_refinement_agent import BRDRefinementAgent
from .epic_generator_agent import EpicGeneratorAgent
from .epic_verifier_agent import EpicVerifierAgent
from .backlog_generator_agent import BacklogGeneratorAgent
from .backlog_verifier_agent import BacklogVerifierAgent

__all__ = [
    "BaseAgent",
    "AgentMessage",
    "AgentRole",
    "BRDGeneratorAgent",
    "BRDVerifierAgent",
    "BRDRefinementAgent",
    "EpicGeneratorAgent",
    "EpicVerifierAgent",
    "BacklogGeneratorAgent",
    "BacklogVerifierAgent",
]
