---
id: checkout-cpu_saturation
title: checkout: CPU saturation and throttled workers
service: checkout
cause: cpu_saturation
---
# checkout: CPU saturation and throttled workers

Owner: checkout on-call. Scope: order orchestration. Primary impact: order placement and cart conversion.

## Symptoms

CPU utilization and throttled time are high, request duration increases, and worker queues grow without corresponding database or network latency.

## Distinguishing evidence

Compare CPU usage with quota, throttled periods, event-loop lag, queue depth, and request mix. Inspect a short CPU profile. Distinguish CPU-bound work from time waiting on a dependency.
Inspect order failures, dependency duration, pending reservations, and duplicate authorizations. This service must reserve stock and authorize payment before accepting an order; inspect payments and inventory as part of the dependency boundary.

## Safe next steps

1. Reduce optional expensive work and rate-limit the costly request class.
2. Scale workers only if downstream systems and node capacity have room.
3. Roll back a confirmed hot-loop regression or disable the responsible feature flag.

Service-specific constraint: An order can have a payment authorization even when the caller sees a timeout. Inspect its idempotency key before replay.

## Verify recovery

CPU throttling and queue depth decline, throughput recovers, and request p95 returns to baseline. Verify order placement and cart conversion with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the runtime owner when a profile shows a hot loop or scaling raises contention. Do not raise concurrency blindly. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
