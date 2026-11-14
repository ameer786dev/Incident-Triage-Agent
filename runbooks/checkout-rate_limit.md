---
id: checkout-rate_limit
title: checkout: Rate limit 429 and provider quota exhausted
service: checkout
cause: rate_limit
---
# checkout: Rate limit 429 and provider quota exhausted

Owner: checkout on-call. Scope: order orchestration. Primary impact: order placement and cart conversion.

## Symptoms

Responses include HTTP 429 or resource quota exceeded. Repeated retries can amplify request volume even when CPU, memory, and database latency are normal.

## Distinguishing evidence

Read Retry-After, quota headers, request rate, retry rate, and the identity or tenant being limited. Distinguish dependency quota from local ingress admission limits.
Inspect order failures, dependency duration, pending reservations, and duplicate authorizations. This service must reserve stock and authorize payment before accepting an order; inspect payments and inventory as part of the dependency boundary.

## Safe next steps

1. Honor Retry-After and apply exponential backoff with jitter and a finite retry budget.
2. Reduce duplicate traffic and queue only work that can safely wait.
3. Coordinate a temporary quota increase with the provider after verifying the expected traffic source.

Service-specific constraint: An order can have a payment authorization even when the caller sees a timeout. Inspect its idempotency key before replay.

## Verify recovery

The limited identity remains below quota, 429 rate falls, and queued work drains without a new retry spike. Verify order placement and cart conversion with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the dependency owner for sustained expected traffic. Never bypass tenant isolation or rotate credentials to evade a quota. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
