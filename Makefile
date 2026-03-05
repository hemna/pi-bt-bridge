# Pi BT Bridge Makefile
#
# Convenience targets for development and deployment.
#
# Usage:
#   make help           - Show available targets
#   make deploy         - Deploy to Pi (fast, uses piwheels)
#   make deploy-wheels  - Build wheels + deploy (for slow/missing piwheels)
#
# Configuration:
#   PI_HOST - Target Pi (default: waboring@pi-sugar.hemna.com)
#   PI_DIR  - Project directory on Pi (default: ~/pi-bt-bridge)
#
# Examples:
#   make deploy
#   make deploy PI_HOST=pi@raspberrypi.local
#   PI_HOST=pi@mypi.local make deploy-wheels

# Default configuration
PI_HOST ?= waboring@pi-sugar.hemna.com
PI_DIR ?= ~/pi-bt-bridge

# Detect OS for platform-specific commands
UNAME := $(shell uname)

.PHONY: help wheels deploy deploy-wheels test lint clean run-pi status logs

# Default target
help: ## Show this help message
	@echo "Pi BT Bridge - Available targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Configuration:"
	@echo "  PI_HOST=$(PI_HOST)"
	@echo "  PI_DIR=$(PI_DIR)"
	@echo ""
	@echo "Examples:"
	@echo "  make deploy                          # Deploy using piwheels"
	@echo "  make deploy-wheels                   # Build wheels + deploy"
	@echo "  make deploy PI_HOST=pi@mypi.local    # Deploy to different Pi"

# Build targets
wheels: ## Build ARM wheels in Docker for Raspberry Pi
	@./scripts/build-wheels.sh

# Deployment targets
deploy: ## Deploy project to Pi (uses piwheels for dependencies)
	@./scripts/deploy.sh $(PI_HOST)

deploy-wheels: wheels ## Build ARM wheels, then deploy with local wheels
	@./scripts/deploy.sh $(PI_HOST)

# Remote execution targets
run-pi: ## Run the daemon on Pi (foreground, for testing)
	ssh $(PI_HOST) "cd $(PI_DIR) && .venv/bin/python -m src.main"

status: ## Check daemon status on Pi
	ssh $(PI_HOST) "systemctl status bt-bridge 2>/dev/null || echo 'Service not installed'"

logs: ## Show daemon logs from Pi
	ssh $(PI_HOST) "journalctl -u bt-bridge -f 2>/dev/null || echo 'Service not installed'"

# Local development targets
test: ## Run tests locally
	pytest tests/ -v

test-cov: ## Run tests with coverage report
	pytest tests/ -v --cov=src --cov-report=term-missing

lint: ## Run ruff linter
	ruff check src/ tests/

lint-fix: ## Run ruff linter and fix issues
	ruff check --fix src/ tests/

typecheck: ## Run mypy type checker
	mypy src/

# Cleanup targets
clean: ## Clean build artifacts
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf src/*.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
	@echo "Cleaned build artifacts"

clean-wheels: ## Remove built wheels
	rm -rf dist/wheels/
	@echo "Cleaned wheels"

# Installation targets
install-dev: ## Install development dependencies locally
	pip install -e ".[dev]"

# Pi management targets
pi-shell: ## Open SSH shell to Pi
	ssh $(PI_HOST)

pi-configure: ## Run interactive configuration wizard on Pi
	ssh -t $(PI_HOST) "cd $(PI_DIR) && sudo ./scripts/configure.sh"

pi-config: ## Edit config on Pi (manual)
	ssh -t $(PI_HOST) "sudo nano /etc/bt-bridge/config.json"

pi-restart: ## Restart daemon on Pi
	ssh $(PI_HOST) "sudo systemctl restart bt-bridge"

pi-install-service: ## Install systemd service on Pi
	ssh $(PI_HOST) "cd $(PI_DIR) && sudo cp systemd/bt-bridge.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable bt-bridge"
	@echo "Service installed. Start with: make pi-restart"
