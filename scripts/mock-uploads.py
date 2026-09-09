"""Run synthetic HTTP uploads in temporary test databases; never touch GCP or a live registry."""
import subprocess
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if __name__ == '__main__':
    print('SYNTHETIC ONLY: three dashboard uploads, worker doubles, governance and denial tests.', flush=True)
    raise SystemExit(subprocess.call([sys.executable, '-m', 'pytest', 'tests/test_hosted_apps.py', 'tests/test_work_handoff.py', '-v'], cwd=ROOT))
