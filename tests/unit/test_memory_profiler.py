"""Tests for memory profiler module."""

import gc
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from core.monitoring.memory_profiler import (
    MemoryLeak,
    MemoryProfiler,
    MemoryRecommendation,
    MemoryReport,
    MemorySeverity,
    MemorySnapshot,
    get_memory_profiler,
    reset_memory_profiler,
    track_memory,
)


class TestMemorySnapshot:
    """Tests for MemorySnapshot dataclass."""
    
    def test_basic_creation(self):
        """Test snapshot creation."""
        snapshot = MemorySnapshot(
            timestamp=time.time(),
            rss_bytes=1024 * 1024 * 500,  # 500MB
            vms_bytes=1024 * 1024 * 1000,  # 1GB
            heap_bytes=1024 * 1024 * 100,  # 100MB
            gc_objects=10000,
        )
        
        assert snapshot.rss_mb == 500.0
        assert snapshot.vms_mb == 1000.0
        assert snapshot.gc_objects == 10000
    
    def test_to_dict(self):
        """Test serialization."""
        snapshot = MemorySnapshot(
            timestamp=time.time(),
            rss_bytes=1024 * 1024 * 500,
            vms_bytes=1024 * 1024 * 1000,
            heap_bytes=0,
            gc_objects=10000,
            gc_generations={0: 100, 1: 50, 2: 25},
        )
        
        d = snapshot.to_dict()
        
        assert d["rss_mb"] == 500.0
        assert "timestamp_iso" in d
        assert d["gc_generations"] == {0: 100, 1: 50, 2: 25}


class TestMemoryLeak:
    """Tests for MemoryLeak dataclass."""
    
    def test_basic_creation(self):
        """Test leak creation."""
        leak = MemoryLeak(
            component="bm25_index",
            growth_rate_mb_per_hour=5.0,
            samples=20,
            confidence=0.85,
            first_detected=time.time(),
            details="Growing steadily",
        )
        
        assert leak.component == "bm25_index"
        assert leak.confidence == 0.85
    
    def test_to_dict(self):
        """Test serialization."""
        leak = MemoryLeak(
            component="cache",
            growth_rate_mb_per_hour=2.5,
            samples=10,
            confidence=0.7,
            first_detected=time.time(),
        )
        
        d = leak.to_dict()
        
        assert d["component"] == "cache"
        assert d["growth_rate_mb_per_hour"] == 2.5


class TestMemoryRecommendation:
    """Tests for MemoryRecommendation dataclass."""
    
    def test_basic_creation(self):
        """Test recommendation creation."""
        rec = MemoryRecommendation(
            severity=MemorySeverity.WARNING,
            category="gc_pressure",
            title="High GC Pressure",
            description="Many objects in gen 0",
            impact_estimate="Latency spikes",
            action="Reduce allocations",
        )
        
        assert rec.severity == MemorySeverity.WARNING
        assert rec.category == "gc_pressure"
    
    def test_to_dict(self):
        """Test serialization."""
        rec = MemoryRecommendation(
            severity=MemorySeverity.CRITICAL,
            category="memory_leak",
            title="Leak Detected",
            description="Memory growing",
            impact_estimate="OOM",
            action="Investigate",
        )
        
        d = rec.to_dict()
        
        assert d["severity"] == "critical"
        assert d["category"] == "memory_leak"


class TestMemoryReport:
    """Tests for MemoryReport dataclass."""
    
    def test_to_dict(self):
        """Test report serialization."""
        snapshot = MemorySnapshot(
            timestamp=time.time(),
            rss_bytes=500 * 1024 * 1024,
            vms_bytes=1000 * 1024 * 1024,
            heap_bytes=0,
            gc_objects=10000,
        )
        
        report = MemoryReport(
            current_snapshot=snapshot,
            peak_rss_mb=600.0,
            baseline_rss_mb=400.0,
            growth_since_baseline_mb=100.0,
            leaks_detected=[],
            recommendations=[],
            component_breakdown={"cache": 100 * 1024 * 1024},
            tracemalloc_enabled=False,
            gc_stats={},
        )
        
        d = report.to_dict()
        
        assert d["peak_rss_mb"] == 600.0
        assert d["growth_since_baseline_mb"] == 100.0
        assert "cache" in d["component_breakdown"]


class TestMemoryProfiler:
    """Tests for MemoryProfiler class."""
    
    @pytest.fixture
    def profiler(self):
        """Create profiler for testing."""
        p = MemoryProfiler(
            sample_interval_seconds=0.1,
            enable_tracemalloc=False,
            leak_detection_threshold_mb=1.0,
            leak_detection_min_samples=3,
        )
        yield p
        p.stop_monitoring()
    
    def test_take_snapshot(self, profiler):
        """Test taking memory snapshot."""
        snapshot = profiler.take_snapshot()
        
        assert snapshot.timestamp > 0
        assert snapshot.gc_objects > 0
        assert isinstance(snapshot.gc_generations, dict)
    
    def test_take_snapshot_with_label(self, profiler):
        """Test labeled snapshot."""
        snapshot = profiler.take_snapshot(label="test_point")
        
        assert snapshot is not None
    
    def test_track_component(self, profiler):
        """Test component tracking."""
        profiler.track_component("bm25_index", 100 * 1024 * 1024)
        profiler.track_component("bm25_index", 110 * 1024 * 1024)
        
        report = profiler.get_report()
        
        assert "bm25_index" in report.component_breakdown
    
    def test_get_report(self, profiler):
        """Test getting full report."""
        profiler.take_snapshot()
        
        report = profiler.get_report()
        
        assert report.current_snapshot is not None
        assert isinstance(report.leaks_detected, list)
        assert isinstance(report.recommendations, list)
    
    def test_force_gc(self, profiler):
        """Test forced garbage collection."""
        # Create some garbage
        garbage = [{"data": "x" * 1000} for _ in range(100)]
        del garbage
        
        result = profiler.force_gc()
        
        assert "gen0" in result
        assert "gen1" in result
        assert "gen2" in result
        assert "freed_mb" in result
    
    def test_reset_baseline(self, profiler):
        """Test resetting baseline."""
        profiler.take_snapshot()
        
        new_baseline = profiler.reset_baseline()
        
        assert new_baseline is not None
        report = profiler.get_report()
        # Growth should be ~0 right after reset
        assert abs(report.growth_since_baseline_mb) < 10
    
    def test_compare_snapshots(self, profiler):
        """Test comparing snapshots."""
        profiler.take_snapshot()
        time.sleep(0.1)
        profiler.take_snapshot()
        
        comparison = profiler.compare_snapshots(0, -1)
        
        assert "time_diff_seconds" in comparison
        assert "rss_diff_mb" in comparison
        assert "older" in comparison
        assert "newer" in comparison
    
    def test_compare_insufficient_samples(self, profiler):
        """Test comparison with insufficient samples."""
        comparison = profiler.compare_snapshots()
        
        assert "error" in comparison
    
    def test_start_stop_monitoring(self, profiler):
        """Test background monitoring."""
        profiler.start_monitoring()
        time.sleep(0.3)
        profiler.stop_monitoring()
        
        # Should have collected some samples
        report = profiler.get_report()
        assert report.current_snapshot is not None
    
    def test_recommendations_high_memory(self, profiler):
        """Test recommendations for high memory."""
        # Create a snapshot with high memory usage manually
        snapshot = MemorySnapshot(
            timestamp=time.time(),
            rss_bytes=3 * 1024 * 1024 * 1024,  # 3GB
            vms_bytes=4 * 1024 * 1024 * 1024,
            heap_bytes=0,
            gc_objects=10000,
        )
        
        # Generate recommendations for this snapshot
        recommendations = profiler._generate_recommendations(snapshot, [])
        
        # Should have critical recommendation
        severities = [r.severity for r in recommendations]
        assert MemorySeverity.CRITICAL in severities


class TestTrackMemory:
    """Tests for track_memory context manager."""
    
    def test_basic_tracking(self):
        """Test basic memory tracking."""
        reset_memory_profiler()
        
        with track_memory("test_operation") as tracker:
            # Allocate some memory
            data = [{"x": i} for i in range(1000)]
        
        # Should have tracked something
        assert hasattr(tracker, 'delta_mb')
    
    def test_tracking_without_psutil(self):
        """Test tracking when psutil unavailable."""
        with patch.dict(sys.modules, {'psutil': None}):
            # Should not crash
            with track_memory("safe_operation"):
                pass


class TestGlobalProfiler:
    """Tests for global profiler instance."""
    
    def test_get_memory_profiler(self):
        """Test getting global profiler."""
        reset_memory_profiler()
        
        p1 = get_memory_profiler()
        p2 = get_memory_profiler()
        
        assert p1 is p2
        
        reset_memory_profiler()
    
    def test_reset_memory_profiler(self):
        """Test resetting global profiler."""
        p1 = get_memory_profiler()
        reset_memory_profiler()
        p2 = get_memory_profiler()
        
        assert p1 is not p2
        
        reset_memory_profiler()
    
    def test_env_configuration(self):
        """Test configuration from environment."""
        reset_memory_profiler()
        
        with patch.dict("os.environ", {
            "NOVA_MEMORY_SAMPLE_INTERVAL": "30",
            "NOVA_MEMORY_TRACEMALLOC": "0",
        }):
            profiler = get_memory_profiler()
            assert profiler.sample_interval == 30.0
        
        reset_memory_profiler()


class TestMemorySeverity:
    """Tests for MemorySeverity enum."""
    
    def test_severity_values(self):
        """Test all severity values."""
        assert MemorySeverity.INFO == "info"
        assert MemorySeverity.WARNING == "warning"
        assert MemorySeverity.CRITICAL == "critical"
