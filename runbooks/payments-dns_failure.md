---
id: payments-dns_failure
title: payments: DNS resolution failure NXDOMAIN and resolver outage
service: payments
cause: dns_failure
---
# payments: DNS resolution failure NXDOMAIN and resolver outage

Owner: payments on-call. Scope: payment authorization. Primary impact: card authorizations and order completion.

## Symptoms

Connections fail before a TCP session begins. Logs contain NXDOMAIN, EAI_AGAIN, getaddrinfo failed, or a name resolution error.

## Distinguishing evidence

Resolve the exact dependency hostname from an affected container and a healthy container. Inspect DNS response codes, search domains, resolver latency, and recent service-name changes.
Inspect authorization success, provider latency, ledger query time, and retry count. This service must authorize charges using a stable idempotency key; inspect payment provider and payment ledger as part of the dependency boundary.

## Safe next steps

1. Compare the configured hostname and service discovery record with the known good deployment.
2. Restore a missing service record or revert a verified hostname configuration change.
3. If names are correct, escalate resolver health and avoid a fleet-wide restart that would discard working DNS caches.

Service-specific constraint: Never blindly retry a charge. Reconcile the provider authorization ID and ledger entry first.

## Verify recovery

The exact hostname resolves from affected replicas and a new connection reaches the intended dependency. Verify card authorizations and order completion with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the networking owner if multiple service names fail or the resolver is unavailable. Avoid hardcoded IPs without an approved emergency plan. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
