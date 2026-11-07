"""Resolve the lab checkout without baking an operator workstation path into sources."""
import os
from pathlib import Path


def lab_repository():
    here = Path(__file__).resolve().parent
    explicit = os.environ.get('STUDIO_NORTH_REPO')
    candidates = [Path(explicit)] if explicit else [*here.parents, here.parent.parent / 'customer-economics-lab']
    for candidate in candidates:
        if (candidate / 'cohort_lab').is_dir() and (candidate / 'hosting').is_dir():
            return candidate.resolve()
    raise RuntimeError('Set STUDIO_NORTH_REPO to the customer-economics-lab checkout.')
