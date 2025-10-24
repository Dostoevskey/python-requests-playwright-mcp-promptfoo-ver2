#!/bin/bash
# Script to push code to the new ver2 repository

set -euo pipefail

echo "🚀 Pushing dual-mode LLM testing framework to GitHub..."
echo ""

# Push the implementation branch
echo "📤 Pushing strict-llm-evidence branch (with new implementation)..."
git push -u ver2 strict-llm-evidence

echo ""
echo "📤 Pushing main branch..."
git push ver2 main

echo ""
echo "✅ Successfully pushed to github.com/Dostoevskey/python-requests-playwright-mcp-promptfoo-ver2"
echo ""
echo "🔗 View your repository:"
echo "   https://github.com/Dostoevskey/python-requests-playwright-mcp-promptfoo-ver2"
echo ""
echo "📊 Key branches:"
echo "   - main: Base project"
echo "   - strict-llm-evidence: Dual-mode LLM testing implementation ⭐"

