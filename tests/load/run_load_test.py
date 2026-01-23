#!/usr/bin/env python3
"""
Load testing script for NovaRAG.
Simulates concurrent users and measures system performance.

Usage:
    python tests/load/run_load_test.py --users 5 --duration 300 --model llama3.2:3b
"""

import argparse
import json
import time
import threading
import requests
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import statistics

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("[WARNING] psutil not installed - memory tracking disabled")
    print("         Install with: pip install psutil")


class LoadTester:
    def __init__(self, base_url: str, users: int, duration: int, model: str):
        self.base_url = base_url
        self.users = users
        self.duration = duration
        self.model = model
        self.results: List[Dict[str, Any]] = []
        self.errors: List[Dict[str, Any]] = []
        self.lock = threading.Lock()
        self.stop_flag = threading.Event()
        self.start_memory = 0
        self.peak_memory = 0
        
    def load_questions(self) -> List[str]:
        """Load test questions from fixture file or use defaults."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "eval_questions.json"
        
        if fixture_path.exists():
            try:
                with open(fixture_path, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
                    print("[WARNING] Invalid fixture format, using defaults")
            except Exception as e:
                print(f"[WARNING] Failed to load fixtures: {e}, using defaults")
        
        # Default questions if fixture not available
        return [
            "What is the recommended oil change interval?",
            "How do I troubleshoot error code P0171?",
            "Explain the brake bleeding procedure step by step",
            "What are the symptoms of a failing alternator?",
            "How do I replace the air filter?",
            "What causes engine overheating?",
            "How do I check transmission fluid level?",
            "What is the tire pressure specification?",
            "How do I diagnose a battery drain issue?",
            "Explain the procedure to replace brake pads",
            "What are signs of a failing fuel pump?",
            "How do I reset the check engine light?",
            "What is the coolant replacement interval?",
            "How do I test the starter motor?",
            "What causes rough idle?",
            "How do I replace spark plugs?",
            "What is the procedure for wheel alignment?",
            "How do I diagnose steering problems?",
            "What causes transmission slipping?",
            "How do I check for vacuum leaks?",
        ]
    
    def send_query(self, question: str, user_id: int) -> Dict[str, Any]:
        """Send a single query and measure response time."""
        start_time = time.time()
        result = {
            "user_id": user_id,
            "question": question[:50],  # Truncate for logging
            "start_time": start_time,
            "success": False,
            "latency": 0,
            "error": None,
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/api/query",
                json={"question": question, "mode": "Auto"},
                timeout=60  # 60s timeout
            )
            
            latency = time.time() - start_time
            result["latency"] = latency
            
            if response.status_code == 200:
                result["success"] = True
                data = response.json()
                result["answer_length"] = len(data.get("answer", ""))
            else:
                result["error"] = f"HTTP {response.status_code}"
                
        except requests.exceptions.Timeout:
            result["error"] = "Timeout (>60s)"
            result["latency"] = time.time() - start_time
        except Exception as e:
            result["error"] = str(e)[:100]
            result["latency"] = time.time() - start_time
        
        return result
    
    def user_worker(self, user_id: int, questions: List[str]):
        """Simulate a single user making requests."""
        import random
        
        while not self.stop_flag.is_set():
            # Pick random question
            question = random.choice(questions)
            
            # Send query
            result = self.send_query(question, user_id)
            
            # Record result
            with self.lock:
                if result["success"]:
                    self.results.append(result)
                else:
                    self.errors.append(result)
            
            # Update memory tracking
            if PSUTIL_AVAILABLE:
                try:
                    process = psutil.Process()
                    memory_gb = process.memory_info().rss / 1024**3
                    with self.lock:
                        self.peak_memory = max(self.peak_memory, memory_gb)
                except Exception:
                    pass
            
            # Small random delay to simulate human behavior
            time.sleep(random.uniform(0.5, 2.0))
    
    def run(self):
        """Execute load test."""
        print("=" * 70)
        print("NOVARAG LOAD TEST")
        print("=" * 70)
        print("Configuration:")
        print(f"  Users: {self.users}")
        print(f"  Duration: {self.duration}s ({self.duration // 60} minutes)")
        print(f"  Model: {self.model}")
        print(f"  Base URL: {self.base_url}")
        print("=" * 70)
        
        # Load questions
        questions = self.load_questions()
        print(f"Loaded {len(questions)} test questions")
        
        # Check server availability
        print("\nChecking server availability...")
        try:
            response = requests.get(f"{self.base_url}/", timeout=5)
            if response.status_code == 200:
                print("✅ Server is reachable")
            else:
                print(f"⚠️  Server returned HTTP {response.status_code}")
        except Exception as e:
            print(f"❌ Server not reachable: {e}")
            print("   Make sure Flask app is running:")
            print("   python nova_flask_app.py")
            return
        
        # Warmup
        print("\nPerforming warmup (3 queries)...")
        for i in range(3):
            result = self.send_query(questions[i % len(questions)], user_id=0)
            if result["success"]:
                print(f"  Warmup {i+1}/3: {result['latency']:.1f}s ✅")
            else:
                print(f"  Warmup {i+1}/3: {result['error']} ❌")
        
        # Record starting memory
        if PSUTIL_AVAILABLE:
            try:
                process = psutil.Process()
                self.start_memory = process.memory_info().rss / 1024**3
                self.peak_memory = self.start_memory
                print(f"\nStarting memory: {self.start_memory:.1f} GB")
            except Exception:
                pass
        
        # Start load test
        print(f"\n{'=' * 70}")
        print(f"Starting load test at {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'=' * 70}\n")
        
        threads = []
        for user_id in range(1, self.users + 1):
            t = threading.Thread(target=self.user_worker, args=(user_id, questions))
            t.daemon = True
            t.start()
            threads.append(t)
        
        # Wait for duration
        try:
            time.sleep(self.duration)
        except KeyboardInterrupt:
            print("\n\n⚠️  Test interrupted by user")
        
        # Stop all threads
        self.stop_flag.set()
        print("\nStopping workers...")
        for t in threads:
            t.join(timeout=5)
        
        # Print results
        self.print_results()
    
    def print_results(self):
        """Print comprehensive test results."""
        print("\n" + "=" * 70)
        print("LOAD TEST RESULTS")
        print("=" * 70)
        
        total_queries = len(self.results) + len(self.errors)
        if total_queries == 0:
            print("No queries completed")
            return
        
        # Basic stats
        print("\nBasic Metrics:")
        print(f"  Total Queries: {total_queries}")
        print(f"  Successful: {len(self.results)}")
        print(f"  Failed: {len(self.errors)}")
        print(f"  Error Rate: {len(self.errors) / total_queries * 100:.1f}%")
        
        # Latency stats
        if self.results:
            latencies = [r["latency"] for r in self.results]
            avg_latency = statistics.mean(latencies)
            p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) > 0 else 0
            
            print("\nLatency Metrics:")
            print(f"  Average: {avg_latency:.1f}s")
            print(f"  p50 (median): {statistics.median(latencies):.1f}s")
            print(f"  p95: {p95_latency:.1f}s")
            print(f"  Min: {min(latencies):.1f}s")
            print(f"  Max: {max(latencies):.1f}s")
            
            # Throughput
            throughput_per_min = len(self.results) / (self.duration / 60)
            print("\nThroughput:")
            print(f"  Queries/minute: {throughput_per_min:.1f}")
            print(f"  Queries/second: {throughput_per_min / 60:.2f}")
        
        # Memory usage
        if PSUTIL_AVAILABLE and self.peak_memory > 0:
            print("\nMemory Usage:")
            print(f"  Starting: {self.start_memory:.1f} GB")
            print(f"  Peak: {self.peak_memory:.1f} GB")
            print(f"  Growth: +{(self.peak_memory - self.start_memory):.1f} GB")
        
        # Error summary
        if self.errors:
            print("\nError Summary:")
            error_types = {}
            for err in self.errors:
                error_type = err.get("error", "Unknown")
                error_types[error_type] = error_types.get(error_type, 0) + 1
            
            for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
                print(f"  {error_type}: {count}")
        
        # Summary table (matching documentation format)
        print(f"\n{'=' * 70}")
        print("SUMMARY TABLE")
        print(f"{'=' * 70}")
        if self.results:
            latencies = [r["latency"] for r in self.results]
            avg_latency = statistics.mean(latencies)
            p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) > 0 else 0
            throughput_per_min = len(self.results) / (self.duration / 60)
            error_rate_pct = len(self.errors) / total_queries * 100
            
            print("| Users | Avg Latency (s) | p95 Latency (s) | Throughput (q/min) | Error Rate | Memory Peak (GB) |")
            print("|-------|-----------------|-----------------|---------------------|------------|------------------|")
            memory_str = f"{self.peak_memory:.1f}" if PSUTIL_AVAILABLE and self.peak_memory > 0 else "N/A"
            print(f"| {self.users:5} | {avg_latency:15.1f} | {p95_latency:15.1f} | {throughput_per_min:19.0f} | {error_rate_pct:9.0f}% | {memory_str:16} |")
        
        print(f"{'=' * 70}\n")
        
        # Save results to file
        self.save_results()
    
    def save_results(self):
        """Save detailed results to JSON file."""
        output_dir = Path(__file__).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = output_dir / f"results_{self.users}users_{timestamp}.json"
        
        data = {
            "config": {
                "users": self.users,
                "duration": self.duration,
                "model": self.model,
                "base_url": self.base_url,
                "timestamp": timestamp,
            },
            "summary": {
                "total_queries": len(self.results) + len(self.errors),
                "successful": len(self.results),
                "failed": len(self.errors),
                "error_rate_pct": len(self.errors) / (len(self.results) + len(self.errors)) * 100 if (len(self.results) + len(self.errors)) > 0 else 0,
            },
            "results": self.results,
            "errors": self.errors,
        }
        
        if self.results:
            latencies = [r["latency"] for r in self.results]
            data["summary"]["avg_latency"] = statistics.mean(latencies)
            data["summary"]["p95_latency"] = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) > 0 else 0
            data["summary"]["throughput_per_min"] = len(self.results) / (self.duration / 60)
        
        if PSUTIL_AVAILABLE and self.peak_memory > 0:
            data["summary"]["memory_peak_gb"] = self.peak_memory
            data["summary"]["memory_start_gb"] = self.start_memory
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"📊 Results saved to: {filename}")


def main():
    parser = argparse.ArgumentParser(description="NovaRAG Load Testing Tool")
    parser.add_argument("--users", type=int, default=5, help="Number of concurrent users (default: 5)")
    parser.add_argument("--duration", type=int, default=300, help="Test duration in seconds (default: 300)")
    parser.add_argument("--model", type=str, default="llama3.2:3b", help="Model to use (default: llama3.2:3b)")
    parser.add_argument("--url", type=str, default="http://localhost:5000", help="Base URL (default: http://localhost:5000)")
    
    args = parser.parse_args()
    
    tester = LoadTester(
        base_url=args.url,
        users=args.users,
        duration=args.duration,
        model=args.model
    )
    
    tester.run()


if __name__ == "__main__":
    main()
