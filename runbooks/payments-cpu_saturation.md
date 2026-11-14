---
id: payments-cpu_saturation
title: payments: CPU saturation and throttled workers
service: payments
cause: cpu_saturation
---
# payments: CPU saturation and throttled workers

Owner: payments on-call. Scope: payment authorization. Primary impact: card authorizations and order completion.

## Symptoms

CPU utilization and throttled time are high, request duration increases, and worker queues grow without corresponding database or network latency.

## Distinguishing evidence

Compare CPU usage with quota, throttled periods, event-loop lag, queue depth, and request mix. Inspect a short CPU profile. Distinguish CPU-bound work from time waiting on a dependency.
Inspect authorization success, provider latency, ledger query time, and retry count. This service must authorize charges using a stable idempotency key; inspect payment provider and payment ledger as part of the dependency boundary.

## Safe next steps

1. Reduce optional expensive work and rate-limit the costly request class.
2. Scale workers only if downstream systems and node capacity have room.
3. Roll back a confirmed hot-loop regression or disable the responsible feature flag.

Service-specific constraint: Never blindly retry a charge. Reconcile the provider authorization ID and ledger entry first.

## Verify recovery

CPU throttling and queue depth decline, throughput recovers, and request p95 returns to baseline. Verify card authorizations and order completion with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the runtime owner when a profile shows a hot loop or scaling raises contention. Do not raise concurrency blindly. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
