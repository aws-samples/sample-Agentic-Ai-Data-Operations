# ASCII Stage Blocks

Every phase and numbered step announces itself with an ASCII block built by
`shared/utils/ascii_display` — never hand-drawn, so terminal output and
`trace_events.jsonl` stay identical at width 70.

- Default banner + summary → `stage_block(title, lines)`
- Auto-discovered findings → `discovery_block(title, findings)`
- Gates and checklists (e.g. Step 5.9's 7 checks) → `checklist_block(title, [(passed, name)])`
- Ontology entities → `entity_block(entities)`
- Q&A → `exchange_block(...)`, already emitted by `AgentTracer.log_exchange`

Title: `PHASE {n} - {NAME}` or `STEP {n.n} - {NAME}`, uppercase.

```text
+--------------------------------------------------------------------+
|  STEP 2.1 - DUPLICATE DETECTION                                    |
+--------------------------------------------------------------------+
|  * Scanned 3 workloads under workloads/                            |
|  * No source overlap found                                         |
|  * Proceeding to Step 2.2 connectivity check                       |
+--------------------------------------------------------------------+
```

Pure ASCII (`+ - | *`) only. Unicode box diagrams already in the prompts are reference
material to read, not output to emit — leave them as they are.
