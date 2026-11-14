---
id: gateway-dependency_timeout
title: gateway: Dependency timeout and upstream request deadline
service: gateway
cause: dependency_timeout
---
# gateway: Dependency timeout and upstream request deadline

Owner: gateway on-call. Scope: public HTTP ingress and request routing. Primary impact: all storefront requests.

## Symptoms

Dependency request duration increases and caller deadlines expire. The caller can have normal CPU, memory, and database latency while the downstream service is slow.

## Distinguishing evidence

Follow the request trace into the named dependency, compare caller and callee duration, and check circuit-breaker state. If the callee has a specific database, DNS, or memory failure, attribute that root cause instead.
Inspect ingress error rate, route latency, upstream health, and active requests. This service must route /work requests to checkout while preserving trace IDs; inspect checkout as part of the dependency boundary.

## Safe next steps

1. Inspect the named dependency and report the first failing hop with trace evidence.
2. Enable an existing safe fallback or circuit breaker and reduce retry amplification.
3. Use bounded retries only for idempotent operations; reconcile operations that may have completed after the deadline.

Service-specific constraint: Gateway replicas are stateless; route and timeout configuration changes affect every request.

## Verify recovery

The dependency completes within budget, timeout rate returns to baseline, and in-flight requests drain. Verify all storefront requests with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the downstream owner with the trace ID and failing time window. Do not increase every timeout without checking the end-to-end deadline. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
