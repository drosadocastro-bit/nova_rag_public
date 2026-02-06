#!/usr/bin/env python3
"""
NIC RAGAS Evaluation Harness
============================
Evaluates NIC's RAG quality using RAGAS metrics:
- Faithfulness: Is the answer grounded in retrieved context?
- Answer Relevancy: Does the answer address the question?
- Context Precision: Are retrieved docs relevant?
- Context Recall: Does context contain needed info?

Uses Ollama as the evaluator LLM (no external API needed).
"""

from __future__ import annotations

import json
import os
import sys
import time
import math
import requests
import re
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

# LangChain for local Ollama integration
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_ollama import ChatOllama  # Native Ollama client with num_ctx/format support

# =============================================================================
# CONFIGURATION
# =============================================================================
NIC_API_BASE = "http://127.0.0.1:5000/api"
OLLAMA_BASE = "http://127.0.0.1:11434/v1"

# RAGAS needs an LLM for evaluation - using registered Ollama models
# Use Llama 3.2 8B as evaluator (current production model)
EVAL_MODEL = "llama3.2-8b:latest"

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

def check_ollama_ready() -> bool:
    """Check if Ollama is running."""
    try:
        r = requests.get(f"{OLLAMA_BASE}/models", timeout=5)
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

def _split_atomic_lines(text: str) -> str:
    """Split text into one atomic statement per line (conservative)."""
    if not text:
        return ""
    text = text.replace(" | ", "\n")
    parts = [p.strip() for p in re.split(r"[;\n]+", text) if p.strip()]
    if len(parts) <= 1:
        return text.strip()
    return "\n".join(parts)


def extract_answer_text(answer: Any) -> str:
    """Extract text from answer (handles string or dict) with atomic lines."""
    if isinstance(answer, str):
        return _split_atomic_lines(answer)
    if isinstance(answer, dict):
        # Handle refusal schema (single atomic line)
        if answer.get("response_type") == "refusal":
            return f"[REFUSAL] {answer.get('message', 'Request declined')}"
        # Handle structured responses as atomic lines
        lines = []
        if answer.get("risks"):
            for risk in answer.get("risks", []):
                lines.append(f"WARNING: {risk}")
        if answer.get("steps"):
            for step in answer.get("steps", []):
                lines.append(f"STEP: {step}")
        if answer.get("verification"):
            for item in answer.get("verification", []):
                lines.append(f"VERIFY: {item}")
        if lines:
            return "\n".join(lines)
        # Fallback
        return json.dumps(answer)
    return _split_atomic_lines(str(answer))


def extract_diagnostic_confidence(response: dict) -> Optional[float]:
    """Extract diagnostic_confidence from NIC response if present."""
    if not isinstance(response, dict):
        return None
    if "diagnostic_confidence" in response:
        value = response.get("diagnostic_confidence")
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    answer = response.get("answer")
    if isinstance(answer, dict) and "diagnostic_confidence" in answer:
        value = answer.get("diagnostic_confidence")
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def infer_domain(question: str) -> str:
    """Heuristic domain inference for reporting (defaults to vehicle)."""
    q = question.lower()
    domain_keywords = {
        "radar": ["radar", "nexrad", "asr", "beacon", "doppler"],
        "nuclear": ["reactor", "nuclear", "criticality"],
        "hvac": ["hvac", "compressor", "refrigerant", "thermostat"],
        "forklift": ["forklift", "mast", "lift"],
        "medical": ["mri", "patient", "scan", "contrast"],
        "electronics": ["gpio", "microcontroller", "i2c", "voltage", "resistor"],
    }
    for domain, keywords in domain_keywords.items():
        if any(k in q for k in keywords):
            return domain
    return "vehicle"

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

def safe_mean(values: list[Any]) -> Optional[float]:
    vals: list[float] = []
    for v in values:
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if math.isnan(fv):
            continue
        vals.append(fv)
    return sum(vals) / len(vals) if vals else None


def build_embeddings() -> Optional[LangchainEmbeddingsWrapper]:
    """Build HuggingFace embeddings for retrieval metrics (offline-friendly)."""
    embed_model = os.environ.get("RAGAS_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    try:
        embeddings = HuggingFaceEmbeddings(
            model_name=embed_model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        return LangchainEmbeddingsWrapper(embeddings)
    except Exception as exc:
        print(f"      [WARN] Embeddings unavailable ({embed_model}): {exc}")
        return None


def aggregate_by_key(per_sample: list[dict], key: str, metric_keys: list[str]) -> dict:
    grouped: dict[str, list[dict]] = {}
    for row in per_sample:
        group = row.get(key, "unknown") or "unknown"
        grouped.setdefault(group, []).append(row)
    aggregates = {}
    for group, rows in grouped.items():
        aggregates[group] = {
            metric: safe_mean([r.get(metric) for r in rows if r.get(metric) is not None])
            for metric in metric_keys
        }
        aggregates[group]["count"] = len(rows)
    return aggregates


def compute_overclaim_flags(per_sample: list[dict], conf_threshold: float = 0.7, faith_threshold: float = 0.5) -> list[dict]:
    flags = []
    for row in per_sample:
        confidence = row.get("diagnostic_confidence")
        faithfulness = row.get("faithfulness")
        if confidence is None or faithfulness is None:
            continue
        if confidence >= conf_threshold and faithfulness <= faith_threshold:
            flags.append({
                "id": row.get("id"),
                "category": row.get("category"),
                "domain": row.get("domain"),
                "diagnostic_confidence": confidence,
                "faithfulness": faithfulness,
            })
    return flags


def compute_confidence_correlation(per_sample: list[dict]) -> Optional[float]:
    pairs = []
    for row in per_sample:
        confidence = row.get("diagnostic_confidence")
        faithfulness = row.get("faithfulness")
        if confidence is None or faithfulness is None:
            continue
        try:
            pairs.append((float(confidence), float(faithfulness)))
        except (TypeError, ValueError):
            continue
    if len(pairs) < 2:
        return None
    xs, ys = zip(*pairs)
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def run_single_evaluation(
    max_samples: Optional[int],
    prose_mode: bool,
    mode_label: str,
    save_outputs: bool = True,
) -> Optional[dict]:
    """Run a single RAGAS evaluation mode and return a report dict."""
    print("=" * 70)
    print("NIC RAGAS EVALUATION")
    print("=" * 70)
    print(f"Timestamp: {TIMESTAMP}")
    print(f"Mode: {mode_label}")
    print()

    print("[1/5] Checking prerequisites...")
    if not check_server_ready():
        print("ERROR: NIC Flask server not running at", NIC_API_BASE)
        print("       Start it with: .\\start_fastapi_qwen4b.ps1")
        return None
    print("      NIC server: OK")

    if not check_ollama_ready():
        print("ERROR: Ollama not running at", OLLAMA_BASE)
        print("       Start Ollama and pull a model (e.g., llama3.2:8b)")
        return None
    print("      Ollama: OK")

    print("\n[2/5] Loading test dataset...")
    test_cases = load_test_dataset()
    print(f"      Loaded {len(test_cases)} test cases")

    if max_samples and len(test_cases) > max_samples:
        test_cases = test_cases[:max_samples]
        print(f"      Using first {max_samples} samples")

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
        diagnostic_confidence = extract_diagnostic_confidence(response)
        domain = infer_domain(case["question"])

        results.append({
            "question": case["question"],
            "answer": answer_text,
            "contexts": contexts,
            "ground_truth": case["ground_truth"],
            "id": case["id"],
            "category": case["category"],
            "domain": domain,
            "diagnostic_confidence": diagnostic_confidence,
        })

        time.sleep(0.5)

    print(f"      Collected {len(results)} valid responses")
    if len(results) == 0:
        print("ERROR: No valid responses collected")
        return None

    print("\n[4/5] Running RAGAS evaluation...")
    print("      This may take several minutes (LLM-based evaluation)...")

    ragas_data = {
        "question": [r["question"] for r in results],
        "answer": [r["answer"] for r in results],
        "contexts": [r["contexts"] for r in results],
        "ground_truth": [r["ground_truth"] for r in results],
    }
    dataset = Dataset.from_dict(ragas_data)

    os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "ollama")
    os.environ["OPENAI_BASE_URL"] = os.environ.get("OPENAI_BASE_URL", OLLAMA_BASE)
    os.environ["OLLAMA_DEBUG"] = "1"

    eval_llm = ChatOllama(
        model=EVAL_MODEL,
        base_url="http://127.0.0.1:11434",
        temperature=0.0,
        num_ctx=16384,
        format="json",
        num_predict=2048,
    )

    wrapped_llm_for_eval = LangchainLLMWrapper(eval_llm)
    wrapped_embeddings = build_embeddings()

    if wrapped_embeddings:
        print("      Running LLM + embedding evaluation (retrieval metrics enabled)")
    else:
        print("      Running LLM-only evaluation (no embeddings)")
    print("      Config: num_ctx=16384, format=json, temperature=0.0, num_predict=2048")
    print(f"      Using ChatOllama ({EVAL_MODEL} via Ollama)")

    metrics: list[Any] = [
        Faithfulness(llm=wrapped_llm_for_eval),  # type: ignore[arg-type]
    ]
    if wrapped_embeddings:
        metrics.extend([
            ContextPrecision(),
            ContextRecall(),
        ])

    scores = None
    try:
        from ragas.run_config import RunConfig
        run_config = RunConfig(
            max_workers=1,
            max_wait=900,
            max_retries=4,
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
        eval_result = {"error": str(e)}

    print("\n[5/5] Generating report...")

    report = {
        "timestamp": TIMESTAMP,
        "mode": mode_label,
        "config": {
            "nic_api": NIC_API_BASE,
            "eval_model": EVAL_MODEL,
            "total_samples": len(results),
            "embeddings_enabled": wrapped_embeddings is not None,
        },
        "results": results,
    }

    if scores is not None:
        metric_keys = [k for k in scores.columns if k in {"faithfulness", "context_precision", "context_recall", "answer_relevancy"}]
        agg_scores = {
            metric: safe_mean([v for v in scores[metric]])
            for metric in metric_keys
        }
        report["aggregate_scores"] = agg_scores

        per_sample_scores = []
        for idx, row in scores.iterrows():
            sample = results[idx]
            record = {
                "id": sample.get("id"),
                "category": sample.get("category"),
                "domain": sample.get("domain"),
                "diagnostic_confidence": sample.get("diagnostic_confidence"),
            }
            for metric in metric_keys:
                record[metric] = row.get(metric)
            per_sample_scores.append(record)

        report["per_sample_scores"] = per_sample_scores
        report["aggregate_by_category"] = aggregate_by_key(per_sample_scores, "category", metric_keys)
        report["aggregate_by_domain"] = aggregate_by_key(per_sample_scores, "domain", metric_keys)
        report["overclaim_flags"] = compute_overclaim_flags(per_sample_scores)
        report["confidence_faithfulness_correlation"] = compute_confidence_correlation(per_sample_scores)

        valid_scores = [s for s in agg_scores.values() if s is not None]
        if valid_scores:
            report["overall_score"] = sum(valid_scores) / len(valid_scores)

        # Identify worst 20% samples
        scored = []
        for item in per_sample_scores:
            vals = [item.get(k) for k in metric_keys if item.get(k) is not None]
            if vals:
                scored.append({
                    "id": item.get("id"),
                    "category": item.get("category"),
                    "domain": item.get("domain"),
                    "score": sum(vals) / len(vals),
                })
        scored.sort(key=lambda x: x["score"])
        cutoff = max(1, int(len(scored) * 0.2)) if scored else 0
        report["worst_samples"] = scored[:cutoff]

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
        if valid_scores:
            overall = sum(valid_scores) / len(valid_scores)
            print()
            print(f"  {'OVERALL RAG QUALITY':20s}: {overall:.2%}")
        print("=" * 70)

    else:
        report["error"] = "RAGAS evaluation failed"
        print("WARNING: RAGAS evaluation failed, see error above")

    if save_outputs:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        report_path = os.path.join(OUTPUT_DIR, f"ragas_report_{TIMESTAMP}.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\nReport saved to: {report_path}")

        if scores is not None:
            csv_path = os.path.join(OUTPUT_DIR, f"ragas_scores_{TIMESTAMP}.csv")
            scores.to_csv(csv_path, index=False)
            print(f"Scores CSV saved to: {csv_path}")

    return report


def run_dual_mode_evaluation(max_samples: Optional[int]) -> Optional[dict]:
    full_report = run_single_evaluation(
        max_samples,
        prose_mode=False,
        mode_label="FULL (LLM-generated)",
        save_outputs=False,
    )
    if not full_report:
        return None
    prose_report = run_single_evaluation(
        max_samples,
        prose_mode=True,
        mode_label="PROSE (retrieval-only)",
        save_outputs=False,
    )
    if not prose_report:
        return None

    full_scores = full_report.get("aggregate_scores", {})
    prose_scores = prose_report.get("aggregate_scores", {})
    delta_scores = {}
    for metric in set(full_scores.keys()) | set(prose_scores.keys()):
        if full_scores.get(metric) is not None and prose_scores.get(metric) is not None:
            delta_scores[metric] = prose_scores[metric] - full_scores[metric]
        else:
            delta_scores[metric] = None

    report = {
        "timestamp": TIMESTAMP,
        "config": {
            "nic_api": NIC_API_BASE,
            "eval_model": EVAL_MODEL,
            "total_samples": full_report.get("config", {}).get("total_samples"),
            "embeddings_enabled": full_report.get("config", {}).get("embeddings_enabled", False),
        },
        "modes": {
            "full": full_report,
            "prose": prose_report,
        },
        "delta_scores": delta_scores,
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report_path = os.path.join(OUTPUT_DIR, f"ragas_report_{TIMESTAMP}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport saved to: {report_path}")

    return report


def run_ragas_evaluation(max_samples: Optional[int] = 20, prose_mode: bool = False) -> Optional[dict]:
    """Backward-compatible single-mode entrypoint."""
    mode_label = "PROSE (retrieval-only)" if prose_mode else "FULL (LLM-generated)"
    return run_single_evaluation(max_samples, prose_mode=prose_mode, mode_label=mode_label)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    # Parse command line args
    max_samples = 20  # Default: evaluate 20 samples
    mode = "dual"
    
    args = sys.argv[1:]
    for arg in args:
        if arg in {"--prose", "--prose-only"}:
            mode = "prose"
        elif arg == "--full-only":
            mode = "full"
        elif arg == "--dual":
            mode = "dual"
        elif arg == "--all":
            max_samples = None
        else:
            try:
                max_samples = int(arg)
            except ValueError:
                print(f"Usage: python {sys.argv[0]} [num_samples] [--all] [--dual|--full-only|--prose-only]")
                print("  num_samples: Number of test cases to evaluate (default: 20)")
                print("  --all: Evaluate all test cases")
                print("  --dual: Run FULL and PROSE modes (default)")
                print("  --full-only: Run FULL mode only")
                print("  --prose-only: Run PROSE mode only")
                print("  --prose: Backward-compatible alias for --prose-only")
                sys.exit(1)
    
    print(f"Starting RAGAS evaluation with {max_samples or 'ALL'} samples...")
    if mode == "dual":
        print("Using DUAL mode (FULL + PROSE)")
    elif mode == "prose":
        print("Using PROSE mode (retrieval-only for cleaner answers)")
    else:
        print("Using FULL mode (LLM-generated answers)")
    print()

    if mode == "dual":
        result = run_dual_mode_evaluation(max_samples=max_samples)
    elif mode == "prose":
        result = run_ragas_evaluation(max_samples=max_samples, prose_mode=True)
    else:
        result = run_ragas_evaluation(max_samples=max_samples, prose_mode=False)
    
    if not result:
        sys.exit(1)

    # Return exit code based on overall quality
    if mode == "dual":
        scores = result.get("modes", {}).get("full", {}).get("aggregate_scores", {})
    else:
        scores = result.get("aggregate_scores", {})

    valid = [s for s in scores.values() if s is not None]
    if valid:
        overall = sum(valid) / len(valid)
        sys.exit(0 if overall >= 0.6 else 1)

    sys.exit(1)
