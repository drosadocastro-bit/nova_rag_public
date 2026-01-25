"""
Real-time Web Dashboard for NIC Observability

Simple HTML5 dashboard with live metrics display.
No external JavaScript dependencies (vanilla JS).
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NIC Observability Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: #333;
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        header {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        h1 {
            color: #2a5298;
            font-size: 28px;
        }
        
        .status {
            display: flex;
            gap: 20px;
            align-items: center;
        }
        
        .status-item {
            text-align: right;
        }
        
        .status-item label {
            font-size: 12px;
            color: #999;
            display: block;
            margin-bottom: 5px;
        }
        
        .status-item .value {
            font-size: 18px;
            font-weight: bold;
            color: #2a5298;
        }
        
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #4CAF50;
            margin-right: 8px;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        
        .card {
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        .card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }
        
        .card h2 {
            color: #2a5298;
            font-size: 18px;
            margin-bottom: 15px;
            border-bottom: 2px solid #e0e0e0;
            padding-bottom: 10px;
        }
        
        .metric {
            margin-bottom: 15px;
            padding: 10px;
            background: #f9f9f9;
            border-radius: 4px;
            border-left: 3px solid #2a5298;
        }
        
        .metric label {
            font-size: 12px;
            color: #999;
            display: block;
            margin-bottom: 5px;
        }
        
        .metric .value {
            font-size: 22px;
            font-weight: bold;
            color: #2a5298;
        }
        
        .metric .unit {
            font-size: 12px;
            color: #999;
            margin-left: 5px;
        }
        
        .metric .sub {
            font-size: 12px;
            color: #666;
            margin-top: 3px;
        }
        
        .alert {
            padding: 10px;
            border-radius: 4px;
            margin-bottom: 10px;
            border-left: 4px solid;
        }
        
        .alert.critical {
            background: #ffebee;
            border-left-color: #f44336;
            color: #c62828;
        }
        
        .alert.warning {
            background: #fff8e1;
            border-left-color: #ff9800;
            color: #e65100;
        }
        
        .alert.info {
            background: #e3f2fd;
            border-left-color: #2196F3;
            color: #1565c0;
        }
        
        .progress {
            height: 4px;
            background: #e0e0e0;
            border-radius: 2px;
            overflow: hidden;
            margin-top: 8px;
        }
        
        .progress-bar {
            height: 100%;
            background: linear-gradient(90deg, #4CAF50, #45a049);
            transition: width 0.3s ease;
        }
        
        .chart-container {
            height: 250px;
            background: #f9f9f9;
            border-radius: 4px;
            padding: 10px;
            position: relative;
        }
        
        .chart {
            width: 100%;
            height: 100%;
            display: flex;
            align-items: flex-end;
            gap: 2px;
            padding: 5px;
            background: #f9f9f9;
        }
        
        .bar {
            flex: 1;
            background: linear-gradient(180deg, #2196F3, #1976D2);
            border-radius: 2px 2px 0 0;
            position: relative;
            min-height: 2px;
            transition: background 0.2s;
        }
        
        .bar:hover {
            background: linear-gradient(180deg, #42A5F5, #1976D2);
        }
        
        .bar-label {
            position: absolute;
            bottom: -20px;
            left: 50%;
            transform: translateX(-50%);
            font-size: 10px;
            color: #999;
            white-space: nowrap;
        }
        
        .footer {
            text-align: center;
            color: rgba(255,255,255,0.7);
            padding: 20px;
            font-size: 12px;
        }
        
        .refresh-indicator {
            display: inline-block;
            margin-left: 10px;
            font-size: 12px;
            color: #666;
        }
        
        @media (max-width: 768px) {
            .grid {
                grid-template-columns: 1fr;
            }
            
            h1 {
                font-size: 20px;
            }
            
            header {
                flex-direction: column;
                gap: 15px;
                text-align: center;
            }
            
            .status {
                flex-direction: column;
                gap: 10px;
                width: 100%;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>
                    <span class="status-indicator"></span>
                    NIC Observability Dashboard
                </h1>
            </div>
            <div class="status">
                <div class="status-item">
                    <label>Status</label>
                    <div class="value" id="status">Loading...</div>
                </div>
                <div class="status-item">
                    <label>Uptime</label>
                    <div class="value" id="uptime">--</div>
                </div>
                <div class="status-item">
                    <label>Last Updated</label>
                    <div class="value refresh-indicator" id="last-updated">--</div>
                </div>
            </div>
        </header>
        
        <div class="grid">
            <!-- Performance Card -->
            <div class="card">
                <h2>Performance</h2>
                <div class="metric">
                    <label>Query Latency (P95)</label>
                    <div class="value" id="p95-latency">--<span class="unit">ms</span></div>
                    <div class="progress">
                        <div class="progress-bar" id="p95-progress" style="width: 0%;"></div>
                    </div>
                </div>
                <div class="metric">
                    <label>Memory Usage (Delta)</label>
                    <div class="value" id="memory-delta">--<span class="unit">MB</span></div>
                </div>
                <div class="metric">
                    <label>Cache Hit Rate</label>
                    <div class="value" id="cache-hit-rate">--<span class="unit">%</span></div>
                    <div class="progress">
                        <div class="progress-bar" id="cache-progress" style="width: 0%;"></div>
                    </div>
                </div>
            </div>
            
            <!-- Queries Card -->
            <div class="card">
                <h2>Query Statistics</h2>
                <div class="metric">
                    <label>Total Queries</label>
                    <div class="value" id="total-queries">0</div>
                </div>
                <div class="metric">
                    <label>Failed Queries</label>
                    <div class="value" id="failed-queries">0</div>
                </div>
                <div class="metric">
                    <label>Error Rate</label>
                    <div class="value" id="error-rate">--<span class="unit">%</span></div>
                    <div class="progress">
                        <div class="progress-bar" id="error-progress" style="width: 0%; background: linear-gradient(90deg, #f44336, #d32f2f);"></div>
                    </div>
                </div>
            </div>
            
            <!-- Hardware Info Card -->
            <div class="card">
                <h2>Hardware Context</h2>
                <div class="metric">
                    <label>Active Tier</label>
                    <div class="value" id="hardware-tier">--</div>
                </div>
                <div class="metric">
                    <label>Models Loaded</label>
                    <div class="value" id="models-loaded">0</div>
                </div>
                <div class="metric">
                    <label>Batch Size</label>
                    <div class="value" id="batch-size">--</div>
                </div>
            </div>
        </div>
        
        <!-- Latency Chart -->
        <div class="card">
            <h2>Query Latency Trend (Last 50 Queries)</h2>
            <div class="chart-container">
                <div class="chart" id="latency-chart"></div>
            </div>
        </div>
        
        <!-- Alerts -->
        <div class="card">
            <h2>Active Alerts</h2>
            <div id="alerts-container">
                <div class="alert info">No active alerts</div>
            </div>
        </div>
        
        <!-- Recent Queries Log -->
        <div class="card">
            <h2>Recent Queries</h2>
            <div id="recent-queries" style="font-size: 13px; line-height: 1.6;">
                <div style="color: #999;">Loading...</div>
            </div>
        </div>
        
        <div class="footer">
            <p>Nova NIC Observability Dashboard | Real-time metrics powered by observability framework</p>
        </div>
    </div>
    
    <script>
        const API_BASE = '/api/observability';
        const REFRESH_INTERVAL = 5000; // 5 seconds
        let latencyHistory = [];
        
        async function fetchDashboardData() {
            try {
                const response = await fetch(API_BASE + '/dashboard');
                return await response.json();
            } catch (error) {
                console.error('Failed to fetch dashboard data:', error);
                return null;
            }
        }
        
        function formatDuration(seconds) {
            if (seconds < 60) return Math.round(seconds) + 's';
            const minutes = Math.floor(seconds / 60);
            const secs = Math.round(seconds % 60);
            return `${minutes}m ${secs}s`;
        }
        
        function formatTime(timestamp) {
            const now = new Date().getTime();
            const ago = now - timestamp * 1000;
            if (ago < 60000) return 'now';
            const minutes = Math.floor(ago / 60000);
            if (minutes < 60) return `${minutes}m ago`;
            const hours = Math.floor(minutes / 60);
            return `${hours}h ago`;
        }
        
        function updateMetrics(data) {
            if (!data) return;
            
            // Status
            document.getElementById('status').textContent = 'Healthy';
            document.getElementById('uptime').textContent = formatDuration(data.uptime);
            document.getElementById('last-updated').textContent = 'now';
            
            // Metrics
            const metrics = data.metrics?.metric_stats || {};
            
            if (metrics.query_latency_ms) {
                const p95 = metrics.query_latency_ms.p95 || 0;
                document.getElementById('p95-latency').textContent = Math.round(p95) + 'ms';
                document.getElementById('p95-progress').style.width = Math.min(100, (p95 / 200) * 100) + '%';
            }
            
            if (metrics.memory_delta_mb) {
                const mem = metrics.memory_delta_mb.mean || 0;
                document.getElementById('memory-delta').textContent = Math.round(mem * 10) / 10 + 'MB';
            }
            
            if (metrics.cache_hit) {
                const cacheHitRate = (metrics.cache_hit.mean || 0) * 100;
                document.getElementById('cache-hit-rate').textContent = Math.round(cacheHitRate) + '%';
                document.getElementById('cache-progress').style.width = cacheHitRate + '%';
            }
            
            // Query stats
            document.getElementById('total-queries').textContent = data.queries_total || 0;
            document.getElementById('failed-queries').textContent = data.queries_failed || 0;
            
            const errorRate = (data.error_rate || 0) * 100;
            document.getElementById('error-rate').textContent = Math.round(errorRate * 10) / 10 + '%';
            document.getElementById('error-progress').style.width = Math.min(100, errorRate) + '%';
            
            // Alerts
            const alertsContainer = document.getElementById('alerts-container');
            const activeAlerts = data.active_alerts || [];
            if (activeAlerts.length === 0) {
                alertsContainer.innerHTML = '<div class="alert info">No active alerts</div>';
            } else {
                alertsContainer.innerHTML = activeAlerts.map(alert => 
                    `<div class="alert ${alert.severity}"><strong>${alert.rule_name}</strong><br/>${alert.message}</div>`
                ).join('');
            }
            
            // Recent queries
            const recentQueries = data.recent_queries || [];
            const queryLog = document.getElementById('recent-queries');
            if (recentQueries.length === 0) {
                queryLog.innerHTML = '<div style="color: #999;">No recent queries</div>';
            } else {
                queryLog.innerHTML = recentQueries.slice(0, 10).map(q => 
                    `<div style="padding: 8px; background: #f9f9f9; border-radius: 4px; margin-bottom: 5px;">
                        <strong>${q.query_text?.substring(0, 50) || 'Query'}...</strong><br/>
                        <span style="color: #666; font-size: 12px;">
                            ${Math.round(q.duration_ms || 0)}ms | 
                            ${q.hardware_tier || 'standard'} | 
                            ${formatTime(q.timestamp)}
                        </span>
                    </div>`
                ).join('');
            }
            
            // Update latency chart
            const recentLatencies = recentQueries.map(q => q.duration_ms || 0).slice(-50);
            if (recentLatencies.length > 0) {
                latencyHistory = recentLatencies;
                updateLatencyChart();
            }
        }
        
        function updateLatencyChart() {
            const chart = document.getElementById('latency-chart');
            const maxLatency = Math.max(...latencyHistory, 200);
            
            chart.innerHTML = latencyHistory.map((latency, i) => {
                const height = (latency / maxLatency) * 100;
                return `<div class="bar" style="height: ${height}%" title="${Math.round(latency)}ms"></div>`;
            }).join('');
        }
        
        async function refresh() {
            const data = await fetchDashboardData();
            if (data) {
                updateMetrics(data);
            }
        }
        
        // Initial load and auto-refresh
        refresh();
        setInterval(refresh, REFRESH_INTERVAL);
    </script>
</body>
</html>
"""


def create_dashboard_blueprint():
    """Create Flask blueprint for dashboard."""
    from flask import Blueprint, render_template_string
    
    dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')
    
    @dashboard_bp.route('/')
    def dashboard():
        return render_template_string(DASHBOARD_HTML)
    
    return dashboard_bp
