# NIC - Offline RAG System Makefile
# Common development commands for ease of use

.PHONY: help install test lint format docker-build docker-up docker-down clean coverage security

# Default target
help:
	@echo "NIC Development Commands:"
	@echo ""
	@echo "  make install        - Install dependencies"
	@echo "  make test           - Run unit tests"
	@echo "  make test-all       - Run all tests (unit + integration)"
	@echo "  make coverage       - Run tests with coverage report"
	@echo "  make lint           - Lint code with ruff"
	@echo "  make format         - Format code with ruff"
	@echo "  make security       - Run security scans"
	@echo "  make docker-build   - Build Docker images"
	@echo "  make docker-up      - Start Docker services"
	@echo "  make docker-down    - Stop Docker services"
	@echo "  make clean          - Clean temporary files"
	@echo "  make dev-setup      - Complete development setup"
	@echo ""

# Installation
install:
	@echo "Installing dependencies..."
	pip install -r requirements.txt

# Testing
test:
	@echo "Running unit tests..."
	pytest tests/unit/ -v

test-all:
	@echo "Running all tests..."
	pytest tests/ -v

coverage:
	@echo "Running tests with coverage..."
	pytest --cov=. --cov-report=html --cov-report=term
	@echo "Coverage report generated in htmlcov/index.html"

# Linting and formatting
lint:
	@echo "Linting code..."
	ruff check --select=E9,F63,F7,F82 .
	ruff check .

format:
	@echo "Formatting code..."
	ruff format .

# Security
security:
	@echo "Running security scans..."
	@echo "1. Bandit code analysis..."
	bandit -r . -ll || true
	@echo ""
	@echo "2. Dependency audit..."
	pip-audit --requirement requirements.txt || true

# Docker operations
docker-build:
	@echo "Building Docker images..."
	docker-compose build

docker-up:
	@echo "Starting Docker services..."
	docker-compose up -d
	@echo "Services started. Access NIC at http://localhost:5000"
	@echo "Pull models: docker exec -it nic-ollama ollama pull llama3.2:3b"

docker-down:
	@echo "Stopping Docker services..."
	docker-compose down

docker-logs:
	@echo "Showing Docker logs..."
	docker-compose logs -f

# Cleanup
clean:
	@echo "Cleaning temporary files..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	rm -rf htmlcov/ .pytest_cache/ .ruff_cache/
	@echo "Cleanup complete"

# Development setup
dev-setup: install
	@echo "Setting up development environment..."
	@echo "1. Installing development dependencies..."
	pip install ruff bandit pip-audit pytest pytest-cov pytest-mock
	@echo ""
	@echo "2. Creating necessary directories..."
	mkdir -p vector_db data models sessions
	@echo ""
	@echo "3. Copying environment example..."
	[ ! -f .env ] && cp .env.example .env || true
	@echo ""
	@echo "✓ Development setup complete!"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Edit .env with your configuration"
	@echo "  2. Install Ollama: https://ollama.com"
	@echo "  3. Pull models: ollama pull llama3.2:3b"
	@echo "  4. Run tests: make test"
	@echo "  5. Start app: python nova_flask_app.py"

# Quick validation
validate:
	@echo "Running quick validation..."
	@echo "1. Python syntax check..."
	python -m py_compile nova_flask_app.py backend.py cache_utils.py
	@echo "2. Import check..."
	python -c "import backend; import cache_utils; print('✓ Imports OK')"
	@echo "3. Running unit tests..."
	pytest tests/unit/ -v --tb=short
	@echo ""
	@echo "✓ Validation complete!"

# CI simulation
ci-local:
	@echo "Simulating CI pipeline locally..."
	@make lint
	@make test
	@make security
	@echo ""
	@echo "✓ CI simulation complete!"
