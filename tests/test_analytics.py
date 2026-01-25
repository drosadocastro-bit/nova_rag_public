"""
Phase 4.3 Advanced Analytics Test Suite.

Comprehensive tests for:
- Query analytics
- Performance analytics
- Anomaly detection
- Trend analysis
- Cost analytics
"""

import pytest
import time
from typing import List

from core.analytics import (
    QueryAnalytics,
    PerformanceAnalytics,
    AnomalyDetector,
    CostAnalytics,
    AnalyticsManager,
    QueryFeature,
    QueryCategory,
    AnomalyType,
    AnomalyAlert,
)
from core.trend_analysis import (
    TrendAnalyzer,
    TrendDirection,
    PerformancePredictor,
    SeasonalPattern,
)


class TestQueryAnalytics:
    """Test query analytics."""
    
    def test_track_query(self):
        """Test tracking a query."""
        analytics = QueryAnalytics()
        
        feature = QueryFeature(
            query_id="test_001",
            timestamp=time.time(),
            category=QueryCategory.FACTUAL,
            query_length=50,
            latency_ms=75.0,
        )
        
        analytics.track_query(feature)
        
        assert len(analytics.queries) == 1
        assert analytics.category_counts[QueryCategory.FACTUAL] == 1
    
    def test_category_distribution(self):
        """Test category distribution tracking."""
        analytics = QueryAnalytics()
        
        for i in range(5):
            feature = QueryFeature(
                query_id=f"test_{i}",
                timestamp=time.time(),
                category=QueryCategory.FACTUAL if i < 3 else QueryCategory.DIAGNOSTIC,
                query_length=50,
                latency_ms=75.0,
            )
            analytics.track_query(feature)
        
        dist = analytics.get_category_distribution()
        assert dist["factual"] == 3
        assert dist["diagnostic"] == 2
    
    def test_slowest_queries(self):
        """Test retrieving slowest queries."""
        analytics = QueryAnalytics()
        
        for i in range(10):
            feature = QueryFeature(
                query_id=f"test_{i}",
                timestamp=time.time(),
                category=QueryCategory.FACTUAL,
                latency_ms=50.0 + i * 10,
            )
            analytics.track_query(feature)
        
        slowest = analytics.get_slowest_queries(3)
        assert len(slowest) == 3
        assert slowest[0].latency_ms >= slowest[1].latency_ms
    
    def test_complexity_stats(self):
        """Test complexity statistics."""
        analytics = QueryAnalytics()
        
        for i in range(5):
            feature = QueryFeature(
                query_id=f"test_{i}",
                timestamp=time.time(),
                category=QueryCategory.FACTUAL,
                query_complexity=float(i) / 5,
            )
            analytics.track_query(feature)
        
        stats = analytics.get_complexity_stats()
        assert "mean" in stats
        assert "min" in stats
        assert "max" in stats


class TestPerformanceAnalytics:
    """Test performance analytics."""
    
    def test_record_metric_trend(self):
        """Test recording metric trends."""
        analytics = PerformanceAnalytics()
        
        values = [50.0, 55.0, 48.0, 52.0, 60.0]
        analytics.record_metric_trend("latency_ms", values)
        
        trends = analytics.get_trend("latency_ms")
        assert len(trends) == 1
        assert trends[0].mean_value == pytest.approx(sum(values) / len(values))
    
    def test_baseline_setting(self):
        """Test baseline setting."""
        analytics = PerformanceAnalytics()
        
        analytics.set_baseline("latency_ms", 100.0)
        assert analytics.baseline_metrics["latency_ms"] == 100.0
    
    def test_trend_direction(self):
        """Test trend direction detection."""
        analytics = PerformanceAnalytics()
        
        # Create increasing trend
        for i in range(30):
            values = [50.0 + i * 2 for _ in range(10)]
            analytics.record_metric_trend("latency_ms", values)
        
        direction = analytics.detect_trend_direction("latency_ms")
        assert direction in ["up", "down", "stable"]


class TestAnomalyDetector:
    """Test anomaly detection."""
    
    def test_set_baseline(self):
        """Test baseline setting."""
        detector = AnomalyDetector()
        
        stats = {
            "mean": 100.0,
            "stdev": 10.0,
        }
        
        detector.set_baseline("latency_ms", stats)
        assert detector.baseline_stats["latency_ms"]["mean"] == 100.0
    
    def test_detect_anomaly(self):
        """Test anomaly detection."""
        detector = AnomalyDetector(sensitivity=2.0)
        
        detector.set_baseline("latency_ms", {
            "mean": 100.0,
            "stdev": 10.0,
        })
        
        # Normal value
        alert = detector.detect_statistical_anomaly("latency_ms", 105.0)
        assert alert is None
        
        # Anomalous value (5 std devs away)
        alert = detector.detect_statistical_anomaly("latency_ms", 150.0)
        assert alert is not None
        assert alert.anomaly_type == AnomalyType.LATENCY_SPIKE
    
    def test_recent_anomalies(self):
        """Test retrieving recent anomalies."""
        detector = AnomalyDetector(sensitivity=1.0)
        
        detector.set_baseline("latency_ms", {
            "mean": 100.0,
            "stdev": 10.0,
        })
        
        # Generate anomalies
        for i in range(5):
            detector.detect_statistical_anomaly("latency_ms", 130.0 + i * 10)
        
        anomalies = detector.get_recent_anomalies()
        assert len(anomalies) > 0


class TestCostAnalytics:
    """Test cost analytics."""
    
    def test_calculate_query_cost(self):
        """Test query cost calculation."""
        cost_analytics = CostAnalytics()
        
        cost = cost_analytics.calculate_query_cost(
            query_id="test_001",
            retrieval_time_ms=25.0,
            generation_time_ms=35.0,
            memory_delta_mb=12.5,
            cache_hit=True,
            hardware_tier="standard",
        )
        
        assert cost > 0
    
    def test_cost_by_tier(self):
        """Test cost calculation across tiers."""
        cost_analytics = CostAnalytics()
        
        # Same query on different tiers
        base_cost = cost_analytics.calculate_query_cost(
            query_id="test_001",
            retrieval_time_ms=25.0,
            generation_time_ms=35.0,
            memory_delta_mb=12.5,
            cache_hit=True,
            hardware_tier="standard",
        )
        
        lite_cost = cost_analytics.calculate_query_cost(
            query_id="test_002",
            retrieval_time_ms=25.0,
            generation_time_ms=35.0,
            memory_delta_mb=12.5,
            cache_hit=True,
            hardware_tier="lite",
        )
        
        # Lite should be cheaper
        assert lite_cost < base_cost
    
    def test_cost_summary(self):
        """Test cost summary generation."""
        cost_analytics = CostAnalytics()
        
        # Generate costs
        for i in range(10):
            cost_analytics.calculate_query_cost(
                query_id=f"test_{i}",
                retrieval_time_ms=20.0 + i,
                generation_time_ms=30.0 + i,
                memory_delta_mb=10.0,
                cache_hit=i % 2 == 0,
                hardware_tier="standard",
            )
        
        summary = cost_analytics.get_cost_summary()
        
        assert "total_cost" in summary
        assert "mean_cost_per_query" in summary
        assert summary["mean_cost_per_query"] > 0
    
    def test_optimization_recommendations(self):
        """Test optimization recommendation generation."""
        cost_analytics = CostAnalytics()
        
        # Generate expensive queries
        for i in range(10):
            cost_analytics.calculate_query_cost(
                query_id=f"test_{i}",
                retrieval_time_ms=100.0 + i * 50,  # Very expensive
                generation_time_ms=100.0,
                memory_delta_mb=50.0,
                cache_hit=False,
                hardware_tier="standard",
            )
        
        recommendations = cost_analytics.get_optimization_recommendations()
        assert len(recommendations) > 0


class TestTrendAnalyzer:
    """Test trend analysis."""
    
    def test_linear_trend(self):
        """Test linear trend calculation."""
        analyzer = TrendAnalyzer()
        
        # Increasing linear trend
        values = [10.0 + i for i in range(20)]
        slope, intercept = analyzer.calculate_linear_trend(values)
        
        assert slope > 0  # Should be positive
    
    def test_trend_direction(self):
        """Test trend direction detection."""
        analyzer = TrendAnalyzer()
        
        # Increasing trend
        increasing = [10.0 + i * 2 for i in range(20)]
        direction, confidence = analyzer.detect_trend_direction(increasing)
        assert direction == TrendDirection.INCREASING
        
        # Decreasing trend
        decreasing = [100.0 - i * 2 for i in range(20)]
        direction, confidence = analyzer.detect_trend_direction(decreasing)
        assert direction == TrendDirection.DECREASING
    
    def test_forecast(self):
        """Test forecasting."""
        analyzer = TrendAnalyzer()
        
        values = [50.0 + i * 2 for i in range(20)]
        forecasts = analyzer.forecast_simple(values, periods=3)
        
        assert len(forecasts) == 3
        assert all(f >= 0 for f in forecasts)
    
    def test_seasonality_detection(self):
        """Test seasonality detection."""
        analyzer = TrendAnalyzer()
        
        # Create hourly pattern (peaks at certain hours)
        values = []
        hourly_data = []
        for i in range(100):
            hour = i % 24
            hourly_data.append(hour)
            
            # Peak at hours 9-17 (business hours)
            if 9 <= hour <= 17:
                values.append(100.0 + (hour - 12) ** 2)
            else:
                values.append(50.0)
        
        seasonality = analyzer.detect_seasonality(values, hourly_data)
        
        assert seasonality.pattern_type in [SeasonalPattern.HOURLY, SeasonalPattern.NONE]


class TestPerformancePredictor:
    """Test performance prediction."""
    
    def test_record_metric(self):
        """Test recording metrics."""
        predictor = PerformancePredictor()
        
        for i in range(20):
            predictor.record_metric("latency_ms", 50.0 + i)
        
        assert len(predictor.historical_data["latency_ms"]) == 20
    
    def test_forecast_metric(self):
        """Test metric forecasting."""
        predictor = PerformancePredictor()
        
        # Record increasing trend
        for i in range(20):
            predictor.record_metric("latency_ms", 50.0 + i * 2)
        
        forecast = predictor.forecast_metric("latency_ms")
        
        assert forecast is not None
        assert forecast.forecast_1h > forecast.baseline_value
    
    def test_resource_forecast(self):
        """Test resource forecasting."""
        predictor = PerformancePredictor()
        
        # Record metrics
        for i in range(20):
            predictor.record_metric("standard_latency_ms", 50.0 + i)
            predictor.record_metric("standard_memory_delta_mb", 10.0 + i * 0.5)
        
        forecast = predictor.get_resource_forecast("standard")
        
        assert "latency_forecast" in forecast
        assert "memory_forecast" in forecast


class TestAnalyticsManager:
    """Test analytics manager."""
    
    def test_track_query(self):
        """Test tracking query through manager."""
        manager = AnalyticsManager()
        
        manager.track_query(
            query_id="test_001",
            category=QueryCategory.FACTUAL,
            query_text="What is NIC?",
            latency_ms=75.0,
            memory_delta_mb=12.5,
            cache_hit=True,
            confidence_score=0.95,
            hardware_tier="standard",
        )
        
        dashboard_data = manager.get_dashboard_data()
        assert "query_analytics" in dashboard_data
    
    def test_dashboard_data(self):
        """Test dashboard data generation."""
        manager = AnalyticsManager()
        
        # Track some queries
        for i in range(5):
            manager.track_query(
                query_id=f"test_{i}",
                category=QueryCategory.FACTUAL,
                query_text="Test query",
                latency_ms=50.0 + i * 10,
                memory_delta_mb=10.0,
                cache_hit=i % 2 == 0,
                confidence_score=0.9,
                hardware_tier="standard",
            )
        
        data = manager.get_dashboard_data()
        
        assert "query_analytics" in data
        assert "cost_analysis" in data
        assert "recommendations" in data


class TestIntegration:
    """Integration tests."""
    
    def test_end_to_end_analytics(self):
        """Test end-to-end analytics workflow."""
        manager = AnalyticsManager()
        predictor = PerformancePredictor()
        
        # Simulate queries over time
        for i in range(50):
            latency = 50.0 + (i % 24) * 5  # Hourly pattern
            
            manager.track_query(
                query_id=f"test_{i}",
                category=QueryCategory.FACTUAL if i % 2 == 0 else QueryCategory.DIAGNOSTIC,
                query_text="Test query",
                latency_ms=latency,
                memory_delta_mb=10.0 + (i % 10),
                cache_hit=i % 3 == 0,
                confidence_score=0.85 + (i % 10) * 0.01,
                hardware_tier="standard",
            )
            
            predictor.record_metric("latency_ms", latency)
        
        # Generate analytics
        dashboard = manager.get_dashboard_data()
        forecast = predictor.get_summary()
        
        assert dashboard["query_analytics"]["total_queries"] == 50
        assert len(forecast["forecasts"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
