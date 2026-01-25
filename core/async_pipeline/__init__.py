"""
Async Pipeline Module for NOVA NIC.

High-performance async query handling with:
- Concurrent query execution
- Async embeddings generation
- Background task queue
- Connection pooling
- Graceful degradation
"""

from core.async_pipeline.query_handler import (
    AsyncQueryHandler,
    AsyncQueryResult,
    QueryPriority,
    QueryStatus,
)
from core.async_pipeline.task_queue import (
    BackgroundTaskQueue,
    TaskStatus,
    TaskResult,
    TaskPriority,
)
from core.async_pipeline.embeddings_service import (
    AsyncEmbeddingsService,
    EmbeddingRequest,
    EmbeddingResult,
)

__all__ = [
    # Query Handler
    "AsyncQueryHandler",
    "AsyncQueryResult",
    "QueryPriority",
    "QueryStatus",
    # Task Queue
    "BackgroundTaskQueue",
    "TaskStatus",
    "TaskResult",
    "TaskPriority",
    # Embeddings
    "AsyncEmbeddingsService",
    "EmbeddingRequest",
    "EmbeddingResult",
]
