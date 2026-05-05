#!/usr/bin/python
"""Paper Provider Abstraction Layer."""

from .arxiv import ArxivProvider
from .base import PaperProvider
from .biorxiv import BiorxivProvider
from .osf import OSFProvider, PsyarxivProvider
from .pmc import PMCProvider
from .semantic_scholar import SemanticScholarProvider

__all__ = [
    "PaperProvider",
    "ArxivProvider",
    "PMCProvider",
    "BiorxivProvider",
    "OSFProvider",
    "PsyarxivProvider",
    "SemanticScholarProvider",
]
