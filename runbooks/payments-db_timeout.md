---
id: payments-db_timeout
title: payments: Database query timeout and lock contention
service: payments
cause: db_timeout
---
# payments: Database query timeout and lock contention

Owner: payments on-call. Scope: payment authorization. Primary impact: card authorizations and order completion.

## Symptoms

Database query duration and lock wait increase. Logs contain statement timeout, query deadline exceeded, or canceling statement. Application CPU may remain normal.

## Distinguishing evidence

Read database latency, lock waits, slow-query samples, and the configured statement deadline. Distinguish a slow query from an exhausted application connection pool by checking pool utilization and acquisition wait.
Inspect authorization success, provider latency, ledger query time, and retry count. This service must authorize charges using a stable idempotency key; inspect payment provider and payment ledger as part of the dependency boundary.

## Safe next steps

1. Identify the blocking query or slow query fingerprint and its transaction age.
2. Ask the database owner to cancel the confirmed blocker or apply the documented index/query mitigation.
3. Reduce nonessential query load; use bounded retries with jitter only for idempotent operations.

Service-specific constraint: Never blindly retry a charge. Reconcile the provider authorization ID and ledger entry first.

## Verify recovery

Query p95 and lock wait return to baseline, the same operation completes, and timeout errors stop. Verify card authorizations and order completion with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the database owner before terminating a transaction or changing a statement timeout. Increasing the timeout alone can increase congestion. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
