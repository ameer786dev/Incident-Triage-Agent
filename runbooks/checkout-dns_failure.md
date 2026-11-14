---
id: checkout-dns_failure
title: checkout: DNS resolution failure NXDOMAIN and resolver outage
service: checkout
cause: dns_failure
---
# checkout: DNS resolution failure NXDOMAIN and resolver outage

Owner: checkout on-call. Scope: order orchestration. Primary impact: order placement and cart conversion.

## Symptoms

Connections fail before a TCP session begins. Logs contain NXDOMAIN, EAI_AGAIN, getaddrinfo failed, or a name resolution error.

## Distinguishing evidence

Resolve the exact dependency hostname from an affected container and a healthy container. Inspect DNS response codes, search domains, resolver latency, and recent service-name changes.
Inspect order failures, dependency duration, pending reservations, and duplicate authorizations. This service must reserve stock and authorize payment before accepting an order; inspect payments and inventory as part of the dependency boundary.

## Safe next steps

1. Compare the configured hostname and service discovery record with the known good deployment.
2. Restore a missing service record or revert a verified hostname configuration change.
3. If names are correct, escalate resolver health and avoid a fleet-wide restart that would discard working DNS caches.

Service-specific constraint: An order can have a payment authorization even when the caller sees a timeout. Inspect its idempotency key before replay.

## Verify recovery

The exact hostname resolves from affected replicas and a new connection reaches the intended dependency. Verify order placement and cart conversion with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the networking owner if multiple service names fail or the resolver is unavailable. Avoid hardcoded IPs without an approved emergency plan. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
