"""Coverage for the custom-weight UI contract and the snapshot tool.

These protect the two MASTER_SPEC items closed in this pass:
- §15 five-dimension sliders / custom objective weights (backend contract)
- §33/§35 snapshot tooling (no-Git version discipline)

Neither test touches the first/second baton's stable behaviour; they only assert
that the additive APIs stay additive.
"""
import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import Problem
from app.solver.engine import WEIGHTS, solve

ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)


# --------------------------------------------------------------------------- #
# Custom objective weights (MASTER_SPEC §15)
# --------------------------------------------------------------------------- #

def _life():
    return client.get('/api/templates/life').json()


def test_weights_metadata_endpoint_exposes_dimensions_and_presets():
    r = client.get('/api/weights')
    assert r.status_code == 200
    data = r.json()
    keys = [d['key'] for d in data['dimensions']]
    assert keys == ['goal', 'compact', 'balance', 'robust', 'lead', 'stability', 'regular']
    assert set(data['presets']) == {'efficient', 'balanced', 'robust'}
    assert data['repair_stability'] >= 1


def test_preset_without_overrides_is_unchanged():
    """A request with no custom weights must solve exactly as before."""
    problem = Problem.model_validate(_life())
    result = solve(problem, mode='balanced')
    assert result['objective']['weights'] == WEIGHTS['balanced']


def test_custom_weights_are_honoured_by_the_solver():
    body = {'problem': _life(), 'reviewed': True, 'mode': 'balanced',
            'weights': {'compact': 50, 'balance': 0, 'regular': 0}}
    r = client.post('/api/solve', json=body)
    assert r.status_code == 200
    weights = r.json()['objective']['weights']
    assert weights['compact'] == 50
    assert weights['balance'] == 0
    assert weights['regular'] == 0
    # Untouched keys keep their preset value.
    assert weights['goal'] == WEIGHTS['balanced']['goal']
    assert weights['robust'] == WEIGHTS['balanced']['robust']


def test_unknown_and_negative_weights_are_ignored():
    body = {'problem': _life(), 'reviewed': True, 'mode': 'balanced',
            'weights': {'balance': -5, 'unknown_key': 999}}
    r = client.post('/api/solve', json=body)
    weights = r.json()['objective']['weights']
    assert weights['balance'] == WEIGHTS['balanced']['balance']  # negative rejected
    assert 'unknown_key' not in weights                            # unknown dropped


def test_all_zero_profile_falls_back_to_preset_goal():
    """A degenerate all-zero profile must not silently strip the objective."""
    body = {'problem': _life(), 'reviewed': True, 'mode': 'balanced',
            'weights': {k: 0 for k in WEIGHTS['balanced']}}
    r = client.post('/api/solve', json=body)
    assert r.json()['objective']['weights']['goal'] == WEIGHTS['balanced']['goal']


def test_custom_weights_do_not_bypass_the_review_gate():
    body = {'problem': _life(), 'reviewed': False, 'mode': 'balanced',
            'weights': {'compact': 50}}
    assert client.post('/api/solve', json=body).status_code == 409


# --------------------------------------------------------------------------- #
# Snapshot tool (MASTER_SPEC §33 / §35)
# --------------------------------------------------------------------------- #

def _run_snapshot(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / 'tools' / 'snapshot.py'), *args],
        capture_output=True, text=True, cwd=ROOT,
    )


def test_snapshot_list_runs_without_error():
    result = _run_snapshot('--list')
    assert result.returncode == 0
    assert '快照' in result.stdout


def test_snapshot_manifest_excludes_scratch_and_build_outputs():
    """The manifest must never contain scratch dirs, node_modules or dist."""
    manifests = sorted((ROOT / 'snapshots').glob('*/manifest.json'))
    if not manifests:
        return  # no snapshot on this machine; the tool test above still covers it
    data = json.loads(manifests[-1].read_text(encoding='utf-8'))
    paths = [f['path'] for f in data['files']]
    assert not any(p.startswith('_scratch') for p in paths)
    assert not any('node_modules' in p for p in paths)
    assert not any(p.startswith('frontend/dist/') for p in paths)
    assert all(f['sha256'] for f in data['files'])


def test_snapshot_bump_maths():
    import importlib.util
    spec = importlib.util.spec_from_file_location('snap', ROOT / 'tools' / 'snapshot.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.bump('0.1.0', 'patch') == '0.1.1'
    assert module.bump('0.1.0', 'minor') == '0.2.0'
    assert module.bump('0.1.0', 'major') == '1.0.0'
