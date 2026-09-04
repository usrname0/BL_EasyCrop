"""
Run the headless suite against every installed Blender.

    python tests/run.py            # all versions
    python tests/run.py 5.2        # one version

Blender is launched with --factory-startup so a user's own addons and keymaps
cannot change the result. Exits non-zero if any version fails.
"""

import subprocess
import sys
from pathlib import Path

BLENDER_ROOT = Path(r"C:\Program Files\Blender Foundation")
VERSIONS = ["4.4", "4.5", "5.0", "5.1", "5.2"]
TESTS = ["smoke.py", "test_crop.py", "test_commit.py", "test_hittest.py",
         "test_cursor.py", "test_drawing.py", "test_poll.py"]

HERE = Path(__file__).resolve().parent


def blender_exe(version):
    return BLENDER_ROOT / f"Blender {version}" / "blender.exe"


def run(version, test):
    exe = blender_exe(version)
    if not exe.exists():
        print(f"  {test}: SKIP (Blender {version} not installed)")
        return None

    proc = subprocess.run(
        [str(exe), "-b", "--factory-startup", "--python", str(HERE / test)],
        capture_output=True, text=True)

    passed = proc.returncode == 0
    for line in proc.stdout.splitlines():
        if " PASS" in line or " FAIL" in line or line.startswith("  - "):
            print(f"  {line}")
    if not passed:
        tail = [ln for ln in proc.stdout.splitlines()[-15:]
                if ln and not ln.startswith("Blender")]
        for line in tail:
            print(f"    | {line}")
        if proc.stderr.strip():
            for line in proc.stderr.splitlines()[-10:]:
                print(f"    ! {line}")
    return passed


def main():
    versions = sys.argv[1:] or VERSIONS
    results = {}
    for version in versions:
        print(f"Blender {version}")
        for test in TESTS:
            outcome = run(version, test)
            if outcome is not None:
                results[(version, test)] = outcome

    failed = [k for k, ok in results.items() if not ok]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    for version, test in failed:
        print(f"  FAIL {version} {test}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
