"""Build the precomputed runtime data (data/runtime/, babel/runtime.py) from the committed backtest data and the API
cache. By default it makes no network request at all: pool games never checked in Qloo stay 'unchecked' (checked live
when a plan needs them). --check-qloo also checks those in Qloo (about two requests each; mind the hackathon quota).

  python tools/build_runtime.py
  python tools/build_runtime.py --check-qloo
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from babel import net, runtime  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Build data/runtime/ from the API cache.")
    ap.add_argument("--out", default=str(runtime.DIR), help="output folder (default data/runtime)")
    ap.add_argument("--check-qloo", action="store_true", help="check unchecked pool games in Qloo (network)")
    a = ap.parse_args()
    started = time.perf_counter()
    files = runtime.build(check_qloo=a.check_qloo)
    manifest = runtime.save(files, a.out, a.check_qloo)
    print(f"Built {a.out} in {time.perf_counter() - started:.0f} s; network requests: {sum(net.calls.values())}.")
    for name, meta in manifest["files"].items():
        print(f"  {name:<14}{meta['bytes'] / 1024:8.0f} KB")
    print("  counts: " + ", ".join(f"{k} {v}" for k, v in manifest["counts"].items()))
    started = time.perf_counter()
    runtime.load(a.out)
    print(f"Loads in {time.perf_counter() - started:.1f} s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
