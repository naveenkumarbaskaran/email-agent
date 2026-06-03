"""Email Agent — classify, prioritize, and draft replies using Claude."""

from .agent import EmailAgent
from .parser import EmailParser

__all__ = ["EmailAgent", "EmailParser"]
