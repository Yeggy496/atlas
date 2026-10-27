"""Coverage for the two MASTER_SPEC items closed in this pass.

- §23 documented API surface: standalone ``/api/diagnose`` and the
  ``/api/parse-constraints`` alias.
- §25 P2 exports: XLSX and PDF rendered from the exact solved result.

Like the other third-baton test files these only assert that the additions are
purely additive — no existing endpoint changes behaviour.
"""
import io

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from pypdf import PdfReader

from app.main import app
from app.schemas import Problem
from app.exporters import build_pdf, build_xlsx

client = TestClient(app)


def _template(scenario='life'):
    return client.get(f'/api/templates/{scenario}').json()


def _solved(scenario='life'):
    # The lifespan creates SQLite tables, just as it does on server startup.
    # A bare TestClient masks this requirement when an old database exists.
    with TestClient(app) as started_client:
        problem = started_client.get(f'/api/templates/{scenario}').json()
        response = started_client.post(
            '/api/solve', json={'problem': problem, 'reviewed': True, 'mode': 'balanced'}
        )
        assert response.status_code == 200, response.text
        result = response.json()
    return problem, result


# --------------------------------------------------------------------------- #
# §23 API surface
# --------------------------------------------------------------------------- #

def test_parse_constraints_alias_matches_canonical_route():
    payload = {'problem': _template(), 'text': '周五下午不要安排任何课程'}
    alias = client.post('/api/parse-constraints', json=payload)
    canonical = client.post('/api/constraints/parse', json=payload)
    assert alias.status_code == canonical.status_code == 200
    assert alias.json() == canonical.json()


def test_diagnose_reports_no_conflict_for_solvable_problem():
    """A healthy problem must NOT be diagnosed as infeasible (§14)."""
    response = client.post(
        '/api/diagnose',
        json={'problem': _template(), 'reviewed': True, 'mode': 'balanced'},
    )
    assert response.status_code == 200
    body = response.json()
    assert body['status'] in ('OPTIMAL', 'FEASIBLE')
    assert body['infeasible'] is False
    assert body['conflicts'] == []
    assert body['repairs'] == []


def test_diagnose_finds_conflict_and_repairs_for_broken_problem():
    broken = client.post('/api/demo/conflict', json=_template()).json()
    response = client.post(
        '/api/diagnose', json={'problem': broken, 'reviewed': True, 'mode': 'balanced'}
    )
    assert response.status_code == 200
    body = response.json()
    assert body['infeasible'] is True
    assert body['conflicts'], 'a proven-infeasible problem must surface a conflict'
    # Every repair is CP-SAT verified, never a guess.
    assert all(r['verified'] for r in body['repairs'])


def test_diagnose_endpoint_is_documented_in_openapi():
    paths = client.get('/openapi.json').json()['paths']
    assert '/api/diagnose' in paths
    assert '/api/parse-constraints' in paths


# --------------------------------------------------------------------------- #
# §25 P2 exports
# --------------------------------------------------------------------------- #

def test_export_xlsx_is_a_valid_workbook_with_the_full_schedule():
    problem, result = _solved()
    response = client.post(
        '/api/export/xlsx', json={'problem': problem, 'result': result}
    )
    assert response.status_code == 200
    assert 'spreadsheetml' in response.headers['content-type']
    assert '.xlsx' in response.headers['content-disposition']

    workbook = load_workbook(io.BytesIO(response.content))
    assert workbook.sheetnames == ['调度明细', '每日负载', '求解概况']
    sheet = workbook['调度明细']
    assert sheet.max_row == len(result['assignments']) + 1  # header + rows
    # Chinese activity names survive the round trip.
    names = {row[0] for row in sheet.iter_rows(min_row=2, values_only=True)}
    assert {'睡眠', '高等数学'} <= names


def test_export_pdf_is_a_parsable_document():
    problem, result = _solved()
    response = client.post(
        '/api/export/pdf', json={'problem': problem, 'result': result}
    )
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/pdf'
    assert response.content.startswith(b'%PDF')
    assert response.content.rstrip().endswith(b'%%EOF')

    reader = PdfReader(io.BytesIO(response.content))
    text = reader.pages[0].extract_text()
    assert 'OptiDay' in text
    assert result['status'] in text
    assert len(reader.pages) >= 1


def test_export_rejects_unsupported_format():
    problem, result = _solved('lab')
    response = client.post(
        '/api/export/csv', json={'problem': problem, 'result': result}
    )
    assert response.status_code == 404


def test_export_handles_non_scalar_metrics():
    """Regression: metrics contain lists (per-day load) which OpenPyXL rejects."""
    problem, result = _solved()
    assert any(isinstance(v, list) for v in (result.get('metrics') or {}).values())
    payload = build_xlsx(Problem.model_validate(problem), result)
    workbook = load_workbook(io.BytesIO(payload))
    values = [
        row[1]
        for row in workbook['求解概况'].iter_rows(min_row=2, values_only=True)
    ]
    assert any(isinstance(v, str) and ',' in v for v in values)


def test_exporters_are_pure_functions_of_the_result():
    """Same result in, same bytes out — an export never re-solves (§27 #6)."""
    problem, result = _solved('production')
    parsed = Problem.model_validate(problem)
    assert build_xlsx(parsed, result) == build_xlsx(parsed, result)
    assert build_pdf(parsed, result) == build_pdf(parsed, result)
