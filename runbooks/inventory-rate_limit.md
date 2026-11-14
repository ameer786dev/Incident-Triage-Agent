---
id: inventory-rate_limit
title: inventory: Rate limit 429 and provider quota exhausted
service: inventory
cause: rate_limit
---
# inventory: Rate limit 429 and provider quota exhausted

Owner: inventory on-call. Scope: stock availability and reservation. Primary impact: stock checks and reservation confirmation.

## Symptoms

Responses include HTTP 429 or resource quota exceeded. Repeated retries can amplify request volume even when CPU, memory, and database latency are normal.

## Distinguishing evidence

Read Retry-After, quota headers, request rate, retry rate, and the identity or tenant being limited. Distinguish dependency quota from local ingress admission limits.
Inspect reservation failures, stock query duration, lock waits, and expired holds. This service must read available stock and write short-lived reservations; inspect stock database as part of the dependency boundary.

## Safe next steps

1. Honor Retry-After and apply exponential backoff with jitter and a finite retry budget.
2. Reduce duplicate traffic and queue only work that can safely wait.
3. Coordinate a temporary quota increase with the provider after verifying the expected traffic source.

Service-specific constraint: Check reservation IDs and expiry before retrying writes; avoid overselling through duplicate reservations.

## Verify recovery

The limited identity remains below quota, 429 rate falls, and queued work drains without a new retry spike. Verify stock checks and reservation confirmation with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the dependency owner for sustained expected traffic. Never bypass tenant isolation or rotate credentials to evade a quota. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
