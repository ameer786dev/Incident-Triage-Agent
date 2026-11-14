---
id: checkout-connection_pool
title: checkout: Connection pool exhausted and acquisition wait
service: checkout
cause: connection_pool
---
# checkout: Connection pool exhausted and acquisition wait

Owner: checkout on-call. Scope: order orchestration. Primary impact: order placement and cart conversion.

## Symptoms

Pool utilization reaches its maximum and requests wait for a connection. Logs report pool exhausted, acquire timeout, or too many clients while database execution can remain fast.

## Distinguishing evidence

Measure pool active/max, pending acquisition count, acquisition wait, and database execution duration separately. Check leaked connections, long transactions, and total connections across replicas.
Inspect order failures, dependency duration, pending reservations, and duplicate authorizations. This service must reserve stock and authorize payment before accepting an order; inspect payments and inventory as part of the dependency boundary.

## Safe next steps

1. Find long-held or leaked connections and reduce admission of new database work.
2. Roll back a confirmed connection leak and ensure connections return to the pool in a finally block.
3. Adjust the pool limit only within the database connection budget; coordinate across all replicas.

Service-specific constraint: An order can have a payment authorization even when the caller sees a timeout. Inspect its idempotency key before replay.

## Verify recovery

Pending acquisitions drain, active connections return below the limit, and requests complete without acquisition timeouts. Verify order placement and cart conversion with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the database and service owners if the database connection budget is exhausted. Scaling replicas can worsen connection exhaustion. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
