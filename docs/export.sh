#!/bin/bash
# Export Excalidraw diagrams to PNG

cd "$(dirname "$0")"

echo "========================================="
echo "Exporting Excalidraw Diagrams to PNG"
echo "========================================="
echo

# Check if excalidraw-cli is available
if command -v excalidraw-cli &> /dev/null; then
    echo "Using: excalidraw-cli"
    excalidraw-cli export architecture.excalidraw \
      --output Architecture-Diagram.png \
      --scale 2 \
      --background-color white

    excalidraw-cli export flow.excalidraw \
      --output prompt-flow.png \
      --scale 2 \
      --background-color white

    echo "✓ Diagrams exported successfully"
    ls -lh Architecture-Diagram.png prompt-flow.png

elif command -v npx &> /dev/null; then
    echo "Using: npx @excalidraw/cli"
    npx @excalidraw/cli export architecture.excalidraw \
      --output Architecture-Diagram.png \
      --scale 2 \
      --background-color white

    npx @excalidraw/cli export flow.excalidraw \
      --output prompt-flow.png \
      --scale 2 \
      --background-color white

    echo "✓ Diagrams exported successfully"
    ls -lh Architecture-Diagram.png prompt-flow.png

else
    echo "⚠️  No excalidraw-cli found"
    echo
    echo "To export diagrams, choose one of these options:"
    echo
    echo "Option 1: Install excalidraw-cli globally"
    echo "  npm install -g @excalidraw/cli"
    echo "  Then run: ./docs/export.sh"
    echo
    echo "Option 2: Use npx (no install needed)"
    echo "  npx @excalidraw/cli export docs/architecture.excalidraw -o docs/Architecture-Diagram.png"
    echo
    echo "Option 3: Export manually (easiest)"
    echo "  1. Open https://excalidraw.com"
    echo "  2. Load docs/architecture.excalidraw"
    echo "  3. Click export → PNG"
    echo "  4. Save as docs/Architecture-Diagram.png"
    echo "  5. Repeat for docs/flow.excalidraw → docs/prompt-flow.png"
    echo
    echo "See docs/UPDATE_DIAGRAMS.md for full instructions"
    echo
    exit 1
fi

echo
echo "========================================="
echo "Export Complete"
echo "========================================="
echo
echo "Next steps:"
echo "1. Verify PNGs show 4-agent architecture"
echo "2. Commit changes:"
echo "   git add docs/*.excalidraw docs/*.png"
echo "   git commit -m 'Update diagrams to show 4-agent architecture'"
