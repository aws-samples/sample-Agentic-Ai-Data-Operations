#!/bin/bash
# Push to GitHub - Run after creating repository on GitHub

echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║              PUSHING TO GITHUB: AgentAI-Data-Operation               ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""

# Your GitHub username
GITHUB_USER="johnche88"
REPO_NAME="AgentAI-Data-Operation"

echo "📋 Pre-push checklist:"
echo "   ✅ Repository created on GitHub"
echo "   ✅ Local commits ready (268 files)"
echo "   ✅ Security checks passed"
echo ""

echo "🔗 Setting up remote..."
git remote add origin "https://github.com/$GITHUB_USER/$REPO_NAME.git" 2>/dev/null || {
    echo "   Remote 'origin' already exists. Updating URL..."
    git remote set-url origin "https://github.com/$GITHUB_USER/$REPO_NAME.git"
}

echo "✓ Remote configured: https://github.com/$GITHUB_USER/$REPO_NAME.git"
echo ""

echo "📤 Renaming branch to main..."
git branch -M main
echo "✓ Branch renamed to main"
echo ""

echo "🚀 Pushing to GitHub..."
echo ""
git push -u origin main

if [ $? -eq 0 ]; then
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════════╗"
    echo "║                    ✅ SUCCESS! PUSHED TO GITHUB                      ║"
    echo "╚══════════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "🎉 Your repository is now live at:"
    echo "   https://github.com/$GITHUB_USER/$REPO_NAME"
    echo ""
    echo "📚 Next steps:"
    echo "   1. Add topics/tags on GitHub (aws, data-engineering, glue, etc.)"
    echo "   2. Add a LICENSE file (MIT recommended)"
    echo "   3. Star the repository ⭐"
    echo "   4. Share with the community!"
    echo ""
else
    echo ""
    echo "❌ Push failed. Common issues:"
    echo "   • Repository not created on GitHub yet"
    echo "   • Wrong repository name (should be: $REPO_NAME)"
    echo "   • Authentication required (use GitHub token or SSH key)"
    echo ""
    echo "If you need to authenticate:"
    echo "   • Personal Access Token: https://github.com/settings/tokens"
    echo "   • SSH Key: https://github.com/settings/keys"
    echo ""
fi
