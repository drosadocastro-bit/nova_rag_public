"""
Background Task Queue for NOVA NIC.

Provides async background processing for:
- Document ingestion
- Index rebuilding
- Cache warming
- Model loading
- Maintenance tasks

Features:
- Priority scheduling
- Progress tracking
- Checkpointing
- Retry with backoff
- Task dependencies
"""

import asyncio
import functools
import logging
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class TaskPriority(int, Enum):
    """Task priority levels (lower = higher priority)."""
    
    CRITICAL = 0
    HIGH = 10
    NORMAL = 50
    LOW = 100
    BACKGROUND = 200


class TaskStatus(str, Enum):
    """Task execution status."""
    
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


@dataclass
class TaskProgress:
    """Progress information for a task."""
    
    current: int = 0
    total: int = 0
    message: str = ""
    percentage: float = 0.0
    items_per_second: float = 0.0
    eta_seconds: Optional[float] = None
    
    def update(self, current: int, total: int, message: str = "") -> None:
        """Update progress."""
        self.current = current
        self.total = total
        self.message = message
        self.percentage = (current / total * 100) if total > 0 else 0.0


@dataclass
class TaskResult:
    """Result of task execution."""
    
    task_id: str
    task_name: str
    status: TaskStatus
    result: Any = None
    error: Optional[str] = None
    error_traceback: Optional[str] = None
    
    # Timing
    created_at: float = 0.0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    # Progress
    progress: TaskProgress = field(default_factory=TaskProgress)
    
    # Retries
    attempt: int = 1
    max_retries: int = 0
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Task duration in seconds."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None
    
    @property
    def wait_time_seconds(self) -> Optional[float]:
        """Time waiting in queue."""
        if self.started_at:
            return self.started_at - self.created_at
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "status": self.status.value,
            "result": str(self.result) if self.result else None,
            "error": self.error,
            "created_at": datetime.fromtimestamp(self.created_at).isoformat() if self.created_at else None,
            "started_at": datetime.fromtimestamp(self.started_at).isoformat() if self.started_at else None,
            "completed_at": datetime.fromtimestamp(self.completed_at).isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "wait_time_seconds": self.wait_time_seconds,
            "progress": {
                "current": self.progress.current,
                "total": self.progress.total,
                "percentage": round(self.progress.percentage, 1),
                "message": self.progress.message,
                "eta_seconds": self.progress.eta_seconds,
            },
            "attempt": self.attempt,
            "max_retries": self.max_retries,
        }


@dataclass
class TaskDefinition:
    """Definition of a task to be executed."""
    
    task_id: str
    name: str
    func: Callable
    args: tuple = ()
    kwargs: Dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    max_retries: int = 0
    retry_delay_seconds: float = 5.0
    timeout_seconds: Optional[float] = None
    depends_on: Set[str] = field(default_factory=set)
    
    # Callbacks
    on_progress: Optional[Callable[[TaskProgress], None]] = None
    on_complete: Optional[Callable[[TaskResult], None]] = None
    on_error: Optional[Callable[[TaskResult], None]] = None


class BackgroundTaskQueue:
    """
    Background task queue with priority scheduling.
    
    Features:
    - Priority-based execution
    - Progress tracking
    - Retry with exponential backoff
    - Task dependencies
    - Concurrent execution
    """
    
    def __init__(
        self,
        max_workers: int = 4,
        max_queue_size: int = 1000,
    ):
        """
        Initialize task queue.
        
        Args:
            max_workers: Maximum concurrent tasks
            max_queue_size: Maximum pending tasks
        """
        self.max_workers = max_workers
        self.max_queue_size = max_queue_size
        
        # Task storage
        self._tasks: Dict[str, TaskDefinition] = {}
        self._results: Dict[str, TaskResult] = {}
        
        # Priority queue
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_queue_size)
        
        # Thread pool for sync functions
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="BackgroundTask"
        )
        
        # Worker state
        self._workers: List[asyncio.Task] = []
        self._running = False
        self._shutdown_event = asyncio.Event()
        
        # Metrics
        self._total_submitted = 0
        self._total_completed = 0
        self._total_failed = 0
        
        logger.info(
            f"BackgroundTaskQueue initialized: workers={max_workers}, "
            f"max_queue={max_queue_size}"
        )
    
    def submit(
        self,
        func: Callable,
        *args,
        name: Optional[str] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        max_retries: int = 0,
        retry_delay: float = 5.0,
        timeout: Optional[float] = None,
        depends_on: Optional[Set[str]] = None,
        on_progress: Optional[Callable] = None,
        on_complete: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        **kwargs,
    ) -> str:
        """
        Submit a task for background execution.
        
        Args:
            func: Function to execute
            *args: Positional arguments
            name: Task name for logging
            priority: Task priority
            max_retries: Maximum retry attempts
            retry_delay: Delay between retries (seconds)
            timeout: Execution timeout (seconds)
            depends_on: Set of task IDs that must complete first
            on_progress: Progress callback
            on_complete: Completion callback
            on_error: Error callback
            **kwargs: Keyword arguments
            
        Returns:
            Task ID
        """
        task_id = str(uuid.uuid4())[:8]
        task_name = name or func.__name__
        
        task_def = TaskDefinition(
            task_id=task_id,
            name=task_name,
            func=func,
            args=args,
            kwargs=kwargs,
            priority=priority,
            max_retries=max_retries,
            retry_delay_seconds=retry_delay,
            timeout_seconds=timeout,
            depends_on=depends_on or set(),
            on_progress=on_progress,
            on_complete=on_complete,
            on_error=on_error,
        )
        
        # Create result placeholder
        result = TaskResult(
            task_id=task_id,
            task_name=task_name,
            status=TaskStatus.PENDING,
            created_at=time.time(),
            max_retries=max_retries,
        )
        
        self._tasks[task_id] = task_def
        self._results[task_id] = result
        self._total_submitted += 1
        
        # Add to queue (priority, timestamp for FIFO within priority, task_id)
        try:
            self._queue.put_nowait((priority.value, time.time(), task_id))
            result.status = TaskStatus.QUEUED
            logger.debug(f"Task submitted: {task_name} ({task_id}) priority={priority.name}")
        except asyncio.QueueFull:
            result.status = TaskStatus.FAILED
            result.error = "Queue full"
            logger.warning(f"Task rejected (queue full): {task_name} ({task_id})")
        
        return task_id
    
    async def _check_dependencies(self, task_def: TaskDefinition) -> bool:
        """Check if task dependencies are satisfied."""
        for dep_id in task_def.depends_on:
            if dep_id not in self._results:
                return False
            dep_result = self._results[dep_id]
            if dep_result.status != TaskStatus.COMPLETED:
                return False
        return True
    
    async def _execute_task(self, task_def: TaskDefinition) -> TaskResult:
        """Execute a single task."""
        result = self._results[task_def.task_id]
        result.status = TaskStatus.RUNNING
        result.started_at = time.time()
        
        logger.info(f"Starting task: {task_def.name} ({task_def.task_id})")
        
        try:
            # Check if async
            if asyncio.iscoroutinefunction(task_def.func):
                # Async function
                if task_def.timeout_seconds:
                    coro = asyncio.wait_for(
                        task_def.func(*task_def.args, **task_def.kwargs),
                        timeout=task_def.timeout_seconds
                    )
                else:
                    coro = task_def.func(*task_def.args, **task_def.kwargs)
                
                task_result = await coro
            else:
                # Sync function - run in executor
                loop = asyncio.get_event_loop()
                func_partial = functools.partial(
                    task_def.func, *task_def.args, **task_def.kwargs
                )
                
                if task_def.timeout_seconds:
                    task_result = await asyncio.wait_for(
                        loop.run_in_executor(self._executor, func_partial),
                        timeout=task_def.timeout_seconds
                    )
                else:
                    task_result = await loop.run_in_executor(self._executor, func_partial)
            
            # Success
            result.status = TaskStatus.COMPLETED
            result.result = task_result
            result.completed_at = time.time()
            self._total_completed += 1
            
            logger.info(
                f"Task completed: {task_def.name} ({task_def.task_id}) "
                f"in {result.duration_seconds:.2f}s"
            )
            
            # Completion callback
            if task_def.on_complete:
                try:
                    task_def.on_complete(result)
                except Exception as e:
                    logger.warning(f"Task completion callback error: {e}")
            
        except asyncio.TimeoutError:
            result.status = TaskStatus.FAILED
            result.error = f"Timeout after {task_def.timeout_seconds}s"
            result.completed_at = time.time()
            self._total_failed += 1
            
            logger.warning(f"Task timeout: {task_def.name} ({task_def.task_id})")
            
        except Exception as e:
            result.error = str(e)
            result.error_traceback = traceback.format_exc()
            result.completed_at = time.time()
            
            # Check for retry
            if result.attempt <= task_def.max_retries:
                result.status = TaskStatus.RETRYING
                result.attempt += 1
                
                logger.warning(
                    f"Task failed (attempt {result.attempt - 1}/{task_def.max_retries + 1}): "
                    f"{task_def.name} ({task_def.task_id}) - {e}"
                )
                
                # Requeue with delay
                await asyncio.sleep(
                    task_def.retry_delay_seconds * (2 ** (result.attempt - 2))  # Exponential backoff
                )
                self._queue.put_nowait((
                    task_def.priority.value,
                    time.time(),
                    task_def.task_id
                ))
            else:
                result.status = TaskStatus.FAILED
                self._total_failed += 1
                
                logger.error(
                    f"Task failed (final): {task_def.name} ({task_def.task_id}) - {e}"
                )
                
                # Error callback
                if task_def.on_error:
                    try:
                        task_def.on_error(result)
                    except Exception as cb_error:
                        logger.warning(f"Task error callback error: {cb_error}")
        
        return result
    
    async def _worker_loop(self, worker_id: int) -> None:
        """Worker loop to process tasks."""
        logger.debug(f"Worker {worker_id} started")
        
        while self._running:
            try:
                # Get task with timeout to allow shutdown check
                try:
                    priority, timestamp, task_id = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                task_def = self._tasks.get(task_id)
                if not task_def:
                    continue
                
                # Check dependencies
                if task_def.depends_on:
                    deps_ready = await self._check_dependencies(task_def)
                    if not deps_ready:
                        # Requeue
                        await asyncio.sleep(0.5)
                        self._queue.put_nowait((priority, time.time(), task_id))
                        continue
                
                # Execute
                await self._execute_task(task_def)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
        
        logger.debug(f"Worker {worker_id} stopped")
    
    async def start(self) -> None:
        """Start the task queue workers."""
        if self._running:
            return
        
        self._running = True
        self._shutdown_event.clear()
        
        # Start workers
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker_loop(i))
            self._workers.append(worker)
        
        logger.info(f"Started {self.max_workers} task queue workers")
    
    async def stop(self, wait: bool = True, timeout: float = 30.0) -> None:
        """Stop the task queue."""
        if not self._running:
            return
        
        self._running = False
        
        if wait:
            # Wait for workers to finish current tasks
            logger.info("Waiting for workers to complete...")
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._workers, return_exceptions=True),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for workers, cancelling...")
        
        # Cancel remaining workers
        for worker in self._workers:
            if not worker.done():
                worker.cancel()
        
        self._workers.clear()
        
        # Shutdown executor
        self._executor.shutdown(wait=False)
        
        logger.info("Task queue stopped")
    
    def get_task_status(self, task_id: str) -> Optional[TaskResult]:
        """Get status of a task."""
        return self._results.get(task_id)
    
    def get_all_tasks(
        self,
        status: Optional[TaskStatus] = None,
        limit: int = 100,
    ) -> List[TaskResult]:
        """Get all tasks, optionally filtered by status."""
        results = list(self._results.values())
        
        if status:
            results = [r for r in results if r.status == status]
        
        # Sort by created_at descending
        results.sort(key=lambda r: r.created_at, reverse=True)
        
        return results[:limit]
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending task."""
        if task_id not in self._results:
            return False
        
        result = self._results[task_id]
        if result.status in (TaskStatus.PENDING, TaskStatus.QUEUED):
            result.status = TaskStatus.CANCELLED
            result.completed_at = time.time()
            logger.info(f"Task cancelled: {task_id}")
            return True
        
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        status_counts = {}
        for status in TaskStatus:
            status_counts[status.value] = sum(
                1 for r in self._results.values() if r.status == status
            )
        
        return {
            "total_submitted": self._total_submitted,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
            "queue_size": self._queue.qsize(),
            "workers": len(self._workers),
            "running": self._running,
            "status_counts": status_counts,
        }
    
    def clear_completed(self, older_than_seconds: float = 3600) -> int:
        """Clear old completed tasks from memory."""
        cutoff = time.time() - older_than_seconds
        to_remove = []
        
        for task_id, result in self._results.items():
            if result.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                if result.completed_at and result.completed_at < cutoff:
                    to_remove.append(task_id)
        
        for task_id in to_remove:
            del self._results[task_id]
            if task_id in self._tasks:
                del self._tasks[task_id]
        
        if to_remove:
            logger.info(f"Cleared {len(to_remove)} old task records")
        
        return len(to_remove)


# ==================
# Decorator for Background Tasks
# ==================

def background_task(
    name: Optional[str] = None,
    priority: TaskPriority = TaskPriority.NORMAL,
    max_retries: int = 0,
    timeout: Optional[float] = None,
):
    """
    Decorator to mark a function as a background task.
    
    Usage:
        @background_task(name="process_documents", priority=TaskPriority.HIGH)
        def process_documents(paths: List[str]) -> int:
            ...
    """
    def decorator(func: Callable) -> Callable:
        setattr(func, '_background_task', True)
        setattr(func, '_task_name', name or func.__name__)
        setattr(func, '_task_priority', priority)
        setattr(func, '_task_max_retries', max_retries)
        setattr(func, '_task_timeout', timeout)
        return func
    return decorator
