"""
Trend Analysis and Prediction for NIC Analytics.

Provides:
- Time-series trend analysis
- Seasonal pattern detection
- Performance prediction
- Growth forecasting
- Resource planning
"""

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from statistics import mean, stdev

logger = logging.getLogger(__name__)

_performance_predictor: Optional["PerformancePredictor"] = None


class TrendDirection(str, Enum):
    """Trend direction classification."""
    
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    VOLATILE = "volatile"


@dataclass
class TrendForecast:
    """Forecast for a metric."""
    
    metric_name: str
    direction: TrendDirection
    confidence: float  # 0-1
    
    # Forecasts
    forecast_1h: float
    forecast_1d: float
    forecast_1w: float
    
    # Statistics
    current_value: float
    baseline_value: float
    change_percent: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "direction": self.direction.value,
            "confidence": round(self.confidence, 2),
            "forecasts": {
                "1h": round(self.forecast_1h, 2),
                "1d": round(self.forecast_1d, 2),
                "1w": round(self.forecast_1w, 2),
            },
            "current": round(self.current_value, 2),
            "baseline": round(self.baseline_value, 2),
            "change_percent": round(self.change_percent, 1),
        }


class SeasonalPattern(str, Enum):
    """Detected seasonal patterns."""
    
    HOURLY = "hourly"       # Peak hours
    DAILY = "daily"         # Weekday patterns
    WEEKLY = "weekly"       # Week patterns
    NONE = "none"           # No pattern


@dataclass
class SeasonalityAnalysis:
    """Seasonality information."""
    
    pattern_type: SeasonalPattern
    confidence: float
    peaks: List[int]  # Hours/days when peak occurs
    troughs: List[int]
    variation: float  # Percentage variation
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern": self.pattern_type.value,
            "confidence": round(self.confidence, 2),
            "peaks": self.peaks,
            "troughs": self.troughs,
            "variation": round(self.variation, 1),
        }


class TrendAnalyzer:
    """
    Analyzes trends in time-series data.
    
    Methods:
    - Linear regression trend
    - Exponential smoothing
    - Seasonal decomposition
    - Change point detection
    """
    
    def __init__(self, min_data_points: int = 10):
        self.min_data_points = min_data_points
    
    def calculate_linear_trend(self, values: List[float]) -> Tuple[float, float]:
        """
        Calculate linear trend using least squares.
        
        Returns:
            (slope, intercept)
        """
        if len(values) < self.min_data_points:
            return 0.0, 0.0
        
        n = len(values)
        x_values = list(range(n))
        
        # Calculate means
        x_mean = mean(x_values)
        y_mean = mean(values)
        
        # Calculate slope
        numerator = sum((x - x_mean) * (y - y_mean) 
                       for x, y in zip(x_values, values))
        denominator = sum((x - x_mean) ** 2 for x in x_values)
        
        if denominator == 0:
            return 0.0, y_mean
        
        slope = numerator / denominator
        intercept = y_mean - slope * x_mean
        
        return slope, intercept
    
    def exponential_smoothing(
        self,
        values: List[float],
        alpha: float = 0.3,
    ) -> List[float]:
        """Apply exponential smoothing to values."""
        if not values:
            return []
        
        smoothed = [values[0]]
        
        for value in values[1:]:
            smoothed_value = alpha * value + (1 - alpha) * smoothed[-1]
            smoothed.append(smoothed_value)
        
        return smoothed
    
    def detect_trend_direction(self, values: List[float]) -> Tuple[TrendDirection, float]:
        """
        Detect trend direction.
        
        Returns:
            (direction, confidence)
        """
        if len(values) < self.min_data_points:
            return TrendDirection.STABLE, 0.0
        
        slope, _ = self.calculate_linear_trend(values)
        
        # Calculate volatility
        smoothed = self.exponential_smoothing(values)
        residuals = [v - s for v, s in zip(values, smoothed)]
        volatility = stdev(residuals) if len(residuals) > 1 else 0
        
        mean_val = mean(values)
        if mean_val == 0:
            return TrendDirection.STABLE, 0.0
        
        # Normalize slope
        normalized_slope = (slope / mean_val) * 100
        volatility_ratio = volatility / mean_val if mean_val > 0 else 1.0
        
        # Determine direction
        if volatility_ratio > 0.3:
            return TrendDirection.VOLATILE, 0.5
        elif normalized_slope > 2.0:
            confidence = min(1.0, abs(normalized_slope) / 15)
            return TrendDirection.INCREASING, confidence
        elif normalized_slope < -2.0:
            confidence = min(1.0, abs(normalized_slope) / 15)
            return TrendDirection.DECREASING, confidence
        else:
            return TrendDirection.STABLE, 1.0
    
    def forecast_simple(
        self,
        values: List[float],
        periods: int = 1,
    ) -> List[float]:
        """
        Simple forecast using linear extrapolation.
        
        Args:
            values: Historical values
            periods: Number of periods to forecast
            
        Returns:
            Forecasted values
        """
        if len(values) < self.min_data_points:
            return [mean(values)] * periods
        
        slope, intercept = self.calculate_linear_trend(values)
        
        # Extrapolate
        n = len(values)
        forecasts = []
        
        for i in range(1, periods + 1):
            forecast_value = slope * (n + i) + intercept
            forecasts.append(max(0, forecast_value))  # No negative values
        
        return forecasts
    
    def detect_seasonality(
        self,
        values: List[float],
        hourly_data: Optional[List[int]] = None,
    ) -> SeasonalityAnalysis:
        """
        Detect seasonal patterns.
        
        Args:
            values: Time-series values
            hourly_data: Hour of day for each value (0-23)
            
        Returns:
            Seasonality information
        """
        if len(values) < 24:
            return SeasonalityAnalysis(
                pattern_type=SeasonalPattern.NONE,
                confidence=0.0,
                peaks=[],
                troughs=[],
                variation=0.0,
            )
        
        if hourly_data and len(hourly_data) == len(values):
            # Hourly pattern analysis
            hourly_values = [[] for _ in range(24)]
            for hour, value in zip(hourly_data, values):
                hourly_values[hour].append(value)
            
            # Calculate mean for each hour
            hourly_means = [mean(v) if v else 0 for v in hourly_values]
            
            # Find peaks and troughs
            overall_mean = mean(values)
            peaks = [i for i, h in enumerate(hourly_means) if h > overall_mean * 1.2]
            troughs = [i for i, h in enumerate(hourly_means) if h < overall_mean * 0.8]
            
            if peaks or troughs:
                variation = (max(hourly_means) - min(hourly_means)) / overall_mean * 100
                confidence = min(1.0, (len(peaks) + len(troughs)) / 24)
                
                return SeasonalityAnalysis(
                    pattern_type=SeasonalPattern.HOURLY,
                    confidence=confidence,
                    peaks=peaks,
                    troughs=troughs,
                    variation=variation,
                )
        
        return SeasonalityAnalysis(
            pattern_type=SeasonalPattern.NONE,
            confidence=0.0,
            peaks=[],
            troughs=[],
            variation=0.0,
        )
    
    def detect_change_point(
        self,
        values: List[float],
        sensitivity: float = 2.0,
    ) -> Optional[int]:
        """
        Detect change point in time-series.
        
        Args:
            values: Time-series data
            sensitivity: Deviation threshold (std devs)
            
        Returns:
            Index of change point, or None
        """
        if len(values) < 20:
            return None
        
        # Use a sliding window approach
        window = len(values) // 3
        
        first_mean = mean(values[:window])
        last_mean = mean(values[-window:])
        
        if abs(first_mean - last_mean) < stdev(values) * sensitivity:
            return None
        
        # Find where the change is most significant
        max_diff = 0
        change_point = None
        
        for i in range(window, len(values) - window):
            before_mean = mean(values[max(0, i-window):i])
            after_mean = mean(values[i:min(len(values), i+window)])
            
            diff = abs(after_mean - before_mean)
            if diff > max_diff:
                max_diff = diff
                change_point = i
        
        return change_point


class PerformancePredictor:
    """
    Predicts future performance based on historical trends.
    
    Predicts:
    - Query latency
    - Memory usage
    - Error rates
    - Resource requirements
    """
    
    def __init__(self):
        self.analyzer = TrendAnalyzer()
        self.historical_data: Dict[str, List[float]] = {}
        self.forecasts: Dict[str, TrendForecast] = {}
    
    def record_metric(self, metric_name: str, value: float) -> None:
        """Record a metric value."""
        if metric_name not in self.historical_data:
            self.historical_data[metric_name] = []
        
        self.historical_data[metric_name].append(value)
        
        # Keep last 1000 values
        if len(self.historical_data[metric_name]) > 1000:
            self.historical_data[metric_name] = self.historical_data[metric_name][-1000:]
    
    def forecast_metric(self, metric_name: str) -> Optional[TrendForecast]:
        """Generate forecast for a metric."""
        if metric_name not in self.historical_data:
            return None
        
        values = self.historical_data[metric_name]
        
        if len(values) < 10:
            return None
        
        # Analyze trend
        direction, confidence = self.analyzer.detect_trend_direction(values)
        
        # Get forecasts
        forecast_values = self.analyzer.forecast_simple(values, periods=3)
        
        # Calculate change
        current = values[-1]
        baseline = mean(values)
        change_percent = ((current - baseline) / baseline * 100) if baseline > 0 else 0
        
        forecast = TrendForecast(
            metric_name=metric_name,
            direction=direction,
            confidence=confidence,
            forecast_1h=forecast_values[0] if len(forecast_values) > 0 else current,
            forecast_1d=forecast_values[1] if len(forecast_values) > 1 else current,
            forecast_1w=forecast_values[2] if len(forecast_values) > 2 else current,
            current_value=current,
            baseline_value=baseline,
            change_percent=change_percent,
        )
        
        self.forecasts[metric_name] = forecast
        return forecast
    
    def get_resource_forecast(self, tier: str = "standard") -> Dict[str, Any]:
        """Forecast resource requirements."""
        # Get latency forecast
        latency_forecast = self.forecast_metric(f"{tier}_latency_ms")
        memory_forecast = self.forecast_metric(f"{tier}_memory_delta_mb")
        
        recommendations = []
        
        if latency_forecast and latency_forecast.direction == TrendDirection.INCREASING:
            recommendations.append({
                "resource": "compute",
                "action": "Consider upgrading compute resources",
                "reason": "Latency trending upward",
            })
        
        if memory_forecast and memory_forecast.direction == TrendDirection.INCREASING:
            recommendations.append({
                "resource": "memory",
                "action": "Monitor memory usage, consider migration to higher tier",
                "reason": "Memory usage trending upward",
            })
        
        return {
            "latency_forecast": latency_forecast.to_dict() if latency_forecast else None,
            "memory_forecast": memory_forecast.to_dict() if memory_forecast else None,
            "recommendations": recommendations,
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Get forecasting summary.
        Auto-generates forecasts for any metric with sufficient data if not already cached."""
        for metric_name, values in self.historical_data.items():
            if len(values) >= 10 and metric_name not in self.forecasts:
                self.forecast_metric(metric_name)
        
        return {
            "forecasts": {
                name: forecast.to_dict()
                for name, forecast in self.forecasts.items()
            },
            "data_points": sum(len(v) for v in self.historical_data.values()),
        }


def get_performance_predictor() -> PerformancePredictor:
    """Get global performance predictor instance."""
    global _performance_predictor
    if _performance_predictor is None:
        _performance_predictor = PerformancePredictor()
    return _performance_predictor
