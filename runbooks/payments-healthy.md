---
id: payments-healthy
title: payments: Healthy service and stale alert verification
service: payments
cause: healthy
---
# payments: Healthy service and stale alert verification

Owner: payments on-call. Scope: payment authorization. Primary impact: card authorizations and order completion.

## Symptoms

Request error rate, latency, CPU, memory, storage, and dependency checks are within the service baseline. There are no corroborating recent failures.

## Distinguishing evidence

Check the alert evaluation timestamp, service labels, current time window, and successful representative requests. Missing telemetry is not evidence of health.
Inspect authorization success, provider latency, ledger query time, and retry count. This service must authorize charges using a stable idempotency key; inspect payment provider and payment ledger as part of the dependency boundary.

## Safe next steps

1. Verify that metrics and logs are fresh and correspond to the alerted service and environment.
2. Check a representative request and compare the alert window with the current window.
3. Record a recovered or stale alert only when fresh telemetry supports it; otherwise escalate as insufficient evidence.

Service-specific constraint: Never blindly retry a charge. Reconcile the provider authorization ID and ledger entry first.

## Verify recovery

Fresh telemetry and successful requests consistently show normal operation across two windows. Verify card authorizations and order completion with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate when data is missing, stale, contradictory, or a user reports impact despite normal aggregate metrics. Do not perform rollback or restart based only on a stale page. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
