---
id: checkout-disk_full
title: checkout: Disk full ENOSPC and inode exhaustion
service: checkout
cause: disk_full
---
# checkout: Disk full ENOSPC and inode exhaustion

Owner: checkout on-call. Scope: order orchestration. Primary impact: order placement and cart conversion.

## Symptoms

Writes fail with ENOSPC or no space left on device. Disk occupancy or inode utilization approaches its limit; log buffering and temporary files may fail.

## Distinguishing evidence

Compare free bytes and free inodes on the affected mount, inspect bounded directory sizes, and distinguish writable container layers from persistent volumes.
Inspect order failures, dependency duration, pending reservations, and duplicate authorizations. This service must reserve stock and authorize payment before accepting an order; inspect payments and inventory as part of the dependency boundary.

## Safe next steps

1. Pause nonessential writes and identify the owner of the growing directory.
2. Apply the approved log rotation or temporary-file cleanup policy to confirmed disposable files.
3. Expand the affected volume when supported; preserve database files and incident evidence.

Service-specific constraint: An order can have a payment authorization even when the caller sees a timeout. Inspect its idempotency key before replay.

## Verify recovery

Both bytes and inodes have headroom and a representative write succeeds without ENOSPC. Verify order placement and cart conversion with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the storage owner before deleting persistent data. Never remove database, ledger, or reservation files as a generic cleanup step. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
