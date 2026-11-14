---
id: payments-disk_full
title: payments: Disk full ENOSPC and inode exhaustion
service: payments
cause: disk_full
---
# payments: Disk full ENOSPC and inode exhaustion

Owner: payments on-call. Scope: payment authorization. Primary impact: card authorizations and order completion.

## Symptoms

Writes fail with ENOSPC or no space left on device. Disk occupancy or inode utilization approaches its limit; log buffering and temporary files may fail.

## Distinguishing evidence

Compare free bytes and free inodes on the affected mount, inspect bounded directory sizes, and distinguish writable container layers from persistent volumes.
Inspect authorization success, provider latency, ledger query time, and retry count. This service must authorize charges using a stable idempotency key; inspect payment provider and payment ledger as part of the dependency boundary.

## Safe next steps

1. Pause nonessential writes and identify the owner of the growing directory.
2. Apply the approved log rotation or temporary-file cleanup policy to confirmed disposable files.
3. Expand the affected volume when supported; preserve database files and incident evidence.

Service-specific constraint: Never blindly retry a charge. Reconcile the provider authorization ID and ledger entry first.

## Verify recovery

Both bytes and inodes have headroom and a representative write succeeds without ENOSPC. Verify card authorizations and order completion with the service dashboard and one bounded representative request. Retain log IDs, metric timestamps, deploy revision, and trace IDs in the incident record.

## Rollback and escalation

Escalate to the storage owner before deleting persistent data. Never remove database, ledger, or reservation files as a generic cleanup step. A mitigation needs an owner, a scope, a success check, and a rollback condition. Diagnostic evidence supports a recommendation; this runbook does not authorize autonomous production changes.
