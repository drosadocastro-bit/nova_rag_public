# Phase 4.3: Analytics Quick Start Guide

Get started with NIC analytics in 5 minutes.

## Installation

Analytics is automatically available after Phase 4.1 (Observability) setup.

```bash
# Verify Phase 4.1 is installed
python -c "from core.observability import get_metrics_collector; print('Phase 4.1 OK')"

# Verify Phase 4.3 modules
python -c "from core.analytics import get_analytics_manager; print('Phase 4.3 OK')"
```

## Basic Usage

### 1. Track a Query

```python
from core.analytics import get_analytics_manager, QueryCategory

manager = get_analytics_manager()

manager.track_query(
    query_id="user_q_001",
    category=QueryCategory.FACTUAL,
    query_text="What is the oil capacity?",
    latency_ms=85.5,
    memory_delta_mb=15.2,
    cache_hit=True,
    confidence_score=0.96,
    hardware_tier="standard",
)

print("Query tracked successfully!")
```

### 2. View Analytics Dashboard

```python
from core.analytics import get_analytics_manager

manager = get_analytics_manager()
dashboard = manager.get_dashboard_data()

print(f"Total Queries: {dashboard['query_analytics']['total_queries']}")
print(f"Average Latency: {dashboard['query_analytics'].get('average_latency_ms', 0):.1f} ms")
print(f"Cache Hit Rate: {dashboard['query_analytics'].get('cache_hit_rate', 0):.1%}")
print(f"Total Cost: ${dashboard['cost_analysis']['total_cost']:.2f}")
```

### 3. Check for Anomalies

```python
from core.analytics import get_analytics_manager

manager = get_analytics_manager()
anomalies = manager.anomaly_detector.get_recent_anomalies(limit=10)

if anomalies:
    print("⚠️  Anomalies Detected:")
    for anomaly in anomalies:
        print(f"  - {anomaly.metric_name}: {anomaly.anomaly_type.value}")
        print(f"    Value: {anomaly.actual_value:.1f} (expected: {anomaly.baseline_value:.1f})")
        print(f"    Severity: {anomaly.severity}")
else:
    print("✓ No anomalies detected")
```

### 4. Get Performance Forecast

```python
from core.trend_analysis import get_performance_predictor

predictor = get_performance_predictor()
forecast = predictor.forecast_metric("latency_ms")

if forecast:
    print("📊 Latency Forecast:")
    print(f"  Current: {forecast.current_value:.1f} ms")
    print(f"  1 Hour:  {forecast.forecast_1h:.1f} ms (confidence: {forecast.confidence_1h:.0%})")
    print(f"  1 Day:   {forecast.forecast_1d:.1f} ms (confidence: {forecast.confidence_1d:.0%})")
    print(f"  1 Week:  {forecast.forecast_1w:.1f} ms (confidence: {forecast.confidence_1w:.0%})")
else:
    print("Not enough data for forecast yet")
```

### 5. Get Cost Analysis

```python
from core.analytics import get_analytics_manager

manager = get_analytics_manager()
cost_summary = manager.cost_analytics.get_cost_summary()
recommendations = manager.cost_analytics.get_optimization_recommendations()

print(f"💰 Cost Analysis:")
print(f"  Total Cost: ${cost_summary['total_cost']:.2f}")
print(f"  Cost/Query: ${cost_summary['mean_cost_per_query']:.4f}")
print(f"\n💡 Top Optimizations:")
for rec in recommendations[:3]:
    print(f"  - {rec['message']}")
    print(f"    Could save: {rec['potential_savings']}")
```

## Common Tasks

### Get Query Category Distribution

```python
from core.analytics import get_analytics_manager

manager = get_analytics_manager()
distribution = manager.query_analytics.get_category_distribution()

print("Query Types:")
for category, count in distribution.items():
    print(f"  {category.title()}: {count}")
```

### Find Slowest Queries

```python
from core.analytics import get_analytics_manager

manager = get_analytics_manager()
slowest = manager.query_analytics.get_slowest_queries(limit=5)

print("5 Slowest Queries:")
for i, query in enumerate(slowest, 1):
    print(f"  {i}. {query.query_id}: {query.latency_ms:.1f} ms")
```

### Monitor Real-time Performance Trend

```python
from core.analytics import get_analytics_manager

manager = get_analytics_manager()
stats = manager.performance_analytics.get_trend_stats("latency_ms")

print("Performance Trend:")
print(f"  Min: {stats['min']:.1f} ms")
print(f"  Max: {stats['max']:.1f} ms")
print(f"  Mean: {stats['mean']:.1f} ms")
print(f"  Trend: {stats['trend']}")
```

### Get Resource Forecast for Capacity Planning

```python
from core.trend_analysis import get_performance_predictor

predictor = get_performance_predictor()
forecast = predictor.get_resource_forecast("standard")

print("Resource Forecast (Standard Tier):")
print(f"  Latency: {forecast['latency_forecast']}")
print(f"  Memory: {forecast['memory_forecast']}")
print(f"  Error Rate: {forecast['error_rate_forecast']}")
```

## REST API Quick Reference

All endpoints are available at `/api/analytics/*`

```bash
# Get dashboard
curl http://localhost:5000/api/analytics/dashboard

# Get query analytics
curl http://localhost:5000/api/analytics/queries

# Check for anomalies
curl http://localhost:5000/api/analytics/anomalies

# Get performance metrics
curl http://localhost:5000/api/analytics/performance

# Get cost analysis
curl http://localhost:5000/api/analytics/costs

# Get forecasts
curl http://localhost:5000/api/analytics/forecasts

# Get recommendations
curl http://localhost:5000/api/analytics/recommendations

# Get summary report
curl http://localhost:5000/api/analytics/report/summary

# Export as JSON
curl http://localhost:5000/api/analytics/export/json
```

### With Filters

```bash
# Get anomalies with high severity only
curl "http://localhost:5000/api/analytics/anomalies?min_severity=high"

# Get FACTUAL queries only
curl "http://localhost:5000/api/analytics/queries?category=factual"

# Get top 5 slowest queries
curl "http://localhost:5000/api/analytics/queries?limit=5"

# Forecast for lite hardware tier
curl "http://localhost:5000/api/analytics/forecasts?hardware_tier=lite"
```

## Configuration Tips

### Adjust Anomaly Detection Sensitivity

```python
from core.analytics import AnomalyDetector

# Only alert on major anomalies (>2 standard deviations)
detector = AnomalyDetector(sensitivity=2.0)

# Alert on subtle anomalies (>1.5 standard deviations)
detector = AnomalyDetector(sensitivity=1.5)
```

### Set Performance Baseline

```python
from core.analytics import get_analytics_manager

manager = get_analytics_manager()

# Set baseline for anomaly detection
manager.performance_analytics.set_baseline("latency_ms", 80.0)
manager.anomaly_detector.set_baseline("latency_ms", {
    "mean": 80.0,
    "stdev": 12.0,
})

print("Baseline set! Anomaly detection now active.")
```

## Running Tests

```bash
# Run all analytics tests
pytest tests/test_analytics.py -v

# Run specific test
pytest tests/test_analytics.py::TestQueryAnalytics::test_track_query -v

# Run with coverage
pytest tests/test_analytics.py --cov=core.analytics --cov=core.trend_analysis
```

## Integration with Phase 4.1

Analytics automatically consumes data from Phase 4.1 observability:

```python
# Phase 4.1: Observability collects metrics
from core.observability import get_metrics_collector

metrics = get_metrics_collector()
# Metrics automatically available to analytics

# Phase 4.3: Analytics processes the data
from core.analytics import get_analytics_manager

manager = get_analytics_manager()
dashboard = manager.get_dashboard_data()
# Dashboard contains analysis of Phase 4.1 metrics
```

## Next Steps

1. **Monitor Dashboard**: Check `/api/analytics/dashboard` daily
2. **Set Baselines**: Configure performance baselines for your system
3. **Review Recommendations**: Implement top cost optimization recommendations
4. **Watch Forecasts**: Monitor latency forecasts for capacity planning
5. **Investigate Anomalies**: Set up alerts for high-severity anomalies

## Troubleshooting

### "No analytics data yet"
```python
# Solution: Track some queries first
manager.track_query(...) # See Basic Usage section
```

### "Forecasts show low confidence"
```python
# Solution: More data needed (minimum 20 queries recommended)
# Check: len(predictor.historical_data['latency_ms'])
```

### "Anomalies too frequent / not detected"
```python
# Solution: Adjust sensitivity or verify baseline is set
manager.anomaly_detector = AnomalyDetector(sensitivity=2.5)
```

## Example Dashboard Output

```
Analytics Dashboard
==================

📊 Query Analytics
  Total Queries: 5,432
  Factual: 2,168 (40%)
  Procedural: 1,087 (20%)
  Diagnostic: 1,088 (20%)
  Other: 1,089 (20%)
  Average Latency: 78.5 ms
  Cache Hit Rate: 74.2%

⚡ Performance
  Latency Trend: ↑ increasing
  Memory Trend: → stable
  Current P95 Latency: 125.3 ms

⚠️  Anomalies
  Recent Anomalies: 3
  Types: latency_spike (2), memory_spike (1)
  Highest Severity: high

💰 Cost Analysis
  Total Cost: $178.42
  Cost Per Query: $0.0328
  Most Expensive Tier: standard (82.3%)

💡 Recommendations
  1. Optimize retrieval caching (Save 34%)
  2. Reduce query complexity (Save 12%)
  3. Cache more results (Save 8%)

📈 Forecasts (1-hour, 1-day, 1-week)
  Latency: 79.2 ms, 85.5 ms, 98.3 ms (confidence: 92%, 87%, 75%)
```

## Support

For issues or questions:
1. Check [PHASE4_3_ANALYTICS.md](governance/PHASE4_3_ANALYTICS.md) for detailed docs
2. Review [test_analytics.py](tests/test_analytics.py) for usage examples
3. Check logs: `tail -f server.log | grep analytics`
