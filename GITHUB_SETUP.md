# GitHub Repository Setup Instructions

## 🎯 Goal
Push the dual-mode LLM testing framework to:
**https://github.com/Dostoevskey/python-requests-playwright-mcp-promptfoo-ver2**

---

## ⚡ Quick Setup (30 seconds + 1 command)

### Step 1: Create Repository Manually

The provided token doesn't have `repo` scope (needed to create repositories via API).

**Go to**: https://github.com/new

**Fill in**:
- **Repository name**: `python-requests-playwright-mcp-promptfoo-ver2`
- **Description**: 
  ```
  Local test automation stack with dual-mode LLM testing - Postgres, Playwright, Ollama, Allure. Features stability tests and strict quality audits for genuine defect detection.
  ```
- **Visibility**: ✅ Public
- **Initialize repository**: ❌ LEAVE ALL UNCHECKED
  - ❌ Add a README file
  - ❌ Add .gitignore  
  - ❌ Choose a license

**Click**: "Create repository"

### Step 2: Push Code

Once created, run this script:

```bash
./push_to_ver2.sh
```

Or manually:

```bash
git push -u ver2 strict-llm-evidence
git push ver2 main
```

---

## 📦 What's Being Pushed

### New Implementation (strict-llm-evidence branch)

**10 files changed, 2,301 insertions(+)**

#### Modified Files (5)
1. ✏️ `tests/llm/test_article_generation.py` - Reduced retries 4→2
2. ✏️ `tests/conftest.py` - Added llm_audit marker
3. ✏️ `pyproject.toml` - Marker definitions
4. ✏️ `Makefile` - New `test:llm:audit` target
5. ✏️ `README.md` - Comprehensive documentation updates

#### New Files (5)
1. ⭐ `tests/llm/test_article_quality_audit.py` - 389 lines, zero-retry strict validation
2. 📄 `docs/IMPLEMENTATION_SUMMARY.md` - Full technical details (1000+ lines)
3. 📄 `docs/QUICK_REFERENCE.md` - Command cheat sheet
4. 📄 `docs/ARCHITECTURE.md` - Visual flow diagrams
5. 📄 `CHANGES.md` - Change summary

---

## 🔑 Alternative: Create Token with Repo Scope

If you prefer to create repositories via CLI/API:

1. Go to: https://github.com/settings/tokens/new
2. **Note**: "Dual-mode LLM testing repository creation"
3. **Expiration**: Your choice
4. **Scopes**: 
   - ✅ `repo` (Full control of private repositories)
   - ✅ `workflow` (Update GitHub Action workflows - optional)
5. Click "Generate token"
6. Copy the new token

Then:

```bash
# Authenticate with new token
echo "YOUR_NEW_TOKEN" | gh auth login --with-token

# Create repository
gh repo create Dostoevskey/python-requests-playwright-mcp-promptfoo-ver2 \
  --public \
  --description "Local test automation stack with dual-mode LLM testing" \
  --source=. \
  --remote=ver2 \
  --push
```

---

## ✅ Verification

After pushing, verify at:
- **Repository**: https://github.com/Dostoevskey/python-requests-playwright-mcp-promptfoo-ver2
- **Implementation branch**: https://github.com/Dostoevskey/python-requests-playwright-mcp-promptfoo-ver2/tree/strict-llm-evidence

You should see:
- ✅ 10 changed files
- ✅ New `tests/llm/test_article_quality_audit.py`
- ✅ Updated README with dual-mode testing documentation
- ✅ All new documentation files in `docs/`

---

## 📊 Repository Features

Once pushed, your repository will showcase:

### Core Implementation
- ✅ **Dual-mode LLM testing** (stability + strict audits)
- ✅ **PostgreSQL integration** via Docker Compose
- ✅ **Zero-retry quality audits** with statistical analysis
- ✅ **Automated model recommendations** based on success rates
- ✅ **Rich Allure reporting** with failure attachments

### Documentation
- 📖 Comprehensive README with testing philosophy
- 📖 Implementation summary (1000+ lines)
- 📖 Quick reference guide
- 📖 Architecture diagrams
- 📖 Change summary

### Testing Philosophy
> "Test failures with clear root cause analysis are more valuable than forced passes that hide model defects."

---

## 🎉 What This Demonstrates

Your repository will show:

1. **Staff SDET-level thinking**: Critical analysis, multiple solution evaluation
2. **Genuine defect detection**: Tests designed to fail with poor models
3. **Production-ready infrastructure**: PostgreSQL, Docker, health checks
4. **Actionable insights**: Automated recommendations from test results
5. **Comprehensive documentation**: Architecture, philosophy, usage

Perfect portfolio piece for demonstrating QA architecture skills! 🚀

---

## 🆘 Troubleshooting

### Issue: "remote: Repository not found"
**Solution**: Create the repository on GitHub first (Step 1 above)

### Issue: "Resource not accessible by personal access token"
**Solution**: Token lacks `repo` scope. Use manual creation (fastest) or generate new token with `repo` scope.

### Issue: "! [rejected] ... (fetch first)"
**Solution**: The repository was initialized with README. Either:
- Delete and recreate without initialization
- Force push: `git push -f ver2 strict-llm-evidence`

---

## 📞 Ready to Push?

Once you've created the repository:

```bash
./push_to_ver2.sh
```

That's it! Your dual-mode LLM testing framework will be live on GitHub. 🎊

