.PHONY: help install test clean run deploy

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
	@echo "  make lint        - Run flake8 linter"

install:
	@echo "Installing dependencies..."
	pip install -r requirements.txt
	pip install -e .

test:
	@echo "Running tests..."
	pytest tests/ -v

test-unit:
	@echo "Running unit tests..."
	pytest tests/unit/ -v

test-integration:
	@echo "Running integration tests..."
	pytest tests/integration/ -v

test-coverage:
	@echo "Running tests with coverage..."
	pytest tests/unit/ tests/integration/ --cov=src --cov-report=html --cov-report=term-missing
	@echo "Coverage report: htmlcov/index.html"

test-watch:
	@echo "Running tests in watch mode..."
	pytest-watch tests/unit/ -- -v

clean:
	@echo "Cleaning build artifacts..."
	rm -rf build/ dist/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

run:
	@echo "Starting detector..."
	python src/main.py --config config.yaml

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
	ssh $(PI_HOST) 'cd ~/gunshot-detection-system && sudo bash install.sh'

format:
	@echo "Formatting code with black..."
	black src/

lint:
	@echo "Running flake8..."
	flake8 src/ --max-line-length=100
