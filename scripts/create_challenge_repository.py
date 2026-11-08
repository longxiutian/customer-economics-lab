"""Create an independent team workspace; does not publish or advance the lab."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]


def create(destination: Path) -> dict:
    destination=destination.resolve()
    if destination==ROOT or ROOT in destination.parents:
        raise ValueError('Create the team repository outside the frozen lab source')
    if destination.exists():
        raise ValueError('Preserve existing work; use a new destination')
    source=ROOT/'challenge'
    expected=['main.py','pyproject.toml','uv.lock','README.md','.gitignore']
    for name in expected:
        if not (source/'template'/name).is_file():raise ValueError('Incomplete released template')
    files={name:source/'template'/name for name in expected}
    files.update({'submission-contract.json':source/'submission-contract.json',
                  'prediction_grid.csv':source/'prediction_grid.csv'})
    destination.mkdir(parents=True)
    for name,path in files.items():shutil.copyfile(path,destination/name)
    receipt={'status':'created','destination':str(destination),'published':False,'lesson_advanced':False,
             'files':{name:hashlib.sha256((destination/name).read_bytes()).hexdigest() for name in files}}
    (destination/'scaffold-receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--destination',type=Path,required=True)
    print(json.dumps(create(p.parse_args().destination),indent=2))
