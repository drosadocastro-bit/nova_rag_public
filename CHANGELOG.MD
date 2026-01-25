# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Version Policy

- **MAJOR**: Breaking API changes or safety-critical architecture changes
- **MINOR**: New features, new domains, significant enhancements
- **PATCH**: Bug fixes, performance improvements, documentation

## [Unreleased]

### Added
- CHANGELOG.md for version tracking
- GitHub issue and PR templates
- Pre-commit hooks configuration
- Security policy (SECURITY.md)
- Development dependencies in requirements-dev.txt

## [0.3.5] - 2026-01-25

### Added
- Phase 3.5: Neural advisory layer with fine-tuned embeddings
- Domain isolation milestone achieving 0% cross-contamination
- Anomaly detection architecture design
- Training data generator (4,010 domain pairs)
- Fine-tuning script for embeddings (267 lines optimized)

### Changed
- Domain-aware pre-filtering with 80%+ accuracy from target domain
- Enhanced vocabulary-based detection for 9 domains

### Fixed
- Cross-contamination reduced from 19.2% to 0% across all test cases

### Upgrade Notes
- No breaking changes from 0.3.0
- Existing indexes are compatible
- Set `NOVA_DOMAIN_BOOST_FACTOR=0.25` for optimal domain isolation

## [0.3.0] - 2026-01-20

### Added
- Phase 3: Scalable indexing and real-world corpus integration
- Incremental indexing system with zero-downtime updates
- Hot-reload API endpoint for live corpus updates
- 6,610 chunks indexed across 9 domains
- BM25 disk caching with automatic invalidation

### Changed
- Indexing performance: 3.3s per manual (34% faster than 5s target)

### Upgrade Notes
- Rebuild index with `python ingest_multi_domain.py` for new chunking
- BM25 cache will auto-rebuild on first query

## [0.2.5] - 2026-01-15

### Added
- Phase 2.5: Enhanced multi-domain retrieval
- Domain intent classifier with confidence scoring
- Evidence chain tracking for audit compliance
- HTML document support with BeautifulSoup4
- Domain caps for balanced results

### Fixed
- Cross-contamination reduced from 19.2% to 0%

### Upgrade Notes
- New environment variables: `NOVA_DOMAIN_BOOST_FACTOR`, `NOVA_DOMAIN_PREFETCH_MULTIPLIER`
- Optional: Configure domain caps in `core/retrieval/retrieval_engine.py`

## [0.2.0] - 2026-01-10

### Added
- Phase 2: Safety-hardened retrieval pipeline
- Multi-layer safety controls
- Confidence gating, citation audit, risk assessment
- Evidence logging for audit trail

### Upgrade Notes
- New dependencies: Add safety modules to imports
- Confidence thresholds configurable via environment variables

## [0.1.0] - 2026-01-05

### Added
- Phase 1: MVP with basic retrieval + single LLM pass
- Offline/air-gapped operation
- FAISS + BM25 hybrid retrieval
- Local LLM via Ollama

### Upgrade Notes
- Initial release - fresh installation required
- Requires: Python 3.10+, Ollama with compatible model
- Run `pip install -r requirements.txt` and `python ingest_multi_domain.py`