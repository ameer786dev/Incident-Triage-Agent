---
id: checkout-bad_deploy
title: checkout: Bad deploy and release regression
service: checkout
cause: bad_deploy
---
# checkout: Bad deploy and release regression

Owner: checkout on-call. Scope: order orchestration. Primary impact: order placement and cart conversion.

## Symptoms

Error rate rises shortly after a new version becomes active. Exceptions repeat on the new revision while healthy older replicas serve the same request.

## Distinguishing evidence

Compare deploy timestamp, image revision, and canary versus baseline errors. Look for configuration validation errors, missing fields, TypeError, or changed request contracts. A recent deploy alone does not establish causality.
Inspect order failures, dependency duration, pending reservations, and duplicate authorizations. This service must reserve stock and authorize payment before accepting an order; inspect payments and inventory as part of the dependency boundary.

## Safe next steps

1. Pause the rollout and compare errors by version before changing capacity.
2. If the new revision alone fails, roll back the image and its compatible configuration to the last known good release.
3. Check schema compatibility and feature flags before rollback; an irreversible migration requires the database owner.

Service-specific constraint: An order can have a payment authorization even when the caller sees a timeout. Inspect its idempotency key before replay.

## Verify recovery

The prior revision serves the same request successfully and error rate returns to baseline for two observation windows. Verify order placement and cart conversion with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the release owner if both revisions fail, no baseline exists, or rollback would cross an incompatible schema change. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
