"""Restore frozen serving artifacts without training; verify every SHA-256."""
import argparse,hashlib,json,os,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--directory',type=Path,default=root/'models')
parser.add_argument('--verify-only',action='store_true')
args=parser.parse_args()
manifest=json.loads((root/'models/manifest.json').read_text(encoding='utf-8-sig'))
args.directory.mkdir(parents=True,exist_ok=True)
for item in manifest['artifacts']:
    name=item['file']
    if Path(name).name!=name:raise ValueError('Manifest filename must be a basename')
    target=args.directory/name
    def valid(p):
        if not p.is_file() or p.stat().st_size!=item['bytes']:return False
        with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()==item['sha256']
    if valid(target):print('Verified',name);continue
    if args.verify_only:raise ValueError(f'Missing or mismatched artifact: {name}')
    expected=f"https://huggingface.co/spaces/Aayush1574/cardioscope-api/resolve/{manifest['revision']}/models/{name}"
    if item['url']!=expected:raise ValueError('Unexpected artifact URL')
    temporary=target.with_name(target.name+'.download')
    try:
        urllib.request.urlretrieve(expected,temporary)
        if not valid(temporary):raise ValueError(f'Checksum mismatch: {name}')
        os.replace(temporary,target)
    finally:temporary.unlink(missing_ok=True)
    print('Restored',name)
