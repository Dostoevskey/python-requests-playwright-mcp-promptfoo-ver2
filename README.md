# Local Test Automation Stack

Automation workspace that provisions the Conduit RealWorld demo app, seeds deterministic data, and runs API, UI, and LLM prompt validation entirely on local infrastructure.

## Features
- **PostgreSQL-backed demo app** via Docker Compose with health checks and deterministic migrations.
- Bundled Conduit RealWorld demo app with a bootstrap script that installs dependencies and runs migrations without additional git clones.
- Deterministic seed data creates five users and ten articles through the public API.
- Health guardrails verify frontend, backend, and database readiness before pytest executes.
- Pytest suites cover REST CRUD operations, authentication, pagination, and Playwright UI flows with multi-context support (desktop + mobile).
- Allure reporting baked into every run with attachments for API responses, Playwright traces, and LLM outputs.
- **Dual-mode LLM testing**: Stability tests (with limited retries) + strict quality audits (zero retries, designed to expose model defects).
- Prompt evaluation harness built on Ollama + Promptfoo with small local models (`gemma3:4b`, `deepseek-r1:8b`) and judge validation via `gpt-oss:20b`.
- **Genuine defect detection** - LLM tests can and should fail when models produce hallucinations, proving test framework effectiveness.
- Bundled prompt suites derived from `llm-prompt-testing-quick-start`, each with its own configuration for independent evaluation.
- GitHub Actions CI pipeline validates the API, UI, and LLM suites and archives Allure bundles for every push/PR.
- Optional Playwright MCP server integration for interactive locator capture from the same workspace.

## Project Layout
```
.
├── config/               # Environment, seed, and promptfoo configs
├── demo-app/             # Vendored RealWorld example app (frontend + backend sources)
├── scripts/              # Bootstrap, seeding, and health utilities
├── src/                  # Shared helpers (API client, health, ollama)
├── tests/
│   ├── api/              # Requests-based API coverage
│   ├── ui/               # Playwright MCP multi-context UI coverage
│   └── llm/              # Promptfoo + Ollama integration tests
├── promptfoo/            # Offline prompt suites and shared templates
├── docker-compose.yml    # Optional container stack for postgres/backend/frontend
├── Makefile              # Friendly entry points
├── pyproject.toml        # Python dependencies + pytest config
└── package.json          # Node dependencies for promptfoo
```

## Prerequisites
- Python 3.10+ with `pip` and virtual environment support (`python3-venv` on Debian/Ubuntu).
- Node.js 18+ (needed for the demo app and Promptfoo CLI).
- Docker + Docker Compose (optional but simplifies demo app + PostgreSQL orchestration).
- Allure command line (`brew install allure`, `scoop install allure`, or download from JetBrains).
- Ollama installed locally with access to the following models:
  - `ollama pull gemma3:4b`
  - `ollama pull deepseek-r1:8b`
  - `ollama pull gpt-oss:20b`
- PostgreSQL client tools (`psql`) for migrations and health checks.

## Quick Start

1. **Install Python dependencies**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

2. **Install Node dependencies**
   ```bash
   npm install
   ```

3. **Provision the RealWorld demo app**
   ```bash
   make demo:setup        # Installs workspaces, writes backend .env, runs migrations
   make demo:seed         # Populates five users + ten articles through the public API
   ```

   > The RealWorld frontend + backend sources ship with this repository. `make demo:reset` simply removes workspace `node_modules` before reinstalling.

4. **Launch the stack (Docker Compose)**
   ```bash
   make compose:up          # brings postgres + backend + frontend up in the background
   make check:health        # waits for backend/frontend/database readiness
   ```
   When you are done, run `make compose:down` to stop the containers.

   > Prefer a manual workflow? You can still run `(cd demo-app/src && npm run dev)` in two terminals to launch backend (3001) and frontend (3000) without Docker.

5. **Seed demo data (optional once per environment)**
   ```bash
   make demo:seed
   ```

> After the first `pip`/`npm` install, all RealWorld sources and prompt suites are already vendored, so the entire test stack runs offline.

## Test Suites

| Command | Description | Expected Behavior |
|---------|-------------|-------------------|
| `make test:api` | Requests-based CRUD, auth, and pagination tests | Should pass consistently |
| `make test:ui` | Playwright MCP multi-context runs (`--headed`) | Should pass consistently |
| `make test:llm` | Ollama-powered article generation (2 retries for stability) | Should pass in CI, may flake locally |
| `make test:llm:audit` | **STRICT LLM quality audit** (zero retries, statistical analysis) | **Expected to fail with poor models** |
| `make test` | Full pytest suite (all markers except llm_audit) | Balanced stability |

All pytest runs write Allure results to `allure-results/`. Generate a report via:

```bash
make report         # opens Allure dashboard in a browser
```

### LLM Testing Philosophy: Dual-Mode Approach

This framework implements **two complementary LLM test strategies**:

#### 1. **Stability Tests** (`test_article_generation.py`, `@pytest.mark.llm`)
- **Purpose**: CI/CD reliability, smoke testing
- **Retry logic**: Up to 2 attempts per scenario
- **Failure threshold**: Fail only if all retries exhausted
- **Usage**: `make test:llm` or `pytest -m llm`
- **Expected result**: Pass in CI (with `USE_FAKE_OLLAMA=1`), occasional flakiness locally

#### 2. **Quality Audit Tests** (`test_article_quality_audit.py`, `@pytest.mark.llm_audit`)
- **Purpose**: Genuine defect detection, model evaluation
- **Retry logic**: **ZERO retries** - first attempt must pass
- **Failure threshold**: Fail if any model has <60% success rate over 5 iterations
- **Usage**: `make test:llm:audit` or `pytest -m llm_audit --verbose`
- **Expected result**: **FAIL with small models** (gemma3:4b, deepseek-r1:8b)

**Why this matters**: The audit tests are **designed to fail** when models produce hallucinations, off-topic content, or incoherent outputs. Test failures prove the framework can detect genuine LLM defects rather than always passing with retry workarounds.

#### Interpreting Audit Failures

When `test_article_quality_audit.py` fails:

✅ **This is success** - The test has detected genuine model weaknesses  
✅ Check Allure attachments for detailed failure analysis (hallucinations, judge reasoning)  
✅ Review the "quality_audit_report" attachment for success rates and recommendations

**Model Replacement Guidance** (from audit report):
- **Success rate < 40%**: 🔴 Replace model immediately
- **Success rate 40-60%**: 🟡 Consider replacement or prompt tuning
- **Success rate 60-80%**: 🟢 Acceptable for local testing
- **Success rate > 80%**: 🟢 Model performs well

#### Example: Running Audit Tests Locally

```bash
# Start the stack
make compose:up
make demo:seed

# Run strict quality audit (WILL LIKELY FAIL with small models)
make test:llm:audit

# View detailed failure analysis
make report  # Check "quality_audit_report" and "FAILURE_*" attachments
```

Expected audit output for gemma3:4b:
```
## gemma3:4b
- Success Rate: 53.3% (8/15)
- Recommendation: 🟡 CONSIDER REPLACEMENT - Model is marginal

### Failure Breakdown:
  - judge_rejected (hallucination/incoherence): 4 occurrences
  - off_topic (coverage 33%): 2 occurrences
  - too_short (245 < 300): 1 occurrence
```

### Health-Aware Fixtures
- `tests/conftest.py` loads `config/demo.env`, asserts backend/frontend/database readiness, and surfaces metadata to Allure.
- PostgreSQL connection validated via `wait_for_database()` before any test execution.
- API tests rely on `src/utils/api_client.py` for clean request helpers and token management.
- UI tests (`tests/ui/test_articles_ui.py`) exercise login, article authoring, pagination, and authenticated routing using dual browser contexts (desktop + mobile) configured in `tests/ui/conftest.py`.
- LLM tests automatically fall back to stubs when `USE_FAKE_OLLAMA=1` or `CI=true`.

## Prompt Evaluation

### Promptfoo Workflow
Each prompt suite lives under `promptfoo/suites/<name>`. They are adapted from the `llm-prompt-testing-quick-start` repository and reworked to run entirely on local Ollama models. Evaluate the bundled article writer suite with:
```bash
make promptfoo
# or watch mode
make promptfoo-watch
```

Available suites:

- `articles` – structured article drafting with rubric enforcement.
- `is_nlq_agent_prompt` – JSON scoring of NLQ questions.
- `is_nlq_minimal_agent_prompt` – lightweight yes/no validation.
- `nlq_to_sql` – SQL synthesis with aggregate queries.
- `nlq_to_sql_experiment` – JOIN-focused SQL prompts.
- `try_this_nlq_agent_prompt` – natural language question generation with row limits.

You can run an individual suite with `npx promptfoo eval --config promptfoo/suites/<suite>/promptfooconfig.yaml`.

### Pytest + Ollama

The framework includes two complementary test modules:

#### `test_article_generation.py` - Stability Tests
Reads prompt templates from `promptfoo/prompts/articles.yaml`, renders with Jinja2, and uses `OllamaRunner`/`gpt-oss:20b` to:
1. Generate content with each lightweight model (up to 2 attempts for stability)
2. Ensure character-length compliance (300-500 chars)
3. Verify topic coverage with keyword heuristics
4. Judge validation via `gpt-oss:20b` with retry logic
5. Attach all attempts (including failures) to Allure

**Use case**: CI/CD pipelines, smoke testing (set `USE_FAKE_OLLAMA=1` for deterministic stubs)

#### `test_article_quality_audit.py` - Quality Audits (NEW)
Implements **strict zero-retry validation** to expose genuine model defects:
1. Runs 5 iterations per scenario per model (statistical significance)
2. **NO retries** - each attempt must pass judge validation
3. Fails test if model success rate < 60%
4. Generates comprehensive audit reports with:
   - Per-model success rates and failure breakdowns
   - Actionable replacement recommendations
   - All failure outputs attached to Allure
5. Demonstrates test framework can detect hallucinations/incoherence

**Use case**: Local model evaluation, demonstrating test rigor (expected to fail with small models)

**Key difference**: Stability tests prioritize reliability (retries), audit tests prioritize defect detection (zero retries).

Outputs, prompts, judge decisions, and statistical summaries are attached to Allure for traceability.

### Playwright MCP (Optional)
Launch the MCP helper to capture DOM snippets and selectors while the RealWorld frontend is running:

```bash
npm run mcp -- --url http://localhost:3000/#/
```

The server exposes Model Context Protocol commands that tools like Cursor or Claude can consume to generate Playwright flows. See the in-terminal instructions for details.

## Setup Notes
- **PostgreSQL is the default database** - configured via Docker Compose with health checks and migrations managed by Sequelize.
- The repository intentionally ignores `demo-app/src/` and `promptfoo/source/` so you can freely update upstream projects without polluting Git history.
- Update `config/demo.env` to align with custom ports, database credentials, or Ollama endpoints.
- If you rely on Docker, ensure `demo-app/src` exists before `docker compose up` so volume mounts succeed.
- Database credentials default to `conduit/conduit` (username/password) for the `conduit_local` database running on `localhost:5432`.

## Troubleshooting
- **Missing Python packages** – create a virtual environment (`python3 -m venv .venv`) before installing `requirements.txt`.
- **`ollama` errors** – confirm the daemon is running (`ollama serve`) and models are pulled locally.
- **Promptfoo CLI not found** – run `npm install` to place `promptfoo` in `node_modules/.bin`, or invoke via `npx promptfoo`.
- **Playwright browsers missing** – after `pip install`, run `python -m playwright install --with-deps chromium`.
- **Allure CLI unavailable** – install globally or use Docker (`docker run -p 4040:4040 -v $PWD/allure-results:/app/results frankescobar/allure-docker-service`).
- **GitHub Actions failures** – review `.github/workflows/ci.yml` to replay `npm install`, `python scripts/health_check.py`, `python scripts/seed_demo_data.py`, and `python -m pytest` locally, then inspect uploaded Allure artifacts from the workflow run.

## Known Gaps & Future Enhancements

### What's Working Well ✅
- **Dual-mode LLM testing** successfully exposes model defects while maintaining CI stability
- **PostgreSQL integration** provides production-like database behavior with Docker orchestration
- **Comprehensive Allure reporting** captures all failure modes for analysis
- **Health checks** prevent flaky tests due to infrastructure timing issues

### Potential Improvements 🔄
- **Model replacement recommendations**: Currently manual; could auto-suggest specific replacement models (e.g., "gemma3:4b → llama3:8b") based on failure patterns
- **Historical trend tracking**: Persist audit results over time to detect model degradation
- **SQLite fallback**: Add optional SQLite mode for ultra-fast smoke tests without Docker
- **Visual regression**: Extend UI tests with screenshot comparison for CSS/layout validation
- **Judge consensus**: Use multiple judge models to reduce false positives from single-judge flakiness
- **Parallel audit execution**: Run audit iterations in parallel for faster local feedback

### Design Decisions 📋
- **Why allow LLM test failures?** Small local models (gemma3:4b, deepseek-r1:8b) frequently produce hallucinations. Hiding failures with excessive retries would undermine test credibility. Audit failures prove the framework works.
- **Why Postgres not SQLite?** Production environments use Postgres; testing against SQLite creates false confidence about database compatibility (transactions, concurrent access, JSON operators).
- **Why 60% threshold for audits?** Empirically tuned - below 60% indicates systematic model issues, above 60% suggests acceptable quality for local testing.
