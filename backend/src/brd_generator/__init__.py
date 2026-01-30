"""BRD Generator - AI-powered Business Requirements Document generation."""

__version__ = "0.1.0"

from .core.generator import BRDGenerator
from .models.request import BRDRequest
from .models.output import BRDOutput, BRDDocument, Epic, UserStory

__all__ = [
    "BRDGenerator",
    "BRDRequest",
    "BRDOutput",
    "BRDDocument",
    "Epic",
    "UserStory",
]
