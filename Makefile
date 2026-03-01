.PHONY: help install test test-unit test-integration test-coverage test-watch clean run service deploy format lint

PY := ./tools/py

help:
	@echo "Gunshot Detection System - Make Commands"
	@echo ""
	@echo "  make install     - Install system dependencies and Python packages"
	@echo "  make test        - Run tests"
	@echo "  make clean       - Remove build artifacts"
	@echo "  make run         - Run the detector (development mode)"
	@echo "  make service     - Install and start systemd service"
	@echo "  make deploy      - Deploy to remote Pi (set PI_HOST=user@host)"
	@echo "  make format      - Format code with black"
	@echo "  make lint        - Run ruff linter"

install:
	@echo "Installing dependencies..."
	$(PY) -m pip install -r requirements.txt
	$(PY) -m pip install -e .

test:
	@echo "Running tests..."
	$(PY) -m pytest tests/ -v

test-unit:
	@echo "Running unit tests..."
	$(PY) -m pytest tests/unit/ -v

test-integration:
	@echo "Running integration tests..."
	$(PY) -m pytest tests/integration/ -v

test-coverage:
	@echo "Running tests with coverage..."
	$(PY) -m pytest tests/unit/ tests/integration/ --cov=src --cov-report=html --cov-report=term-missing
	@echo "Coverage report: htmlcov/index.html"

test-watch:
	@echo "Running tests in watch mode..."
	@echo "Note: Requires pytest-watch (pip install pytest-watch)"
	$(PY) -m pytest_watch tests/unit/ -- -v

clean:
	@echo "Cleaning build artifacts..."
	rm -rf build/ dist/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

run:
	@echo "Starting detector..."
	$(PY) main.py --config examples/config.example.yaml

service:
	@echo "Installing systemd service..."
	sudo cp systemd/gunshot-detector.service /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable gunshot-detector
	sudo systemctl start gunshot-detector
	@echo "Service installed and started"
	@echo "Check status: sudo systemctl status gunshot-detector"

deploy:
ifndef PI_HOST
	$(error PI_HOST is not set. Usage: make deploy PI_HOST=pi@192.168.1.50)
endif
	@echo "Deploying to $(PI_HOST)..."
	rsync -avz --exclude=venv --exclude=__pycache__ --exclude=.git \
		. $(PI_HOST):~/gunshot-detection-system/
	ssh $(PI_HOST) 'cd ~/gunshot-detection-system && sudo bash scripts/install.sh'

format:
	@echo "Formatting code with black..."
	$(PY) -m black src/ tests/ scripts/

lint:
	@echo "Running ruff..."
	$(PY) -m ruff check src/ tests/ scripts/
