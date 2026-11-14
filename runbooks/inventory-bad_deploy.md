---
id: inventory-bad_deploy
title: inventory: Bad deploy and release regression
service: inventory
cause: bad_deploy
---
# inventory: Bad deploy and release regression

Owner: inventory on-call. Scope: stock availability and reservation. Primary impact: stock checks and reservation confirmation.

## Symptoms

Error rate rises shortly after a new version becomes active. Exceptions repeat on the new revision while healthy older replicas serve the same request.

## Distinguishing evidence

Compare deploy timestamp, image revision, and canary versus baseline errors. Look for configuration validation errors, missing fields, TypeError, or changed request contracts. A recent deploy alone does not establish causality.
Inspect reservation failures, stock query duration, lock waits, and expired holds. This service must read available stock and write short-lived reservations; inspect stock database as part of the dependency boundary.

## Safe next steps

1. Pause the rollout and compare errors by version before changing capacity.
2. If the new revision alone fails, roll back the image and its compatible configuration to the last known good release.
3. Check schema compatibility and feature flags before rollback; an irreversible migration requires the database owner.

Service-specific constraint: Check reservation IDs and expiry before retrying writes; avoid overselling through duplicate reservations.

## Verify recovery

The prior revision serves the same request successfully and error rate returns to baseline for two observation windows. Verify stock checks and reservation confirmation with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the release owner if both revisions fail, no baseline exists, or rollback would cross an incompatible schema change. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
