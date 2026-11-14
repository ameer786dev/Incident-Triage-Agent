---
id: inventory-db_timeout
title: inventory: Database query timeout and lock contention
service: inventory
cause: db_timeout
---
# inventory: Database query timeout and lock contention

Owner: inventory on-call. Scope: stock availability and reservation. Primary impact: stock checks and reservation confirmation.

## Symptoms

Database query duration and lock wait increase. Logs contain statement timeout, query deadline exceeded, or canceling statement. Application CPU may remain normal.

## Distinguishing evidence

Read database latency, lock waits, slow-query samples, and the configured statement deadline. Distinguish a slow query from an exhausted application connection pool by checking pool utilization and acquisition wait.
Inspect reservation failures, stock query duration, lock waits, and expired holds. This service must read available stock and write short-lived reservations; inspect stock database as part of the dependency boundary.

## Safe next steps

1. Identify the blocking query or slow query fingerprint and its transaction age.
2. Ask the database owner to cancel the confirmed blocker or apply the documented index/query mitigation.
3. Reduce nonessential query load; use bounded retries with jitter only for idempotent operations.

Service-specific constraint: Check reservation IDs and expiry before retrying writes; avoid overselling through duplicate reservations.

## Verify recovery

Query p95 and lock wait return to baseline, the same operation completes, and timeout errors stop. Verify stock checks and reservation confirmation with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the database owner before terminating a transaction or changing a statement timeout. Increasing the timeout alone can increase congestion. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
