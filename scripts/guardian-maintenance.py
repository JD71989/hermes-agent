"""Safe, repeatable Guardian OS maintenance preflight.
Never resets/discards Git work and never changes credentials or live execution flags.
"""
from __future__ import annotations
import json, subprocess, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    return p.returncode, (p.stdout + p.stderr).strip()

def check_python() -> bool:
    print("[PYTHON]", sys.version.split()[0])
    try:
        import pytest
        print("[PYTEST]", pytest.__version__)
        return True
    except Exception as exc:
        print("[PYTEST] MISSING", exc)
        return False
def check_guardian_registry() -> bool:
    from guardian_os.registry import load_registry
    r = load_registry(ROOT / "guardian_os")
    ok = len(r.departments) == 7 and r.missing_capabilities("news-media") == ()
    print("[GUARDIAN OS]", "OK" if ok else "FAILED", f"departments={len(r.departments)} plugins={len(r.plugins)}")
    return ok

def check_web_build() -> bool:
    import shutil
    npm_name = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm_name:
        print("[WEB BUILD] UNAVAILABLE (npm not found)")
        return False
    code, out = run([npm_name, "run", "build", "--prefix", "web"])
    print("[WEB BUILD]", "OK" if code == 0 else "FAILED")
    if code != 0:
        print(out[-2000:])
    return code == 0
def check_dashboard() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:9119/api/health", timeout=5) as r:
            body = r.read().decode()
        data = json.loads(body)
        ok = data.get("ok") is True
        print("[DASHBOARD]", "OK" if ok else "FAILED", body)
        return ok
    except Exception as exc:
        print("[DASHBOARD] UNAVAILABLE", exc)
        return False
def check_git() -> bool:
    _, name = run(["git", "config", "--get", "user.name"])
    _, email = run(["git", "config", "--get", "user.email"])
    print("[GIT IDENTITY]", "CONFIGURED" if name and email else "NOT CONFIGURED")
    print("[GIT STATUS]")
    _, status = run(["git", "status", "--short"])
    print(status or "(clean)")
    return bool(name and email)

def main() -> int:
    checks = [check_python(), check_guardian_registry(), check_web_build(), check_dashboard()]
    git_ok = check_git()
    print("\nRESULT:", "PASS" if all(checks) else "FAIL")
    print("GIT CHECKPOINT:", "READY" if git_ok else "WAITING FOR USER IDENTITY")
    return 0 if all(checks) else 1

if __name__ == "__main__":
    raise SystemExit(main())
