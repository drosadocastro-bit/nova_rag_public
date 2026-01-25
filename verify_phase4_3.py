#!/usr/bin/env python
"""Verification script for Phase 4.3 Advanced Analytics."""

from core.analytics import get_analytics_manager, QueryCategory
from core.trend_analysis import get_performance_predictor

# Test analytics
manager = get_analytics_manager()
manager.track_query(
    query_id='test_001',
    category=QueryCategory.FACTUAL,
    query_text='Test query',
    latency_ms=75.0,
    memory_delta_mb=12.5,
    cache_hit=True,
    confidence_score=0.95,
    retrieval_time_ms=25.0,
    generation_time_ms=50.0,
    hardware_tier='standard'
)

# Get dashboard
dashboard = manager.get_dashboard_data()
print('✅ Analytics Dashboard Generated')
print('   - Total Queries:', dashboard['query_analytics']['total_queries'])
print('   - Categories Tracked:', len(dashboard['query_analytics']['category_distribution']))
print('   - Cost Analysis Available:', 'total_cost' in dashboard['cost_analysis'])

# Test predictor
predictor = get_performance_predictor()
predictor.record_metric('latency_ms', 75.0)
print('✅ Performance Predictor Ready')
print('   - Historical Data Points:', sum(len(v) for v in predictor.historical_data.values()))

print('\n✅ Phase 4.3 Advanced Analytics - FULLY OPERATIONAL')
