# How semantic.yaml Becomes a Knowledge Graph

**A visual guide to the transformation from YAML configuration to Neptune graph database.**

---

## Overview

The semantic layer transforms flat YAML configuration files into a rich, interconnected knowledge graph in Amazon Neptune. This enables semantic search, automatic SQL generation, and intelligent query understanding.

---

## The Transformation Process

```
semantic.yaml (YAML)
    ↓
+ Glue Catalog (technical metadata)
    ↓
+ Lake Formation (LF-Tags)
    ↓
= UnifiedMetadataGraph (Python objects)
    ↓
+ Titan Embeddings (1024-dim vectors)
    ↓
= Neptune Knowledge Graph (vertices + edges + embeddings)
```

---

## Example: financial_portfolios Workload

### BEFORE: semantic.yaml (Flat Structure)

```yaml
workload: financial_portfolios
database: financial_portfolios_db

tables:
  - name: portfolios
    table_type: dimension
    grain: one row per portfolio
    primary_key: portfolio_id

    columns:
      - name: portfolio_id
        role: identifier
        type: bigint
        description: Unique portfolio identifier

      - name: portfolio_name
        role: attribute
        type: string
        description: Name of the portfolio
        business_terms: [Portfolio Name, Account Name]

      - name: region
        role: dimension
        type: string
        description: Geographic region
        sample_values: [North America, Europe, Asia Pacific]

  - name: positions
    table_type: fact
    grain: one row per position per date
    primary_key: [position_id, snapshot_date]

    relationships:
      - type: many_to_one
        target_table: portfolios
        join_column: portfolio_id
        target_column: portfolio_id

    columns:
      - name: position_id
        role: identifier
        type: bigint

      - name: portfolio_id
        role: identifier
        type: bigint
        description: Foreign key to portfolios

      - name: market_value
        role: measure
        type: decimal(18,2)
        default_aggregation: sum
        description: Current market value of position
        business_terms: [Market Value, Position Value, AUM]

      - name: snapshot_date
        role: temporal
        type: date
        description: Date of snapshot

seed_questions:
  - question: What is the total portfolio value?
    sql: |
      SELECT SUM(market_value) AS total_value
      FROM financial_portfolios_db.positions
    explanation: Sum all position market values
```

### AFTER: Neptune Graph (Interconnected Structure)

#### Vertices (Nodes)

```gremlin
// 1. Database vertex
g.addV('database')
  .property('name', 'financial_portfolios_db')
  .property('workload', 'financial_portfolios')

// 2. Table vertices
g.addV('table')
  .property('name', 'portfolios')
  .property('database', 'financial_portfolios_db')
  .property('type', 'dimension')
  .property('grain', 'one row per portfolio')
  .property('primary_key', 'portfolio_id')
  .property('embedding', '0.123,0.456,...')  // 1024 floats

g.addV('table')
  .property('name', 'positions')
  .property('database', 'financial_portfolios_db')
  .property('type', 'fact')
  .property('grain', 'one row per position per date')
  .property('primary_key', 'position_id,snapshot_date')
  .property('embedding', '0.789,0.012,...')

// 3. Column vertices
g.addV('column')
  .property('name', 'portfolio_id')
  .property('table', 'portfolios')
  .property('data_type', 'bigint')
  .property('role', 'identifier')
  .property('description', 'Unique portfolio identifier')
  .property('is_foreign_key', false)
  .property('embedding', '0.345,0.678,...')

g.addV('column')
  .property('name', 'market_value')
  .property('table', 'positions')
  .property('data_type', 'decimal(18,2)')
  .property('role', 'measure')
  .property('default_aggregation', 'sum')
  .property('description', 'Current market value')
  .property('pii_classification', 'NONE')  // from Lake Formation
  .property('embedding', '0.901,0.234,...')

g.addV('column')
  .property('name', 'portfolio_id')
  .property('table', 'positions')
  .property('data_type', 'bigint')
  .property('role', 'identifier')
  .property('is_foreign_key', true)
  .property('references', 'portfolios.portfolio_id')
  .property('embedding', '0.567,0.890,...')

// 4. Business term vertices
g.addV('business_term')
  .property('term', 'Market Value')
  .property('synonyms', 'Position Value,AUM')
  .property('description', 'Current market value of position')
  .property('embedding', '0.123,0.456,...')

g.addV('business_term')
  .property('term', 'Portfolio Name')
  .property('synonyms', 'Account Name')
  .property('embedding', '0.789,0.012,...')

// 5. Query vertices (from seed_questions)
g.addV('query')
  .property('query_id', 'query_abc123')
  .property('nl_text', 'What is the total portfolio value?')
  .property('sql', 'SELECT SUM(market_value)...')
  .property('workload', 'financial_portfolios')
  .property('tables_used', 'positions')
  .property('embedding', '0.345,0.678,...')
```

#### Edges (Relationships)

```gremlin
// Database → Table
g.V(db_id).addE('contains').to(g.V(portfolios_table_id))
g.V(db_id).addE('contains').to(g.V(positions_table_id))

// Table → Column
g.V(portfolios_table_id).addE('has_column').to(g.V(portfolio_id_col_id))
g.V(portfolios_table_id).addE('has_column').to(g.V(portfolio_name_col_id))
g.V(positions_table_id).addE('has_column').to(g.V(market_value_col_id))

// Column → Column (Foreign Key)
g.V(positions_portfolio_id_col_id)
  .addE('references')
  .to(g.V(portfolios_portfolio_id_col_id))
  .property('relationship_type', 'foreign_key')

// Column → Business Term
g.V(market_value_col_id)
  .addE('described_by')
  .to(g.V(market_value_term_id))

g.V(portfolio_name_col_id)
  .addE('described_by')
  .to(g.V(portfolio_name_term_id))

// Query → Table
g.V(query_id).addE('uses').to(g.V(positions_table_id))
```

---

## Visual Representation

### YAML Structure (Flat)

```
workload
├── tables[]
│   ├── name
│   ├── columns[]
│   │   ├── name
│   │   ├── role
│   │   └── business_terms[]
│   ├── relationships[]
│   └── seed_questions[]
└── business_terms[]
```

### Neptune Graph (Interconnected)

```
                    ┌──────────────┐
                    │   Database   │
                    │  portfolios  │
                    │      _db     │
                    └───────┬──────┘
                            │
                   ┌────────┴────────┐
                   │                 │
           ┌───────▼────────┐ ┌─────▼────────┐
           │     Table      │ │    Table     │
           │   portfolios   │ │  positions   │
           │  (dimension)   │ │    (fact)    │
           └───────┬────────┘ └─────┬────────┘
                   │                 │
        ┌──────────┼────────┐        │
        │          │        │        │
  ┌─────▼───┐ ┌───▼────┐ ┌─▼────────▼───┐
  │ Column  │ │ Column │ │   Column     │
  │portfolio│ │portfolio│ │ market_value │
  │  _id    │ │ _name  │ │   (measure)  │
  │   (PK)  │ │        │ │  agg: SUM    │
  └────┬────┘ └───┬────┘ └──────┬───────┘
       │          │              │
       │     ┌────▼──────┐ ┌─────▼─────────┐
       │     │  Business │ │   Business    │
       │     │   Term    │ │     Term      │
       │     │ Portfolio │ │ Market Value  │
       │     │   Name    │ │               │
       │     └───────────┘ └───────────────┘
       │
       │ (FK reference)
       └──────────────────┐
                          │
                    ┌─────▼────┐
                    │  Column  │
                    │portfolio │
                    │   _id    │
                    │  (FK)    │
                    └──────────┘
```

---

## Key Transformations

### 1. Tables → Vertices + Properties

**YAML:**
```yaml
- name: positions
  table_type: fact
  grain: one row per position per date
  primary_key: [position_id, snapshot_date]
```

**Neptune:**
```gremlin
g.addV('table')
  .property('name', 'positions')
  .property('type', 'fact')
  .property('grain', 'one row per position per date')
  .property('primary_key', 'position_id,snapshot_date')
  .property('embedding', [1024 floats from Titan])
```

### 2. Columns → Vertices + Role Properties

**YAML:**
```yaml
- name: market_value
  role: measure
  type: decimal(18,2)
  default_aggregation: sum
  description: Current market value
```

**Neptune:**
```gremlin
g.addV('column')
  .property('name', 'market_value')
  .property('data_type', 'decimal(18,2)')
  .property('role', 'measure')
  .property('default_aggregation', 'sum')
  .property('description', 'Current market value')
  .property('pii_classification', 'NONE')  // from LF
  .property('embedding', [1024 floats])
```

### 3. Relationships → Edges

**YAML:**
```yaml
relationships:
  - type: many_to_one
    target_table: portfolios
    join_column: portfolio_id
    target_column: portfolio_id
```

**Neptune:**
```gremlin
// Mark column as FK
column.is_foreign_key = true
column.references = 'portfolios.portfolio_id'

// Create edge
g.V(positions_portfolio_id_col)
  .addE('references')
  .to(g.V(portfolios_portfolio_id_col))
  .property('relationship_type', 'foreign_key')
```

### 4. Business Terms → Vertices + Edges

**YAML:**
```yaml
columns:
  - name: market_value
    business_terms: [Market Value, Position Value, AUM]
```

**Neptune:**
```gremlin
// Create business term vertex
g.addV('business_term')
  .property('term', 'Market Value')
  .property('synonyms', 'Position Value,AUM')
  .property('embedding', [1024 floats])

// Link column to term
g.V(market_value_col)
  .addE('described_by')
  .to(g.V(market_value_term))
```

### 5. Seed Queries → Vertices (in SynoDB)

**YAML:**
```yaml
seed_questions:
  - question: What is the total portfolio value?
    sql: SELECT SUM(market_value) FROM positions
    explanation: Sum all position market values
```

**DynamoDB (SynoDB):**
```json
{
  "query_id": "query_abc123",
  "workload": "financial_portfolios",
  "nl_text": "What is the total portfolio value?",
  "sql": "SELECT SUM(market_value) FROM financial_portfolios_db.positions",
  "explanation": "Sum all position market values",
  "tables_used": ["positions"],
  "query_type": "seed",
  "success_count": 0,
  "embedding": [1024 floats from Titan]
}
```

---

## How Queries Use the Knowledge Graph

### Natural Language Query
> "What is the total portfolio value by region?"

### Step 1: Semantic Search (Vector Similarity)

```python
# Generate query embedding
query_embedding = titan.generate_embedding("total portfolio value by region")

# Find similar tables
tables = neptune.search(query_embedding)
# Returns: [(positions, 0.89), (portfolios, 0.76)]
```

### Step 2: Graph Traversal (Relationships)

```gremlin
// Get metadata for positions table
g.V('financial_portfolios_db.positions')
  .outE('has_column').inV()
  .valueMap()

// Returns:
// - market_value (measure, role=measure, agg=sum)
// - portfolio_id (FK to portfolios)
// - region (from portfolios via FK)

// Find join path
g.V('positions_table')
  .outE('has_column').inV()
  .has('is_foreign_key', true)
  .outE('references').inV()
  .inE('has_column').outV()

// Returns: positions → portfolios (via portfolio_id)
```

### Step 3: Metadata Retrieval

```python
metadata = {
  'positions': {
    'columns': [
      {'name': 'market_value', 'role': 'measure', 'agg': 'sum'},
      {'name': 'portfolio_id', 'role': 'identifier', 'is_fk': True}
    ],
    'relationships': [
      {'target': 'portfolios', 'on': 'portfolio_id'}
    ]
  },
  'portfolios': {
    'columns': [
      {'name': 'region', 'role': 'dimension'}
    ]
  }
}
```

### Step 4: Similar Queries (SynoDB)

```python
# Find similar past queries
similar = synodb.search("total portfolio value by region")

# Returns:
# 1. "What is the total portfolio value?" (similarity: 0.87)
#    SQL: SELECT SUM(market_value) FROM positions
# 2. "Show me revenue by region" (similarity: 0.73)
#    SQL: SELECT region, SUM(revenue) FROM sales GROUP BY region
```

### Step 5: SQL Generation (LLM)

```python
# LLM prompt includes:
# - Query intent (aggregation + group by)
# - Table metadata (measures, dimensions, FKs)
# - Similar queries (patterns)

# Generated SQL:
SELECT
  portfolios.region,
  SUM(positions.market_value) AS total_value
FROM financial_portfolios_db.positions
JOIN financial_portfolios_db.portfolios
  ON positions.portfolio_id = portfolios.portfolio_id
GROUP BY portfolios.region
ORDER BY total_value DESC
LIMIT 10000
```

---

## Graph Statistics for financial_portfolios

| Entity | Count | Example |
|--------|-------|---------|
| **Vertices** | | |
| Database | 1 | financial_portfolios_db |
| Tables | 3 | portfolios, positions, stocks |
| Columns | 25 | market_value, portfolio_id, region |
| Business Terms | 8 | Market Value, AUM, Portfolio Name |
| Queries (seed) | 8 | "What is total value?" |
| **Edges** | | |
| contains | 3 | database → table |
| has_column | 25 | table → column |
| references (FK) | 3 | positions.portfolio_id → portfolios.portfolio_id |
| described_by | 15 | market_value → Market Value term |
| uses | 8 | query → tables |
| **Embeddings** | 50 | 1024 dims each (Titan) |

---

## Benefits of Graph Structure

### 1. Semantic Search

**Without graph:**
- Keyword matching only
- "portfolio value" doesn't match "market_value" column

**With graph + embeddings:**
- Vector similarity: "portfolio value" → 0.89 match to "market_value"
- Synonym expansion via business terms: "AUM" = "Market Value"

### 2. Relationship Discovery

**Without graph:**
- Must manually specify JOINs
- Hard to find multi-hop paths

**With graph:**
- Automatic FK traversal: positions → portfolios → customers
- Find shortest join path between any tables

### 3. Metadata Enrichment

**Without graph:**
- Column names only
- No context about role or usage

**With graph:**
- Role metadata: measure vs dimension
- Default aggregations: SUM, AVG, COUNT
- PII classification from Lake Formation
- Business descriptions from semantic.yaml

### 4. Query Learning

**Without graph:**
- Each query is independent
- No learning from past queries

**With graph:**
- Similar queries via embeddings
- Success tracking (SynoDB)
- Pattern reuse

---

## Summary

### What Goes In

1. **semantic.yaml** - Business context (roles, aggregations, terms, relationships, seed queries)
2. **Glue Catalog** - Technical metadata (schemas, types, partitions, locations)
3. **Lake Formation** - Access control (LF-Tags for PII, sensitivity)

### What Comes Out

1. **Neptune Graph** - Interconnected vertices and edges
2. **Titan Embeddings** - 1024-dim vectors for semantic search
3. **SynoDB** - Query store with patterns

### What You Can Do

1. ✅ Ask natural language questions
2. ✅ Get automatically generated SQL
3. ✅ Search for relevant tables semantically
4. ✅ Discover join paths between tables
5. ✅ Find similar past queries
6. ✅ Navigate complex data models
7. ✅ Enforce PII access controls

---

## Try It Yourself

```bash
# 1. Load metadata to Neptune
python shared/semantic_layer/load_to_neptune.py \
  --workload financial_portfolios \
  --database financial_portfolios_db \
  --neptune-endpoint YOUR-NEPTUNE-ENDPOINT

# 2. Query the graph
python shared/semantic_layer/example_usage.py

# 3. Ask natural language questions
from shared.semantic_layer import execute_nl_query

result = execute_nl_query(
    "What is the total portfolio value by region?",
    workload="financial_portfolios",
    database="financial_portfolios_db",
    neptune_endpoint="YOUR-NEPTUNE-ENDPOINT",
    athena_database="financial_portfolios_db",
    s3_output_location="s3://bucket/results/"
)

print(result.sql)   # Generated SQL
print(result.rows)  # Query results
```

---

**Next**: See `QUICKSTART.md` for complete setup instructions.
