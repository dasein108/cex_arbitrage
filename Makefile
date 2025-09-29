# CEX Arbitrage - Development Tools
# Simple Makefile for code formatting and maintenance

.PHONY: help install format lint clean check-all

# Default target
help:
	@echo "CEX Arbitrage Development Tools"
	@echo ""
	@echo "Available commands:"
	@echo "  make install      - Install production dependencies only"
	@echo "  make install-dev  - Install development dependencies only"
	@echo "  make install-all  - Install all dependencies (prod + dev)"
	@echo "  make format       - Format all Python code (black + isort + autoflake)"
	@echo "  make lint         - Run linting (ruff + mypy)"
	@echo "  make clean        - Remove unused imports and variables"
	@echo "  make check-all    - Run all code quality checks"
	@echo ""

# Install dependencies
install:
	@echo "Installing production dependencies..."
	pip install -r requirements.txt

# Install development dependencies
install-dev:
	@echo "Installing development dependencies..."
	pip install -r requirements-dev.txt

# Install all dependencies (production + development)
install-all:
	@echo "Installing all dependencies..."
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

# Format all code
format:
	@echo "Formatting Python code..."
	@echo "1. Removing unused imports and variables..."
	autoflake --in-place --remove-all-unused-imports --remove-unused-variables --recursive src/ tests/ examples/ || true
	@echo "2. Sorting imports..."
	isort src/ tests/ examples/ || true
	@echo "3. Formatting code with Black..."
	black src/ tests/ examples/ --line-length 120 || true
	@echo "✅ Code formatting complete!"

# Clean unused imports/variables only
clean:
	@echo "Removing unused imports and variables..."
	autoflake --in-place --remove-all-unused-imports --remove-unused-variables --recursive src/ tests/ examples/
	@echo "✅ Cleanup complete!"

# Lint code
lint:
	@echo "Running code quality checks..."
	@echo "1. Ruff linting..."
	ruff check src/ tests/ examples/ || true
	@echo "2. Type checking with mypy..."
	mypy src/ || true
	@echo "✅ Linting complete!"

# Run all checks
check-all: clean format lint
	@echo "✅ All code quality checks complete!"

# Quick format (just black and isort)
quick-format:
	@echo "Quick formatting..."
	isort src/ tests/ examples/
	black src/ tests/ examples/ --line-length 120
	@echo "✅ Quick format complete!"