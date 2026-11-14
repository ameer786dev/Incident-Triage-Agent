---
id: inventory-healthy
title: inventory: Healthy service and stale alert verification
service: inventory
cause: healthy
---
# inventory: Healthy service and stale alert verification

Owner: inventory on-call. Scope: stock availability and reservation. Primary impact: stock checks and reservation confirmation.

## Symptoms

Request error rate, latency, CPU, memory, storage, and dependency checks are within the service baseline. There are no corroborating recent failures.

## Distinguishing evidence

Check the alert evaluation timestamp, service labels, current time window, and successful representative requests. Missing telemetry is not evidence of health.
Inspect reservation failures, stock query duration, lock waits, and expired holds. This service must read available stock and write short-lived reservations; inspect stock database as part of the dependency boundary.

## Safe next steps

1. Verify that metrics and logs are fresh and correspond to the alerted service and environment.
2. Check a representative request and compare the alert window with the current window.
3. Record a recovered or stale alert only when fresh telemetry supports it; otherwise escalate as insufficient evidence.

Service-specific constraint: Check reservation IDs and expiry before retrying writes; avoid overselling through duplicate reservations.

## Verify recovery

Fresh telemetry and successful requests consistently show normal operation across two windows. Verify stock checks and reservation confirmation with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate when data is missing, stale, contradictory, or a user reports impact despite normal aggregate metrics. Do not perform rollback or restart based only on a stale page. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
