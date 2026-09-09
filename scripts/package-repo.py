"""Create a portable source archive; never include secrets, local data or dependencies."""
from pathlib import Path
import argparse,zipfile,subprocess
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',default=str(root.parent/'dreamcatcher.zip'));args=p.parse_args()
excluded={'.git','.venv','node_modules','data','__pycache__','.pytest_cache','test-results','.openai','work-integration-evidence'}
# A reviewed git checkout is the source of truth; never sweep untracked work files.
tracked=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0')
with zipfile.ZipFile(args.output,'x',zipfile.ZIP_DEFLATED) as archive:
    for name in sorted(filter(None,tracked)):
        relative=Path(name);path=root/relative
        if not path.is_file() or path.is_symlink() or any(part in excluded for part in relative.parts):continue
        if relative.parts[:2] in (('frontend','dist'),('sdk','dist')):continue
        if path.name=='work_connections.py':continue
        if path.name.startswith('.env') and path.name!='.env.example':continue
        if path.suffix in ('.sqlite','.db','.pyc','.pem','.key') or path.name.endswith('.zip'):continue
        archive.write(path,Path('dreamcatcher')/relative)
    sdk=root/'artifacts/dreamcatcher-sdk.tgz'
    if sdk.is_file() and not sdk.is_symlink():archive.write(sdk,'dreamcatcher/artifacts/dreamcatcher-sdk.tgz')
print(args.output)
