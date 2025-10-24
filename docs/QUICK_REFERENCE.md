# Quick Reference: Dual-Mode LLM Testing

## Commands

```bash
# Stability tests (2 retries, CI-friendly)
make test:llm

# Quality audits (0 retries, expected to fail)
make test:llm:audit

# View results
make report
```

## Test Modes

| Mode | Marker | Retries | Fails When | Purpose |
|------|--------|---------|-----------|---------|
| Stability | `llm` | 2 | All attempts exhausted | CI/CD reliability |
| Audit | `llm_audit` | 0 | Success rate < 60% | Defect detection |

## Model Quality Thresholds

| Success Rate | Status | Action |
|--------------|--------|--------|
| < 40% | 🔴 | Replace immediately |
| 40-60% | 🟡 | Consider replacement |
| 60-80% | 🟢 | Acceptable |
| > 80% | 🟢 | Performing well |

## Environment Variables

```bash
# Use real models (local testing)
export USE_FAKE_OLLAMA=0
make test:llm:audit

# Use stubs (CI/fast testing)
export USE_FAKE_OLLAMA=1
make test:llm
```

## Expected Results

### Stability Tests (`make test:llm`)
- **CI** (`USE_FAKE_OLLAMA=1`): ✅ PASS
- **Local** (`USE_FAKE_OLLAMA=0`): ✅ PASS (mostly), occasional flakiness OK

### Audit Tests (`make test:llm:audit`)
- **CI** (`USE_FAKE_OLLAMA=1`): ✅ PASS (stubs are perfect)
- **Local** (`USE_FAKE_OLLAMA=0`): ❌ **FAIL** (gemma3:4b, deepseek-r1:8b produce hallucinations)

## Interpreting Audit Failures

When audit tests fail locally:

1. ✅ **This is EXPECTED** - Proves framework can detect defects
2. ✅ Open Allure report: `make report`
3. ✅ Find attachment: "quality_audit_report"
4. ✅ Review success rates and recommendations
5. ✅ Check "FAILURE_*" attachments for examples

## Common Scenarios

### "My audit test failed - is this a bug?"

**No!** Audit failures are a **feature**. They prove your test can detect:
- Hallucinations (judge rejects incoherent output)
- Off-topic content (keyword coverage < 50%)
- Length violations (< 300 or > 500 chars)

### "How do I make audit tests pass?"

**Option 1**: Replace model (recommended)
```bash
# Replace gemma3:4b with llama3:8b
ollama pull llama3:8b
# Update tests/llm/test_article_quality_audit.py:
GENERATOR_MODELS = ["llama3:8b", "deepseek-r1:8b"]
```

**Option 2**: Tune prompts (may help)
- Adjust character limits in prompt
- Simplify topic complexity
- Add explicit anti-hallucination instructions

**Option 3**: Use stubs (CI only)
```bash
export USE_FAKE_OLLAMA=1
make test:llm:audit  # Will pass with perfect stubs
```

### "CI is failing on audit tests"

CI should **NOT** run audit tests by default. Check:
1. Does CI set `USE_FAKE_OLLAMA=1`? (stability tests should pass)
2. Is CI running `pytest -m llm_audit`? (shouldn't be)
3. Use `pytest -m "llm and not llm_audit"` in CI

## File Locations

```
tests/llm/
├── test_article_generation.py      # Stability tests (2 retries)
├── test_article_quality_audit.py   # Audit tests (0 retries)
└── test_promptfoo_suite.py         # Promptfoo integration

docs/
├── IMPLEMENTATION_SUMMARY.md       # Full implementation details
└── QUICK_REFERENCE.md             # This file

config/
└── demo.env                        # Postgres credentials

promptfoo/
└── prompts/
    └── articles.yaml               # Prompt templates
```

## Postgres Setup

Already configured! Just run:
```bash
docker compose up -d postgres
make demo:setup
make demo:seed
```

Credentials (see `config/demo.env`):
- Host: `localhost:5432`
- Database: `conduit_local`
- User/Password: `conduit/conduit`

## Troubleshooting

### "No Ollama models found"

```bash
ollama pull gemma3:4b
ollama pull deepseek-r1:8b
ollama pull gpt-oss:20b
```

### "Database connection failed"

```bash
docker compose up -d postgres
docker compose ps  # Verify postgres is healthy
```

### "Tests skip with 'Backend not ready'"

```bash
make check:health  # Should pass
# If fails, wait 30s and retry
```

### "I want to see ALL failures, not just < 60%"

Edit `tests/llm/test_article_quality_audit.py`:
```python
# Line 372: Change threshold to 1.0 (100%)
if summary.success_rate < 1.0:  # Was: 0.6
    # Now fails unless ALL runs pass
```

## Best Practices

✅ **DO**: Run audit tests locally to evaluate models  
✅ **DO**: Review Allure attachments when audits fail  
✅ **DO**: Use audit failure data to justify model replacements  
✅ **DO**: Run stability tests in CI with `USE_FAKE_OLLAMA=1`  

❌ **DON'T**: Expect audit tests to pass with small models  
❌ **DON'T**: Run audit tests in CI (unless allow-failure)  
❌ **DON'T**: Add retries to audit tests (defeats the purpose)  
❌ **DON'T**: Hide failures - they prove framework effectiveness  

## Key Takeaway

**Test failures (with clear root cause analysis) are more valuable than forced passes that hide model defects.**

Audit failures prove your test framework works correctly.

