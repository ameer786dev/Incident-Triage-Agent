---
id: gateway-oom
title: gateway: Out of memory OOMKilled and heap exhaustion
service: gateway
cause: oom
---
# gateway: Out of memory OOMKilled and heap exhaustion

Owner: gateway on-call. Scope: public HTTP ingress and request routing. Primary impact: all storefront requests.

## Symptoms

Resident memory approaches its container limit, processes restart, and logs or container events report OOMKilled, allocation failure, or exit code 137.

## Distinguishing evidence

Compare memory RSS with the configured memory limit and restart count. Verify exit reason; exit 137 without memory pressure can have other causes. Inspect heap growth, request size, and cache cardinality.
Inspect ingress error rate, route latency, upstream health, and active requests. This service must route /work requests to checkout while preserving trace IDs; inspect checkout as part of the dependency boundary.

## Safe next steps

1. Shed oversized or nonessential requests and capture a bounded memory profile from a healthy replica.
2. Restore capacity with a known healthy replica or roll back a revision with confirmed increasing memory use.
3. Increase memory only after checking node headroom and setting an expiry for the temporary change.

Service-specific constraint: Gateway replicas are stateless; route and timeout configuration changes affect every request.

## Verify recovery

RSS stays below the limit with stable headroom, restart count stops growing, and representative requests succeed. Verify all storefront requests with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the service owner if memory grows monotonically or no safe replica has enough headroom; repeated restarts do not repair a leak. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
