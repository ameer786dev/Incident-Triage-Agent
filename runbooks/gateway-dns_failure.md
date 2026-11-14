---
id: gateway-dns_failure
title: gateway: DNS resolution failure NXDOMAIN and resolver outage
service: gateway
cause: dns_failure
---
# gateway: DNS resolution failure NXDOMAIN and resolver outage

Owner: gateway on-call. Scope: public HTTP ingress and request routing. Primary impact: all storefront requests.

## Symptoms

Connections fail before a TCP session begins. Logs contain NXDOMAIN, EAI_AGAIN, getaddrinfo failed, or a name resolution error.

## Distinguishing evidence

Resolve the exact dependency hostname from an affected container and a healthy container. Inspect DNS response codes, search domains, resolver latency, and recent service-name changes.
Inspect ingress error rate, route latency, upstream health, and active requests. This service must route /work requests to checkout while preserving trace IDs; inspect checkout as part of the dependency boundary.

## Safe next steps

1. Compare the configured hostname and service discovery record with the known good deployment.
2. Restore a missing service record or revert a verified hostname configuration change.
3. If names are correct, escalate resolver health and avoid a fleet-wide restart that would discard working DNS caches.

Service-specific constraint: Gateway replicas are stateless; route and timeout configuration changes affect every request.

## Verify recovery

The exact hostname resolves from affected replicas and a new connection reaches the intended dependency. Verify all storefront requests with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the networking owner if multiple service names fail or the resolver is unavailable. Avoid hardcoded IPs without an approved emergency plan. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
