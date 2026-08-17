from .base import Indexer, IndexerPool, SearchQuery
from .unit3d import Unit3dIndexer

__all__ = ["Indexer", "IndexerPool", "SearchQuery", "Unit3dIndexer", "build_indexer"]


def build_indexer(config, api_key, cache=None):
    """Instantiate the client implementation named by ``config.type``."""
    if config.type == "unit3d":
        return Unit3dIndexer(config, api_key, cache=cache)
    raise ValueError(f"unknown indexer type: {config.type!r}")
