---
id: payments-bad_deploy
title: payments: Bad deploy and release regression
service: payments
cause: bad_deploy
---
# payments: Bad deploy and release regression

Owner: payments on-call. Scope: payment authorization. Primary impact: card authorizations and order completion.

## Symptoms

Error rate rises shortly after a new version becomes active. Exceptions repeat on the new revision while healthy older replicas serve the same request.

## Distinguishing evidence

Compare deploy timestamp, image revision, and canary versus baseline errors. Look for configuration validation errors, missing fields, TypeError, or changed request contracts. A recent deploy alone does not establish causality.
Inspect authorization success, provider latency, ledger query time, and retry count. This service must authorize charges using a stable idempotency key; inspect payment provider and payment ledger as part of the dependency boundary.

## Safe next steps

1. Pause the rollout and compare errors by version before changing capacity.
2. If the new revision alone fails, roll back the image and its compatible configuration to the last known good release.
3. Check schema compatibility and feature flags before rollback; an irreversible migration requires the database owner.

Service-specific constraint: Never blindly retry a charge. Reconcile the provider authorization ID and ledger entry first.

## Verify recovery

The prior revision serves the same request successfully and error rate returns to baseline for two observation windows. Verify card authorizations and order completion with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the release owner if both revisions fail, no baseline exists, or rollback would cross an incompatible schema change. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
