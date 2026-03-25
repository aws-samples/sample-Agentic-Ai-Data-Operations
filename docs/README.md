# Documentation Folder

This folder contains actively referenced documentation and diagrams for the Agentic Data Onboarding System.

## Contents

### Architecture Diagrams

| File | Purpose | Referenced In |
|------|---------|---------------|
| `Architecture-Diagram.png` | 4-agent architecture diagram (exported PNG) | README.md |
| `architecture.excalidraw` | Architecture diagram source (editable) | - |
| `flow.excalidraw` | Workflow diagram source (editable) | - |

**To update diagrams**:
1. Edit `.excalidraw` files at https://excalidraw.com
2. Export to PNG
3. Replace `Architecture-Diagram.png`

### Documentation

| File | Purpose | Referenced In |
|------|---------|---------------|
| `aws-account-setup.md` | AWS infrastructure setup guide | CLAUDE.md (5 refs) |
| `getting-started.md` | Quick start guide | README.md (2 refs) |
| `governance-framework.md` | Data governance framework | Multiple files (12 refs) |
| `governance-integration-example.md` | Governance integration examples | Multiple files (6 refs) |
| `mcp-integration.md` | MCP integration patterns | CLAUDE.md (1 ref) |
| `mcp-servers.md` | MCP server architecture | CLAUDE.md (1 ref) |

### Utilities

| File | Purpose |
|------|---------|
| `export.sh` | Export Excalidraw diagrams to PNG (automated) |

### Examples

| Folder | Purpose |
|--------|---------|
| `logging_examples/` | Example logging output (trace events, cognitive maps) |

## Diagram Export

To export updated diagrams:

```bash
# Option 1: Automated (requires npx)
./export.sh

# Option 2: Manual
# 1. Open https://excalidraw.com
# 2. Load architecture.excalidraw or flow.excalidraw
# 3. Export to PNG
# 4. Save as Architecture-Diagram.png or prompt-flow.png
```

## Maintenance

This folder has been cleaned to contain **only actively referenced files**. Before adding new files:

1. Ensure they're referenced in repo documentation
2. Use descriptive filenames
3. Update this README

**Last cleanup**: March 24, 2026
