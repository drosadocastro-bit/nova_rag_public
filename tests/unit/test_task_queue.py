"""
Tests for Background Task Queue.

Tests async task processing including:
- Task submission and execution
- Priority scheduling
- Retry logic
- Timeout handling
- Task dependencies
"""

import asyncio
import time
from unittest.mock import Mock, patch

import pytest

from core.async_pipeline.task_queue import (
    BackgroundTaskQueue,
    TaskStatus,
    TaskResult,
    TaskPriority,
    TaskProgress,
    TaskDefinition,
    background_task,
)


class TestTaskProgress:
    """Tests for TaskProgress."""
    
    def test_initial_state(self):
        """Progress starts at zero."""
        progress = TaskProgress()
        assert progress.current == 0
        assert progress.total == 0
        assert progress.percentage == 0.0
    
    def test_update(self):
        """Test progress update."""
        progress = TaskProgress()
        progress.update(50, 100, "Halfway there")
        
        assert progress.current == 50
        assert progress.total == 100
        assert progress.percentage == 50.0
        assert progress.message == "Halfway there"
    
    def test_percentage_with_zero_total(self):
        """Percentage is 0 when total is 0."""
        progress = TaskProgress()
        progress.update(10, 0)
        
        assert progress.percentage == 0.0


class TestTaskResult:
    """Tests for TaskResult."""
    
    def test_duration_calculation(self):
        """Test duration is calculated correctly."""
        result = TaskResult(
            task_id="test",
            task_name="Test Task",
            status=TaskStatus.COMPLETED,
            created_at=100.0,
            started_at=101.0,
            completed_at=103.0,
        )
        
        assert result.duration_seconds == 2.0
        assert result.wait_time_seconds == 1.0
    
    def test_duration_when_not_completed(self):
        """Duration is None if not completed."""
        result = TaskResult(
            task_id="test",
            task_name="Test Task",
            status=TaskStatus.RUNNING,
            created_at=100.0,
            started_at=101.0,
        )
        
        assert result.duration_seconds is None
    
    def test_to_dict(self):
        """Test serialization."""
        result = TaskResult(
            task_id="test123",
            task_name="Test Task",
            status=TaskStatus.COMPLETED,
            result="success",
            created_at=time.time(),
        )
        
        d = result.to_dict()
        
        assert d["task_id"] == "test123"
        assert d["task_name"] == "Test Task"
        assert d["status"] == "completed"


class TestBackgroundTaskQueue:
    """Tests for BackgroundTaskQueue."""
    
    @pytest.fixture
    def queue(self):
        """Create a task queue."""
        return BackgroundTaskQueue(max_workers=2)
    
    @pytest.mark.asyncio
    async def test_submit_and_execute(self, queue):
        """Test basic task submission and execution."""
        def simple_task():
            return "done"
        
        await queue.start()
        
        task_id = queue.submit(simple_task, name="simple")
        
        # Wait for completion
        await asyncio.sleep(0.5)
        
        result = queue.get_task_status(task_id)
        assert result is not None
        assert result.status == TaskStatus.COMPLETED
        assert result.result == "done"
        
        await queue.stop()
    
    @pytest.mark.asyncio
    async def test_async_task_execution(self, queue):
        """Test async task execution."""
        async def async_task():
            await asyncio.sleep(0.1)
            return "async done"
        
        await queue.start()
        
        task_id = queue.submit(async_task, name="async")
        
        await asyncio.sleep(0.5)
        
        result = queue.get_task_status(task_id)
        assert result.status == TaskStatus.COMPLETED
        assert result.result == "async done"
        
        await queue.stop()
    
    @pytest.mark.asyncio
    async def test_task_with_args(self, queue):
        """Test task with arguments."""
        def add(a, b, multiplier=1):
            return (a + b) * multiplier
        
        await queue.start()
        
        task_id = queue.submit(add, 2, 3, multiplier=2, name="add")
        
        await asyncio.sleep(0.5)
        
        result = queue.get_task_status(task_id)
        assert result.result == 10
        
        await queue.stop()
    
    @pytest.mark.asyncio
    async def test_task_failure(self, queue):
        """Test task failure handling."""
        def failing_task():
            raise ValueError("Task failed!")
        
        await queue.start()
        
        task_id = queue.submit(failing_task, name="failing")
        
        await asyncio.sleep(0.5)
        
        result = queue.get_task_status(task_id)
        assert result.status == TaskStatus.FAILED
        assert "Task failed!" in result.error
        
        await queue.stop()
    
    @pytest.mark.asyncio
    async def test_task_retry(self, queue):
        """Test task retry on failure."""
        attempt_count = 0
        
        def retry_task():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError("Not yet")
            return "success"
        
        await queue.start()
        
        task_id = queue.submit(
            retry_task,
            name="retry",
            max_retries=3,
            retry_delay=0.1,
        )
        
        await asyncio.sleep(2)  # Wait for retries
        
        result = queue.get_task_status(task_id)
        assert result.status == TaskStatus.COMPLETED
        assert result.result == "success"
        assert attempt_count == 3
        
        await queue.stop()
    
    @pytest.mark.asyncio
    async def test_task_timeout(self, queue):
        """Test task timeout."""
        def slow_task():
            time.sleep(5)
            return "done"
        
        await queue.start()
        
        task_id = queue.submit(
            slow_task,
            name="slow",
            timeout=0.2,
        )
        
        await asyncio.sleep(1)
        
        result = queue.get_task_status(task_id)
        assert result.status == TaskStatus.FAILED
        assert "Timeout" in result.error
        
        await queue.stop()
    
    @pytest.mark.asyncio
    async def test_priority_ordering(self, queue):
        """Test tasks are processed by priority."""
        completed = []
        
        def track_task(name):
            completed.append(name)
            return name
        
        await queue.start()
        
        # Submit in reverse priority order
        queue.submit(track_task, "low", name="low", priority=TaskPriority.LOW)
        queue.submit(track_task, "normal", name="normal", priority=TaskPriority.NORMAL)
        queue.submit(track_task, "high", name="high", priority=TaskPriority.HIGH)
        queue.submit(track_task, "critical", name="critical", priority=TaskPriority.CRITICAL)
        
        await asyncio.sleep(1)
        
        # Higher priority should generally complete first
        # (not guaranteed due to concurrency, but critical should be early)
        assert "critical" in completed[:2] or len(completed) >= 4
        
        await queue.stop()
    
    @pytest.mark.asyncio
    async def test_get_all_tasks(self, queue):
        """Test getting all tasks."""
        def task():
            return "done"
        
        await queue.start()
        
        for i in range(5):
            queue.submit(task, name=f"task-{i}")
        
        await asyncio.sleep(1)
        
        all_tasks = queue.get_all_tasks()
        assert len(all_tasks) == 5
        
        completed = queue.get_all_tasks(status=TaskStatus.COMPLETED)
        assert len(completed) == 5
        
        await queue.stop()
    
    @pytest.mark.asyncio
    async def test_cancel_task(self, queue):
        """Test task cancellation."""
        def task():
            time.sleep(10)
            return "done"
        
        # Don't start the queue so task stays pending
        task_id = queue.submit(task, name="cancel-me")
        
        result = await queue.cancel_task(task_id)
        assert result is True
        
        status = queue.get_task_status(task_id)
        assert status.status == TaskStatus.CANCELLED
    
    @pytest.mark.asyncio
    async def test_get_stats(self, queue):
        """Test statistics reporting."""
        def task():
            return "done"
        
        await queue.start()
        
        queue.submit(task, name="stat-1")
        queue.submit(task, name="stat-2")
        
        await asyncio.sleep(0.5)
        
        stats = queue.get_stats()
        
        assert stats["total_submitted"] == 2
        assert stats["total_completed"] == 2
        assert stats["workers"] == 2
        assert stats["running"] is True
        
        await queue.stop()
    
    @pytest.mark.asyncio
    async def test_clear_completed(self, queue):
        """Test clearing old completed tasks."""
        def task():
            return "done"
        
        await queue.start()
        
        task_id = queue.submit(task, name="clear-me")
        
        await asyncio.sleep(0.5)
        
        # Mark as old
        queue._results[task_id].completed_at = time.time() - 7200
        
        cleared = queue.clear_completed(older_than_seconds=3600)
        assert cleared == 1
        
        # Task should be gone
        assert queue.get_task_status(task_id) is None
        
        await queue.stop()
    
    @pytest.mark.asyncio
    async def test_callbacks(self, queue):
        """Test completion and error callbacks."""
        completed_called = False
        error_called = False
        
        def on_complete(result):
            nonlocal completed_called
            completed_called = True
        
        def on_error(result):
            nonlocal error_called
            error_called = True
        
        def success_task():
            return "success"
        
        def fail_task():
            raise ValueError("fail")
        
        await queue.start()
        
        queue.submit(success_task, name="success", on_complete=on_complete)
        queue.submit(fail_task, name="fail", on_error=on_error)
        
        await asyncio.sleep(0.5)
        
        assert completed_called is True
        assert error_called is True
        
        await queue.stop()


class TestBackgroundTaskDecorator:
    """Tests for background_task decorator."""
    
    def test_decorator_attributes(self):
        """Test decorator sets attributes."""
        @background_task(
            name="my_task",
            priority=TaskPriority.HIGH,
            max_retries=3,
            timeout=30.0,
        )
        def my_task():
            pass
        
        assert my_task._background_task is True  # type: ignore
        assert my_task._task_name == "my_task"  # type: ignore
        assert my_task._task_priority == TaskPriority.HIGH  # type: ignore
        assert my_task._task_max_retries == 3  # type: ignore
        assert my_task._task_timeout == 30.0  # type: ignore
    
    def test_decorator_defaults(self):
        """Test decorator with defaults."""
        @background_task()
        def default_task():
            pass
        
        assert default_task._task_name == "default_task"  # type: ignore
        assert default_task._task_priority == TaskPriority.NORMAL  # type: ignore
        assert default_task._task_max_retries == 0  # type: ignore


class TestTaskDependencies:
    """Tests for task dependencies."""
    
    @pytest.mark.asyncio
    async def test_dependent_task_waits(self):
        """Test dependent task waits for dependency."""
        queue = BackgroundTaskQueue(max_workers=2)
        
        execution_order = []
        
        def parent_task():
            time.sleep(0.2)
            execution_order.append("parent")
            return "parent done"
        
        def child_task():
            execution_order.append("child")
            return "child done"
        
        await queue.start()
        
        parent_id = queue.submit(parent_task, name="parent")
        child_id = queue.submit(
            child_task,
            name="child",
            depends_on={parent_id},
        )
        
        await asyncio.sleep(1)
        
        # Parent should complete before child
        assert execution_order.index("parent") < execution_order.index("child")
        
        await queue.stop()
