# Mal Unified Payment Data: Architecture and Migration Strategy

*Companion to the Part 1 implementation. Context: Mal is a UAE-based, Shariah-compliant, multi-product neobank. Three product squads (Cards, Transfers, Bill Payments) each shipped their own payment event pipeline with divergent schemas. This document covers how we converge on one canonical model and roll it out across squads without stalling their roadmaps.*

---

## 1. Canonical Entity Design Rationale

**Why this schema structure.** I modelled a single `PaymentEvent` entity rather than a table per product. Every payment Mal processes, whether a card swipe at Carrefour, a P2P transfer, or a DEWA bill, shares the same spine: who paid, how much, in what currency, what state it ended in, and when. Forcing all three squads onto that spine is what lets a downstream analyst answer "what did customer X spend across all products this month" with one query instead of three joins against three vocabularies. The squad-specific fields that genuinely differ (merchant MCC for cards, purpose code for transfers, biller category for bills) live in an open `attributes` map, so they survive without polluting the core contract.

**How it handles extensibility.** Adding a future payment type, such as wallet top-ups, salary disbursement, or a buy-now-pay-later product, requires exactly two things: a new value in the `PaymentType` enum and a new source mapper. The canonical table, every downstream query, and the dashboard are untouched. The `attributes` map absorbs new source fields with zero schema migration, and new enum values are a non-breaking change under the governance rules in Section 3. This is the core of platform thinking: the cost of onboarding source N+1 is a single mapper file, not a new pipeline.

**Trade-offs (simplicity vs completeness).** I deliberately kept the core narrow. I did not model a full double-entry ledger, multi-leg settlement, or FX conversion lineage. Those belong in a finance or ledger domain, not the payment-event lake, and modelling them prematurely would have made every squad's mapper heavier and slowed adoption. I chose a flat event over a deeply normalised model because analysts query flat tables far more easily and columnar storage makes the width cheap. The Shariah dimension is treated as first-class (`fee_amount` plus `is_shariah_compliant`) rather than buried in `attributes`, because for an Islamic bank the distinction between profit or fee and interest is a compliance requirement, not an optional attribute. Getting that wrong is a regulatory issue with the Higher Shariah Authority, not just a data-quality one.

---

## 2. Phased Migration Plan

The constraint that shapes everything: the three squads are mid-roadmap and will resist anything that looks like "stop your work to adopt our thing." So the plan is additive first, cutover last. The canonical pipeline runs alongside existing pipelines until trust is earned, and no squad is asked to delete anything until their data is provably reconciled.

### Day 0 to 30: prove it on one squad (no squad disruption)
- Stand up the canonical pipeline reading copies of the three raw feeds. Squads change nothing; we consume what they already emit.
- Pick Bill Payments as the pilot. Rationale: it is the simplest schema (clean status codes, single party, no FX), lowest transaction volume, and lowest blast radius if something is wrong, so we de-risk the pattern before touching the higher-stakes Cards feed.
- Publish the canonical table read-only and reconcile it against the squad's own numbers daily. Milestone: 100% row and value reconciliation on Bill Payments for 7 consecutive days.
- Deliverable: the data contract (Section 3) signed off by the pilot squad lead.

### Day 30 to 60: onboard the remaining squads
- Add the Transfers mapper, then Cards (highest volume and the FX or multi-currency edge cases, so it goes last with the most reconciliation scrutiny).
- Run all three in parallel with existing pipelines; downstream consumers can start migrating queries to the unified table while old tables still exist (backward compatibility, below).
- Milestone: all three squads reconciled; first two downstream consumers (for example Finance reporting and Growth analytics) cut over to `payment_events`.

### Day 60 to 90: cutover and decommission
- Migrate remaining downstream consumers. Announce a deprecation date for the three legacy tables (not a deletion, a freeze).
- Squads point their producers at the canonical schema directly. They can emit canonical, or emit raw and let us own the mapper. The squad's choice lowers their lift.
- Milestone: legacy payment tables frozen read-only; over 80% of payment queries running on the unified model; one squad fully producing canonical.

### Backward compatibility during transition
Old and new run in parallel for the full 90 days. Legacy tables are never dropped before a deprecation window closes; they are frozen, then retired. For schema evolution, v1 records remain readable via the `migrate_v1_to_v2` upgrade path (shown in Part 1) so the lake presents one current shape even while producers migrate at different speeds.

### Dependency management across squads
Each squad owns its mapper, the data platform team owns the canonical contract. This keeps the dependency one-directional: squads depend on a stable contract, not on each other. Contract changes go through the governance process in Section 3 so no squad can break another. A shared CI check (the validation step from Part 1) runs on every squad's mapper PR, so a malformed change is caught before it reaches the lake.

---

## 3. Data Contract and Governance

**Versioning, breaking vs non-breaking.** The contract uses semantic versioning with a clear, enforced rule:
- Non-breaking (minor bump): adding an optional field with a default, adding a new enum value, widening a type. Ships freely; consumers are unaffected.
- Breaking (major bump): removing or renaming a field, making an optional field required, changing a field's type or meaning. Requires a migration function (for example `migrate_v1_to_v2`), a deprecation window, and consumer sign-off before the old version is retired.

**Schema validation enforcement points.** Validation runs at three gates: (1) ingestion, where every row is validated against the Pydantic contract and failures are quarantined with a reason rather than silently dropped; (2) CI, where each squad's mapper PR runs the validator against sample data so contract violations fail the build; (3) monitoring, where the DQ dashboard surfaces per-source compliance rate continuously, so drift is visible even when individual rows pass.

**Ownership model.** The data platform team owns the canonical contract and is the approver for any breaking change. Each squad owns its source mapper and its raw feed. Breaking changes require a written proposal, a migration path, and sign-off from every affected downstream consumer plus the platform lead. This is a lightweight RFC, not a committee. The split means squads keep autonomy over their own data while the shared contract stays stable. For an Islamic bank, the `is_shariah_compliant` and fee or profit fields carry an additional sign-off from Shariah compliance, because changing their semantics is a regulatory matter.

---

## 4. Adoption Metrics and Stakeholder Plan

**KPIs for the reuse program (3 to 5):**
1. Query consolidation rate: the percentage of payment-related analytics queries running against `payment_events` vs legacy tables. Target: over 80% by day 90. This is the truest measure that the platform is actually being reused.
2. Schema compliance rate per source: the percentage of rows passing the contract, tracked on the dashboard. Target: over 99% sustained.
3. Time-to-onboard a new source: engineering days to add a new payment type. Target: under 1 day (one mapper). This proves extensibility is real, not aspirational.
4. Reconciliation accuracy: the variance between canonical totals and each squad's source-of-truth. Target: 0 during parallel-run. This is what earns squad trust.
5. Incident reduction: payment-data incidents per quarter caused by schema drift. Expected to fall as validation moves drift detection from "discovered by an angry analyst" to "caught in CI."

**Communication plan for cross-team buy-in.** Lead with the squads' own pain, not platform purity. Every squad currently re-answers "how does my product compare to the others" by hand. A short demo showing one query spanning all three products, built in front of them on their real data, does more than a design doc. Run a fortnightly 30-minute sync during the 90 days, keep a single Slack channel for contract questions, and publish the reconciliation dashboard openly so progress (and the platform team's own honesty about gaps) is visible.

**Handling resistance from squads with existing pipelines.** The legitimate fear is "this slows my roadmap." The plan neutralises it structurally: (1) squads change nothing in phase one, since we consume their existing feeds; (2) the platform team writes the initial mappers, so the squad's lift is review, not build; (3) parallel-run means no risky big-bang cutover; (4) we onboard the easiest, most willing squad first and let its win create pull from the others rather than pushing top-down. Where a squad still resists, the escalation is to the metric: if their data stays siloed, they are the ones who cannot answer the cross-product questions leadership asks. Make the cost of non-adoption visible rather than mandating adoption.

---

## 5. Production Considerations

**What changes at 100K transactions per day.** The Part 1 stack (DuckDB, Parquet, plain Python) is the right minimal choice to prove the model, but at 100K per day (roughly 1.2M or more events per week) I would change: (1) the warehouse, moving from a local DuckDB file to a managed columnar warehouse (Snowflake or BigQuery) for concurrency and storage scale, keeping the exact same canonical schema so nothing downstream changes; (2) ingestion, moving from batch CSV reads to streaming or micro-batch (for example Kafka into a consumer running the same mappers), since card authorisations are latency-sensitive; (3) partitioning, partitioning the event table by `event_date` and clustering by `source_system` so queries prune effectively; (4) orchestration, replacing plain Python with a scheduler (Airflow or Dagster) for retries, backfills, and dependency-aware runs.

**Monitoring and alerting strategy.** Promote the three dashboard checks to active alerts: (1) a freshness SLA that alerts if a source has not ingested within its expected window. Card volume is steady, but bill payments are bursty around month-end, so thresholds are per-source. (2) a compliance drop that pages if any source's schema compliance falls below threshold, which almost always signals an unannounced producer change. (3) a volume anomaly that alerts on deviation from a rolling baseline, with the baseline made seasonality-aware for the UAE context. Ramadan and Eid drive large, expected spikes, and the Friday to Saturday weekend shifts daily patterns, so a naive day-over-day rule would false-alarm constantly. Route alerts to the owning squad, not a central inbox, so the team that can fix it is the team that hears about it.

**What I intentionally cut from Part 1, and why.** No real ledger or double-entry modelling (belongs in the finance domain), no FX-rate lineage (a separate reference dataset), no PII tokenisation or field-level encryption (essential in production under CBUAE data and outsourcing rules, but out of scope for a local mock), no incremental or CDC loading (full-rebuild is fine at a few thousand rows, wrong at 1.2M per week), and no real orchestration. Each cut is a conscious simplicity vs completeness trade. Part 1 exists to prove the canonical model and the onboarding pattern are sound; production hardening is the deliberate next layer, not an oversight.
