---
id: checkout-dependency_timeout
title: checkout: Dependency timeout and upstream request deadline
service: checkout
cause: dependency_timeout
---
# checkout: Dependency timeout and upstream request deadline

Owner: checkout on-call. Scope: order orchestration. Primary impact: order placement and cart conversion.

## Symptoms

Dependency request duration increases and caller deadlines expire. The caller can have normal CPU, memory, and database latency while the downstream service is slow.

## Distinguishing evidence

Follow the request trace into the named dependency, compare caller and callee duration, and check circuit-breaker state. If the callee has a specific database, DNS, or memory failure, attribute that root cause instead.
Inspect order failures, dependency duration, pending reservations, and duplicate authorizations. This service must reserve stock and authorize payment before accepting an order; inspect payments and inventory as part of the dependency boundary.

## Safe next steps

1. Inspect the named dependency and report the first failing hop with trace evidence.
2. Enable an existing safe fallback or circuit breaker and reduce retry amplification.
3. Use bounded retries only for idempotent operations; reconcile operations that may have completed after the deadline.

Service-specific constraint: An order can have a payment authorization even when the caller sees a timeout. Inspect its idempotency key before replay.

## Verify recovery

The dependency completes within budget, timeout rate returns to baseline, and in-flight requests drain. Verify order placement and cart conversion with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the downstream owner with the trace ID and failing time window. Do not increase every timeout without checking the end-to-end deadline. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
