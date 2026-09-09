"""Create a portable source archive; never include secrets, local data or dependencies."""
from pathlib import Path
import argparse,zipfile
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',default=str(root.parent/'dreamcatcher.zip'));args=p.parse_args()
excluded={'.git','.venv','node_modules','data','__pycache__','.pytest_cache','test-results','dist','.openai'}
with zipfile.ZipFile(args.output,'w',zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(root.rglob('*')):
        relative=path.relative_to(root)
        if not path.is_file() or any(part in excluded for part in relative.parts):continue
        if path.name.startswith('.env') and path.name!='.env.example':continue
        if path.suffix in ('.sqlite','.db','.pyc','.pem','.key') or path.name.endswith('.zip'):continue
        archive.write(path,Path('dreamcatcher')/relative)
print(args.output)
