#!/usr/bin/env python3
"""Trigger a Codemagic M2 build, stream live progress in GitHub Actions, and download IPAs."""

import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

API_BASE = "https://api.codemagic.io"
TERMINAL_STATUSES = {"finished", "failed", "canceled", "timeout", "skipped"}

STATUS_ICON = {
    "waiting": "⏳",
    "queued": "⏳",
    "initializing": "🔄",
    "fetching": "📥",
    "preparing": "🧰",
    "building": "🔨",
    "testing": "🧪",
    "publishing": "📦",
    "finishing": "🏁",
    "finished": "✅",
    "success": "✅",
    "running": "▶️",
    "pending": "⬜",
    "skipped": "⏭️",
    "failed": "❌",
    "canceled": "🚫",
    "timeout": "⏰",
}


def api_request(method: str, url: str, token: str, payload=None, retries: int = 5, retry_statuses=(429, 500, 502, 503, 504)):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"x-auth-token": token}
    if data is not None:
        headers["Content-Type"] = "application/json"

    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", errors="replace")
            if (err.code >= 500 or err.code in retry_statuses) and attempt < retries:
                time.sleep(min(attempt * 3, 15))
                continue
            raise RuntimeError(f"Codemagic API {method} {url} -> HTTP {err.code}: {body}") from err
        except urllib.error.URLError as err:
            if attempt < retries:
                time.sleep(min(attempt * 3, 15))
                continue
            raise RuntimeError(f"Codemagic API {method} {url} failed: {err}") from err
    raise RuntimeError(f"Codemagic API {method} {url} exhausted retries")


def fmt_elapsed(seconds: float) -> str:
    mins, secs = divmod(int(seconds), 60)
    return f"{mins:02d}:{secs:02d}"


def write_summary(build_url: str, status: str, elapsed: float, actions: list, upstream_sha: str):
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    lines = [
        f"## Codemagic 8-Core M2 Build — {STATUS_ICON.get(status, 'ℹ️')} `{status}`",
        "",
        f"- **Upstream commit:** [`fluxerapp/flutter_client@{upstream_sha[:12]}`](https://github.com/fluxerapp/flutter_client/commit/{upstream_sha})",
        f"- **Elapsed:** `{fmt_elapsed(elapsed)}`",
        f"- **Codemagic logs:** [Open build in Codemagic]({build_url})",
        "",
        "| Step | Status |",
        "|---|---|",
    ]
    for act in actions:
        name = act.get("name") or act.get("type") or "step"
        st = act.get("status") or "unknown"
        lines.append(f"| {name} | {STATUS_ICON.get(st, '•')} `{st}` |")
    Path(summary_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def download_artifact(art_url: str, dest: Path, token: str):
    # Codemagic artifacts API: mint a short-lived public URL, fallback to direct header auth
    download_url = art_url
    headers = {}
    try:
        pub = api_request(
            "POST",
            f"{art_url}/public-url",
            token,
            payload={"expiresAt": int(time.time()) + 900},
        )
        if pub.get("url"):
            download_url = pub["url"]
    except Exception:
        headers["x-auth-token"] = token

    req = urllib.request.Request(download_url, headers=headers)
    with urllib.request.urlopen(req, timeout=300) as resp, dest.open("wb") as out:
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            out.write(chunk)


def main() -> int:
    token = os.environ["CODEMAGIC_API_TOKEN"].strip()
    app_id = os.environ["CODEMAGIC_APP_ID"].strip()
    workflow_id = os.environ.get("CODEMAGIC_WORKFLOW_ID", "fluxer-ios-unsigned").strip()
    builder_branch = os.environ.get("BUILDER_BRANCH", "main").strip()
    upstream_branch = os.environ["UPSTREAM_BRANCH"].strip()
    upstream_sha = os.environ["UPSTREAM_SHA"].strip()
    out_dir = Path(os.environ["OUTPUT_DIR"]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    existing_build_id = os.environ.get("CODEMAGIC_BUILD_ID", "").strip()
    if existing_build_id:
        build_id = existing_build_id
        print(f"Attaching to existing Codemagic build: {build_id}", flush=True)
    else:
        print(f"Triggering Codemagic workflow '{workflow_id}' on mac_mini_m2 for Fluxer {upstream_sha[:12]}...", flush=True)
        trigger_resp = api_request(
            "POST",
            f"{API_BASE}/builds",
            token,
            payload={
                "appId": app_id,
                "workflowId": workflow_id,
                "branch": builder_branch,
                "environment": {
                    "variables": {
                        "UPSTREAM_BRANCH": upstream_branch,
                        "UPSTREAM_SHA": upstream_sha,
                    }
                },
            },
        )
        build_id = trigger_resp.get("buildId") or trigger_resp.get("_id")
        if not build_id:
            raise RuntimeError(f"Unexpected Codemagic response (missing buildId): {trigger_resp}")

    build_url = f"https://codemagic.io/app/{app_id}/build/{build_id}"
    print(f"Codemagic build URL: {build_url}", flush=True)

    # Give Codemagic a moment to make the newly created build readable on GET /builds/{id}
    if not existing_build_id:
        time.sleep(4)

    start_time = time.monotonic()
    last_build_status = None
    seen_actions = {}
    build_obj = {}

    while True:
        # Retry 404 briefly right after creation (Codemagic eventual consistency)
        poll = api_request(
            "GET",
            f"{API_BASE}/builds/{build_id}",
            token,
            retries=8,
            retry_statuses=(404, 429, 500, 502, 503, 504),
        )
        build_obj = poll.get("build") or poll
        status = (build_obj.get("status") or "unknown").lower()
        actions = build_obj.get("buildActions") or []
        elapsed = time.monotonic() - start_time

        if status != last_build_status:
            print(f"[{fmt_elapsed(elapsed)}] {STATUS_ICON.get(status, 'ℹ️')} Build status: {status}", flush=True)
            last_build_status = status

        for idx, act in enumerate(actions):
            name = act.get("name") or act.get("type") or f"Step {idx + 1}"
            st = (act.get("status") or "pending").lower()
            key = f"{idx}:{name}"
            if seen_actions.get(key) != st:
                seen_actions[key] = st
                if st != "pending":
                    print(f"[{fmt_elapsed(elapsed)}]   {STATUS_ICON.get(st, '•')} {name} -> {st}", flush=True)

        if status in TERMINAL_STATUSES:
            write_summary(build_url, status, elapsed, actions, upstream_sha)
            break

        time.sleep(8)

    final_status = (build_obj.get("status") or "unknown").lower()
    if final_status != "finished":
        msg = build_obj.get("message") or ""
        print(f"::error::Codemagic build ended with status '{final_status}'. {msg} Logs: {build_url}", flush=True)
        return 1

    artefacts = build_obj.get("artefacts") or build_obj.get("artifacts") or []
    wanted = {
        "fluxer-unsigned.ipa",
        "fluxer-sideload-no-plugins.ipa",
        "upstream-commit.txt",
    }
    downloaded = set()

    print(f"Downloading build artifacts from Codemagic ({len(artefacts)} available)...", flush=True)
    for art in artefacts:
        name = Path(art.get("name") or "").name
        url = art.get("url")
        if name in wanted and url:
            dest = out_dir / name
            print(f"  Downloading {name}...", flush=True)
            download_artifact(url, dest, token)
            size_mb = dest.stat().st_size / (1024 * 1024)
            print(f"  Saved {name} ({size_mb:.2f} MB)", flush=True)
            if name.endswith(".ipa"):
                with zipfile.ZipFile(dest, "r") as zf:
                    bad = zf.testzip()
                    if bad is not None:
                        raise RuntimeError(f"Downloaded IPA failed ZIP verification at {bad}: {name}")
            downloaded.add(name)

    missing = wanted - downloaded
    if missing:
        raise RuntimeError(
            f"Missing expected artifacts from Codemagic: {sorted(missing)}. "
            f"Available: {[a.get('name') for a in artefacts]}"
        )

    print("All Codemagic artifacts downloaded and verified.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
