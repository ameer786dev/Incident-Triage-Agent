---
id: inventory-dns_failure
title: inventory: DNS resolution failure NXDOMAIN and resolver outage
service: inventory
cause: dns_failure
---
# inventory: DNS resolution failure NXDOMAIN and resolver outage

Owner: inventory on-call. Scope: stock availability and reservation. Primary impact: stock checks and reservation confirmation.

## Symptoms

Connections fail before a TCP session begins. Logs contain NXDOMAIN, EAI_AGAIN, getaddrinfo failed, or a name resolution error.

## Distinguishing evidence

Resolve the exact dependency hostname from an affected container and a healthy container. Inspect DNS response codes, search domains, resolver latency, and recent service-name changes.
Inspect reservation failures, stock query duration, lock waits, and expired holds. This service must read available stock and write short-lived reservations; inspect stock database as part of the dependency boundary.

## Safe next steps

1. Compare the configured hostname and service discovery record with the known good deployment.
2. Restore a missing service record or revert a verified hostname configuration change.
3. If names are correct, escalate resolver health and avoid a fleet-wide restart that would discard working DNS caches.

Service-specific constraint: Check reservation IDs and expiry before retrying writes; avoid overselling through duplicate reservations.

## Verify recovery

The exact hostname resolves from affected replicas and a new connection reaches the intended dependency. Verify stock checks and reservation confirmation with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the networking owner if multiple service names fail or the resolver is unavailable. Avoid hardcoded IPs without an approved emergency plan. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
