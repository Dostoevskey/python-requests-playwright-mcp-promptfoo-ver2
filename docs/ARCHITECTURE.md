# Architecture: Dual-Mode LLM Testing Framework

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Test Automation Framework                     │
│                  (Postgres + Ollama + Allure)                    │
└─────────────────────────────────────────────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
              ┌─────▼─────┐           ┌──────▼──────┐
              │ CI/CD     │           │   Local     │
              │ Pipeline  │           │ Development │
              └─────┬─────┘           └──────┬──────┘
                    │                        │
                    │                        │
        USE_FAKE_OLLAMA=1        USE_FAKE_OLLAMA=0
                    │                        │
                    │                        │
       ┌────────────▼──────────┐   ┌────────▼──────────────┐
       │  Stability Tests      │   │ Stability + Audits    │
       │  (2 retries)          │   │ (2 retries + 0 retry) │
       │  ✅ Always Pass       │   │ ❌ Audits may fail     │
       └───────────┬───────────┘   └────────┬──────────────┘
                   │                        │
                   └────────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │   Allure Reporting    │
                    │  - Pass/Fail status   │
                    │  - Failure attachments│
                    │  - Audit statistics   │
                    └───────────────────────┘
```

---

## Test Flow Architecture

### Stability Tests (`test_article_generation.py`)

```
┌──────────────┐
│ Test Start   │
└──────┬───────┘
       │
       ▼
┌──────────────────────┐
│ Load Prompt Template │  (articles.yaml)
│ Render with Jinja2   │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ Generate with Model  │  (gemma3:4b / deepseek-r1:8b)
│ Attempt 1            │  temperature=0.25, seed=deterministic
└──────┬───────────────┘
       │
       ├─► ✅ Length OK (300-500 chars)
       ├─► ✅ Topic Coverage OK (keywords present)
       ├─► ✅ Judge Approves (gpt-oss:20b)
       │
       ▼
   ┌───┴───┐
   │ Pass? │───► YES ──► Attach to Allure ──► Test Pass
   └───┬───┘
       │
       NO
       │
       ▼
┌──────────────────────┐
│ Generate with Model  │
│ Attempt 2            │  temperature=0.15, seed=different
└──────┬───────────────┘
       │
       ├─► ✅ Length OK
       ├─► ✅ Topic Coverage OK
       ├─► ✅ Judge Approves
       │
       ▼
   ┌───┴───┐
   │ Pass? │───► YES ──► Attach to Allure ──► Test Pass
   └───┬───┘
       │
       NO
       │
       ▼
   ❌ Test Fail
   Attach all attempts to Allure
```

---

### Audit Tests (`test_article_quality_audit.py`)

```
┌──────────────┐
│ Test Start   │
└──────┬───────┘
       │
       ▼
┌────────────────────────────────┐
│ Load Prompt Template           │  (articles.yaml)
│ 3 scenarios × 2 models = 6 runs│
└────────┬───────────────────────┘
         │
         ▼
┌────────────────────────────────┐
│ For Each Model-Scenario Pair   │
│ Run 5 Iterations                │
└────────┬───────────────────────┘
         │
         ▼
    ┌────┴────┐
    │Iteration│◄──────┐
    │  1-5    │       │
    └────┬────┘       │
         │            │
         ▼            │
┌──────────────────────────┐    │
│ Generate Output          │    │
│ (zero retries)           │    │
└──────┬───────────────────┘    │
       │                        │
       ├─► Length Check          │
       ├─► Topic Coverage Check   │
       ├─► Judge Validation      │
       │                        │
       ▼                        │
   ┌───┴────┐                   │
   │ Result │                   │
   └───┬────┘                   │
       │                        │
       ├─► ✅ Pass: Record      │
       │   (failure_reason=None)│
       │                        │
       ├─► ❌ Fail: Record       │
       │   - too_short          │
       │   - too_long           │
       │   - off_topic          │
       │   - judge_rejected     │
       │                        │
       ▼                        │
   Attach to Allure             │
   (iteration details)          │
       │                        │
       └──────────► Loop ───────┘
                    (next iteration)
         │
         │ (after 5 iterations)
         ▼
┌────────────────────────────────┐
│ Calculate Statistics           │
│ - Success rate                 │
│ - Failure breakdown            │
│ - Recommendation               │
└────────┬───────────────────────┘
         │
         ▼
    ┌────┴─────┐
    │Success   │
    │Rate >= 60%│
    └────┬─────┘
         │
    ┌────┴────┐
    │         │
    YES       NO
    │         │
    ▼         ▼
✅ Pass    ❌ Fail
Attach    Attach:
report    - Full report
          - All failures
          - Recommendations
```

---

## Data Flow: Postgres + Ollama + Allure

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Compose                            │
└─────────────────────────────────────────────────────────────────┘
           │                     │                    │
           │                     │                    │
    ┌──────▼──────┐      ┌──────▼──────┐     ┌──────▼──────┐
    │  Postgres   │      │   Backend   │     │  Frontend   │
    │  (port 5432)│      │  (port 3001)│     │ (port 3000) │
    └──────┬──────┘      └──────┬──────┘     └──────┬──────┘
           │                     │                    │
           │ Health Check        │ Health Check       │ Health Check
           │ (psycopg2)          │ (httpx)            │ (httpx)
           │                     │                    │
    ┌──────▼─────────────────────▼────────────────────▼──────┐
    │              Pytest Session (conftest.py)              │
    │  - Loads config/demo.env                               │
    │  - Waits for all services ready                        │
    │  - Seeds deterministic data (5 users, 10 articles)     │
    └────────────────────────┬───────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
    ┌─────────▼─────────┐         ┌────────▼────────┐
    │   API Tests       │         │   LLM Tests     │
    │ (requests)        │         │ (ollama client) │
    └─────────┬─────────┘         └────────┬────────┘
              │                            │
              │                            │
              │                   ┌────────▼────────┐
              │                   │ Ollama Daemon   │
              │                   │ (localhost:11434)│
              │                   └────────┬────────┘
              │                            │
              │                   ┌────────▼────────┐
              │                   │  Generator      │
              │                   │  Models         │
              │                   │  - gemma3:4b    │
              │                   │  - deepseek-r1  │
              │                   └────────┬────────┘
              │                            │
              │                   ┌────────▼────────┐
              │                   │  Judge Model    │
              │                   │  - gpt-oss:20b  │
              │                   └────────┬────────┘
              │                            │
              └────────────┬───────────────┘
                           │
                  ┌────────▼────────┐
                  │  Allure Results │
                  │  (allure-results/)│
                  │  - Attachments  │
                  │  - Screenshots  │
                  │  - Logs         │
                  └────────┬────────┘
                           │
                  ┌────────▼────────┐
                  │  Allure Report  │
                  │  (make report)  │
                  │  - HTML UI      │
                  │  - Test history │
                  │  - Trends       │
                  └─────────────────┘
```

---

## Environment Variable Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                       config/demo.env                            │
│  DB_HOST=postgres                                                │
│  DB_NAME=conduit_local                                           │
│  DB_USER=conduit                                                 │
│  DB_PASSWORD=conduit                                             │
│  OLLAMA_BASE_URL=http://localhost:11434                          │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 │ load_dotenv()
                                 │
                    ┌────────────▼────────────┐
                    │  tests/conftest.py      │
                    │  Settings fixture       │
                    └────────────┬────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
              ┌─────▼─────┐           ┌──────▼──────┐
              │ Database  │           │   Ollama    │
              │ Connection│           │   Client    │
              │ (psycopg2)│           │ (ollama-py) │
              └───────────┘           └──────┬──────┘
                                             │
                                             │
                                ┌────────────▼────────────┐
                                │  USE_FAKE_OLLAMA check  │
                                └────────────┬────────────┘
                                             │
                                ┌────────────┴────────────┐
                                │                         │
                           ┌────▼────┐              ┌─────▼─────┐
                           │ Real    │              │  Stub     │
                           │ Models  │              │ Responses │
                           └─────────┘              └───────────┘
```

---

## Decision Tree: Audit Test Evaluation

```
                        ┌─────────────┐
                        │  Generate   │
                        │   Output    │
                        └──────┬──────┘
                               │
                               ▼
                   ┌───────────────────────┐
                   │ Length Check          │
                   │ 300 ≤ chars ≤ 500     │
                   └───────────┬───────────┘
                               │
                    ┌──────────┴──────────┐
                    │                     │
                   FAIL                  PASS
                    │                     │
        ┌───────────┴────────┐           │
        │                    │           │
   < 300 chars          > 500 chars      │
        │                    │           │
        ▼                    ▼           │
   failure_reason      failure_reason    │
   = "too_short"      = "too_long"      │
        │                    │           │
        └────────┬───────────┘           │
                 │                       │
                 ▼                       ▼
            ❌ Record                ┌────────────────┐
            Attach to Allure       │ Topic Coverage  │
                                   │ Keywords present│
                                   └────────┬────────┘
                                            │
                                 ┌──────────┴──────────┐
                                 │                     │
                                FAIL                  PASS
                                 │                     │
                          coverage < 0.5         coverage ≥ 0.5
                                 │                     │
                                 ▼                     ▼
                          failure_reason      ┌────────────────┐
                          = "off_topic"       │ Judge Validation│
                                 │            │ (gpt-oss:20b)   │
                                 │            └────────┬────────┘
                                 │                     │
                                 │          ┌──────────┴──────────┐
                                 │          │                     │
                                 │         FAIL                  PASS
                                 │          │                     │
                                 │          ▼                     ▼
                                 │   failure_reason         failure_reason
                                 │   = "judge_rejected"     = None
                                 │          │                     │
                                 └──────────┼─────────────────────┘
                                            │
                                 ┌──────────┴──────────┐
                                 │                     │
                            failure_reason        failure_reason
                            != None               == None
                                 │                     │
                                 ▼                     ▼
                            ❌ Failed             ✅ Passed
                            Attach:              Attach:
                            - Output             - Output
                            - Judge reasoning    - Judge approval
```

---

## Model Quality Assessment Pipeline

```
┌────────────────────────────────────────────────────────────────┐
│          Run 5 Iterations per Model-Scenario Pair              │
└────────────────────────┬───────────────────────────────────────┘
                         │
            ┌────────────┼────────────┐
            │            │            │
      Iteration 1   Iteration 2   ... Iteration 5
            │            │            │
            ▼            ▼            ▼
        ┌───────┐    ┌───────┐    ┌───────┐
        │Result │    │Result │    │Result │
        └───┬───┘    └───┬───┘    └───┬───┘
            │            │            │
            └────────────┼────────────┘
                         │
                         ▼
            ┌────────────────────────┐
            │  Aggregate Results     │
            │  - Successful: 3       │
            │  - Failed: 2           │
            │  - Success Rate: 60%   │
            └────────────┬───────────┘
                         │
                         ▼
            ┌────────────────────────┐
            │  Categorize Failures   │
            │  - too_short: 1        │
            │  - judge_rejected: 1   │
            └────────────┬───────────┘
                         │
                         ▼
            ┌────────────────────────┐
            │  Generate              │
            │  Recommendation        │
            └────────────┬───────────┘
                         │
            ┌────────────┴────────────┐
            │                         │
       Success Rate < 60%      Success Rate ≥ 60%
            │                         │
            ▼                         ▼
   ┌────────────────┐        ┌────────────────┐
   │ 🔴 / 🟡        │        │ 🟢 Acceptable  │
   │ Replace Model  │        │ Keep Model     │
   └────────┬───────┘        └────────┬───────┘
            │                         │
            └────────────┬────────────┘
                         │
                         ▼
            ┌────────────────────────┐
            │  Attach to Allure:     │
            │  - Summary report      │
            │  - All failures        │
            │  - Recommendations     │
            └────────────────────────┘
                         │
                         ▼
                 ┌───────────────┐
                 │  Test Result  │
                 └───────┬───────┘
                         │
            ┌────────────┴────────────┐
            │                         │
       All models          At least one model
       ≥ 60%               < 60%
            │                         │
            ▼                         ▼
        ✅ PASS                  ❌ FAIL
        (rare with              (expected with
         small models)           small models)
```

---

## File Organization

```
project-root/
│
├── config/
│   └── demo.env                    # Postgres credentials, Ollama URL
│
├── demo-app/
│   ├── src/
│   │   ├── backend/
│   │   │   ├── .env               # Generated by bootstrap script
│   │   │   └── config/
│   │   │       └── config.js      # Sequelize Postgres config
│   │   └── frontend/
│   │       └── ...
│   └── .postgres-data/            # Postgres volume mount
│
├── docs/
│   ├── ARCHITECTURE.md            # This file
│   ├── IMPLEMENTATION_SUMMARY.md  # Full details
│   └── QUICK_REFERENCE.md         # Command cheat sheet
│
├── tests/
│   ├── conftest.py                # Settings, health checks, markers
│   ├── api/
│   │   └── test_*.py              # Requests-based API tests
│   ├── ui/
│   │   └── test_*.py              # Playwright UI tests
│   └── llm/
│       ├── test_article_generation.py      # Stability (2 retries)
│       ├── test_article_quality_audit.py   # Audit (0 retries) ⭐
│       └── test_promptfoo_suite.py         # Promptfoo wrapper
│
├── promptfoo/
│   └── prompts/
│       └── articles.yaml          # Prompt templates
│
├── docker-compose.yml             # Postgres + backend + frontend
├── Makefile                       # make test:llm, make test:llm:audit
├── pyproject.toml                 # Pytest markers
├── README.md                      # Main documentation
└── CHANGES.md                     # Change summary
```

---

## Execution Flow: `make test:llm:audit`

```
1. make test:llm:audit
       │
       ▼
2. docker compose up -d postgres demo-backend demo-frontend
       │
       ├─► Start Postgres container (port 5432)
       ├─► Wait for health check (pg_isready)
       ├─► Start backend (port 3001)
       │   └─► Run migrations (sequelize)
       └─► Start frontend (port 3000)
       │
       ▼
3. python scripts/health_check.py
       │
       ├─► Check backend: GET /api/articles
       ├─► Check frontend: GET /
       └─► Check database: SELECT 1
       │
       ▼
4. sleep 3
       │
       ▼
5. python scripts/seed_demo_data.py
       │
       ├─► Create 5 users via POST /api/users
       └─► Create 10 articles via POST /api/articles
       │
       ▼
6. pytest -m llm_audit --verbose
       │
       ├─► Load config/demo.env
       ├─► Initialize Settings fixture
       ├─► Check Ollama models available
       │   (gemma3:4b, deepseek-r1:8b, gpt-oss:20b)
       │
       ├─► Run test_article_quality_audit.py
       │   │
       │   ├─► For each model × scenario:
       │   │   ├─► Iteration 1
       │   │   ├─► Iteration 2
       │   │   ├─► Iteration 3
       │   │   ├─► Iteration 4
       │   │   └─► Iteration 5
       │   │
       │   ├─► Calculate statistics
       │   ├─► Generate recommendations
       │   └─► Attach to Allure
       │
       └─► Test Result (PASS or FAIL)
       │
       ▼
7. allure-results/ populated
       │
       ▼
8. make report
       │
       └─► allure serve allure-results
           └─► Open browser with interactive report
```

---

## Key Components Interaction

```
┌──────────────────────────────────────────────────────────────────┐
│                       User Invokes                                │
│                  make test:llm:audit                              │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  Docker Compose        │
              │  - Postgres ready      │
              │  - Backend ready       │
              │  - Frontend ready      │
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  Health Checks         │
              │  - Database connection │
              │  - API responsive      │
              │  - Frontend up         │
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  Seed Data             │
              │  - 5 users created     │
              │  - 10 articles created │
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  Pytest Session Start  │
              │  - Load settings       │
              │  - Register markers    │
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  Test Collection       │
              │  - Filter: @llm_audit  │
              │  - Found: 1 test       │
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  Ollama Client Init    │
              │  - Check USE_FAKE_OLLAMA│
              │  - Connect to daemon   │
              │  - Verify models       │
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  Run Audit Test        │
              │  - 5 iterations × 2    │
              │    models × 3 scenarios│
              │  = 30 generation calls │
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  Statistical Analysis  │
              │  - Success rates       │
              │  - Failure categories  │
              │  - Recommendations     │
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  Allure Attachments    │
              │  - Individual results  │
              │  - Failure outputs     │
              │  - Summary report      │
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  Test Verdict          │
              │  - All ≥60%: PASS      │
              │  - Any <60%: FAIL      │
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  Pytest Session End    │
              │  - Write runtime stats │
              │  - Exit with code      │
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  User Reviews Report   │
              │  make report           │
              └────────────────────────┘
```

---

## Summary

This architecture implements **dual-mode LLM testing** with:

1. **Infrastructure**: Postgres + Ollama via Docker Compose
2. **Health Validation**: Automated checks before test execution
3. **Dual Test Modes**: Stability (retries) vs Audit (zero retries)
4. **Statistical Analysis**: 5-iteration quality assessment
5. **Actionable Reporting**: Automated recommendations via Allure

**Key Principle**: Test failures with detailed analysis prove framework effectiveness better than forced passes.

