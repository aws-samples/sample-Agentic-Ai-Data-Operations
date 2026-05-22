"""ASCII display layouts for agent exchanges, discovery, and trace output."""

MAX_WIDTH = 70


def _pad(text: str, width: int = MAX_WIDTH - 4) -> str:
    if len(text) > width:
        return text[: width - 1] + ">"
    return text.ljust(width)


def _box(label: str, lines: list[str]) -> str:
    border = "+" + "-" * (MAX_WIDTH - 2) + "+"
    rows = [border]
    rows.append("|  " + _pad(label) + "|")
    rows.append(border)
    for line in lines:
        rows.append("|  " + _pad(line) + "|")
    rows.append(border)
    return "\n".join(rows)


def query_block(question: str, source: str = "", user: str = "", ts: str = "") -> str:
    lines = [f'"{question}"']
    meta_parts = []
    if source:
        meta_parts.append(f"source: {source}")
    if user:
        meta_parts.append(f"user: {user}")
    if ts:
        meta_parts.append(f"ts: {ts}")
    if meta_parts:
        lines.append(" | ".join(meta_parts))
    return _box("QUERY", lines)


def response_block(
    summary: str, status: str = "OK", tokens: str = "", latency: str = "", cost: str = ""
) -> str:
    lines = [f">> {summary}"]
    lines.append(f"STATUS: {status}")
    stat_parts = []
    if tokens:
        stat_parts.append(f"tokens: {tokens}")
    if latency:
        stat_parts.append(f"latency: {latency}")
    if cost:
        stat_parts.append(f"cost: {cost}")
    if stat_parts:
        lines.append(" | ".join(stat_parts))
    return _box("AGENT RESPONSE", lines)


def exchange_block(
    question: str,
    summary: str,
    status: str = "OK",
    source: str = "",
    user: str = "",
    ts: str = "",
    tokens: str = "",
    latency: str = "",
    cost: str = "",
) -> str:
    q = query_block(question, source=source, user=user, ts=ts)
    connector = " " * 30 + "|\n" + " " * 30 + "v"
    r = response_block(summary, status=status, tokens=tokens, latency=latency, cost=cost)
    return f"{q}\n{connector}\n{r}"


def discovery_block(title: str, findings: list[str]) -> str:
    lines = []
    for f in findings:
        lines.append(f"* {f}")
    return _box(f"DISCOVERED: {title}", lines)


def entity_block(entities: list[dict]) -> str:
    lines = []
    row = ""
    for i, e in enumerate(entities):
        name = e.get("name", "?")
        cols = e.get("columns", 0)
        etype = e.get("type", "?")
        cell = f"[{name} ({cols} cols, {etype})]"
        if len(row) + len(cell) + 3 > MAX_WIDTH - 4:
            lines.append(row.rstrip())
            row = ""
        row += cell + "  "
    if row.strip():
        lines.append(row.rstrip())
    return _box("DISCOVERED ENTITIES", lines)


def checklist_block(title: str, items: list[tuple[bool, str]]) -> str:
    lines = []
    for done, text in items:
        mark = "x" if done else " "
        lines.append(f"[{mark}] {text}")
    return _box(title, lines)
