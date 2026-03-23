# Visual Prompt Workflow Guide

## 🔄 Progressive Onboarding Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│ START: I have data to onboard                                    │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ ROUTE: Check Existing Source                                      │
│                                                                   │
│ Prompt: "Check if data from [SOURCE] has been onboarded..."      │
│ Time: 2-5 min                                                     │
└─────────────────────────────┬───────────────────────────────────┘
                              │
            ┌─────────────────┴─────────────────┐
            │                                   │
            ▼                                   ▼
┌────────────────────────┐       ┌────────────────────────────────┐
│ FOUND                  │       │ NOT FOUND                      │
│                        │       │                                │
│ Options:               │       │ Ready to onboard!              │
│ - Use existing         │       │ Go to ONBOARD ──────┐         │
│ - Modify it            │       │                      │         │
│ - Complete partial     │       │                      │         │
└────────────────────────┘       └──────────────────────┼─────────┘
                                                        │
                                                        ▼
                              ┌─────────────────────────────────────┐
                              │ ONBOARD: Build Data Pipeline        │
                              │                                     │
                              │ Prompt: "Onboard [NAME]..."         │
                              │ Creates: Bronze→Silver→Gold         │
                              │ Time: 30-60 min                     │
                              │ Output: Full workload + 50+ tests   │
                              └─────────────┬───────────────────────┘
                                            │
                              ┌─────────────┴────────────────┐
                              │ Tests: pytest tests/ -v       │
                              │ Expected: 50+ passing ✓       │
                              └─────────────┬────────────────┘
                                            │
                    ┌───────────────────────┼────────────────────────┐
                    │                       │                        │
                    ▼                       ▼                        ▼
        ┌────────────────────┐  ┌──────────────────────┐  ┌─────────────────┐
        │ ENRICH: Link       │  │ CONSUME: Create      │  │ GOVERN: Trace   │
        │ FK Relationship    │  │ Dashboard            │  │ Lineage         │
        │                    │  │                      │  │                 │
        │ Link to another    │  │ QuickSight visuals   │  │ Document flow   │
        │ dataset via FK     │  │ for stakeholders     │  │ for governance  │
        │                    │  │                      │  │                 │
        │ Time: 15-20 min    │  │ Time: 20-30 min      │  │ Time: 10-15 min │
        └────────────────────┘  └──────────────────────┘  └─────────────────┘
```

---

## 🎲 Demo Workflow (No Real Data)

```
┌────────────────────────────────────────────────────────────────┐
│ START: Need demo/test data                                      │
└────────────────────────┬───────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│ GENERATE: Create Synthetic Data (Table 1)                      │
│                                                                 │
│ Example: customers (100 rows)                                  │
│ Output: shared/fixtures/customers.csv                           │
│ Time: 10-15 min                                                 │
└────────────────────────┬───────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│ GENERATE: Create Synthetic Data (Table 2)                      │
│                                                                 │
│ Example: orders (300 rows, FK to customers)                    │
│ Output: shared/fixtures/orders.csv                              │
│ Time: 10-15 min                                                 │
└────────────────────────┬───────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│ ONBOARD: Build customers pipeline → customer_master workload   │
│ Time: 30-60 min                                                 │
└────────────────────────┬───────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│ ONBOARD: Build orders pipeline → order_transactions workload   │
│ Time: 30-60 min                                                 │
└────────────────────────┬───────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│ ENRICH: Link FK relationship (orders → customers)               │
│ Time: 15-20 min                                                 │
└────────────────────────┬───────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│ CONSUME: Create unified dashboard (customer + order metrics)   │
│ Time: 20-30 min                                                 │
└────────────────────────┬───────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│ DONE: Complete demo ready                                       │
│ - Synthetic data (reproducible with seed)                       │
│ - Two workloads (customers, orders)                             │
│ - FK relationship validated                                     │
│ - Dashboard with 5+ visuals                                     │
│ - 100+ tests passing                                            │
└────────────────────────────────────────────────────────────────┘
```

---

## 🏭 Production Onboarding Workflow

```
Day 1: Onboard primary dataset
├─ ROUTE: Check existing
├─ ONBOARD: Build main dataset pipeline (e.g., customer_master)
├─ Validate: Run tests, check quality
├─ Deploy: Deploy to MWAA (deploy_to_aws.py --mwaa-bucket=BUCKET or manual S3 upload)
└─ Verify: Post-Deployment Verification (8 smoke tests: Glue, Athena, LF-Tags, TBAC, KMS, MWAA, QuickSight, CloudTrail)

Day 2: Onboard related dataset
├─ ROUTE: Check existing
├─ ONBOARD: Build related dataset pipeline (e.g., order_transactions)
├─ ENRICH: Link FK relationship to customer_master
├─ Validate: Test FK integrity, cross-workload DAG dependencies
├─ Deploy: Deploy to MWAA (Airflow DAG with ExternalTaskSensor)
└─ Verify: Post-Deployment Verification

Day 3: Enable self-service analytics
├─ CONSUME: Create QuickSight dashboard (customer + order metrics)
├─ Grant permissions to business users
└─ Schedule SPICE refresh

Day 4: Governance documentation
├─ GOVERN: Trace lineage (both workloads)
├─ Generate data_product_catalog.yaml
├─ Share with compliance/governance team
└─ Document in data catalog
```

---

## 🔀 Pattern Combinations

### Minimal Onboarding
```
ROUTE (Check) → ONBOARD (Build)
```
Result: Single workload, Bronze→Silver→Gold, ready to query

---

### With Relationships
```
ROUTE → ONBOARD (Dataset A) → ONBOARD (Dataset B) → ENRICH (Link A→B)
```
Result: Two workloads with validated FK relationship

---

### With Visualization
```
ROUTE → ONBOARD → CONSUME (Dashboard)
```
Result: Workload + business-user-friendly dashboard

---

### Full Production
```
ROUTE → ONBOARD → ENRICH → CONSUME → GOVERN
```
Result: Workload + relationships + dashboard + governance docs

---

### Demo Setup
```
GENERATE (data 1) → GENERATE (data 2) → ONBOARD → ONBOARD → ENRICH → CONSUME
```
Result: Complete demo with synthetic data

---

## 📊 Decision Tree

```
Do I have real data?
├─ YES
│  └─ Has it been onboarded?
│     ├─ YES → Use existing or modify (ROUTE will tell you)
│     └─ NO → Onboard it (ONBOARD)
│
└─ NO (need demo data)
   └─ Generate synthetic data (GENERATE)
      └─ Then onboard (ONBOARD)

Is my data related to another dataset?
├─ YES → Add relationship (ENRICH)
└─ NO → Skip ENRICH

Do stakeholders need dashboards?
├─ YES → Create QuickSight dashboard (CONSUME)
└─ NO → Skip CONSUME

Does governance need documentation?
├─ YES → Generate lineage (GOVERN)
└─ NO → Skip GOVERN (but you'll need it eventually)

Does my data need regulatory compliance?
├─ YES → Regulation prompts loaded during ONBOARD Phase 1 (GDPR, CCPA, HIPAA, SOX, PCI DSS)
└─ NO → Skip regulation prompts (not loaded by default)

Ready to deploy to AWS?
└─ ONBOARD (03) → deploy_to_aws.py → MWAA deployment → verification (8 smoke tests)
```

---

## ⏱️ Time Estimates

| Pattern | First Use | Subsequent Uses |
|---------|-----------|-----------------|
| ROUTE: Check Existing | 2-5 min | 1-2 min |
| GENERATE: Create Data | 10-15 min | 5 min (reuse) |
| ONBOARD: Build Pipeline | 30-60 min | 20-30 min |
| ENRICH: Link Relationship | 15-20 min | 10 min |
| CONSUME: Create Dashboard | 20-30 min | 15 min |
| GOVERN: Trace Lineage | 10-15 min | 5 min |

**Total for complete onboarding**: 2-3 hours (first dataset), 1-2 hours (subsequent)

---

## 🎯 Quick Reference

**Starting point** → Always ROUTE (Check Existing)

**New data** → ONBOARD (Build Pipeline)

**Link datasets** → ENRICH (Link Relationship)

**Business users need access** → CONSUME (Dashboard)

**Audit/governance** → GOVERN (Lineage)

**Demo without real data** → GENERATE (Create Data) then ONBOARD

---

## 💡 Pro Tips

1. **ROUTE saves time**: Always check first. Finding an existing workload at 90% complete saves hours vs starting from scratch.

2. **GENERATE for testing**: Generate small synthetic datasets (100-500 rows) to test your pipeline logic before connecting to production.

3. **ONBOARD is iterative**: First onboarding doesn't need perfect quality rules. Get basic pipeline working, then refine.

4. **ENRICH before CONSUME**: Add relationships first, then dashboards can use joins in queries.

5. **GOVERN for new team members**: Lineage docs help new engineers understand data flow quickly.

6. **Copy-paste liberally**: Use `PROMPTS_EXAMPLES.md` as templates. No need to write from scratch.

7. **Test locally first**: Run `pytest tests/ -v` before deploying to AWS. Faster feedback loop.

8. **One pattern at a time**: Don't try to do ONBOARD+ENRICH+CONSUME in one prompt. Break it up, validate each step.

9. **Regulation prompts are optional**: `prompts/regulation/` contains compliance controls for GDPR, CCPA, HIPAA, SOX, PCI DSS. These are loaded ONLY when you select a regulation during ONBOARD Phase 1 discovery—not default.

10. **Deploy after build**: After ONBOARD completes and tests pass, deploy to MWAA using `deploy_to_aws.py` or manual S3 upload. Run 8 post-deployment smoke tests to verify Glue, Athena, LF-Tags, TBAC, KMS, MWAA, QuickSight, CloudTrail.
