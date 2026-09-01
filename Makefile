APP_NAME = app
APP_NAME_TEST = test_app

.PHONY: clean help build run stop clean-pyc clean-build clean-cache clean-artifacts ruff_check ruff_fix ruff_format test cov

help:
	@echo "==================== Usage ===================="
	@echo "build              : Build app container"
	@echo "run                : Clean + build + start service"
	@echo "stop               : Stop all containers"
	@echo "clean-pyc          : Remove python artifacts"
	@echo "clean-build        : Remove build artifacts"
	@echo "clean-cache        : Remove tool caches (.ruff_cache, .pytest_cache, .coverage, ...)"
	@echo "clean-artifacts    : clean-build + clean-pyc + clean-cache (runs before ruff/test)"
	@echo "clean              : Full cleanup including containers"
	@echo "ruff_check         : Clean + run ruff lint check"
	@echo "ruff_fix           : Clean + run ruff lint with auto-fix"
	@echo "ruff_format        : Clean + reformat the code with ruff format (manual only, not in CI)"
	@echo "test               : Clean + ruff check + run tests. Use make test k=<name> for specific test"
	@echo "cov                : Clean + ruff check + tests with coverage report (fresh build)"

### BUILD AND RUN
build:
	@docker compose build

run: clean build
	@docker compose up

stop:
	@docker compose stop

### CLEANING
# Artifacts written by a container running as root are not removable by the host
# user: the owning directory has no write bit for them, so unlink fails. Each
# clean target therefore retries as root in a throwaway container. The image is
# the one the project's Dockerfiles already build on, so no extra pull.
ROOT_RM = docker run --rm -v $(CURDIR):/workdir -w /workdir python:3.12-slim

clean-pyc:
	@find . -name '*.pyc' -delete 2>/dev/null || $(ROOT_RM) find . -name *.pyc -delete
	@find . -name '*.pyo' -delete 2>/dev/null || $(ROOT_RM) find . -name *.pyo -delete
	@find . -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null \
		|| $(ROOT_RM) find . -name __pycache__ -type d -prune -exec rm -rf {} +

clean-build:
	@rm -rf build/ dist/ *.egg-info 2>/dev/null \
		|| $(ROOT_RM) sh -c "rm -rf build dist *.egg-info"

clean-cache:
	@rm -rf .mypy_cache/ .pytest_cache/ .ruff_cache/ .coverage .coverage.* htmlcov/ 2>/dev/null \
		|| $(ROOT_RM) sh -c "rm -rf .mypy_cache .pytest_cache .ruff_cache .coverage .coverage.* htmlcov"

clean-artifacts: clean-build clean-pyc clean-cache

clean: clean-artifacts
	@docker compose down --remove-orphans
	@docker compose -f docker-compose-test.yml down --remove-orphans

### LINTING
ruff_check: clean-artifacts
	@docker compose -f docker-compose-test.yml build $(APP_NAME_TEST)
	@docker compose -f docker-compose-test.yml run --rm $(APP_NAME_TEST) ruff check .

# Run by hand when you want it; nothing else (CI included) reformats the code.
RUFF_WRITE = docker compose -f docker-compose-test.yml run --rm -v $(CURDIR):/email_classifier --user $(shell id -u):$(shell id -g) $(APP_NAME_TEST)

ruff_fix: clean-artifacts
	@docker compose -f docker-compose-test.yml build $(APP_NAME_TEST)
	@$(RUFF_WRITE) ruff check --fix .

ruff_format: clean-artifacts
	@docker compose -f docker-compose-test.yml build $(APP_NAME_TEST)
	@$(RUFF_WRITE) ruff format .

### TESTING
test: clean-artifacts
	@docker compose -f docker-compose-test.yml build $(APP_NAME_TEST)
	-@docker compose -f docker-compose-test.yml run --rm $(APP_NAME_TEST) ruff check .
	@docker compose -f docker-compose-test.yml run --rm $(APP_NAME_TEST) pytest tests -s -vv -k "${k}"

cov: clean-artifacts
	@docker compose -f docker-compose-test.yml build --no-cache $(APP_NAME_TEST)
	-@docker compose -f docker-compose-test.yml run --rm $(APP_NAME_TEST) ruff check .
	@docker compose -f docker-compose-test.yml run --rm $(APP_NAME_TEST) pytest --cov=app --cov=bot --cov-report=term-missing tests/
