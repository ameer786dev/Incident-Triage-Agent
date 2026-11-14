---
id: gateway-rate_limit
title: gateway: Rate limit 429 and provider quota exhausted
service: gateway
cause: rate_limit
---
# gateway: Rate limit 429 and provider quota exhausted

Owner: gateway on-call. Scope: public HTTP ingress and request routing. Primary impact: all storefront requests.

## Symptoms

Responses include HTTP 429 or resource quota exceeded. Repeated retries can amplify request volume even when CPU, memory, and database latency are normal.

## Distinguishing evidence

Read Retry-After, quota headers, request rate, retry rate, and the identity or tenant being limited. Distinguish dependency quota from local ingress admission limits.
Inspect ingress error rate, route latency, upstream health, and active requests. This service must route /work requests to checkout while preserving trace IDs; inspect checkout as part of the dependency boundary.

## Safe next steps

1. Honor Retry-After and apply exponential backoff with jitter and a finite retry budget.
2. Reduce duplicate traffic and queue only work that can safely wait.
3. Coordinate a temporary quota increase with the provider after verifying the expected traffic source.

Service-specific constraint: Gateway replicas are stateless; route and timeout configuration changes affect every request.

## Verify recovery

The limited identity remains below quota, 429 rate falls, and queued work drains without a new retry spike. Verify all storefront requests with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the dependency owner for sustained expected traffic. Never bypass tenant isolation or rotate credentials to evade a quota. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
