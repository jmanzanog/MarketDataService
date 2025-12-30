#!/bin/bash
# -----------------------------------------------------------------------------
# Local Verification Script (Linux/macOS)
# Replicates GitHub Actions CI steps locally
# -----------------------------------------------------------------------------

set -e # Exit on error

# Terminal colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting quality checks...${NC}"

# 1. Check virtual environment
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo -e "${YELLOW}Warning: You don't seem to be in a virtual environment. It is recommended to activate one.${NC}"
fi

# 2. Install required tools if missing
echo -e "\n${YELLOW}[1/7] Installing/Updating quality tools...${NC}"
pip install -q ruff bandit pip-audit mypy types-requests pytest-cov

# 3. Dependency consistency
echo -e "\n${YELLOW}[2/7] Checking dependency consistency...${NC}"
pip check

# 4. Dependency Audit (Security)
echo -e "\n${YELLOW}[3/7] Auditing dependencies with pip-audit...${NC}"
pip-audit

# 5. Code Security (Bandit)
echo -e "\n${YELLOW}[4/7] Analyzing code security with Bandit...${NC}"
bandit -r src/ -ll

# 6. Formatting and Linting (Ruff)
echo -e "\n${YELLOW}[5/7] Verifying formatting with Ruff...${NC}"
ruff format --check src/ tests/

echo -e "\n${YELLOW}[6/7] Running Linting with Ruff...${NC}"
ruff check src/ tests/

# 7. Typing (Mypy)
echo -e "\n${YELLOW}[7/7] Verifying types with Mypy...${NC}"
mypy src/ --ignore-missing-imports --no-error-summary || echo -e "${RED}Mypy found type issues, but continuing...${NC}"

# 8. Tests
echo -e "\n${YELLOW}Running unit and internal integration tests...${NC}"
pytest tests/ -v --cov=src --cov-report=term-missing --ignore=tests/test_container_integration.py

echo -e "\n${GREEN}All mandatory CI checks passed successfully!${NC}"
echo -e "${YELLOW}Note: Container (Docker) tests were skipped for speed.${NC}"
echo -e "${YELLOW}To run them manually: pytest tests/test_container_integration.py -m container${NC}"
