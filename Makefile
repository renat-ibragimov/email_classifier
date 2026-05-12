APP_NAME = app
APP_NAME_TEST = test_app

.PHONY: clean help build run stop clean-pyc clean-build ruff_check ruff_fix test cov

help:
	@echo "==================== Usage ===================="
	@echo "build              : Build app container"
	@echo "run                : Clean + build + start service"
	@echo "stop               : Stop all containers"
	@echo "clean-pyc          : Remove python artifacts"
	@echo "clean-build        : Remove build artifacts"
	@echo "clean              : Full cleanup including containers"
	@echo "ruff_check         : Run ruff lint check"
	@echo "ruff_fix           : Run ruff lint with auto-fix"
	@echo "test               : Ruff check + run tests. Use make test k=<name> for specific test"
	@echo "cov                : Ruff check + tests with coverage report (fresh build)"

### BUILD AND RUN
build:
	@docker compose build

run: clean build
	@docker compose up

stop:
	@docker compose stop

### CLEANING
clean-pyc:
	find . -name '*.pyc' -exec rm -rf {} +
	find . -name '*.pyo' -exec rm -rf {} +
	find . -name '__pycache__' -exec rm -rf {} +

clean-build:
	rm -rf build/ dist/ *.egg-info

clean: clean-build clean-pyc
	-rm -rf .mypy_cache/ .pytest_cache/ .ruff_cache/ .coverage htmlcov/
	@docker compose down --remove-orphans
	@docker compose -f docker-compose-test.yml down --remove-orphans

### LINTING
ruff_check:
	@docker compose -f docker-compose-test.yml build $(APP_NAME_TEST)
	@docker compose -f docker-compose-test.yml run --rm $(APP_NAME_TEST) ruff check .

ruff_fix:
	@docker compose -f docker-compose-test.yml build $(APP_NAME_TEST)
	@docker compose -f docker-compose-test.yml run --rm -v $(CURDIR):/email_classifier --user $(shell id -u):$(shell id -g) $(APP_NAME_TEST) ruff check --fix .

### TESTING
test:
	@docker compose -f docker-compose-test.yml build $(APP_NAME_TEST)
	-@docker compose -f docker-compose-test.yml run --rm $(APP_NAME_TEST) ruff check .
	@docker compose -f docker-compose-test.yml run --rm $(APP_NAME_TEST) pytest tests -s -vv -k "${k}"

cov: clean-build
	@docker compose -f docker-compose-test.yml build --no-cache $(APP_NAME_TEST)
	-@docker compose -f docker-compose-test.yml run --rm $(APP_NAME_TEST) ruff check .
	@docker compose -f docker-compose-test.yml run --rm $(APP_NAME_TEST) pytest --cov=app --cov-report=term-missing tests/
