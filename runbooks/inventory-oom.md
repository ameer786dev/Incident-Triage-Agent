---
id: inventory-oom
title: inventory: Out of memory OOMKilled and heap exhaustion
service: inventory
cause: oom
---
# inventory: Out of memory OOMKilled and heap exhaustion

Owner: inventory on-call. Scope: stock availability and reservation. Primary impact: stock checks and reservation confirmation.

## Symptoms

Resident memory approaches its container limit, processes restart, and logs or container events report OOMKilled, allocation failure, or exit code 137.

## Distinguishing evidence

Compare memory RSS with the configured memory limit and restart count. Verify exit reason; exit 137 without memory pressure can have other causes. Inspect heap growth, request size, and cache cardinality.
Inspect reservation failures, stock query duration, lock waits, and expired holds. This service must read available stock and write short-lived reservations; inspect stock database as part of the dependency boundary.

## Safe next steps

1. Shed oversized or nonessential requests and capture a bounded memory profile from a healthy replica.
2. Restore capacity with a known healthy replica or roll back a revision with confirmed increasing memory use.
3. Increase memory only after checking node headroom and setting an expiry for the temporary change.

Service-specific constraint: Check reservation IDs and expiry before retrying writes; avoid overselling through duplicate reservations.

## Verify recovery

RSS stays below the limit with stable headroom, restart count stops growing, and representative requests succeed. Verify stock checks and reservation confirmation with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the service owner if memory grows monotonically or no safe replica has enough headroom; repeated restarts do not repair a leak. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
