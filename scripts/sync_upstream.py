#!/usr/bin/env python3
"""Rebase the Norx branch onto upstream and run the required smoke checks.

The real branch is never rewritten.  The rebase is performed in a temporary
worktree so conflicts and failed tests leave the current branch untouched.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SHA = re.compile(r"^[0-9a-f]{40}$")


class SyncError(RuntimeError):
    pass


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise SyncError(f"git {' '.join(args)} failed ({result.returncode}): {detail}")
    return result


def command(
    argv: list[str], cwd: Path, timeout: int
) -> dict[str, Any]:
    record: dict[str, Any] = {"argv": argv, "cwd": str(cwd), "timeout_seconds": timeout}
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        record.update({"status": "unavailable", "returncode": None, "stderr": "command not found"})
        return record
    except subprocess.TimeoutExpired as exc:
        record.update(
            {
                "status": "timeout",
                "returncode": None,
                "stdout_tail": tail(exc.stdout or ""),
                "stderr_tail": tail(exc.stderr or ""),
            }
        )
        return record
    record.update(
        {
            "status": "passed" if result.returncode == 0 else "failed",
            "returncode": result.returncode,
            "stdout_tail": tail(result.stdout),
            "stderr_tail": tail(result.stderr),
        }
    )
    return record


def tail(value: str, lines: int = 40) -> str:
    return "\n".join(value.splitlines()[-lines:])


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def baseline_from(path: Path) -> str:
    match = re.search(r"\| Upstream baseline commit \| `([0-9a-f]{40})` \|", path.read_text(encoding="utf-8"))
    if not match:
        raise SyncError(f"{path} does not contain a 40-character upstream baseline commit")
    return match.group(1)


def load_lock(repo: Path, baseline: str) -> dict[str, Any]:
    try:
        import tomllib
    except ModuleNotFoundError as exc:
        raise SyncError("Python 3.11+ is required to validate gamma.lock") from exc
    try:
        data = tomllib.loads((repo / "gamma.lock").read_text(encoding="utf-8"))
    except (FileNotFoundError, tomllib.TOMLDecodeError) as exc:
        raise SyncError(f"cannot parse gamma.lock: {exc}") from exc
    source = data.get("source", {})
    if source.get("upstream_commit") != baseline:
        raise SyncError("gamma.lock source.upstream_commit does not match UPSTREAM.md")
    return data


def is_ancestor(repo: Path, old: str, new: str) -> bool:
    return git(repo, "merge-base", "--is-ancestor", old, new, check=False).returncode == 0


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def host_smoke(worktree: Path, timeout: int) -> dict[str, Any]:
    if shutil.which("cmake") is None:
        return {"status": "unavailable", "reason": "cmake is not installed"}
    build = worktree / "build" / "upstream-sync"
    configure = [
        "cmake",
        "-S",
        ".",
        "-B",
        str(build),
        "-DCMAKE_BUILD_TYPE=Release",
        "-DBUILD_SHARED_LIBS=OFF",
        "-DBUILD_CURL_EXE=ON",
        "-DBUILD_TESTING=OFF",
        "-DBUILD_LIBCURL_DOCS=OFF",
        "-DBUILD_MISC_DOCS=OFF",
        "-DBUILD_EXAMPLES=OFF",
        "-DCURL_USE_OPENSSL=OFF",
        "-DCURL_USE_LIBPSL=OFF",
        "-DCURL_USE_LIBSSH2=OFF",
        "-DCURL_USE_GSSAPI=OFF",
        "-DCURL_ZLIB=OFF",
        "-DCURL_BROTLI=OFF",
        "-DCURL_ZSTD=OFF",
        "-DCURL_USE_LIBIDN2=OFF",
        "-DCURL_USE_NGHTTP2=OFF",
        "-DCURL_USE_NGTCP2=OFF",
        "-DCURL_USE_QUIC=OFF",
    ]
    records = [command(configure, worktree, timeout)]
    if records[-1]["status"] == "passed":
        records.append(command(["cmake", "--build", str(build), "--parallel", "2"], worktree, timeout))
    if records[-1]["status"] == "passed":
        binaries = [build / "src" / "curl", build / "src" / "curl.exe", build / "src" / "Release" / "curl.exe"]
        binary = next((path for path in binaries if path.exists()), None)
        if binary is None:
            records.append({"status": "failed", "reason": "built curl executable was not found"})
        else:
            records.append(command([str(binary), "--version"], worktree, timeout))
    return {
        "status": "passed" if records and records[-1].get("status") == "passed" else "failed",
        "commands": records,
    }


def qemu_smoke(worktree: Path, explicit: str | None, timeout: int) -> dict[str, Any]:
    if explicit:
        argv = shlex.split(explicit, posix=os.name != "nt")
        if not argv:
            return {"status": "failed", "reason": "empty QEMU command"}
        return command(argv, worktree, timeout)
    try:
        import tomllib

        recipe = tomllib.loads((worktree / "gamma.toml").read_text(encoding="utf-8"))
    except (FileNotFoundError, tomllib.TOMLDecodeError) as exc:
        return {"status": "failed", "reason": f"cannot inspect gamma.toml: {exc}"}
    if recipe.get("status") == "provenance-only":
        return {"status": "not-applicable", "reason": "curl target port is not selected yet"}
    return {"status": "failed", "reason": "QEMU smoke command is required once the target port is selected"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch", default="norx/curl-port")
    parser.add_argument("--upstream-ref", default="master")
    parser.add_argument("--report", default="build/upstream-sync-report.json")
    parser.add_argument("--skip-host", action="store_true", help="skip the host build for a fast local rebase check")
    parser.add_argument("--qemu-command", help="command to run for the target smoke test")
    parser.add_argument("--host-timeout", type=int, default=900)
    parser.add_argument("--qemu-timeout", type=int, default=900)
    parser.add_argument(
        "--push-rollback",
        action="store_true",
        help="push norx/last-known-good after saving it locally; may update the remote rollback branch",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(__file__).resolve().parents[1]
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = repo / report_path
    report: dict[str, Any] = {
        "schema": "norx-upstream-sync-report",
        "schema_version": 1,
        "started_at": now(),
        "repository": str(repo),
        "branch": args.branch,
        "upstream_ref": args.upstream_ref,
        "last_known_good": {"ref": "refs/heads/norx/last-known-good"},
    }
    worktree: Path | None = None
    failure: str | None = None
    try:
        branch_head = git(repo, "rev-parse", f"refs/heads/{args.branch}").stdout.strip()
        old = baseline_from(repo / "UPSTREAM.md")
        lock = load_lock(repo, old)
        report["current_head"] = branch_head
        report["old_upstream_commit"] = old
        report["lock_status"] = "consistent"
        if not is_ancestor(repo, old, branch_head):
            raise SyncError(f"branch {args.branch} is not descended from recorded upstream commit {old}")
        fork_commit = lock.get("source", {}).get("fork_commit")
        if fork_commit and SHA.fullmatch(fork_commit) and not is_ancestor(repo, fork_commit, branch_head):
            raise SyncError("gamma.lock source.fork_commit is not an ancestor of the maintained branch")
        upstream_url = git(repo, "remote", "get-url", "upstream").stdout.strip()
        report["upstream_url"] = upstream_url
        git(repo, "fetch", "--tags", "--prune", "upstream")
        new = git(repo, "rev-parse", f"refs/remotes/upstream/{args.upstream_ref}^{{commit}}").stdout.strip()
        if not SHA.fullmatch(new):
            raise SyncError(f"upstream ref resolved to an invalid commit: {new}")
        report["new_upstream_commit"] = new
        if not is_ancestor(repo, old, new):
            raise SyncError("upstream history is not a fast-forward from the recorded baseline")
        merges = git(repo, "rev-list", "--merges", f"{old}..{args.branch}").stdout.splitlines()
        if merges:
            raise SyncError("maintained branch contains merge commits; flatten the patch queue before syncing")
        patches = git(repo, "rev-list", "--reverse", f"{old}..{args.branch}").stdout.splitlines()
        report["patch_commits"] = patches

        git(repo, "update-ref", "refs/heads/norx/last-known-good", branch_head)
        report["last_known_good"]["sha"] = branch_head
        if args.push_rollback:
            pushed = git(
                repo,
                "push",
                "--force-with-lease",
                "origin",
                "refs/heads/norx/last-known-good:refs/heads/norx/last-known-good",
                check=False,
            )
            report["last_known_good"]["push_status"] = "passed" if pushed.returncode == 0 else "failed"
            if pushed.returncode:
                raise SyncError(pushed.stderr.strip() or "could not push the rollback ref")
        else:
            report["last_known_good"]["push_status"] = "not-requested"

        worktree = Path(tempfile.mkdtemp(prefix="curl-upstream-sync-"))
        git(repo, "worktree", "add", "--detach", str(worktree), new)
        candidate: dict[str, Any] = {"upstream_commit": new, "status": "rebasing"}
        for patch in patches:
            cherry = git(
                worktree,
                "-c",
                "user.name=Norx upstream sync",
                "-c",
                "user.email=norx-upstream-sync@invalid",
                "cherry-pick",
                "--no-edit",
                patch,
                check=False,
            )
            if cherry.returncode:
                candidate["status"] = "conflict"
                candidate["conflict_commit"] = patch
                candidate["conflict_status"] = git(worktree, "status", "--short").stdout.splitlines()
                git(worktree, "cherry-pick", "--abort", check=False)
                report["candidate"] = candidate
                raise SyncError(f"patch {patch} conflicts on upstream {new}")
        candidate["commit"] = git(worktree, "rev-parse", "HEAD").stdout.strip()
        candidate["status"] = "rebased"
        report["candidate"] = candidate
        candidate_baseline = baseline_from(worktree / "UPSTREAM.md")
        report["metadata_update_required"] = candidate_baseline != new
        if candidate_baseline != new:
            raise SyncError("UPSTREAM.md and gamma.lock must be updated to the new candidate baseline")
        load_lock(worktree, new)
        report["candidate_lock_status"] = "consistent"

        report["host_smoke"] = {"status": "skipped"} if args.skip_host else host_smoke(worktree, args.host_timeout)
        if report["host_smoke"]["status"] not in {"passed", "skipped"}:
            raise SyncError("host smoke test failed or is unavailable")
        report["qemu_smoke"] = qemu_smoke(worktree, args.qemu_command, args.qemu_timeout)
        if report["qemu_smoke"]["status"] not in {"passed", "not-applicable"}:
            raise SyncError("QEMU smoke test failed or is required")
        report["result"] = "passed"
    except (OSError, SyncError) as exc:
        failure = str(exc)
        report["result"] = "failed"
        report["error"] = failure
    finally:
        if worktree is not None:
            git(repo, "worktree", "remove", "--force", str(worktree), check=False)
            shutil.rmtree(worktree, ignore_errors=True)
        report["finished_at"] = now()
        write_report(report_path, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if failure else 0


if __name__ == "__main__":
    sys.exit(main())
