PYTHON ?= python3
PIP ?= pip3
PLAYWRIGHT_BROWSER ?= chromium
PYTEST ?= $(PYTHON) -m pytest
ENV_FILE ?= config/demo.env
CI_FLAG := $(shell echo "$(CI)" | tr A-Z a-z)
PYTHONPATH := $(if $(PYTHONPATH),$(PYTHONPATH):,).
export PYTHONPATH

ifdef USE_FAKE_OLLAMA
LLM_USE_FAKE := $(USE_FAKE_OLLAMA)
else
LLM_USE_FAKE := $(if $(filter true yes 1,$(CI_FLAG)),1,0)
endif

ifeq ($(strip $(LLM_USE_FAKE)),0)
PYTEST_DISTRIBUTION ?=
else
PYTEST_DISTRIBUTION ?= -n auto
endif
UI_ENV_FILE := $(or $(DEMO_ENV_FILE),$(ENV_FILE))

install:
	$(PYTHON) -m pip install -r requirements.txt
	npm install
	$(PYTHON) -m playwright install --with-deps $(PLAYWRIGHT_BROWSER)

compose\:up:
	docker compose up -d postgres demo-backend demo-frontend

compose\:down:
	docker compose down

lint:
	$(PYTHON) -m pytest --collect-only

check\:health:
	$(PYTHON) scripts/health_check.py --env-file config/demo.env

promptfoo:
	npm run promptfoo:test

promptfoo-watch:
	npm run promptfoo:test:watch

DemoSetup: demo\:setup

demo\:setup:
	bash scripts/bootstrap_demo_app.sh

DemoSeed: demo\:seed

demo\:seed:
	docker compose up -d postgres demo-backend demo-frontend
	$(PYTHON) scripts/health_check.py --env-file config/demo.env
	sleep 3
	$(PYTHON) scripts/seed_demo_data.py --env-file config/demo.env

DemoReset: demo\:reset

demo\:reset:
	bash scripts/bootstrap_demo_app.sh --reset
	$(PYTHON) scripts/seed_demo_data.py --env-file config/demo.env

PlaywrightUI: test\:ui

test\:api:
	@bash -c 'set -euo pipefail; \
		docker compose up -d postgres demo-backend demo-frontend; \
		trap "docker compose down" EXIT; \
		$(PYTHON) scripts/health_check.py --env-file "$(ENV_FILE)"; \
		sleep 3; \
		$(PYTHON) scripts/seed_demo_data.py --env-file "$(ENV_FILE)"; \
		PYTHONPATH=. $(PYTEST) -m api'

test\:ui:
	@bash -c 'set -euo pipefail; \
		docker compose up -d postgres demo-backend demo-frontend; \
		trap "docker compose down" EXIT; \
		$(PYTHON) scripts/health_check.py --env-file "$(ENV_FILE)"; \
		sleep 3; \
		$(PYTHON) scripts/seed_demo_data.py --env-file "$(ENV_FILE)"; \
		PYTHONPATH=. $(PYTEST) -m ui --headed'

test\:llm:
	@bash -c 'set -euo pipefail; \
		docker compose up -d postgres demo-backend demo-frontend; \
		trap "docker compose down" EXIT; \
		$(PYTHON) scripts/health_check.py --env-file "$(ENV_FILE)"; \
		sleep 3; \
		$(PYTHON) scripts/seed_demo_data.py --env-file "$(ENV_FILE)"; \
		PYTHONPATH=. $(PYTEST) -m llm'

test\:llm\:audit:
	@bash -c 'set -euo pipefail; \
		docker compose up -d postgres demo-backend demo-frontend; \
		trap "docker compose down" EXIT; \
		$(PYTHON) scripts/health_check.py --env-file "$(ENV_FILE)"; \
		sleep 3; \
		$(PYTHON) scripts/seed_demo_data.py --env-file "$(ENV_FILE)"; \
		echo ""; \
		echo "⚠️  STRICT QUALITY AUDIT MODE ⚠️"; \
		echo "This test uses zero retries and may FAIL with small models."; \
		echo "Failures demonstrate the test framework can detect LLM defects."; \
		echo "Review Allure attachments for detailed failure analysis."; \
		echo ""; \
		PYTHONPATH=. $(PYTEST) -m llm_audit --verbose'

test:
	@bash -c 'set -euo pipefail; \
		docker compose up -d postgres demo-backend demo-frontend; \
		trap "docker compose down" EXIT; \
		$(PYTHON) scripts/health_check.py --env-file "$(ENV_FILE)"; \
		sleep 3; \
		$(PYTHON) scripts/seed_demo_data.py --env-file "$(ENV_FILE)"; \
		USE_FAKE_OLLAMA=$(LLM_USE_FAKE) PYTHONPATH=. $(PYTEST) $(PYTEST_DISTRIBUTION) --reruns 1'

report:
	allure serve allure-results

.PHONY: install compose\:up compose\:down lint check\:health promptfoo promptfoo-watch demo\:setup demo\:seed demo\:reset test\:api test\:ui test\:llm test\:llm\:audit test report
