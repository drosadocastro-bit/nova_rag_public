#!/usr/bin/env python3
"""
Resource Usage Profiler for NIC.

Profiles memory, CPU, and disk usage to identify bottlenecks
and support optimization for potato hardware.

Usage:
    python scripts/profile_resource_usage.py [--mode baseline|phase3.5|all]
"""

import os
import sys
import json
import time
import psutil
import tracemalloc
import traceback
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, List
from datetime import datetime

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ["NOVA_DISABLE_VISION"] = "1"  # Skip vision for profiling
os.environ["NOVA_ANOMALY_DETECTOR"] = "0"  # Skip for baseline


@dataclass
class MemorySnapshot:
    """Memory usage at a point in time."""
    timestamp: str
    resident_mb: float
    virtual_mb: float
    percent: float
    description: str


@dataclass
class ResourceProfile:
    """Complete resource profile."""
    component: str
    start_time: str
    end_time: str
    duration_seconds: float
    
    # Memory
    initial_memory_mb: float
    peak_memory_mb: float
    final_memory_mb: float
    memory_delta_mb: float
    
    # CPU
    cpu_percent: float
    num_threads: int
    
    # Disk
    cache_size_mb: float
    vector_db_size_mb: float
    
    # Snapshots
    snapshots: List[Dict[str, Any]]


class ResourceProfiler:
    """Profile resource usage across NIC components."""
    
    def __init__(self):
        self.process = psutil.Process()
        self.base_dir = Path(__file__).parent.parent
        self.profiles: List[ResourceProfile] = []
        
    def get_memory_info(self) -> tuple[float, float, float]:
        """Get RSS (resident), VMS (virtual), and percent."""
        info = self.process.memory_info()
        # Convert bytes to MB
        rss_mb = info.rss / 1024 / 1024
        vms_mb = info.vms / 1024 / 1024
        percent = self.process.memory_percent()
        return rss_mb, vms_mb, percent
    
    def get_disk_sizes(self) -> tuple[float, float]:
        """Get cache and vector_db sizes in MB."""
        cache_path = self.base_dir / "cache"
        vector_db_path = self.base_dir / "vector_db"
        
        cache_size = self._get_dir_size(cache_path) if cache_path.exists() else 0
        vector_db_size = self._get_dir_size(vector_db_path) if vector_db_path.exists() else 0
        
        return cache_size / 1024 / 1024, vector_db_size / 1024 / 1024
    
    @staticmethod
    def _get_dir_size(path: Path) -> int:
        """Get total size of directory in bytes."""
        total = 0
        try:
            for entry in path.rglob("*"):
                if entry.is_file():
                    total += entry.stat().st_size
        except:
            pass
        return total
    
    def profile_component(
        self,
        component_name: str,
        func,
        *args,
        **kwargs
    ) -> ResourceProfile:
        """Profile a component's resource usage."""
        print(f"\n{'='*70}")
        print(f"Profiling: {component_name}")
        print(f"{'='*70}")
        
        # Initial state
        tracemalloc.start()
        initial_rss, initial_vms, initial_percent = self.get_memory_info()
        initial_cache_mb, initial_vector_mb = self.get_disk_sizes()
        
        start_time = time.time()
        start_timestamp = datetime.now().isoformat()
        
        snapshots = []
        
        # Snapshot: Initial
        rss, vms, pct = self.get_memory_info()
        snapshots.append({
            "timestamp": datetime.now().isoformat(),
            "resident_mb": rss,
            "virtual_mb": vms,
            "percent": pct,
            "description": "Initial",
        })
        print(f"Initial Memory: {rss:.1f} MB")
        
        # Run component
        peak_memory = initial_rss
        try:
            result = func(*args, **kwargs)
            rss, vms, pct = self.get_memory_info()
            snapshots.append({
                "timestamp": datetime.now().isoformat(),
                "resident_mb": rss,
                "virtual_mb": vms,
                "percent": pct,
                "description": "After execution",
            })
            peak_memory = max(peak_memory, rss)
            print(f"After execution: {rss:.1f} MB (delta: +{rss - initial_rss:.1f} MB)")
        except Exception as e:
            print(f"ERROR: {e}")
            traceback.print_exc()
            rss = initial_rss
        
        end_time = time.time()
        end_timestamp = datetime.now().isoformat()
        duration = end_time - start_time
        
        # Final state
        final_rss, final_vms, final_percent = self.get_memory_info()
        final_cache_mb, final_vector_mb = self.get_disk_sizes()
        
        # Memory tracing
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_from_trace = peak / 1024 / 1024
        peak_memory = max(peak_memory, peak_from_trace)
        
        cpu_percent = self.process.cpu_percent(interval=0.1)
        num_threads = self.process.num_threads()
        
        profile = ResourceProfile(
            component=component_name,
            start_time=start_timestamp,
            end_time=end_timestamp,
            duration_seconds=duration,
            initial_memory_mb=initial_rss,
            peak_memory_mb=peak_memory,
            final_memory_mb=final_rss,
            memory_delta_mb=final_rss - initial_rss,
            cpu_percent=cpu_percent,
            num_threads=num_threads,
            cache_size_mb=final_cache_mb,
            vector_db_size_mb=final_vector_mb,
            snapshots=snapshots,
        )
        
        self.profiles.append(profile)
        
        # Print summary
        print(f"\nProfile Summary:")
        print(f"  Duration:     {duration:.2f}s")
        print(f"  Peak Memory:  {peak_memory:.1f} MB")
        print(f"  Memory Delta: {final_rss - initial_rss:+.1f} MB")
        print(f"  CPU Usage:    {cpu_percent:.1f}%")
        print(f"  Threads:      {num_threads}")
        print(f"  Cache Size:   {final_cache_mb:.1f} MB")
        print(f"  Vector DB:    {final_vector_mb:.1f} MB")
        
        return profile
    
    def save_report(self, output_file: str = "resource_profile.json"):
        """Save profiling results to JSON."""
        report = {
            "timestamp": datetime.now().isoformat(),
            "system_info": {
                "cpu_count": psutil.cpu_count(),
                "total_memory_mb": psutil.virtual_memory().total / 1024 / 1024,
                "available_memory_mb": psutil.virtual_memory().available / 1024 / 1024,
            },
            "profiles": [asdict(p) for p in self.profiles],
            "summary": self._generate_summary(),
        }
        
        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)
        
        print(f"\n✓ Report saved to {output_file}")
        return report
    
    def _generate_summary(self) -> Dict[str, Any]:
        """Generate summary statistics."""
        if not self.profiles:
            return {}
        
        total_memory = sum(p.memory_delta_mb for p in self.profiles)
        peak_overall = max(p.peak_memory_mb for p in self.profiles)
        total_duration = sum(p.duration_seconds for p in self.profiles)
        
        bottlenecks = sorted(self.profiles, key=lambda p: p.peak_memory_mb, reverse=True)
        
        return {
            "total_components": len(self.profiles),
            "total_duration_seconds": total_duration,
            "total_memory_overhead_mb": total_memory,
            "peak_memory_overall_mb": peak_overall,
            "heaviest_components": [
                {
                    "name": p.component,
                    "memory_mb": p.peak_memory_mb,
                    "duration_s": p.duration_seconds,
                }
                for p in bottlenecks[:5]
            ],
            "recommendations": self._generate_recommendations(bottlenecks),
        }
    
    def _generate_recommendations(self, bottlenecks) -> List[str]:
        """Generate optimization recommendations."""
        recs = []
        
        for profile in bottlenecks[:3]:
            if profile.peak_memory_mb > 500:
                recs.append(
                    f"🔴 {profile.component}: {profile.peak_memory_mb:.0f}MB - "
                    "Consider lazy loading or quantization"
                )
            elif profile.peak_memory_mb > 200:
                recs.append(
                    f"🟡 {profile.component}: {profile.peak_memory_mb:.0f}MB - "
                    "Potential optimization target"
                )
            else:
                recs.append(
                    f"🟢 {profile.component}: {profile.peak_memory_mb:.0f}MB - "
                    "Acceptable for potato hardware"
                )
        
        return recs


def profile_text_embeddings(profiler: ResourceProfiler):
    """Profile text embedding model loading."""
    def load_embeddings():
        from core.retrieval.retrieval_engine import get_text_embed_model
        model = get_text_embed_model()
        if model:
            # Warm up with a test query
            _ = model.encode("test query")
        return model
    
    return profiler.profile_component("Text Embeddings (sentence-transformers)", load_embeddings)


def profile_index_loading(profiler: ResourceProfiler):
    """Profile FAISS index loading."""
    def load_index():
        from core.retrieval.retrieval_engine import load_index
        try:
            idx = load_index()
            return idx
        except FileNotFoundError:
            print("  [Skip] Index file not found - this is normal on first run")
            return None
    
    return profiler.profile_component("Vector Index (FAISS)", load_index)


def profile_cross_encoder(profiler: ResourceProfiler):
    """Profile cross-encoder model loading."""
    def load_cross_encoder():
        from core.retrieval.retrieval_engine import get_cross_encoder
        model = get_cross_encoder()
        if model:
            # Warm up
            _ = model.predict([["test", "test"]])
        return model
    
    return profiler.profile_component("Cross-Encoder (reranking)", load_cross_encoder)


def profile_ollama_connection(profiler: ResourceProfiler):
    """Profile Ollama LLM connection."""
    def check_ollama():
        from core.generation.llm_gateway import check_ollama_connection
        try:
            result = check_ollama_connection()
            return result
        except Exception as e:
            print(f"  [Skip] Ollama not available: {e}")
            return None
    
    return profiler.profile_component("Ollama LLM Connection", check_ollama)


def profile_full_query(profiler: ResourceProfiler):
    """Profile a full retrieval + generation query."""
    def run_query():
        try:
            from backend import nova_text_handler
            result = nova_text_handler(
                "What are the main components of a vehicle engine?",
                mode="brief"
            )
            return result
        except Exception as e:
            print(f"  [Warning] Query failed: {e}")
            return None
    
    return profiler.profile_component("Full Query (retrieval + LLM)", run_query)


def profile_anomaly_detector(profiler: ResourceProfiler):
    """Profile anomaly detector loading."""
    def load_anomaly():
        os.environ["NOVA_ANOMALY_DETECTOR"] = "1"
        try:
            from core.phase3_5.anomaly_detector import AnomalyDetector  # type: ignore[import-not-found]
            detector = AnomalyDetector()
            return detector
        except Exception as e:
            print(f"  [Skip] Anomaly detector unavailable: {e}")
            return None
    
    return profiler.profile_component("Anomaly Detector (Phase 3.5)", load_anomaly)


def profile_compliance_reporter(profiler: ResourceProfiler):
    """Profile compliance reporter."""
    def load_compliance():
        try:
            from core.phase3_5.compliance_reporter import ComplianceReporter  # type: ignore[import-not-found]
            reporter = ComplianceReporter()
            return reporter
        except Exception as e:
            print(f"  [Skip] Compliance reporter unavailable: {e}")
            return None
    
    return profiler.profile_component("Compliance Reporter (Phase 3.5)", load_compliance)


def main():
    """Run profiling suite."""
    import argparse
    import traceback
    
    parser = argparse.ArgumentParser(
        description="Profile NIC resource usage for potato hardware optimization"
    )
    parser.add_argument(
        "--mode",
        choices=["baseline", "phase3.5", "all"],
        default="all",
        help="Profile baseline, Phase 3.5 features, or everything",
    )
    parser.add_argument(
        "--output",
        default="resource_profile.json",
        help="Output file for JSON report",
    )
    args = parser.parse_args()
    
    print(f"\n{'='*70}")
    print(f"NOVA NIC - RESOURCE USAGE PROFILER")
    print(f"{'='*70}")
    print(f"\nTarget: Potato Hardware Optimization")
    print(f"Mode: {args.mode.upper()}")
    print(f"Output: {args.output}")
    
    profiler = ResourceProfiler()
    
    baseline_components = [
        ("text_embeddings", profile_text_embeddings),
        ("index_loading", profile_index_loading),
        ("cross_encoder", profile_cross_encoder),
        ("ollama_connection", profile_ollama_connection),
        ("full_query", profile_full_query),
    ]
    
    phase3_5_components = [
        ("anomaly_detector", profile_anomaly_detector),
        ("compliance_reporter", profile_compliance_reporter),
    ]
    
    components = baseline_components
    if args.mode in ("phase3.5", "all"):
        if args.mode == "all":
            components = baseline_components + phase3_5_components
        else:
            components = phase3_5_components
    
    for name, profile_func in components:
        try:
            profile_func(profiler)
        except Exception as e:
            print(f"ERROR profiling {name}: {e}")
            traceback.print_exc()
    
    # Save report
    report = profiler.save_report(args.output)
    
    # Print summary
    print(f"\n{'='*70}")
    print(f"PROFILING SUMMARY")
    print(f"{'='*70}")
    
    summary = report["summary"]
    if summary:
        print(f"\nTotal Components Profiled: {summary['total_components']}")
        print(f"Total Duration: {summary['total_duration_seconds']:.2f}s")
        print(f"Total Memory Overhead: {summary['total_memory_overhead_mb']:.1f}MB")
        print(f"Peak Memory Overall: {summary['peak_memory_overall_mb']:.1f}MB")
        
        print(f"\nHeaviest Components:")
        for comp in summary["heaviest_components"]:
            print(f"  • {comp['name']}: {comp['memory_mb']:.1f}MB ({comp['duration_s']:.2f}s)")
        
        print(f"\nOptimization Recommendations:")
        for rec in summary["recommendations"]:
            print(f"  {rec}")
    
    print(f"\n{'='*70}\n")


if __name__ == "__main__":
    main()
