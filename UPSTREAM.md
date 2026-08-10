# Upstream provenance: curl

Status: upstream baseline synchronized for the Norx curl port; no Norx source
patch has been applied yet.

## Identity

| Field | Value |
| --- | --- |
| Norx repository/package | `curl` |
| Upstream URL | `https://github.com/curl/curl.git` |
| Norx fork URL | `https://github.com/NorxTeam/curl.git` |
| Required remote name | `upstream` |
| Norx push remote | `origin` |
| Upstream baseline tag | `none; baseline is upstream/master` |
| Upstream baseline commit | `1cf6be5a0b4a1db8c501dcda8ac98e09970fd372` |
| Imported at | `2026-08-10 UTC` |
| Last synchronized commit | `2026-08-10; 1cf6be5a0b4a1db8c501dcda8ac98e09970fd372` |

The fork's `master` branch is the untouched upstream baseline. Norx work starts
on `norx/curl-port`; future changes must remain in the ordered `patches/`
queue or in reviewable commits on that branch.

The nearest historical tag is `rc-8_22_0-1`, but the recorded baseline is the
full immutable commit above because `upstream/master` had advanced beyond it.

The repeatable sync procedure is `scripts/sync_upstream.py`. It fetches
`upstream`, rebases the maintained branch in a temporary worktree, preserves
the current branch as `norx/last-known-good`, and emits a JSON report. The CI
entry point is `.github/workflows/upstream-sync.yml`.

## Preserved notices and obligations

| Field | Value |
| --- | --- |
| Primary license | `LicenseRef-curl` (the curl license in `COPYING` and `LICENSES/curl.txt`) |
| Additional retained licenses | `ISC` and `BSD-4-Clause-UC` under `LICENSES/` |
| Retained notice files | `COPYING`, `LICENSES/curl.txt`, `LICENSES/ISC.txt`, `LICENSES/BSD-4-Clause-UC.txt` |
| Copyright headers changed? | `No` |
| Trademark obligations | Do not use a copyright holder's name for advertising or promotion without written authorization; review curl branding before shipping a Norx product name. |
| Distribution obligations | Preserve the copyright and permission notice and all retained third-party license texts. |

No upstream license, copyright, attribution, or notice file has been removed.

## Norx patch queue

The queue is intentionally empty at the baseline fork:

```text
patches/series: no Norx patches yet
```

Before the first port change, add one-purpose patches in order, record their
upstream status and removal condition here, and keep generated build output
out of the queue.

## Build and generated artifacts

| Field | Value |
| --- | --- |
| Gamma recipe | `not added; curl port gate is pending` |
| Build profile/options | `not started` |
| Supported targets | `not started` |
| Offline/network policy | `not started` |
| Manifest path | `not generated` |
| Hash algorithm | `SHA-256` when the first build profile exists |
| Artifact hash scope | `not generated` |

This synchronized fork contains source and provenance only. No Norx binary, SDK,
or generated sysroot is claimed to be a curl release artifact.

## Sync record

```text
sync_date_utc: 2026-08-10
old_upstream_commit: 2d30fd26a060e7c3de3393503fb5ba7e8f3840f8
new_upstream_commit: 1cf6be5a0b4a1db8c501dcda8ac98e09970fd372
patch_rebase_result: clean; 3 downstream commits replayed in a temporary worktree
host_tests: CMake smoke is executed by scripts/sync_upstream.py and CI
target_tests: not run; curl port gate pending
qemu_smoke: not applicable while the curl target port is not selected
last_known_good: norx/last-known-good at 1baeb7653c07727ba2a2f612eb96da2d21222ff4
rollback_revision: norx/last-known-good at 1baeb7653c07727ba2a2f612eb96da2d21222ff4
```
