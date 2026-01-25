"""
Phase 4.1 Observability Test Suite

Comprehensive tests for:
- Metrics collection
- Alert triggering
- Audit logging
- Dashboard data
- Notifications
"""

import pytest
import json
import time
from pathlib import Path
from datetime import datetime, timedelta

# Import observability components
from core.observability import (
    MetricsCollector,
    AuditLogger,
    AlertManager,
    AlertRule,
    AlertSeverity,
    QueryLog,
    MetricPoint,
)
from core.notifications import (
    NotificationManager,
    NotificationConfig,
)


class TestMetricsCollector:
    """Test metrics collection functionality."""
    
    def test_record_metric(self):
        """Test recording a single metric."""
        collector = MetricsCollector()
        
        collector.record("test_metric", 100.0)
        
        assert "test_metric" in collector.metrics
        assert len(collector.metrics["test_metric"]) == 1
        assert collector.metrics["test_metric"][0].value == 100.0
    
    def test_record_with_labels(self):
        """Test recording metrics with labels."""
        collector = MetricsCollector()
        
        collector.record("latency_ms", 50.0, {"tier": "ultra_lite"})
        
        assert len(collector.metrics["latency_ms"]) == 1
        assert collector.metrics["latency_ms"][0].labels["tier"] == "ultra_lite"
    
    def test_get_recent(self):
        """Test retrieving recent metrics."""
        collector = MetricsCollector()
        
        for i in range(10):
            collector.record("test_metric", float(i * 10))
        
        recent = collector.get_recent("test_metric", limit=5)
        assert len(recent) == 5
        assert recent[-1].value == 90.0
    
    def test_percentile_calculation(self):
        """Test percentile calculations."""
        collector = MetricsCollector()
        
        # Record values: 10, 20, 30, 40, 50
        for i in range(1, 6):
            collector.record("test_metric", float(i * 10))
        
        p50 = collector.get_percentile("test_metric", 50)
        p95 = collector.get_percentile("test_metric", 95)
        
        assert p50 is not None
        assert p95 is not None
        assert p50 < p95
    
    def test_statistics(self):
        """Test metric statistics."""
        collector = MetricsCollector()
        
        for i in range(1, 11):
            collector.record("test_metric", float(i))
        
        stats = collector.get_stats("test_metric")
        
        assert stats["count"] == 10
        assert stats["min"] == 1.0
        assert stats["max"] == 10.0
        assert stats["mean"] == 5.5
    
    def test_prometheus_export(self):
        """Test Prometheus format export."""
        collector = MetricsCollector()
        
        collector.record("metric1", 100.0)
        collector.record("metric2", 200.0, {"service": "nva"})
        
        prometheus = collector.to_prometheus()
        
        assert "# HELP nova_nic_metrics" in prometheus
        assert "metric1" in prometheus
        assert "metric2" in prometheus
    
    def test_circular_buffer(self):
        """Test circular buffer behavior."""
        collector = MetricsCollector(max_points_per_metric=100)
        
        # Record more than max
        for i in range(150):
            collector.record("test_metric", float(i))
        
        assert len(collector.metrics["test_metric"]) == 100
    
    def test_summary(self):
        """Test getting summary."""
        collector = MetricsCollector()
        
        collector.record("metric1", 10.0)
        collector.record("metric2", 20.0)
        
        summary = collector.get_summary()
        
        assert "uptime_seconds" in summary
        assert summary["metrics_tracked"] == 2
        assert summary["total_points"] == 2


class TestAuditLogger:
    """Test audit logging functionality."""
    
    def test_log_query(self, tmp_path):
        """Test logging a query."""
        logger = AuditLogger(log_dir=tmp_path)
        
        query_log = QueryLog(
            query_id="test_001",
            timestamp=time.time(),
            query_text="Test query",
            duration_ms=50.0,
        )
        
        logger.log_query(query_log)
        
        assert len(logger.recent_logs) == 1
        assert logger.query_log_file.exists()
    
    def test_log_safety_event(self, tmp_path):
        """Test logging safety events."""
        logger = AuditLogger(log_dir=tmp_path)
        
        logger.log_safety_event(
            event_type="anomaly_detected",
            severity="warning",
            message="Anomalous query pattern",
            query_id="test_001",
        )
        
        assert len(logger.recent_logs) == 1
        assert logger.safety_log_file.exists()
    
    def test_log_event(self, tmp_path):
        """Test logging general events."""
        logger = AuditLogger(log_dir=tmp_path)
        
        logger.log_event(
            event_type="model_loaded",
            details={"model": "embedding", "time_ms": 500},
        )
        
        assert len(logger.recent_logs) == 1
        assert logger.event_log_file.exists()
    
    def test_search_logs(self, tmp_path):
        """Test searching logs."""
        logger = AuditLogger(log_dir=tmp_path)
        
        for i in range(5):
            query_log = QueryLog(
                query_id=f"test_{i}",
                timestamp=time.time(),
                query_text=f"Query {i}",
                duration_ms=50.0 + i * 10,
            )
            logger.log_query(query_log)
        
        results = logger.search_logs(log_type="query", limit=10)
        assert len(results) == 5
    
    def test_file_persistence(self, tmp_path):
        """Test that logs are persisted to files."""
        logger = AuditLogger(log_dir=tmp_path)
        
        logger.log_event("test_event", {"value": 123})
        
        # Check file contains the log
        with open(logger.event_log_file) as f:
            content = f.read()
            assert "test_event" in content
            assert "123" in content


class TestAlertManager:
    """Test alert management."""
    
    def test_add_rule(self):
        """Test adding alert rule."""
        manager = AlertManager()
        
        rule = AlertRule(
            name="high_latency",
            description="Query latency above 200ms",
            metric_name="query_latency_ms",
            operator=">",
            threshold=200.0,
            severity=AlertSeverity.WARNING,
        )
        
        manager.add_rule(rule)
        
        assert "high_latency" in manager.rules
    
    def test_trigger_alert_greater_than(self):
        """Test alert triggers on > operator."""
        manager = AlertManager()
        
        rule = AlertRule(
            name="high_latency",
            description="Query latency above 200ms",
            metric_name="query_latency_ms",
            operator=">",
            threshold=200.0,
            severity=AlertSeverity.WARNING,
        )
        
        manager.add_rule(rule)
        
        # Should trigger
        alert = manager.check_rule(rule, 250.0)
        assert alert is not None
        assert alert.rule_name == "high_latency"
        
        # Should not trigger
        alert = manager.check_rule(rule, 150.0)
        assert alert is None
    
    def test_trigger_alert_less_than(self):
        """Test alert triggers on < operator."""
        manager = AlertManager()
        
        rule = AlertRule(
            name="low_cache_hit",
            description="Cache hit rate below 50%",
            metric_name="cache_hit_rate",
            operator="<",
            threshold=0.5,
            severity=AlertSeverity.WARNING,
        )
        
        manager.add_rule(rule)
        
        # Should trigger
        alert = manager.check_rule(rule, 0.3)
        assert alert is not None
        
        # Should not trigger
        alert = manager.check_rule(rule, 0.7)
        assert alert is None
    
    def test_cooldown_period(self):
        """Test alert cooldown prevents repeated triggers."""
        manager = AlertManager()
        
        rule = AlertRule(
            name="test_alert",
            description="Test",
            metric_name="test_metric",
            operator=">",
            threshold=100.0,
            severity=AlertSeverity.INFO,
            cooldown_seconds=5,
        )
        
        manager.add_rule(rule)
        
        # First trigger
        alert1 = manager.check_rule(rule, 150.0)
        assert alert1 is not None
        
        # Immediate second trigger (within cooldown)
        alert2 = manager.check_rule(rule, 150.0)
        assert alert2 is None  # Should not trigger due to cooldown
    
    def test_evaluate_all_rules(self):
        """Test evaluating multiple rules."""
        manager = AlertManager()
        
        rule1 = AlertRule(
            name="alert1",
            description="Test 1",
            metric_name="metric1",
            operator=">",
            threshold=100.0,
            severity=AlertSeverity.WARNING,
        )
        rule2 = AlertRule(
            name="alert2",
            description="Test 2",
            metric_name="metric2",
            operator="<",
            threshold=50.0,
            severity=AlertSeverity.WARNING,
        )
        
        manager.add_rule(rule1)
        manager.add_rule(rule2)
        
        metrics = {
            "metric1": 150.0,  # Should trigger rule1
            "metric2": 30.0,   # Should trigger rule2
        }
        
        alerts = manager.evaluate(metrics)
        assert len(alerts) == 2
    
    def test_alert_stats(self):
        """Test alert statistics."""
        manager = AlertManager()
        
        rule = AlertRule(
            name="test",
            description="Test",
            metric_name="metric",
            operator=">",
            threshold=100.0,
            severity=AlertSeverity.INFO,
        )
        
        manager.add_rule(rule)
        manager.check_rule(rule, 150.0)  # Trigger once
        
        stats = manager.get_stats()
        
        assert stats["rules_count"] == 1
        assert stats["total_triggered"] == 1


class TestNotificationManager:
    """Test notification system."""
    
    def test_initialization(self):
        """Test notification manager initialization."""
        config = NotificationConfig(
            email_enabled=False,
            webhook_enabled=False,
            in_app_enabled=True,
        )
        
        manager = NotificationManager(config)
        
        assert manager.config.in_app_enabled
    
    @pytest.mark.asyncio
    async def test_in_app_notification(self):
        """Test in-app notifications."""
        config = NotificationConfig(in_app_enabled=True)
        manager = NotificationManager(config)
        
        result = await manager.notify(
            event_type="test",
            severity="info",
            message="Test message",
        )
        
        assert result
        recent = manager.get_recent_notifications()
        assert len(recent) == 1
    
    @pytest.mark.asyncio
    async def test_notify_alert(self):
        """Test alert notifications."""
        config = NotificationConfig(in_app_enabled=True)
        manager = NotificationManager(config)
        
        result = await manager.notify_alert(
            rule_name="high_latency",
            severity="warning",
            message="Latency exceeded threshold",
            metric_value=250.0,
            threshold=200.0,
        )
        
        assert result
    
    def test_notification_stats(self):
        """Test notification statistics."""
        config = NotificationConfig(in_app_enabled=True)
        manager = NotificationManager(config)
        
        stats = manager.get_stats()
        
        assert "in_app_enabled" in stats
        assert stats["in_app_enabled"]


class TestQueryLogging:
    """Test query logging with audit trail."""
    
    def test_query_log_creation(self):
        """Test creating a query log entry."""
        query_log = QueryLog(
            query_id="test_001",
            timestamp=time.time(),
            query_text="What is NIC?",
            duration_ms=75.5,
            retrieval_time_ms=25.0,
            ranking_time_ms=15.0,
            generation_time_ms=35.5,
            memory_delta_mb=12.5,
            cache_hit=True,
            safety_checks_passed=3,
            documents_retrieved=5,
            documents_ranked=5,
            confidence_score=0.95,
            hardware_tier="standard",
        )
        
        log_dict = query_log.to_dict()
        
        assert log_dict["query_id"] == "test_001"
        assert log_dict["duration_ms"] == 75.5
        assert log_dict["cache_hit"] is True


class TestIntegration:
    """Integration tests combining multiple components."""
    
    def test_observability_workflow(self, tmp_path):
        """Test complete observability workflow."""
        # Setup
        metrics = MetricsCollector()
        audit_logger = AuditLogger(log_dir=tmp_path)
        alerts = AlertManager()
        
        # Add alert rule
        rule = AlertRule(
            name="high_latency",
            description="Latency > 100ms",
            metric_name="latency",
            operator=">",
            threshold=100.0,
            severity=AlertSeverity.WARNING,
        )
        alerts.add_rule(rule)
        
        # Simulate query execution
        query_log = QueryLog(
            query_id="test_001",
            timestamp=time.time(),
            query_text="Test query",
            duration_ms=120.0,  # Exceeds threshold
        )
        
        # Record metrics
        metrics.record("latency", query_log.duration_ms)
        
        # Log query
        audit_logger.log_query(query_log)
        
        # Check alerts
        alert_metrics = {"latency": query_log.duration_ms}
        triggered_alerts = alerts.evaluate(alert_metrics)
        
        # Verify
        assert len(audit_logger.recent_logs) == 1
        assert len(triggered_alerts) == 1
        assert triggered_alerts[0].rule_name == "high_latency"
    
    def test_multi_tier_metrics(self):
        """Test metrics across different hardware tiers."""
        collector = MetricsCollector()
        
        # Simulate queries on different tiers
        for tier in ["ultra_lite", "lite", "standard"]:
            for i in range(5):
                latency = 50.0 if tier == "ultra_lite" else 30.0 if tier == "lite" else 20.0
                collector.record("query_latency", latency + i * 5, {"tier": tier})
        
        assert "query_latency" in collector.metrics
        assert len(collector.metrics["query_latency"]) == 15
    
    def test_alert_cooldown_workflow(self):
        """Test alert cooldown in a realistic scenario."""
        manager = AlertManager()
        
        rule = AlertRule(
            name="memory_spike",
            description="Memory delta > 500MB",
            metric_name="memory_delta",
            operator=">",
            threshold=500.0,
            severity=AlertSeverity.CRITICAL,
            cooldown_seconds=300,
        )
        
        manager.add_rule(rule)
        
        # First spike - should alert
        metrics1 = {"memory_delta": 600.0}
        alerts1 = manager.evaluate(metrics1)
        assert len(alerts1) == 1
        
        # Immediate second spike - should not alert (cooldown)
        metrics2 = {"memory_delta": 700.0}
        alerts2 = manager.evaluate(metrics2)
        assert len(alerts2) == 0
        
        # Simulate time passing and another spike
        rule.last_triggered = time.time() - 310  # Past cooldown
        alerts3 = manager.evaluate(metrics2)
        assert len(alerts3) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
