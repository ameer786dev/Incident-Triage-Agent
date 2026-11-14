---
id: checkout-db_timeout
title: checkout: Database query timeout and lock contention
service: checkout
cause: db_timeout
---
# checkout: Database query timeout and lock contention

Owner: checkout on-call. Scope: order orchestration. Primary impact: order placement and cart conversion.

## Symptoms

Database query duration and lock wait increase. Logs contain statement timeout, query deadline exceeded, or canceling statement. Application CPU may remain normal.

## Distinguishing evidence

Read database latency, lock waits, slow-query samples, and the configured statement deadline. Distinguish a slow query from an exhausted application connection pool by checking pool utilization and acquisition wait.
Inspect order failures, dependency duration, pending reservations, and duplicate authorizations. This service must reserve stock and authorize payment before accepting an order; inspect payments and inventory as part of the dependency boundary.

## Safe next steps

1. Identify the blocking query or slow query fingerprint and its transaction age.
2. Ask the database owner to cancel the confirmed blocker or apply the documented index/query mitigation.
3. Reduce nonessential query load; use bounded retries with jitter only for idempotent operations.

Service-specific constraint: An order can have a payment authorization even when the caller sees a timeout. Inspect its idempotency key before replay.

## Verify recovery

Query p95 and lock wait return to baseline, the same operation completes, and timeout errors stop. Verify order placement and cart conversion with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the database owner before terminating a transaction or changing a statement timeout. Increasing the timeout alone can increase congestion. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
