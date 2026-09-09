"""Run reviewed control-plane migrations with a migration-only connection."""
import sys
from pathlib import Path
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
sys.path.insert(0, str(ROOT / 'backend'))
from dreamcatcher.db import migrate
if __name__ == '__main__':
    migrate()
    print('Control migrations complete. State database uses deploy/postgres-state.sql separately.')
