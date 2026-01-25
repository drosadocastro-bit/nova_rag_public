"""
Phase 4.3: Advanced Analytics for NIC

Comprehensive analytics framework built on Phase 4.1 observability data:
- Query classification and feature tracking
- Anomaly detection (statistical & ML-based)
- Trend analysis and prediction
- Cost analytics and optimization
- Performance bottleneck identification
- Custom reports and dashboards
"""

import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from statistics import mean, median, stdev

logger = logging.getLogger(__name__)


class QueryCategory(str, Enum):
    """Classification of query types."""
    
    FACTUAL = "factual"           # Factual questions
    PROCEDURAL = "procedural"     # How-to, procedures
    DIAGNOSTIC = "diagnostic"     # Troubleshooting
    COMPARATIVE = "comparative"   # Comparisons
    PREDICTIVE = "predictive"     # What-if scenarios
    EXPLORATORY = "exploratory"   # Open-ended exploration
    SAFETY = "safety"             # Safety-related
    COMPLIANCE = "compliance"     # Compliance checks


class AnomalyType(str, Enum):
    """Types of detected anomalies."""
    
    LATENCY_SPIKE = "latency_spike"
    MEMORY_SPIKE = "memory_spike"
    ERROR_RATE_INCREASE = "error_rate_increase"
    CACHE_MISS_SURGE = "cache_miss_surge"
    UNUSUAL_PATTERN = "unusual_pattern"
    PERFORMANCE_DEGRADATION = "performance_degradation"


@dataclass
class QueryFeature:
    """Tracked features of a query."""
    
    query_id: str
    timestamp: float
    category: QueryCategory
    features: Dict[str, Any] = field(default_factory=dict)
    
    # Query characteristics
    query_length: int = 0
    query_complexity: float = 0.0  # 0-1
    
    # Performance
    latency_ms: float = 0.0
    memory_delta_mb: float = 0.0
    cache_hit: bool = False
    
    # Quality
    confidence_score: float = 0.0
    
    # Context
    hardware_tier: str = "standard"
    time_of_day: int = 0  # 0-23
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PerformanceTrend:
    """Performance trend data point."""
    
    timestamp: float
    metric_name: str
    mean_value: float
    p50_value: float
    p95_value: float
    p99_value: float
    count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AnomalyAlert:
    """Detected anomaly."""
    
    anomaly_id: str
    anomaly_type: AnomalyType
    severity: str  # low, medium, high, critical
    message: str
    detected_at: float
    metric_value: float
    expected_value: float
    deviation: float  # percentage
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "anomaly_id": self.anomaly_id,
            "anomaly_type": self.anomaly_type.value,
            "severity": self.severity,
            "message": self.message,
            "detected_at": datetime.fromtimestamp(self.detected_at).isoformat(),
            "metric_value": self.metric_value,
            "expected_value": self.expected_value,
            "deviation": self.deviation,
            "details": self.details,
        }


class QueryAnalytics:
    """
    Analyzes query patterns and characteristics.
    
    Tracks:
    - Query categories and types
    - Feature adoption
    - Common query patterns
    - Query complexity distribution
    """
    
    def __init__(self, max_queries: int = 10000):
        self.max_queries = max_queries
        self.queries: deque = deque(maxlen=max_queries)
        
        # Aggregations
        self.category_counts: Dict[QueryCategory, int] = defaultdict(int)
        self.feature_usage: Dict[str, int] = defaultdict(int)
        self.complexity_distribution: List[float] = []
    
    def track_query(self, feature: QueryFeature) -> None:
        """Track a query."""
        self.queries.append(feature)
        self.category_counts[feature.category] += 1
        
        # Track features
        for key in feature.features.keys():
            self.feature_usage[key] += 1
        
        self.complexity_distribution.append(feature.query_complexity)
    
    def get_category_distribution(self) -> Dict[str, int]:
        """Get query category distribution."""
        return {cat.value: count for cat, count in self.category_counts.items()}
    
    def get_top_features(self, limit: int = 20) -> List[Tuple[str, int]]:
        """Get most used features."""
        return sorted(self.feature_usage.items(), key=lambda x: x[1], reverse=True)[:limit]
    
    def get_complexity_stats(self) -> Dict[str, float]:
        """Get query complexity statistics."""
        if not self.complexity_distribution:
            return {}
        
        values = self.complexity_distribution
        return {
            "mean": mean(values),
            "median": median(values),
            "min": min(values),
            "max": max(values),
            "stdev": stdev(values) if len(values) > 1 else 0,
        }
    
    def get_slowest_queries(self, limit: int = 10) -> List[QueryFeature]:
        """Get slowest queries."""
        sorted_queries = sorted(self.queries, key=lambda q: q.latency_ms, reverse=True)
        return list(sorted_queries[:limit])
    
    def get_least_confident(self, limit: int = 10) -> List[QueryFeature]:
        """Get queries with lowest confidence."""
        sorted_queries = sorted(self.queries, key=lambda q: q.confidence_score)
        return list(sorted_queries[:limit])
    
    def get_summary(self) -> Dict[str, Any]:
        """Get query analytics summary."""
        return {
            "total_queries": len(self.queries),
            "category_distribution": self.get_category_distribution(),
            "top_features": self.get_top_features(10),
            "complexity_stats": self.get_complexity_stats(),
            "slowest_queries": [q.to_dict() for q in self.get_slowest_queries(5)],
            "least_confident": [q.to_dict() for q in self.get_least_confident(5)],
        }


class PerformanceAnalytics:
    """
    Analyzes performance trends over time.
    
    Tracks:
    - Latency trends (hourly, daily, weekly)
    - Memory usage patterns
    - Cache effectiveness
    - Error rate trends
    """
    
    def __init__(self, retention_hours: int = 168):  # 1 week
        self.retention_hours = retention_hours
        self.hourly_trends: Dict[str, deque] = defaultdict(lambda: deque(maxlen=retention_hours))
        self.baseline_metrics: Dict[str, float] = {}
    
    def record_metric_trend(
        self,
        metric_name: str,
        values: List[float],
        timestamp: Optional[float] = None,
    ) -> None:
        """Record a metric trend."""
        if not values:
            return
        
        timestamp = timestamp or time.time()
        
        trend = PerformanceTrend(
            timestamp=timestamp,
            metric_name=metric_name,
            mean_value=mean(values),
            p50_value=sorted(values)[len(values) // 2],
            p95_value=sorted(values)[int(len(values) * 0.95)],
            p99_value=sorted(values)[int(len(values) * 0.99)],
            count=len(values),
        )
        
        self.hourly_trends[metric_name].append(trend)
    
    def set_baseline(self, metric_name: str, value: float) -> None:
        """Set baseline for anomaly detection."""
        self.baseline_metrics[metric_name] = value
    
    def get_trend(self, metric_name: str, limit: int = 168) -> List[PerformanceTrend]:
        """Get trend data for a metric."""
        trends = self.hourly_trends.get(metric_name, [])
        return list(trends)[-limit:]
    
    def get_trend_stats(self, metric_name: str) -> Dict[str, float]:
        """Get statistics for a metric trend."""
        trends = self.get_trend(metric_name)
        
        if not trends:
            return {}
        
        means = [t.mean_value for t in trends]
        
        return {
            "current": means[-1] if means else 0,
            "mean": mean(means),
            "min": min(means),
            "max": max(means),
            "trend": (means[-1] - means[0]) / means[0] * 100 if means[0] > 0 else 0,  # % change
        }
    
    def detect_trend_direction(self, metric_name: str, window: int = 24) -> str:
        """Detect if metric is trending up, down, or stable."""
        trends = self.get_trend(metric_name, limit=window)
        
        if len(trends) < 2:
            return "stable"
        
        values = [t.mean_value for t in trends]
        first_half = mean(values[:len(values)//2])
        second_half = mean(values[len(values)//2:])
        
        change_percent = (second_half - first_half) / first_half * 100 if first_half > 0 else 0
        
        if change_percent > 10:
            return "up"
        elif change_percent < -10:
            return "down"
        else:
            return "stable"


class AnomalyDetector:
    """
    Detects anomalies in metrics and performance.
    
    Methods:
    - Statistical deviation detection
    - Pattern-based detection
    - Trend-based detection
    """
    
    def __init__(self, sensitivity: float = 2.0):
        """
        Initialize anomaly detector.
        
        Args:
            sensitivity: Std deviation threshold (higher = less sensitive)
        """
        self.sensitivity = sensitivity
        self.baseline_stats: Dict[str, Dict[str, float]] = {}
        self.anomalies: deque = deque(maxlen=1000)
    
    def set_baseline(self, metric_name: str, stats: Dict[str, float]) -> None:
        """Set baseline statistics for a metric."""
        self.baseline_stats[metric_name] = stats
        logger.info(f"Baseline set for {metric_name}: mean={stats.get('mean', 0):.2f}")
    
    def detect_statistical_anomaly(
        self,
        metric_name: str,
        value: float,
        timestamp: Optional[float] = None,
    ) -> Optional[AnomalyAlert]:
        """Detect statistical deviation from baseline."""
        if metric_name not in self.baseline_stats:
            return None
        
        baseline = self.baseline_stats[metric_name]
        mean_val = baseline.get('mean', 0)
        stdev_val = baseline.get('stdev', 1)
        
        # Calculate z-score
        if stdev_val > 0:
            z_score = abs((value - mean_val) / stdev_val)
        else:
            return None
        
        if z_score > self.sensitivity:
            deviation = ((value - mean_val) / mean_val * 100) if mean_val > 0 else 0
            
            # Determine anomaly type and severity
            if "latency" in metric_name.lower():
                anomaly_type = AnomalyType.LATENCY_SPIKE
                severity = "critical" if z_score > self.sensitivity * 1.5 else "high"
            elif "memory" in metric_name.lower():
                anomaly_type = AnomalyType.MEMORY_SPIKE
                severity = "critical" if z_score > self.sensitivity * 1.5 else "high"
            elif "error" in metric_name.lower():
                anomaly_type = AnomalyType.ERROR_RATE_INCREASE
                severity = "high"
            else:
                anomaly_type = AnomalyType.UNUSUAL_PATTERN
                severity = "medium"
            
            alert = AnomalyAlert(
                anomaly_id=f"anom_{int(time.time())}",
                anomaly_type=anomaly_type,
                severity=severity,
                message=f"{metric_name} is {deviation:.1f}% above baseline",
                detected_at=timestamp or time.time(),
                metric_value=value,
                expected_value=mean_val,
                deviation=deviation,
                details={"z_score": z_score},
            )
            
            self.anomalies.append(alert)
            return alert
        
        return None
    
    def get_recent_anomalies(self, limit: int = 50) -> List[AnomalyAlert]:
        """Get recent anomalies."""
        return list(self.anomalies)[-limit:]


class CostAnalytics:
    """
    Calculates costs and optimization recommendations.
    
    Factors:
    - Hardware tier resource consumption
    - Model loading overhead
    - Cache efficiency
    - Query complexity
    """
    
    # Cost multipliers per tier (relative to standard=1.0)
    TIER_COST_MULTIPLIERS = {
        "ultra_lite": 0.3,   # 30% of standard
        "lite": 0.6,         # 60% of standard
        "standard": 1.0,     # Baseline
        "full": 1.5,         # 150% of standard
    }
    
    # Base costs (arbitrary units)
    RETRIEVAL_COST_PER_MS = 0.001
    GENERATION_COST_PER_MS = 0.002
    MEMORY_COST_PER_MB = 0.0001
    CACHE_MISS_PENALTY = 0.1
    
    def __init__(self):
        self.query_costs: deque = deque(maxlen=10000)
        self.tier_costs: Dict[str, List[float]] = defaultdict(list)
    
    def calculate_query_cost(
        self,
        query_id: str,
        retrieval_time_ms: float,
        generation_time_ms: float,
        memory_delta_mb: float,
        cache_hit: bool,
        hardware_tier: str = "standard",
    ) -> float:
        """Calculate cost of a query."""
        # Base operational cost
        cost = (
            retrieval_time_ms * self.RETRIEVAL_COST_PER_MS +
            generation_time_ms * self.GENERATION_COST_PER_MS +
            memory_delta_mb * self.MEMORY_COST_PER_MB
        )
        
        # Cache miss penalty
        if not cache_hit:
            cost += self.CACHE_MISS_PENALTY
        
        # Apply tier multiplier
        tier_multiplier = self.TIER_COST_MULTIPLIERS.get(hardware_tier, 1.0)
        cost *= tier_multiplier
        
        # Track
        self.query_costs.append(cost)
        self.tier_costs[hardware_tier].append(cost)
        
        return cost
    
    def get_cost_summary(self) -> Dict[str, Any]:
        """Get cost analysis summary."""
        if not self.query_costs:
            return {}
        
        costs = list(self.query_costs)
        
        summary = {
            "total_cost": sum(costs),
            "mean_cost_per_query": mean(costs),
            "median_cost_per_query": median(costs),
            "min_cost": min(costs),
            "max_cost": max(costs),
            "cost_by_tier": {},
        }
        
        for tier, tier_costs_list in self.tier_costs.items():
            if tier_costs_list:
                summary["cost_by_tier"][tier] = {
                    "total": sum(tier_costs_list),
                    "mean": mean(tier_costs_list),
                    "queries": len(tier_costs_list),
                }
        
        return summary
    
    def get_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """Generate cost optimization recommendations."""
        recommendations = []
        
        if not self.query_costs:
            return recommendations
        
        costs = list(self.query_costs)
        expensive_queries = sorted(enumerate(costs), key=lambda x: x[1], reverse=True)[:10]
        
        if expensive_queries and expensive_queries[0][1] > mean(costs) * 2:
            recommendations.append({
                "type": "high_cost_queries",
                "severity": "high",
                "message": "Some queries are significantly more expensive than average",
                "count": len([q for q in expensive_queries if q[1] > mean(costs) * 1.5]),
                "action": "Review slow queries and optimize retrieval/generation",
            })
        
        # Check tier efficiency
        lite_costs = self.tier_costs.get("lite", [])
        standard_costs = self.tier_costs.get("standard", [])
        
        if lite_costs and standard_costs:
            lite_mean = mean(lite_costs)
            standard_mean = mean(standard_costs)
            
            if lite_mean < standard_mean * 0.9:  # Lite is significantly cheaper
                recommendations.append({
                    "type": "tier_migration",
                    "severity": "medium",
                    "message": f"Lite tier is {((standard_mean - lite_mean)/standard_mean*100):.1f}% cheaper",
                    "action": "Consider migrating suitable workloads to lite tier",
                })
        
        return recommendations


class AnalyticsManager:
    """
    Central analytics coordinator.
    
    Combines query, performance, anomaly, and cost analytics.
    """
    
    _instance: Optional["AnalyticsManager"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.query_analytics = QueryAnalytics()
        self.performance_analytics = PerformanceAnalytics()
        self.anomaly_detector = AnomalyDetector()
        self.cost_analytics = CostAnalytics()
        
        self._initialized = True
        logger.info("AnalyticsManager initialized")
    
    def track_query(
        self,
        query_id: str,
        category: QueryCategory,
        query_text: str,
        latency_ms: float,
        memory_delta_mb: float,
        cache_hit: bool,
        confidence_score: float,
        retrieval_time_ms: float = 0,
        generation_time_ms: float = 0,
        hardware_tier: str = "standard",
    ) -> None:
        """Track query for analytics."""
        # Create feature
        feature = QueryFeature(
            query_id=query_id,
            timestamp=time.time(),
            category=category,
            query_length=len(query_text),
            latency_ms=latency_ms,
            memory_delta_mb=memory_delta_mb,
            cache_hit=cache_hit,
            confidence_score=confidence_score,
            hardware_tier=hardware_tier,
            time_of_day=datetime.now().hour,
        )
        
        # Track in query analytics
        self.query_analytics.track_query(feature)
        
        # Calculate and track cost
        cost = self.cost_analytics.calculate_query_cost(
            query_id=query_id,
            retrieval_time_ms=retrieval_time_ms,
            generation_time_ms=generation_time_ms,
            memory_delta_mb=memory_delta_mb,
            cache_hit=cache_hit,
            hardware_tier=hardware_tier,
        )
        
        # Detect anomalies
        anomaly = self.anomaly_detector.detect_statistical_anomaly(
            f"{hardware_tier}_latency_ms",
            latency_ms
        )
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive analytics data for dashboard."""
        return {
            "query_analytics": self.query_analytics.get_summary(),
            "performance_analytics": {
                "latency_trend": self.performance_analytics.get_trend_stats("latency_ms"),
                "memory_trend": self.performance_analytics.get_trend_stats("memory_delta_mb"),
            },
            "anomalies": [a.to_dict() for a in self.anomaly_detector.get_recent_anomalies(10)],
            "cost_analysis": self.cost_analytics.get_cost_summary(),
            "recommendations": self.cost_analytics.get_optimization_recommendations(),
        }


def get_analytics_manager() -> AnalyticsManager:
    """Get singleton analytics manager."""
    return AnalyticsManager()
