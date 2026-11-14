---
id: gateway-bad_deploy
title: gateway: Bad deploy and release regression
service: gateway
cause: bad_deploy
---
# gateway: Bad deploy and release regression

Owner: gateway on-call. Scope: public HTTP ingress and request routing. Primary impact: all storefront requests.

## Symptoms

Error rate rises shortly after a new version becomes active. Exceptions repeat on the new revision while healthy older replicas serve the same request.

## Distinguishing evidence

Compare deploy timestamp, image revision, and canary versus baseline errors. Look for configuration validation errors, missing fields, TypeError, or changed request contracts. A recent deploy alone does not establish causality.
Inspect ingress error rate, route latency, upstream health, and active requests. This service must route /work requests to checkout while preserving trace IDs; inspect checkout as part of the dependency boundary.

## Safe next steps

1. Pause the rollout and compare errors by version before changing capacity.
2. If the new revision alone fails, roll back the image and its compatible configuration to the last known good release.
3. Check schema compatibility and feature flags before rollback; an irreversible migration requires the database owner.

Service-specific constraint: Gateway replicas are stateless; route and timeout configuration changes affect every request.

## Verify recovery

The prior revision serves the same request successfully and error rate returns to baseline for two observation windows. Verify all storefront requests with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the release owner if both revisions fail, no baseline exists, or rollback would cross an incompatible schema change. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
