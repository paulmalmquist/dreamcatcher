"""Generate local secrets without overwriting an existing environment."""
from pathlib import Path
import secrets
root=Path(__file__).resolve().parents[1]
target=root/'.env'
if not target.exists():
    text=(root/'.env.example').read_text()
    text=text.replace('DC_SESSION_SECRET=GENERATE_WITH_SETUP','DC_SESSION_SECRET='+secrets.token_hex(32))
    text=text.replace('DC_BUILD_SIGNING_KEY=GENERATE_WITH_SETUP','DC_BUILD_SIGNING_KEY='+secrets.token_hex(32))
    target.write_text(text)
    target.chmod(0o600)
    print('Created .env with local-only secrets. Never commit this file.')
else:
    print('Preserved existing .env')
