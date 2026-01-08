# Documentation Index

A curated table of contents for the NIC documentation set. Start here to quickly find architecture, safety, evaluation, deployment, and governance materials.

## Overview
- [README](../README.md) — Safety-critical one-pager, repo structure, quick start
- [Quickstart](../QUICKSTART.md) — Detailed environment setup and tips
- [Ollama Modelfiles](../ollama/README.md) — Local model configuration and usage

## User Documentation
- [User Guide](USER_GUIDE.md) — Getting started, example queries, best practices
- [FAQ](FAQ.md) — Frequently asked questions
- [Troubleshooting Guide](TROUBLESHOOTING.md) — Common issues and solutions

## API Documentation
- [API Reference](api/API_REFERENCE.md) — Complete API documentation with examples

## Architecture
- [System Architecture](architecture/SYSTEM_ARCHITECTURE.md) — Components and responsibilities
- [Data Flow](architecture/DATA_FLOW.md) — Request routing, retrieval, and audit flow
- [Threat Model](architecture/THREAT_MODEL.md) — Assumptions, assets, risks, mitigations
- [BM25 Caching](architecture/BM25_CACHING.md) — Cache lifecycle, invalidation, and troubleshooting
- Diagram: [Architecture Diagram](architecture/diagram.svg)

## Safety
- [Safety Model](safety/SAFETY_MODEL.md) — Hallucination defenses and controls
- [Safety-Critical Context](safety/SAFETY_CRITICAL_CONTEXT.md) — Operating context and failure philosophy
- [Human-on-the-Loop](safety/HUMAN_ON_THE_LOOP.md) — Operator authority and procedures
- [Hallucination Defense](safety/HALLUCINATION_DEFENSE.md) — Gating, auditing, fallback

## Evaluation
- [Evaluation Summary](evaluation/EVALUATION_SUMMARY.md) — Coverage, adversarial tests, RAGAS scores
- [Adversarial Tests](evaluation/ADVERSARIAL_TESTS.md) — Attack scenarios and defenses
- [Stress Tests](evaluation/STRESS_TESTS.md) — Load, edge cases, robustness
- [RAGAS Results](evaluation/RAGAS_RESULTS.md) — Metric details from recent runs
- [Performance Benchmarks](evaluation/PERFORMANCE_BENCHMARKS.md) — Latency, throughput, memory metrics
- [Load Test Results](evaluation/LOAD_TEST_RESULTS.md) — Concurrent user testing and scaling recommendations

## Deployment
- [Air-Gapped Deployment](deployment/AIR_GAPPED_DEPLOYMENT.md) — Offline setup and policies
- [Offline Model Setup](deployment/OFFLINE_MODEL_SETUP.md) — Model acquisition and validation
- [Native Engine Setup](deployment/NATIVE_ENGINE_SETUP.md) — Local LLM runtime configuration
- [Configuration Guide](deployment/CONFIGURATION.md) — Environment variables and configuration examples

## Governance (root)
- [NIC Response Policy](../governance/nic_response_policy.json)
- [NIC Decision Flow](../governance/nic_decision_flow.yaml)
- [QA Dataset](../governance/nic_qa_dataset.json)
- Test Suites:
  - [Adversarial Tests (MD)](../governance/test_suites/nic_adversarial_tests.md)
  - [Hallucination Test Suite (JSON)](../governance/test_suites/nic_hallucination_test_suite.json)
  - [Explicit Hallucination Defense (JSON)](../governance/test_suites/explicit_hallucination_defense.json)

## Annex
- This folder contains internal notes (logs, templates, reviews) maintained for reproducibility and traceability. See [Annex README](annex/README.md) for guidance.
