#!/bin/bash
# Test runner script with different test modes

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "======================================"
echo "  Gunshot Detection System - Tests"
echo "======================================"
echo ""

# Parse arguments
TEST_TYPE="${1:-all}"

case "$TEST_TYPE" in
    unit)
        echo -e "${YELLOW}Running unit tests only...${NC}"
        pytest tests/unit/ -v --tb=short
        ;;
    
    integration)
        echo -e "${YELLOW}Running integration tests...${NC}"
        pytest tests/integration/ -v --tb=short
        ;;
    
    hardware)
        echo -e "${YELLOW}Running hardware tests...${NC}"
        echo -e "${RED}Warning: These tests require real hardware!${NC}"
        pytest tests/hardware/ -v --tb=short
        ;;
    
    fast)
        echo -e "${YELLOW}Running fast tests only (unit)...${NC}"
        pytest tests/unit/ -v --tb=short -x
        ;;
    
    coverage)
        echo -e "${YELLOW}Running tests with coverage...${NC}"
        pytest tests/unit/ tests/integration/ \
            --cov=src \
            --cov-report=html \
            --cov-report=term-missing
        echo ""
        echo -e "${GREEN}Coverage report generated in htmlcov/index.html${NC}"
        ;;
    
    all)
        echo -e "${YELLOW}Running all tests...${NC}"
        pytest tests/unit/ tests/integration/ -v --tb=short
        ;;
    
    watch)
        echo -e "${YELLOW}Running tests in watch mode...${NC}"
        echo "Tests will re-run on file changes (Ctrl+C to exit)"
        pytest-watch tests/unit/ -- -v --tb=short
        ;;
    
    *)
        echo -e "${RED}Unknown test type: $TEST_TYPE${NC}"
        echo ""
        echo "Usage: $0 [unit|integration|hardware|fast|coverage|all|watch]"
        echo ""
        echo "  unit         - Run unit tests only (fast)"
        echo "  integration  - Run integration tests (medium)"
        echo "  hardware     - Run hardware tests (requires real hardware)"
        echo "  fast         - Run unit tests, stop on first failure"
        echo "  coverage     - Run tests with coverage report"
        echo "  all          - Run all tests except hardware (default)"
        echo "  watch        - Run tests in watch mode (re-run on changes)"
        exit 1
        ;;
esac

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
else
    echo -e "${RED}✗ Some tests failed${NC}"
fi

exit $EXIT_CODE
