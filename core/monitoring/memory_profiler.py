"""
Memory Profiling and Optimization for NOVA NIC.

Comprehensive memory monitoring with:
- Real-time memory tracking
- Leak detection heuristics
- Object growth analysis
- Per-component memory breakdown
- Optimization recommendations
- Memory snapshots for debugging
"""

import gc
import logging
import os
import sys
import threading
import time
import tracemalloc
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, TypeVar

logger = logging.getLogger(__name__)


class MemorySeverity(str, Enum):
    """Severity levels for memory issues."""
    
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class MemorySnapshot:
    """Point-in-time memory snapshot."""
    
    timestamp: float
    rss_bytes: int  # Resident Set Size
    vms_bytes: int  # Virtual Memory Size
    heap_bytes: int  # Python heap
    gc_objects: int  # Objects tracked by GC
    gc_generations: Dict[int, int] = field(default_factory=dict)
    top_types: List[Tuple[str, int, int]] = field(default_factory=list)  # type, count, size
    
    @property
    def rss_mb(self) -> float:
        """RSS in megabytes."""
        return self.rss_bytes / (1024 * 1024)
    
    @property
    def vms_mb(self) -> float:
        """VMS in megabytes."""
        return self.vms_bytes / (1024 * 1024)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "timestamp_iso": datetime.fromtimestamp(self.timestamp).isoformat(),
            "rss_mb": round(self.rss_mb, 2),
            "vms_mb": round(self.vms_mb, 2),
            "heap_bytes": self.heap_bytes,
            "gc_objects": self.gc_objects,
            "gc_generations": self.gc_generations,
            "top_types": [
                {"type": t, "count": c, "size_kb": round(s / 1024, 2)}
                for t, c, s in self.top_types[:10]
            ],
        }


@dataclass
class MemoryLeak:
    """Detected memory leak information."""
    
    component: str
    growth_rate_mb_per_hour: float
    samples: int
    confidence: float  # 0.0 to 1.0
    first_detected: float
    details: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "component": self.component,
            "growth_rate_mb_per_hour": round(self.growth_rate_mb_per_hour, 3),
            "samples": self.samples,
            "confidence": round(self.confidence, 2),
            "first_detected": datetime.fromtimestamp(self.first_detected).isoformat(),
            "details": self.details,
        }


@dataclass
class MemoryRecommendation:
    """Memory optimization recommendation."""
    
    severity: MemorySeverity
    category: str
    title: str
    description: str
    impact_estimate: str
    action: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "severity": self.severity.value,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "impact_estimate": self.impact_estimate,
            "action": self.action,
        }


@dataclass
class MemoryReport:
    """Comprehensive memory analysis report."""
    
    current_snapshot: MemorySnapshot
    peak_rss_mb: float
    baseline_rss_mb: float
    growth_since_baseline_mb: float
    leaks_detected: List[MemoryLeak]
    recommendations: List[MemoryRecommendation]
    component_breakdown: Dict[str, int]  # Component -> bytes
    tracemalloc_enabled: bool
    gc_stats: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "current": self.current_snapshot.to_dict(),
            "peak_rss_mb": round(self.peak_rss_mb, 2),
            "baseline_rss_mb": round(self.baseline_rss_mb, 2),
            "growth_since_baseline_mb": round(self.growth_since_baseline_mb, 2),
            "leaks_detected": [l.to_dict() for l in self.leaks_detected],
            "recommendations": [r.to_dict() for r in self.recommendations],
            "component_breakdown": {
                k: round(v / (1024 * 1024), 2)  # Convert to MB
                for k, v in self.component_breakdown.items()
            },
            "tracemalloc_enabled": self.tracemalloc_enabled,
            "gc_stats": self.gc_stats,
        }


class MemoryProfiler:
    """
    Comprehensive memory profiler for NOVA NIC.
    
    Features:
    - Real-time memory monitoring
    - Automatic leak detection
    - Component-level tracking
    - Optimization recommendations
    - Snapshot comparison
    """
    
    def __init__(
        self,
        sample_interval_seconds: float = 60.0,
        max_samples: int = 1000,
        enable_tracemalloc: bool = True,
        leak_detection_threshold_mb: float = 10.0,
        leak_detection_min_samples: int = 10,
    ):
        """
        Initialize memory profiler.
        
        Args:
            sample_interval_seconds: Interval between automatic samples
            max_samples: Maximum samples to retain
            enable_tracemalloc: Enable detailed allocation tracking
            leak_detection_threshold_mb: Growth rate to consider a leak
            leak_detection_min_samples: Minimum samples for leak detection
        """
        self.sample_interval = sample_interval_seconds
        self.max_samples = max_samples
        self.enable_tracemalloc = enable_tracemalloc
        self.leak_threshold_mb = leak_detection_threshold_mb
        self.leak_min_samples = leak_detection_min_samples
        
        # State
        self._samples: List[MemorySnapshot] = []
        self._component_allocations: Dict[str, List[int]] = defaultdict(list)
        self._baseline_snapshot: Optional[MemorySnapshot] = None
        self._peak_rss: int = 0
        self._detected_leaks: List[MemoryLeak] = []
        
        # Threading
        self._lock = threading.Lock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitoring = threading.Event()
        
        # Initialize tracemalloc if requested
        if self.enable_tracemalloc and not tracemalloc.is_tracing():
            tracemalloc.start(10)  # 10 frames of traceback
    
    def _get_process_memory(self) -> Tuple[int, int]:
        """Get process RSS and VMS in bytes."""
        try:
            import psutil
            process = psutil.Process()
            mem_info = process.memory_info()
            return mem_info.rss, mem_info.vms
        except ImportError:
            # Fallback without psutil
            return 0, 0
    
    def _get_gc_stats(self) -> Dict[str, Any]:
        """Get garbage collector statistics."""
        stats = {}
        
        # Object counts by generation
        gc_counts = gc.get_count()
        stats["generation_counts"] = {
            0: gc_counts[0],
            1: gc_counts[1],
            2: gc_counts[2],
        }
        
        # GC thresholds
        thresholds = gc.get_threshold()
        stats["thresholds"] = {
            0: thresholds[0],
            1: thresholds[1],
            2: thresholds[2],
        }
        
        # GC state
        stats["is_enabled"] = gc.isenabled()
        stats["callbacks_count"] = len(gc.callbacks)
        
        return stats
    
    def _count_objects_by_type(self, limit: int = 20) -> List[Tuple[str, int, int]]:
        """Count objects by type with size estimation."""
        type_counts: Dict[str, Tuple[int, int]] = defaultdict(lambda: (0, 0))
        
        for obj in gc.get_objects():
            try:
                type_name = type(obj).__name__
                size = sys.getsizeof(obj)
                count, total_size = type_counts[type_name]
                type_counts[type_name] = (count + 1, total_size + size)
            except (TypeError, RecursionError):
                continue
        
        # Sort by size
        sorted_types = sorted(
            [(name, count, size) for name, (count, size) in type_counts.items()],
            key=lambda x: x[2],
            reverse=True
        )
        
        return sorted_types[:limit]
    
    def take_snapshot(self, label: Optional[str] = None) -> MemorySnapshot:
        """
        Take a memory snapshot.
        
        Args:
            label: Optional label for the snapshot
            
        Returns:
            MemorySnapshot with current state
        """
        rss, vms = self._get_process_memory()
        
        # Get heap size from tracemalloc if available
        heap_bytes = 0
        if tracemalloc.is_tracing():
            current, peak = tracemalloc.get_traced_memory()
            heap_bytes = current
        
        gc_stats = self._get_gc_stats()
        top_types = self._count_objects_by_type()
        
        snapshot = MemorySnapshot(
            timestamp=time.time(),
            rss_bytes=rss,
            vms_bytes=vms,
            heap_bytes=heap_bytes,
            gc_objects=len(gc.get_objects()),
            gc_generations=gc_stats["generation_counts"],
            top_types=top_types,
        )
        
        # Update peak
        if rss > self._peak_rss:
            self._peak_rss = rss
        
        # Store sample
        with self._lock:
            self._samples.append(snapshot)
            if len(self._samples) > self.max_samples:
                self._samples.pop(0)
            
            # Set baseline if not set
            if self._baseline_snapshot is None:
                self._baseline_snapshot = snapshot
        
        if label:
            logger.debug(f"Memory snapshot [{label}]: RSS={snapshot.rss_mb:.1f}MB")
        
        return snapshot
    
    def track_component(self, component: str, size_bytes: int) -> None:
        """
        Track memory allocation for a component.
        
        Args:
            component: Component name (e.g., 'bm25_index', 'faiss_index')
            size_bytes: Allocated size in bytes
        """
        with self._lock:
            self._component_allocations[component].append(size_bytes)
            # Keep only recent samples
            if len(self._component_allocations[component]) > 100:
                self._component_allocations[component].pop(0)
    
    def _detect_leaks(self) -> List[MemoryLeak]:
        """Analyze samples for potential memory leaks."""
        leaks = []
        
        with self._lock:
            if len(self._samples) < self.leak_min_samples:
                return leaks
            
            # Analyze RSS growth over time
            samples = self._samples[-self.leak_min_samples:]
            
            # Calculate growth rate
            first_sample = samples[0]
            last_sample = samples[-1]
            time_diff_hours = (last_sample.timestamp - first_sample.timestamp) / 3600
            
            if time_diff_hours < 0.1:  # Need at least 6 minutes of data
                return leaks
            
            rss_growth_mb = (last_sample.rss_bytes - first_sample.rss_bytes) / (1024 * 1024)
            growth_rate = rss_growth_mb / time_diff_hours
            
            # Check if growth exceeds threshold
            if growth_rate > self.leak_threshold_mb:
                # Calculate confidence based on consistency
                growth_values = []
                for i in range(1, len(samples)):
                    delta = samples[i].rss_bytes - samples[i-1].rss_bytes
                    growth_values.append(delta)
                
                # Confidence is higher if growth is consistent
                if growth_values:
                    positive_growth = sum(1 for g in growth_values if g > 0)
                    confidence = positive_growth / len(growth_values)
                else:
                    confidence = 0.5
                
                if confidence > 0.6:  # At least 60% of samples showed growth
                    leak = MemoryLeak(
                        component="process",
                        growth_rate_mb_per_hour=growth_rate,
                        samples=len(samples),
                        confidence=confidence,
                        first_detected=time.time(),
                        details=f"RSS grew from {first_sample.rss_mb:.1f}MB to {last_sample.rss_mb:.1f}MB",
                    )
                    leaks.append(leak)
            
            # Check component-level growth
            for component, sizes in self._component_allocations.items():
                if len(sizes) < 3:
                    continue
                
                # Simple trend detection
                if sizes[-1] > sizes[0] * 1.5:  # 50% growth
                    growth_mb = (sizes[-1] - sizes[0]) / (1024 * 1024)
                    leak = MemoryLeak(
                        component=component,
                        growth_rate_mb_per_hour=growth_mb,
                        samples=len(sizes),
                        confidence=0.7,
                        first_detected=time.time(),
                        details=f"Grew from {sizes[0]/(1024*1024):.1f}MB to {sizes[-1]/(1024*1024):.1f}MB",
                    )
                    leaks.append(leak)
        
        return leaks
    
    def _generate_recommendations(
        self,
        snapshot: MemorySnapshot,
        leaks: List[MemoryLeak]
    ) -> List[MemoryRecommendation]:
        """Generate optimization recommendations."""
        recommendations = []
        
        # High memory usage
        if snapshot.rss_mb > 2000:  # > 2GB
            recommendations.append(MemoryRecommendation(
                severity=MemorySeverity.CRITICAL,
                category="memory_usage",
                title="High Memory Usage",
                description=f"Process using {snapshot.rss_mb:.0f}MB RAM",
                impact_estimate="May cause OOM or system instability",
                action="Consider reducing batch sizes, clearing caches, or adding more RAM",
            ))
        elif snapshot.rss_mb > 1000:  # > 1GB
            recommendations.append(MemoryRecommendation(
                severity=MemorySeverity.WARNING,
                category="memory_usage",
                title="Elevated Memory Usage",
                description=f"Process using {snapshot.rss_mb:.0f}MB RAM",
                impact_estimate="May affect other processes",
                action="Monitor for further growth; consider cache limits",
            ))
        
        # GC pressure
        gc_gen0 = snapshot.gc_generations.get(0, 0)
        if gc_gen0 > 10000:
            recommendations.append(MemoryRecommendation(
                severity=MemorySeverity.WARNING,
                category="gc_pressure",
                title="High GC Pressure",
                description=f"{gc_gen0} objects in generation 0",
                impact_estimate="GC overhead may affect latency",
                action="Consider object pooling or reducing temporary allocations",
            ))
        
        # Object count
        if snapshot.gc_objects > 1_000_000:
            recommendations.append(MemoryRecommendation(
                severity=MemorySeverity.WARNING,
                category="object_count",
                title="High Object Count",
                description=f"{snapshot.gc_objects:,} objects tracked by GC",
                impact_estimate="Large GC scans, potential latency spikes",
                action="Reduce object allocations or use __slots__ for common classes",
            ))
        
        # Leak-specific recommendations
        for leak in leaks:
            if leak.confidence > 0.7:
                recommendations.append(MemoryRecommendation(
                    severity=MemorySeverity.CRITICAL,
                    category="memory_leak",
                    title=f"Potential Leak in {leak.component}",
                    description=f"Growing at {leak.growth_rate_mb_per_hour:.1f}MB/hour",
                    impact_estimate="Will eventually exhaust memory",
                    action=f"Investigate {leak.component} for unclosed resources or growing collections",
                ))
        
        # Top memory consumers
        if snapshot.top_types:
            top_type, top_count, top_size = snapshot.top_types[0]
            if top_size > 100 * 1024 * 1024:  # > 100MB
                recommendations.append(MemoryRecommendation(
                    severity=MemorySeverity.INFO,
                    category="large_type",
                    title=f"Large Allocation: {top_type}",
                    description=f"{top_count:,} objects, {top_size/(1024*1024):.1f}MB total",
                    impact_estimate="Significant memory consumer",
                    action=f"Consider optimizing {top_type} storage or reducing count",
                ))
        
        return recommendations
    
    def get_report(self) -> MemoryReport:
        """Generate comprehensive memory report."""
        snapshot = self.take_snapshot()
        leaks = self._detect_leaks()
        recommendations = self._generate_recommendations(snapshot, leaks)
        
        # Component breakdown
        component_breakdown = {}
        for component, sizes in self._component_allocations.items():
            if sizes:
                component_breakdown[component] = sizes[-1]
        
        baseline_rss = 0.0
        growth = 0.0
        if self._baseline_snapshot:
            baseline_rss = self._baseline_snapshot.rss_mb
            growth = snapshot.rss_mb - baseline_rss
        
        return MemoryReport(
            current_snapshot=snapshot,
            peak_rss_mb=self._peak_rss / (1024 * 1024),
            baseline_rss_mb=baseline_rss,
            growth_since_baseline_mb=growth,
            leaks_detected=leaks,
            recommendations=recommendations,
            component_breakdown=component_breakdown,
            tracemalloc_enabled=tracemalloc.is_tracing(),
            gc_stats=self._get_gc_stats(),
        )
    
    def start_monitoring(self) -> None:
        """Start background memory monitoring."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        
        self._stop_monitoring.clear()
        
        def monitor_loop():
            while not self._stop_monitoring.wait(self.sample_interval):
                try:
                    self.take_snapshot()
                except Exception as e:
                    logger.error(f"Memory monitoring error: {e}")
        
        self._monitor_thread = threading.Thread(
            target=monitor_loop,
            daemon=True,
            name="MemoryProfiler-Monitor"
        )
        self._monitor_thread.start()
        logger.info(f"Started memory monitoring (interval: {self.sample_interval}s)")
    
    def stop_monitoring(self) -> None:
        """Stop background memory monitoring."""
        self._stop_monitoring.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        logger.info("Stopped memory monitoring")
    
    def force_gc(self) -> Dict[str, Any]:
        """
        Force garbage collection and return stats.
        
        Returns:
            Dict with objects collected per generation
        """
        before = self._get_process_memory()[0]
        
        collected: Dict[str, Any] = {
            "gen0": gc.collect(0),
            "gen1": gc.collect(1),
            "gen2": gc.collect(2),
        }
        
        after = self._get_process_memory()[0]
        freed_mb = (before - after) / (1024 * 1024)
        
        collected["freed_mb"] = round(freed_mb, 2)
        logger.info(f"GC completed: freed {freed_mb:.1f}MB, collected {sum(collected.values()) - collected['freed_mb']} objects")
        
        return collected
    
    def get_tracemalloc_top(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get top memory allocations from tracemalloc.
        
        Args:
            limit: Number of top allocations to return
            
        Returns:
            List of allocation info dicts
        """
        if not tracemalloc.is_tracing():
            return []
        
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics('lineno')[:limit]
        
        return [
            {
                "file": str(stat.traceback),
                "size_kb": round(stat.size / 1024, 2),
                "count": stat.count,
            }
            for stat in top_stats
        ]
    
    def compare_snapshots(
        self,
        older_index: int = 0,
        newer_index: int = -1
    ) -> Dict[str, Any]:
        """
        Compare two snapshots.
        
        Args:
            older_index: Index of older snapshot
            newer_index: Index of newer snapshot
            
        Returns:
            Comparison results
        """
        with self._lock:
            if len(self._samples) < 2:
                return {"error": "Not enough samples"}
            
            older = self._samples[older_index]
            newer = self._samples[newer_index]
        
        time_diff = newer.timestamp - older.timestamp
        rss_diff = newer.rss_bytes - older.rss_bytes
        objects_diff = newer.gc_objects - older.gc_objects
        
        return {
            "time_diff_seconds": round(time_diff, 2),
            "rss_diff_mb": round(rss_diff / (1024 * 1024), 2),
            "objects_diff": objects_diff,
            "older": older.to_dict(),
            "newer": newer.to_dict(),
        }
    
    def reset_baseline(self) -> MemorySnapshot:
        """Reset baseline to current state."""
        snapshot = self.take_snapshot()
        with self._lock:
            self._baseline_snapshot = snapshot
            self._peak_rss = snapshot.rss_bytes
        logger.info(f"Reset memory baseline to {snapshot.rss_mb:.1f}MB")
        return snapshot


# ==================
# Context Manager for Tracking
# ==================

class track_memory:
    """
    Context manager for tracking memory during a block.
    
    Example:
        with track_memory("index_rebuild") as tracker:
            rebuild_index()
        print(f"Used {tracker.delta_mb:.1f}MB")
    """
    
    def __init__(self, label: str, profiler: Optional[MemoryProfiler] = None):
        self.label = label
        self.profiler = profiler or get_memory_profiler()
        self.start_rss: int = 0
        self.end_rss: int = 0
        self.delta_mb: float = 0.0
    
    def __enter__(self) -> "track_memory":
        try:
            import psutil
            self.start_rss = psutil.Process().memory_info().rss
        except ImportError:
            pass
        return self
    
    def __exit__(self, *args) -> None:
        try:
            import psutil
            self.end_rss = psutil.Process().memory_info().rss
            self.delta_mb = (self.end_rss - self.start_rss) / (1024 * 1024)
            
            if self.profiler:
                self.profiler.track_component(self.label, self.end_rss - self.start_rss)
            
            logger.debug(f"Memory [{self.label}]: {self.delta_mb:+.1f}MB")
        except ImportError:
            pass


# ==================
# Global Instance
# ==================

_global_profiler: Optional[MemoryProfiler] = None


def get_memory_profiler() -> MemoryProfiler:
    """Get or create global memory profiler instance."""
    global _global_profiler
    
    if _global_profiler is None:
        sample_interval = float(os.environ.get("NOVA_MEMORY_SAMPLE_INTERVAL", "60"))
        enable_tracemalloc = os.environ.get("NOVA_MEMORY_TRACEMALLOC", "0") == "1"
        
        _global_profiler = MemoryProfiler(
            sample_interval_seconds=sample_interval,
            enable_tracemalloc=enable_tracemalloc,
        )
    
    return _global_profiler


def reset_memory_profiler() -> None:
    """Reset global memory profiler (for testing)."""
    global _global_profiler
    if _global_profiler:
        _global_profiler.stop_monitoring()
        _global_profiler = None
