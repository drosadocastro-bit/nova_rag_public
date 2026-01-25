"""
Tests for Analytics Dashboard Module.

Tests dashboard summary, latency breakdown, and domain analytics functions.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from core.monitoring.analytics_dashboard import (
    get_dashboard_summary,
    get_latency_breakdown,
    get_domain_analytics,
    get_real_time_stats,
    QueryMetrics,
    DomainMetrics,
    ModelMetrics,
    DashboardSummary,
    _calculate_percentile,
)


class TestQueryMetrics:
    """Tests for QueryMetrics dataclass."""
    
    def test_default_values(self):
        """Test default initialization."""
        metrics = QueryMetrics()
        assert metrics.total_queries == 0
        assert metrics.successful_queries == 0
        assert metrics.failed_queries == 0
        assert metrics.avg_response_time_ms == 0.0
        assert metrics.avg_confidence == 0.0
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        metrics = QueryMetrics(
            total_queries=100,
            successful_queries=95,
            failed_queries=5,
            avg_response_time_ms=150.5,
        )
        result = metrics.to_dict()
        assert result["total_queries"] == 100
        assert result["successful_queries"] == 95
        assert result["avg_response_time_ms"] == 150.5


class TestDomainMetrics:
    """Tests for DomainMetrics dataclass."""
    
    def test_initialization(self):
        """Test domain metrics initialization."""
        metrics = DomainMetrics(
            domain="vehicle",
            query_count=50,
            avg_response_time_ms=200.0,
            avg_confidence=0.85,
            error_rate=0.02,
        )
        assert metrics.domain == "vehicle"
        assert metrics.query_count == 50
        assert metrics.error_rate == 0.02
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        metrics = DomainMetrics(domain="medical", query_count=25)
        result = metrics.to_dict()
        assert result["domain"] == "medical"
        assert result["query_count"] == 25


class TestModelMetrics:
    """Tests for ModelMetrics dataclass."""
    
    def test_initialization(self):
        """Test model metrics initialization."""
        metrics = ModelMetrics(
            model_name="phi3-mini",
            query_count=100,
            avg_response_time_ms=500.0,
            error_count=2,
        )
        assert metrics.model_name == "phi3-mini"
        assert metrics.query_count == 100


class TestDashboardSummary:
    """Tests for DashboardSummary dataclass."""
    
    def test_to_dict(self):
        """Test complete dictionary conversion."""
        summary = DashboardSummary(
            period_hours=24,
            query_metrics=QueryMetrics(total_queries=100),
            domain_breakdown=[DomainMetrics(domain="vehicle", query_count=50)],
            model_breakdown=[ModelMetrics(model_name="phi3", query_count=100)],
            generated_at="2026-01-25T10:00:00",
        )
        result = summary.to_dict()
        assert result["period_hours"] == 24
        assert result["query_metrics"]["total_queries"] == 100
        assert len(result["domain_breakdown"]) == 1
        assert len(result["model_breakdown"]) == 1


class TestCalculatePercentile:
    """Tests for percentile calculation."""
    
    def test_empty_list(self):
        """Test with empty list."""
        assert _calculate_percentile([], 50) == 0.0
    
    def test_single_value(self):
        """Test with single value."""
        assert _calculate_percentile([100], 50) == 100
    
    def test_p50(self):
        """Test 50th percentile."""
        values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
        p50 = _calculate_percentile(values, 50)
        assert p50 == 60  # Index 5
    
    def test_p95(self):
        """Test 95th percentile."""
        values = [float(x) for x in range(1, 101)]  # 1-100
        p95 = _calculate_percentile(values, 95)
        assert p95 == 96  # Index 95


class TestGetDashboardSummary:
    """Tests for get_dashboard_summary function."""
    
    @patch("core.monitoring.analytics_dashboard._get_connection")
    def test_returns_dashboard_summary(self, mock_conn):
        """Test that function returns DashboardSummary."""
        # Mock empty database
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            "total": 0, "successful": 0, "failed": 0,
            "avg_time": 0, "avg_conf": 0,
        }
        mock_cursor.fetchall.return_value = []
        mock_conn.return_value.cursor.return_value = mock_cursor
        
        result = get_dashboard_summary(hours=24)
        
        assert isinstance(result, DashboardSummary)
        assert result.period_hours == 24
    
    def test_handles_database_error(self):
        """Test graceful handling of database errors."""
        with patch("core.monitoring.analytics_dashboard._get_connection") as mock:
            mock.side_effect = Exception("Database error")
            result = get_dashboard_summary(hours=24)
            assert isinstance(result, DashboardSummary)
            assert result.query_metrics.total_queries == 0


class TestGetLatencyBreakdown:
    """Tests for get_latency_breakdown function."""
    
    @patch("core.monitoring.analytics_dashboard._get_connection")
    def test_empty_data(self, mock_conn):
        """Test with no data."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.return_value.cursor.return_value = mock_cursor
        
        result = get_latency_breakdown(hours=1)
        
        assert result["count"] == 0
        assert result["min_ms"] == 0
        assert result["max_ms"] == 0
    
    @patch("core.monitoring.analytics_dashboard._get_connection")
    def test_with_data(self, mock_conn):
        """Test with latency data."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"response_time_ms": 50},
            {"response_time_ms": 150},
            {"response_time_ms": 250},
            {"response_time_ms": 600},
            {"response_time_ms": 1500},
        ]
        mock_conn.return_value.cursor.return_value = mock_cursor
        
        result = get_latency_breakdown(hours=1)
        
        assert result["count"] == 5
        assert result["min_ms"] == 50
        assert result["max_ms"] == 1500
        assert "distribution" in result


class TestGetDomainAnalytics:
    """Tests for get_domain_analytics function."""
    
    @patch("core.monitoring.analytics_dashboard._get_connection")
    def test_with_domain_data(self, mock_conn):
        """Test domain-specific analytics."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            "total": 50,
            "avg_time": 200.0,
            "avg_conf": 0.85,
            "min_time": 100,
            "max_time": 500,
            "errors": 2,
        }
        mock_conn.return_value.cursor.return_value = mock_cursor
        
        result = get_domain_analytics(domain="vehicle", hours=24)
        
        assert result["domain"] == "vehicle"
        assert result["total_queries"] == 50
        assert result["error_count"] == 2


class TestGetRealTimeStats:
    """Tests for get_real_time_stats function."""
    
    @patch("core.monitoring.analytics_dashboard._get_connection")
    def test_returns_stats(self, mock_conn):
        """Test real-time stats retrieval."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            "queries": 10,
            "avg_time": 150.0,
            "errors": 1,
        }
        mock_conn.return_value.cursor.return_value = mock_cursor
        
        result = get_real_time_stats()
        
        assert result["period"] == "5m"
        assert result["queries"] == 10
        assert "qps" in result
        assert "timestamp" in result
