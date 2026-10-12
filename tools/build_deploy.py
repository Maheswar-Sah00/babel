"""Build the deployment bundle dist/railway/: only what the live server needs, including the private data git leaves out.

  python tools/build_deploy.py          # -> dist/railway/ (git-ignored), checked
  railway up dist/railway --path-as-root --no-gitignore     # deploy it (the bundle holds no .env, no keys)

The bundle is the code (babel/, web/), the backtest files the server reads (backtest/data/, final_report.md), the
precomputed runtime data (data/runtime/, Qloo-derived, private) and just the cache files the four demo buttons read,
recorded by running them through the API with every request refused. deploy/Dockerfile and deploy/railway.json go at
its root. Checks: no secret in any file, then the demos are run again from the bundle itself, offline and with
BABEL_REQUIRE_RUNTIME=1, and must all come back 'ok' with no request. The data goes only to the host, never to git.
"""
import argparse
import io
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dist" / "railway"
CODE = ("babel", "web", "backtest/data", "backtest/final_report.md", "data/runtime", "requirements.txt",
        "requirements-lock.txt", "LICENSE")
AT_ROOT = ("deploy/Dockerfile", "deploy/railway.json")
UPLOAD_WARN_MB = 15  # railway up's upload limit is reported between about 15 and 45 MB (compressed)
PLACEHOLDER = "placeholder-not-a-key"  # readiness needs keys set; the offline check never uses them
PLACEHOLDER_KEYS = dict.fromkeys(("QLOO_API_KEY", "ANTHROPIC_API_KEY"), PLACEHOLDER)


def run_demos(root):
    """Run the four demo buttons through the API with every request refused; (results, cache files read)."""
    sys.path.insert(0, str(root))
    from babel import api  # noqa: E402  (from root: the repo, or the bundle in --verify)

    assert Path(api.__file__).resolve().is_relative_to(root.resolve()), f"babel imported from {api.__file__}"
    sys.path.insert(1, str(ROOT / "tools"))
    import precache_demos as demo  # babel is already imported, so this reuses root's copy
    from collections import Counter
    from fastapi.testclient import TestClient

    cache, read = (root / "cache").resolve(), set()
    original = Path.read_text

    def recording(self, *args, **kwargs):
        path = Path(self).resolve()
        if path.is_relative_to(cache):
            read.add(path.relative_to(root.resolve()))
        return original(self, *args, **kwargs)
    Path.read_text = recording
    blocked = Counter()
    demo.go_offline(blocked)
    results = []
    with TestClient(api.create_app(api.Settings(warmup=True, plan_rate=(100, 60), lookup_rate=(100, 60)))) as client:
        state = client.app.state.babel
        if not state.ready.wait(300) or state.data_status != "ready":
            raise SystemExit(f"Runtime data not ready: {state.data_status}")
        for name, game in demo.demos():
            seen = Counter(blocked)
            r = demo.run(client, name, game)
            results.append({**r, "blocked": dict(Counter(blocked) - seen)})
    Path.read_text = original
    return results, sorted(read)


def failures(results):
    return [f"{r['demo']}: {r['status']} {r['blocked'] or ''} {r['errors'] or ''}".strip()
            for r in results if r["status"] != "ok" or r["blocked"] or r["errors"]]


def copy(src, dst):
    if src.is_dir():
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def secret_findings(folder):
    """The pre-publication scan's rules (tools/check_secrets.py) over every file in the bundle."""
    sys.path.insert(0, str(ROOT / "tools"))
    import check_secrets as cs
    secrets = cs.env_values(ROOT / ".env")
    found = []
    for f in sorted(p for p in folder.rglob("*") if p.is_file()):
        rel = f.relative_to(folder).as_posix()
        if cs.BAD_NAME.search(rel):
            found.append((rel, 0, "file must not be published"))
        found += cs.scan(rel, f.read_bytes(), secrets)
    return found


def compressed_mb(folder):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in folder.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(folder))
    return buf.tell() / 1e6


def build():
    print("1. Recording the cache files the demo buttons read (every request refused) ...")
    results, read = run_demos(ROOT)
    if failures(results):
        raise SystemExit("The demos do not run from the cache alone; run python tools/precache_demos.py first:\n  "
                         + "\n  ".join(failures(results)))
    print(f"   4 demos ok, {len(read)} cache files read")
    assert OUT.resolve().is_relative_to((ROOT / "dist").resolve())
    if OUT.exists():
        shutil.rmtree(OUT)
    for rel in CODE:
        copy(ROOT / rel, OUT / rel)
    for rel in AT_ROOT:
        copy(ROOT / rel, OUT / Path(rel).name)
    for rel in read:
        copy(ROOT / rel, OUT / rel)
    print("2. Scanning the bundle for secrets ...")
    found = secret_findings(OUT)
    for label, line, rule in found:
        print(f"   FOUND  {label}:{line}  {rule}")
    if found:
        shutil.rmtree(OUT)
        raise SystemExit("Secrets found: bundle deleted. Remove them (and rotate any real key).")
    print("   OK: no secrets")
    print("3. Running the demos from the bundle itself (offline, BABEL_REQUIRE_RUNTIME=1) ...")
    env = {**os.environ, **PLACEHOLDER_KEYS, "BABEL_REQUIRE_RUNTIME": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    check = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--verify", str(OUT)], cwd=OUT, env=env)
    if check.returncode:
        raise SystemExit("The bundle does not run the demos on its own (see above).")
    files = [p for p in OUT.rglob("*") if p.is_file()]
    size = sum(p.stat().st_size for p in files) / 1e6
    zipped = compressed_mb(OUT)
    print(f"\nBundle: {OUT.relative_to(ROOT)}  {len(files)} files, {size:.1f} MB ({zipped:.1f} MB compressed)")
    if zipped > UPLOAD_WARN_MB:
        print(f"   Note: over {UPLOAD_WARN_MB} MB compressed; railway up may refuse or time out.")
    print("Deploy: railway up dist/railway --path-as-root --no-gitignore")


def verify(folder):
    results, _ = run_demos(Path(folder))
    for r in results:
        print(f"   {r['demo']:<22} {r['status']}  requests refused: {r['blocked'] or 'none'}")
    if failures(results):
        print("   FAIL:\n   " + "\n   ".join(failures(results)))
        return 1
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build the deployment bundle dist/railway/.")
    ap.add_argument("--verify", metavar="FOLDER", help=argparse.SUPPRESS)
    a = ap.parse_args()
    sys.exit(verify(a.verify) if a.verify else build())
