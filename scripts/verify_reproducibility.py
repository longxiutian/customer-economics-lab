#!/usr/bin/env python3
"""Run two fresh Python processes and compare scientific and presentation outputs.

This is an instructor/release check, not a command for the guided student flow.
It makes a scoped same-environment claim; it does not promise cross-platform
floating-point or PDF byte identity.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compared_files(run: Path, pdf: bool) -> list[str]:
    names = [str(p.relative_to(run)).replace('\\', '/') for p in (run/'tables').glob('*.csv')]
    names += ['analysis_summary.json', 'model_summary.json', 'posterior_draws.json', 'benchmark_summary.json',
              'diagrams/source_inventory.json', 'diagrams/diagram_manifest.json',
              'report/customer-economics-report.tex']
    names += [str(p.relative_to(run)).replace('\\', '/') for p in (run/'report').glob('*.sty')]
    names += [str(p.relative_to(run)).replace('\\', '/') for p in (run/'report').glob('*.csv')]
    names += [str(p.relative_to(run)).replace('\\', '/') for p in (run/'report').glob('*.json')]
    names += [str(p.relative_to(run)).replace('\\', '/') for p in (run/'diagrams').glob('*') if p.suffix in {'.html','.svg','.png'}]
    names += ['diagrams/ucv-tables.json']
    names += [str(p.relative_to(run)).replace('\\', '/') for p in (run/'challenge').glob('*.csv')]
    names += [str(p.relative_to(run)).replace('\\', '/') for p in (run/'challenge').glob('*.json')]
    # Only canonical report figures belong to the scientific/presentation
    # contract. Ad hoc contact sheets and page renders are visual QA evidence.
    names += [str(p.relative_to(run)).replace('\\', '/') for p in (run/'report/figures').glob('*.png')]
    names += [str(p.relative_to(run)).replace('\\', '/') for p in (run/'report/figures').glob('*.pdf')]
    if pdf:
        names.append('report/customer-economics-report.pdf')
    return sorted(set(names))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'outputs/reproducibility')
    parser.add_argument('--steps', type=int, default=3000)
    parser.add_argument('--no-pdf', action='store_true')
    parser.add_argument('--parallel', action='store_true', help='Run the two independent processes concurrently; each owns its output/build directory.')
    args = parser.parse_args()
    parent = args.output.resolve()
    if parent.exists() and any(parent.iterdir()):
        raise SystemExit('Use a new empty reproducibility directory; prior receipts are preserved.')
    parent.mkdir(parents=True, exist_ok=True)
    runs = [parent/'run-a', parent/'run-b']
    def command_for(run):
        command = [sys.executable, str(ROOT/'lab.py'), '--output', str(run), '--steps', str(args.steps)]
        if args.no_pdf:
            command.append('--no-pdf')
        command += ['batch', '--instructor']
        return command
    if args.parallel:
        with contextlib.ExitStack() as stack:
            jobs=[]
            for run in runs:
                log=stack.enter_context((parent/(run.name+'.log')).open('w',encoding='utf-8'))
                jobs.append((run,subprocess.Popen(command_for(run),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)))
            failures=[]
            for run,process in jobs:
                if process.wait(): failures.append(run.name)
                else: print(f'{run.name} completed',flush=True)
            if failures: raise SystemExit(f'{failures} failed; inspect logs. No reproducibility claim made.')
    else:
        for run in runs:
            with (parent/(run.name+'.log')).open('w', encoding='utf-8') as log:
                completed = subprocess.run(command_for(run), cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            if completed.returncode:
                raise SystemExit(f'{run.name} failed; inspect its log. No reproducibility claim made.')
            print(f'{run.name} completed', flush=True)
    files = compared_files(runs[0], not args.no_pdf)
    other = compared_files(runs[1], not args.no_pdf)
    if files != other:
        raise SystemExit('Artifact inventory differs between runs.')
    comparisons = {name: {'run_a_sha256': sha(runs[0]/name), 'run_b_sha256': sha(runs[1]/name)} for name in files}
    mismatches = [name for name, values in comparisons.items() if values['run_a_sha256'] != values['run_b_sha256']]
    receipt = {'schema_version': 1, 'status': 'pass' if not mismatches else 'fail',
               'scope': 'Two fresh processes; same frozen inputs, source, dependency lock, seed, settings and host.',
               'python': platform.python_version(), 'platform': platform.platform(),
               'parallel_processes':bool(args.parallel),
               'seed': 20261116, 'steps': args.steps, 'uv_lock_sha256': sha(ROOT/'uv.lock'),
               'frozen_data_manifest_sha256': sha(ROOT/'data/manifest.json') if (ROOT/'data/manifest.json').exists() else sha(ROOT/'data/data_manifest.json'),
               'compared_files': len(files), 'comparisons': comparisons, 'mismatches': mismatches}
    (parent/'reproducibility.json').write_text(json.dumps(receipt, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    print(json.dumps({k: receipt[k] for k in ('status','compared_files','mismatches')}, indent=2))
    if mismatches:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
