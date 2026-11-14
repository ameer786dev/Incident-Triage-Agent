---
id: gateway-healthy
title: gateway: Healthy service and stale alert verification
service: gateway
cause: healthy
---
# gateway: Healthy service and stale alert verification

Owner: gateway on-call. Scope: public HTTP ingress and request routing. Primary impact: all storefront requests.

## Symptoms

Request error rate, latency, CPU, memory, storage, and dependency checks are within the service baseline. There are no corroborating recent failures.

## Distinguishing evidence

Check the alert evaluation timestamp, service labels, current time window, and successful representative requests. Missing telemetry is not evidence of health.
Inspect ingress error rate, route latency, upstream health, and active requests. This service must route /work requests to checkout while preserving trace IDs; inspect checkout as part of the dependency boundary.

## Safe next steps

1. Verify that metrics and logs are fresh and correspond to the alerted service and environment.
2. Check a representative request and compare the alert window with the current window.
3. Record a recovered or stale alert only when fresh telemetry supports it; otherwise escalate as insufficient evidence.

Service-specific constraint: Gateway replicas are stateless; route and timeout configuration changes affect every request.

## Verify recovery

Fresh telemetry and successful requests consistently show normal operation across two windows. Verify all storefront requests with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate when data is missing, stale, contradictory, or a user reports impact despite normal aggregate metrics. Do not perform rollback or restart based only on a stale page. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
