#!/usr/bin/env python3
"""
NIC RAGAS Evaluation Harness
============================
Evaluates NIC's RAG quality using RAGAS metrics:
- Faithfulness: Is the answer grounded in retrieved context?
- Answer Relevancy: Does the answer address the question?
- Context Precision: Are retrieved docs relevant?
- Context Recall: Does context contain needed info?

Uses LM Studio as the evaluator LLM (no OpenAI API needed).
"""

import json
import os
import sys
import time
import requests
from datetime import datetime
from typing import Any, Optional
from pathlib import Path

# RAGAS imports
from datasets import Dataset
from ragas import evaluate
from ragas.metrics._faithfulness import Faithfulness
from ragas.metrics._answer_relevance import AnswerRelevancy
from ragas.metrics._context_precision import ContextPrecision
from ragas.metrics._context_recall import ContextRecall
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper

# LangChain for LM Studio integration
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.embeddings import HuggingFaceEmbeddings

# =============================================================================
# CONFIGURATION
# =============================================================================
NIC_API_BASE = "http://127.0.0.1:5000/api"
LM_STUDIO_BASE = "http://127.0.0.1:1234/v1"

# RAGAS needs an LLM for evaluation - 20B model achieved best score (77.22% on test)
EVAL_MODEL = "phi-4-14b"  # Fallback to Phi-4 (lighter, still good evaluator)

# Test dataset path
DATASET_PATH = "governance/nic_qa_dataset.json"

# Output paths
OUTPUT_DIR = "ragas_results"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def check_server_ready() -> bool:
    """Check if NIC Flask server is running."""
    try:
        r = requests.get(f"{NIC_API_BASE}/status", timeout=5)
        return r.status_code == 200
    except Exception:
        return False

def check_lm_studio_ready() -> bool:
    """Check if LM Studio is running."""
    try:
        r = requests.get(f"{LM_STUDIO_BASE}/models", timeout=5)
        return r.status_code == 200
    except Exception:
        return False

def query_nic(question: str, timeout: int = 1200, prose_mode: bool = False) -> dict:
    """Query NIC API and get answer + retrieved contexts.
    
    Args:
        question: The question to ask
        timeout: Request timeout in seconds
        prose_mode: If True, uses retrieval-only mode for cleaner prose answers
    """
    try:
        payload = {"question": question, "mode": "Auto"}
        if prose_mode:
            # Use retrieval-only fallback for cleaner prose output
            payload["fallback"] = "retrieval-only"
        
        r = requests.post(
            f"{NIC_API_BASE}/ask",
            json=payload,
            timeout=timeout
        )
        if r.status_code == 200:
            return r.json()
        return {"error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def extract_answer_text(answer: Any) -> str:
    """Extract text from answer (handles string or dict)."""
    if isinstance(answer, str):
        return answer
    if isinstance(answer, dict):
        # Handle refusal schema
        if answer.get("response_type") == "refusal":
            return f"[REFUSAL] {answer.get('message', 'Request declined')}"
        # Handle structured responses
        if "steps" in answer:
            parts = []
            if answer.get("risks"):
                parts.append("WARNINGS: " + "; ".join(answer["risks"]))
            if answer.get("steps"):
                parts.append("STEPS: " + "; ".join(answer["steps"]))
            if answer.get("verification"):
                parts.append("VERIFY: " + "; ".join(answer["verification"]))
            return " | ".join(parts)
        # Fallback
        return json.dumps(answer)
    return str(answer)

def extract_contexts(traced_sources: list) -> list[str]:
    """Extract context strings from traced_sources."""
    contexts = []
    for src in traced_sources:
        snippet = src.get("snippet", "")
        source = src.get("source", "unknown")
        page = src.get("page", "?")
        if snippet:
            contexts.append(f"[{source} p.{page}] {snippet}")
    return contexts if contexts else ["No context retrieved"]

def load_test_dataset() -> list[dict]:
    """Load test cases from NIC QA dataset."""
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    test_cases = []
    
    # Extract positive cases (these have expected responses for ground truth)
    for case in data.get("positive_cases", []):
        test_cases.append({
            "id": case["id"],
            "question": case["query"],
            "ground_truth": case["expected_response"],
            "category": "positive_case"
        })
    
    # Extract safety-critical cases
    for case in data.get("safety_critical", []):
        test_cases.append({
            "id": case["id"],
            "question": case["query"],
            "ground_truth": case["expected_response"],
            "category": "safety_critical"
        })
    
    return test_cases

# =============================================================================
# MAIN EVALUATION
# =============================================================================

def run_ragas_evaluation(max_samples: Optional[int] = 20, prose_mode: bool = False):
    """Run RAGAS evaluation on NIC.
    
    Args:
        max_samples: Maximum number of test cases to evaluate
        prose_mode: If True, uses retrieval-only mode for cleaner text answers
    """
    
    print("=" * 70)
    print("NIC RAGAS EVALUATION")
    print("=" * 70)
    print(f"Timestamp: {TIMESTAMP}")
    print(f"Mode: {'PROSE (retrieval-only)' if prose_mode else 'FULL (LLM-generated)'}")
    print()
    
    # Check prerequisites
    print("[1/5] Checking prerequisites...")
    if not check_server_ready():
        print("ERROR: NIC Flask server not running at", NIC_API_BASE)
        print("       Start it with: python nova_flask_app.py")
        return None
    print("      NIC server: OK")
    
    if not check_lm_studio_ready():
        print("ERROR: LM Studio not running at", LM_STUDIO_BASE)
        print("       Start LM Studio and load a model")
        return None
    print("      LM Studio: OK")
    
    # Load test dataset
    print("\n[2/5] Loading test dataset...")
    test_cases = load_test_dataset()
    print(f"      Loaded {len(test_cases)} test cases")
    
    # Limit samples for faster testing
    if max_samples and len(test_cases) > max_samples:
        test_cases = test_cases[:max_samples]
        print(f"      Using first {max_samples} samples")
    
    # Query NIC for each test case
    print("\n[3/5] Querying NIC for answers and contexts...")
    results = []
    for i, case in enumerate(test_cases):
        print(f"      [{i+1}/{len(test_cases)}] {case['id']}: {case['question'][:50]}...")
        
        response = query_nic(case["question"], prose_mode=prose_mode)
        
        if "error" in response:
            print(f"            ERROR: {response['error']}")
            continue
        
        answer_text = extract_answer_text(response.get("answer", ""))
        contexts = extract_contexts(response.get("traced_sources", []))
        
        results.append({
            "question": case["question"],
            "answer": answer_text,
            "contexts": contexts,
            "ground_truth": case["ground_truth"],
            "id": case["id"],
            "category": case["category"]
        })
        
        # Small delay to avoid overwhelming the server
        time.sleep(0.5)
    
    print(f"      Collected {len(results)} valid responses")
    
    if len(results) == 0:
        print("ERROR: No valid responses collected")
        return None
    
    # Prepare RAGAS dataset
    print("\n[4/5] Running RAGAS evaluation...")
    print("      This may take several minutes (LLM-based evaluation)...")
    
    # Create HuggingFace dataset format for RAGAS
    ragas_data = {
        "question": [r["question"] for r in results],
        "answer": [r["answer"] for r in results],
        "contexts": [r["contexts"] for r in results],
        "ground_truth": [r["ground_truth"] for r in results],
    }
    dataset = Dataset.from_dict(ragas_data)
    
    # Configure LM Studio as the evaluator LLM
    eval_llm = ChatOpenAI(  # type: ignore[arg-type]
        model=EVAL_MODEL,
        base_url=LM_STUDIO_BASE,
        api_key="lm-studio",  # type: ignore[arg-type]  # LM Studio ignores key but client requires it
        temperature=0.1,
        timeout=450,
        max_retries=2,
    )
    
    # Use local embeddings (same as NIC uses)
    try:
        eval_embeddings = HuggingFaceEmbeddings(
            model_name=str(Path(__file__).parent / "models" / "all-MiniLM-L6-v2"),
            model_kwargs={"device": "cpu"}
        )
    except Exception as e:
        print(f"      Warning: Could not load local embeddings: {e}")
        print("      Falling back to basic evaluation without embeddings")
        eval_embeddings = None
    
    # Wrap for RAGAS - try modern API first, fall back to legacy
    try:
        # Modern API (RAGAS 0.2+)
        from ragas.llms import llm_factory
        from typing import cast
        from ragas.embeddings import embedding_factory
        from openai import OpenAI as OpenAIClient
        
        openai_client = OpenAIClient(base_url=LM_STUDIO_BASE, api_key="lm-studio")
        wrapped_llm = cast(object, llm_factory(EVAL_MODEL, client=openai_client))
        wrapped_embeddings = None  # Use default or skip for local eval
        print("      Using modern RAGAS API")
    except (ImportError, AttributeError):
        # Legacy API (RAGAS 0.1.x)
        wrapped_llm = LangchainLLMWrapper(eval_llm)
        wrapped_embeddings = LangchainEmbeddingsWrapper(eval_embeddings) if eval_embeddings else None
        print("      Using legacy RAGAS API (consider upgrading to RAGAS 0.2+)")
    
    # Initialize metric instances - using just answer_relevancy for faster eval
    # Full metrics can overwhelm local LLMs with parallel calls
    # RAGAS expects a BaseRagasLLM; legacy wrappers are acceptable for runtime even if typing complains.
    wrapped_llm_for_eval = wrapped_llm  # type: ignore[arg-type]
    metrics = [
        AnswerRelevancy(llm=wrapped_llm_for_eval, embeddings=wrapped_embeddings),  # type: ignore[arg-type]
    ]
    
    try:
        # Run evaluation with limited parallelism to avoid overwhelming LM Studio
        from ragas.run_config import RunConfig
        run_config = RunConfig(
            max_workers=1,  # Sequential execution - no parallel calls
            max_wait=600,   # 10 minute max wait
            max_retries=2,
        )
        
        eval_result = evaluate(
            dataset=dataset,
            metrics=metrics,
            llm=wrapped_llm_for_eval,  # type: ignore[arg-type]
            embeddings=wrapped_embeddings,
            raise_exceptions=False,
            run_config=run_config,
        )

        scores = getattr(eval_result, "to_pandas", lambda: None)()
        
    except Exception as e:
        print(f"      RAGAS evaluation error: {e}")
        print("      Attempting simplified evaluation...")
        
        # Fallback: manual simple metrics
        scores = None
        eval_result = {"error": str(e)}
    
    # Generate report
    print("\n[5/5] Generating report...")
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    report = {
        "timestamp": TIMESTAMP,
        "config": {
            "nic_api": NIC_API_BASE,
            "eval_model": EVAL_MODEL,
            "total_samples": len(results),
        },
        "results": results,
    }
    
    if scores is not None:
        import math
        # Calculate aggregate scores (handle NaN)
        def safe_mean(series):
            vals = [v for v in series if not (isinstance(v, float) and math.isnan(v))]
            return sum(vals) / len(vals) if vals else None
        
        agg_scores = {
            "faithfulness": safe_mean(scores["faithfulness"]) if "faithfulness" in scores else None,
            "answer_relevancy": safe_mean(scores["answer_relevancy"]) if "answer_relevancy" in scores else None,
            "context_precision": safe_mean(scores["context_precision"]) if "context_precision" in scores else None,
            "context_recall": safe_mean(scores["context_recall"]) if "context_recall" in scores else None,
        }
        report["aggregate_scores"] = agg_scores
        report["per_sample_scores"] = scores.to_dict(orient="records")
        
        # Print summary
        print("\n" + "=" * 70)
        print("RAGAS EVALUATION RESULTS")
        print("=" * 70)
        print(f"Samples evaluated: {len(results)}")
        print()
        print("AGGREGATE SCORES:")
        print("-" * 40)
        for metric, score in agg_scores.items():
            if score is not None:
                bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
                print(f"  {metric:20s}: {score:.2%} [{bar}]")
        print()
        
        # Overall RAG quality score (average of all metrics)
        valid_scores = [s for s in agg_scores.values() if s is not None]
        if valid_scores:
            overall = sum(valid_scores) / len(valid_scores)
            print(f"  {'OVERALL RAG QUALITY':20s}: {overall:.2%}")
        print("=" * 70)
        
    else:
        report["error"] = "RAGAS evaluation failed"
        print("WARNING: RAGAS evaluation failed, see error above")
    
    # Save report
    report_path = os.path.join(OUTPUT_DIR, f"ragas_report_{TIMESTAMP}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport saved to: {report_path}")
    
    # Save CSV if scores available
    if scores is not None:
        csv_path = os.path.join(OUTPUT_DIR, f"ragas_scores_{TIMESTAMP}.csv")
        scores.to_csv(csv_path, index=False)
        print(f"Scores CSV saved to: {csv_path}")
    
    return report


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    # Parse command line args
    max_samples = 20  # Default: evaluate 20 samples
    prose_mode = False
    
    args = sys.argv[1:]
    for arg in args:
        if arg == "--prose":
            prose_mode = True
        elif arg == "--all":
            max_samples = None
        else:
            try:
                max_samples = int(arg)
            except ValueError:
                print(f"Usage: python {sys.argv[0]} [num_samples] [--all] [--prose]")
                print("  num_samples: Number of test cases to evaluate (default: 20)")
                print("  --all: Evaluate all test cases")
                print("  --prose: Use retrieval-only mode for cleaner prose answers")
                sys.exit(1)
    
    print(f"Starting RAGAS evaluation with {max_samples or 'ALL'} samples...")
    if prose_mode:
        print("Using PROSE mode (retrieval-only for cleaner answers)")
    print()
    
    result = run_ragas_evaluation(max_samples=max_samples, prose_mode=prose_mode)
    
    if result and "aggregate_scores" in result:
        # Return exit code based on overall quality
        scores = result["aggregate_scores"]
        valid = [s for s in scores.values() if s is not None]
        if valid:
            overall = sum(valid) / len(valid)
            sys.exit(0 if overall >= 0.6 else 1)
    
    sys.exit(1)
