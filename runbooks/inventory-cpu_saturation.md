---
id: inventory-cpu_saturation
title: inventory: CPU saturation and throttled workers
service: inventory
cause: cpu_saturation
---
# inventory: CPU saturation and throttled workers

Owner: inventory on-call. Scope: stock availability and reservation. Primary impact: stock checks and reservation confirmation.

## Symptoms

CPU utilization and throttled time are high, request duration increases, and worker queues grow without corresponding database or network latency.

## Distinguishing evidence

Compare CPU usage with quota, throttled periods, event-loop lag, queue depth, and request mix. Inspect a short CPU profile. Distinguish CPU-bound work from time waiting on a dependency.
Inspect reservation failures, stock query duration, lock waits, and expired holds. This service must read available stock and write short-lived reservations; inspect stock database as part of the dependency boundary.

## Safe next steps

1. Reduce optional expensive work and rate-limit the costly request class.
2. Scale workers only if downstream systems and node capacity have room.
3. Roll back a confirmed hot-loop regression or disable the responsible feature flag.

Service-specific constraint: Check reservation IDs and expiry before retrying writes; avoid overselling through duplicate reservations.

## Verify recovery

CPU throttling and queue depth decline, throughput recovers, and request p95 returns to baseline. Verify stock checks and reservation confirmation with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the runtime owner when a profile shows a hot loop or scaling raises contention. Do not raise concurrency blindly. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
