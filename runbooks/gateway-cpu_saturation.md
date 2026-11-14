---
id: gateway-cpu_saturation
title: gateway: CPU saturation and throttled workers
service: gateway
cause: cpu_saturation
---
# gateway: CPU saturation and throttled workers

Owner: gateway on-call. Scope: public HTTP ingress and request routing. Primary impact: all storefront requests.

## Symptoms

CPU utilization and throttled time are high, request duration increases, and worker queues grow without corresponding database or network latency.

## Distinguishing evidence

Compare CPU usage with quota, throttled periods, event-loop lag, queue depth, and request mix. Inspect a short CPU profile. Distinguish CPU-bound work from time waiting on a dependency.
Inspect ingress error rate, route latency, upstream health, and active requests. This service must route /work requests to checkout while preserving trace IDs; inspect checkout as part of the dependency boundary.

## Safe next steps

1. Reduce optional expensive work and rate-limit the costly request class.
2. Scale workers only if downstream systems and node capacity have room.
3. Roll back a confirmed hot-loop regression or disable the responsible feature flag.

Service-specific constraint: Gateway replicas are stateless; route and timeout configuration changes affect every request.

## Verify recovery

CPU throttling and queue depth decline, throughput recovers, and request p95 returns to baseline. Verify all storefront requests with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the runtime owner when a profile shows a hot loop or scaling raises contention. Do not raise concurrency blindly. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
