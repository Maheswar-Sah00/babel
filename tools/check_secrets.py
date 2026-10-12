"""Pre-publication secret scan. Never prints a secret, only where it is and which rule matched.

Scans every file git would publish (tracked + untracked-not-ignored) and every blob in the git history for:
  1. the exact values in .env (and their last 16 characters, to catch partial pastes);
  2. common key formats (Qloo hackathon, Anthropic, Groq, OpenAI, GitHub, AWS, Google, Slack, private keys);
  3. files that should never be published (.env, .env.*, *.pem, *.key, id_rsa*).
Usage: python tools/check_secrets.py [--env PATH]      exit 0 = clean, 1 = findings
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "Qloo hackathon key": rb"hack_[0-9a-f]{32,}",
    "Anthropic key": rb"sk-ant-[A-Za-z0-9_\-]{16,}",
    "Groq key": rb"gsk_[A-Za-z0-9]{32,}",
    "OpenAI key": rb"sk-(?:proj-)?[A-Za-z0-9]{32,}",
    "GitHub token": rb"gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,}",
    "AWS access key": rb"AKIA[0-9A-Z]{16}",
    "Google API key": rb"AIza[0-9A-Za-z_\-]{35}",
    "Slack token": rb"xox[abprs]-[A-Za-z0-9-]{10,}",
    "Private key": rb"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "Hard-coded credential": (rb"(?i)(?:api[_-]?key|secret|token|passw(?:or)?d)[\"']?\s*[:=]\s*"
                              rb"[\"'][A-Za-z0-9_\-]{16,}[\"']"),
}
BAD_NAME = re.compile(r"(^|/)(\.env(\.(?!example$)[^/]+)?|[^/]+\.(pem|key)|id_rsa[^/]*)$")


def git(*args, stdin=None):
    return subprocess.run(["git", *args], cwd=ROOT, input=stdin, capture_output=True, check=True).stdout


def env_values(path):
    """Secret values from a .env file (values of 8+ characters), as bytes."""
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        value = value.strip().strip("\"'")
        if sep and not key.strip().startswith("#") and len(value) >= 8:
            out[key.strip()] = value.encode()
    return out


def scan(label, data, secrets):
    """[(label, line, rule)] for one file's bytes."""
    found = []
    for name, value in secrets.items():
        for needle, rule in ((value, f".env value {name}"), (value[-16:], f".env value {name} (last 16 chars)")):
            if needle in data:
                found.append((label, data[:data.index(needle)].count(b"\n") + 1, rule))
                break
    for rule, pattern in PATTERNS.items():
        for m in re.finditer(pattern, data):
            found.append((label, data[:m.start()].count(b"\n") + 1, rule))
    return found


def history_blobs():
    """{blob sha: path} for every blob reachable from any ref (empty when there are no commits)."""
    if not git("rev-list", "--all").strip():
        return {}
    paths = {}
    for line in git("rev-list", "--all", "--objects").decode().splitlines():
        sha, _, path = line.partition(" ")
        if path:
            paths.setdefault(sha, path)
    checked = git("cat-file", "--batch-check", stdin="\n".join(paths).encode()).decode().splitlines()
    return {sha: paths[sha] for sha, kind, *_ in (c.split() for c in checked) if kind == "blob"}


def main():
    env = Path(sys.argv[sys.argv.index("--env") + 1]) if "--env" in sys.argv else ROOT / ".env"
    secrets = env_values(env)
    files = [f for f in git("ls-files", "-z", "--cached", "--others", "--exclude-standard").decode().split("\0") if f]
    findings = [(f, 0, "file must not be published") for f in files if BAD_NAME.search(f)]
    for f in files:
        if (ROOT / f).is_file():
            findings += scan(f, (ROOT / f).read_bytes(), secrets)
    blobs = history_blobs()
    for sha, path in blobs.items():
        findings += scan(f"history {sha[:10]} ({path})", git("cat-file", "blob", sha), secrets)
        if BAD_NAME.search(path):
            findings.append((f"history {sha[:10]} ({path})", 0, "file must not be published"))

    print(f"Scanned {len(files)} publishable files and {len(blobs)} history blobs "
          f"against {len(secrets)} .env values and {len(PATTERNS)} key patterns.")
    for label, line, rule in findings:
        print(f"  FOUND  {label}:{line}  {rule}")
    print("FAIL: remove these before publishing (and rotate any real key)." if findings else "OK: no secrets found.")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
