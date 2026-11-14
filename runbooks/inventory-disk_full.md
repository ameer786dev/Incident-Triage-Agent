---
id: inventory-disk_full
title: inventory: Disk full ENOSPC and inode exhaustion
service: inventory
cause: disk_full
---
# inventory: Disk full ENOSPC and inode exhaustion

Owner: inventory on-call. Scope: stock availability and reservation. Primary impact: stock checks and reservation confirmation.

## Symptoms

Writes fail with ENOSPC or no space left on device. Disk occupancy or inode utilization approaches its limit; log buffering and temporary files may fail.

## Distinguishing evidence

Compare free bytes and free inodes on the affected mount, inspect bounded directory sizes, and distinguish writable container layers from persistent volumes.
Inspect reservation failures, stock query duration, lock waits, and expired holds. This service must read available stock and write short-lived reservations; inspect stock database as part of the dependency boundary.

## Safe next steps

1. Pause nonessential writes and identify the owner of the growing directory.
2. Apply the approved log rotation or temporary-file cleanup policy to confirmed disposable files.
3. Expand the affected volume when supported; preserve database files and incident evidence.

Service-specific constraint: Check reservation IDs and expiry before retrying writes; avoid overselling through duplicate reservations.

## Verify recovery

Both bytes and inodes have headroom and a representative write succeeds without ENOSPC. Verify stock checks and reservation confirmation with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the storage owner before deleting persistent data. Never remove database, ledger, or reservation files as a generic cleanup step. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
