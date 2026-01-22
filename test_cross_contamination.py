"""
Cross-contamination test suite for multi-domain RAG system.

Tests retrieval accuracy per domain to detect when queries from one domain
pull irrelevant results from other domains.
"""

import json
import sys
import pickle
import requests
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime

sys.path.insert(0, '.')
sys.path.insert(0, str(Path(__file__).parent))
from backend import retrieve, nova_text_handler

# Import Chunk class for pickle loading
try:
    from ingest_multi_domain import Chunk
except ImportError:
    # Chunk class is optional - only needed if using cache features
    Chunk = None


@dataclass
class TestCase:
    """Represents a single cross-contamination test."""
    query: str
    expected_domain: str
    description: str
    query_type: str  # "specific", "general", "ambiguous"


# Domain-specific test cases
CROSS_CONTAMINATION_TESTS = {
    "vehicle_civilian": [
        TestCase(
            query="How do I change the engine oil?",
            expected_domain="vehicle",
            description="Basic maintenance on civilian vehicle",
            query_type="specific",
        ),
        TestCase(
            query="What's the tire pressure specification?",
            expected_domain="vehicle",
            description="Civilian maintenance spec",
            query_type="specific",
        ),
        TestCase(
            query="Engine won't start - what should I check?",
            expected_domain="vehicle",
            description="Diagnostic query",
            query_type="specific",
        ),
        TestCase(
            query="How do I bleed the brakes?",
            expected_domain="vehicle",
            description="Maintenance procedure",
            query_type="specific",
        ),
    ],
    "vehicle_military": [
        TestCase(
            query="How do I operate in amphibian mode?",
            expected_domain="vehicle_military",
            description="Military-specific operation",
            query_type="specific",
        ),
        TestCase(
            query="What is the fording procedure for the GMC 6x6?",
            expected_domain="vehicle_military",
            description="Military amphibian procedure",
            query_type="specific",
        ),
        TestCase(
            query="TM9-802 transmission specifications",
            expected_domain="vehicle_military",
            description="Military manual reference",
            query_type="specific",
        ),
    ],
    "forklift": [
        TestCase(
            query="What is the maximum lift capacity?",
            expected_domain="forklift",
            description="Equipment spec query",
            query_type="specific",
        ),
        TestCase(
            query="How do I perform routine maintenance on the forklift?",
            expected_domain="forklift",
            description="Equipment maintenance",
            query_type="specific",
        ),
        TestCase(
            query="Forklift safety procedures",
            expected_domain="forklift",
            description="Equipment safety",
            query_type="specific",
        ),
    ],
    "hvac": [
        TestCase(
            query="How do I set the thermostat?",
            expected_domain="hvac",
            description="HVAC control",
            query_type="specific",
        ),
        TestCase(
            query="What is the proper refrigerant charge?",
            expected_domain="hvac",
            description="HVAC specification",
            query_type="specific",
        ),
    ],
    "radar": [
        TestCase(
            query="How do I calibrate the weather radar?",
            expected_domain="radar",
            description="Radar operation",
            query_type="specific",
        ),
        TestCase(
            query="What are the detection range specifications?",
            expected_domain="radar",
            description="Radar specs",
            query_type="specific",
        ),
    ],
}

# Ambiguous queries that could match multiple domains
AMBIGUOUS_TESTS = [
    TestCase(
        query="What is the maintenance schedule?",
        expected_domain="vehicle",  # Should prefer civilian as baseline
        description="Generic maintenance (ambiguous)",
        query_type="ambiguous",
    ),
    TestCase(
        query="Operating procedures",
        expected_domain="vehicle",  # Should prefer civilian as baseline
        description="Generic operating (ambiguous)",
        query_type="ambiguous",
    ),
]


@dataclass
class RetrievalResult:
    """Captures a single retrieval result."""
    chunk_text: str
    domain: str
    source_file: str
    relevance_score: float  # User-judged: 0=irrelevant, 1=relevant


@dataclass
class TestResult:
    """Captures results for a single test."""
    test_case: TestCase
    retrieved_chunks: List[Dict]
    domain_distribution: Dict[str, int]
    contamination_detected: bool
    contamination_ratio: float  # % of retrieved chunks from wrong domain
    relevance_scores: List[float]


class CrossContaminationTester:
    """Tests multi-domain retrieval for contamination."""

    def __init__(self, k_retrieve: int = 10, metadata_file: str = "vector_db/domain_metadata.json"):
        """Initialize tester."""
        self.k_retrieve = k_retrieve
        self.metadata_file = Path(metadata_file)
        self.metadata: Dict = {}
        self.chunks_cache: Optional[List] = None
        self.load_metadata()
        self.load_chunks_cache()

    def load_metadata(self) -> None:
        """Load domain metadata."""
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r') as f:
                self.metadata = json.load(f)
            print(f"[OK] Loaded metadata: {self.metadata['total_chunks']} total chunks")
            print(f"   Domains: {', '.join(self.metadata['domains'])}")
        else:
            print(f"[WARN] Metadata file not found: {self.metadata_file}")

    def load_chunks_cache(self) -> None:
        """Load chunks for domain extraction."""
        if self.chunks_cache is not None:
            return
        chunks_file = Path("vector_db/chunks_with_metadata.pkl")
        if chunks_file.exists():
            with open(chunks_file, 'rb') as f:
                self.chunks_cache = pickle.load(f)
            if self.chunks_cache is not None:
                print(f"[OK] Loaded {len(self.chunks_cache)} chunks from cache")
        else:
            print(f"[WARN] Chunks file not found: {chunks_file}")

    def extract_domain_from_chunk(self, chunk_dict: Dict) -> str:
        """
        Extract domain from chunk dictionary or by matching text in cache.
        """
        if isinstance(chunk_dict, dict):
            # Try to get domain from dict
            if "domain" in chunk_dict:
                return chunk_dict["domain"]
            
            # Try to match by text if we have cache
            if self.chunks_cache and isinstance(chunk_dict, dict) and "text" in chunk_dict:
                chunk_text = chunk_dict.get("text", "")[:100]  # First 100 chars for matching
                for cached_chunk in self.chunks_cache:
                    if hasattr(cached_chunk, 'text') and cached_chunk.text[:100] == chunk_text:
                        return cached_chunk.domain
        
        # Fallback to file analysis
        if isinstance(chunk_dict, dict):
            source = chunk_dict.get("source_file", "").lower() if isinstance(chunk_dict, dict) else ""
        else:
            source = str(chunk_dict).lower()
        
        if "tm9-802" in source or "amphibian" in source or "dukw" in source:
            return "vehicle_military"
        elif "vehicle" in source:
            return "vehicle"
        elif "forklift" in source or "atlas" in source or "tm-10" in source:
            return "forklift"
        elif "hvac" in source or "carrier" in source:
            return "hvac"
        elif "radar" in source or "wxr" in source:
            return "radar"
        return "unknown"

    def test_query(self, test_case: TestCase) -> TestResult:
        """Run a single test case."""
        print(f"\n  Query: {test_case.query[:60]}...")
        print(f"  Expected domain: {test_case.expected_domain}")

        try:
            # Retrieve relevant chunks
            results = retrieve(test_case.query, k=self.k_retrieve, top_n=self.k_retrieve)
            print(f"  Retrieved: {len(results)} chunks")

            # Analyze domain distribution
            domain_distribution: Dict[str, int] = {}
            for chunk in results:
                domain = self.extract_domain_from_chunk(chunk)
                domain_distribution[domain] = domain_distribution.get(domain, 0) + 1

            # Calculate contamination
            correct_domain_count = domain_distribution.get(test_case.expected_domain, 0)
            contamination_ratio = (len(results) - correct_domain_count) / len(results) if results else 0
            contamination_detected = contamination_ratio > 0.3  # > 30% contamination threshold

            print(f"  Domain distribution: {domain_distribution}")
            print(f"  Contamination: {contamination_ratio*100:.1f}%", end="")
            if contamination_detected:
                print(" [WARN] CONTAMINATION DETECTED")
            else:
                print(" [OK]")

            return TestResult(
                test_case=test_case,
                retrieved_chunks=results,
                domain_distribution=domain_distribution,
                contamination_detected=contamination_detected,
                contamination_ratio=contamination_ratio,
                relevance_scores=[],
            )

        except Exception as e:
            print(f"  [ERROR] Error: {e}")
            import traceback
            traceback.print_exc()
            return TestResult(
                test_case=test_case,
                retrieved_chunks=[],
                domain_distribution={},
                contamination_detected=True,
                contamination_ratio=1.0,
                relevance_scores=[],
            )

    def run_test_suite(self) -> Dict[str, List[TestResult]]:
        """Run full cross-contamination test suite."""
        print("="*70)
        print("CROSS-CONTAMINATION TEST SUITE")
        print("="*70)

        results_by_domain = {}

        # Test domain-specific queries
        for domain, test_cases in CROSS_CONTAMINATION_TESTS.items():
            print(f"\n{'-'*70}")
            print(f"[{domain.upper()}]")
            print(f"{'-'*70}")

            domain_results = []
            for test_case in test_cases:
                result = self.test_query(test_case)
                domain_results.append(result)

            results_by_domain[domain] = domain_results

        # Test ambiguous queries
        print(f"\n{'-'*70}")
        print(f"[AMBIGUOUS QUERIES]")
        print(f"{'-'*70}")
        ambiguous_results = []
        for test_case in AMBIGUOUS_TESTS:
            result = self.test_query(test_case)
            ambiguous_results.append(result)
        results_by_domain["ambiguous"] = ambiguous_results

        return results_by_domain

    def generate_report(self, results: Dict[str, List[TestResult]]) -> None:
        """Generate test report."""
        print("\n" + "="*70)
        print("CROSS-CONTAMINATION TEST REPORT")
        print("="*70)

        # Summary by domain
        total_tests = sum(len(r) for r in results.values())
        total_contaminated = sum(
            sum(1 for test in domain_results if test.contamination_detected)
            for domain_results in results.values()
        )

        print(f"\n[SUMMARY]")
        print(f"{'-'*70}")
        print(f"Total tests run: {total_tests}")
        print(f"Contamination detected: {total_contaminated}/{total_tests} ({100*total_contaminated/total_tests:.1f}%)")

        # Details by domain
        print(f"\n[RESULTS BY DOMAIN]")
        print(f"{'-'*70}")

        for domain, domain_results in sorted(results.items()):
            contaminated = sum(1 for r in domain_results if r.contamination_detected)
            avg_contamination = (
                sum(r.contamination_ratio for r in domain_results) / len(domain_results)
                if domain_results else 0
            )
            print(f"\n{domain.upper()}")
            print(f"  Tests: {len(domain_results)}")
            print(f"  Contaminated: {contaminated}/{len(domain_results)}")
            print(f"  Avg contamination: {avg_contamination*100:.1f}%")

            if contaminated > 0:
                print(f"  [WARN] Issues found:")
                for result in domain_results:
                    if result.contamination_detected:
                        print(
                            f"    - Query: {result.test_case.query[:50]}..."
                            f" (contamination: {result.contamination_ratio*100:.1f}%)"
                        )

        # Save report
        report_file = Path("ragas_results") / f"cross_contamination_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)

        report_data = {
            "timestamp": datetime.now().isoformat(),
            "total_tests": total_tests,
            "total_contaminated": total_contaminated,
            "contamination_rate": total_contaminated / total_tests if total_tests else 0,
            "summary_by_domain": {
                domain: {
                    "total": len(results[domain]),
                    "contaminated": sum(1 for r in results[domain] if r.contamination_detected),
                    "avg_contamination_ratio": (
                        sum(r.contamination_ratio for r in results[domain]) / len(results[domain])
                        if results[domain] else 0
                    ),
                }
                for domain in results.keys()
            },
        }

        with open(report_file, 'w') as f:
            json.dump(report_data, f, indent=2)
        print(f"\n[OK] Report saved to {report_file}")


def main():
    """Run cross-contamination tests."""
    try:
        tester = CrossContaminationTester(k_retrieve=10)
        results = tester.run_test_suite()
        tester.generate_report(results)

        # Determine if tests passed
        contaminated = sum(
            sum(1 for test in domain_results if test.contamination_detected)
            for domain_results in results.values()
        )
        total = sum(len(r) for r in results.values())

        if contaminated == 0:
            print(f"\n[OK] All tests passed! No cross-contamination detected.")
            return 0
        elif contaminated <= total * 0.2:  # <= 20% contamination
            print(f"\n[WARN] Minor contamination detected ({100*contaminated/total:.1f}%). System acceptable.")
            return 0
        else:
            print(f"\n[ERROR] Significant contamination detected ({100*contaminated/total:.1f}%). Needs investigation.")
            return 1

    except Exception as e:
        print(f"[ERROR] Test suite failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
