"""Protect the public identity and upgrades from existing server configurations."""
from fastapi.testclient import TestClient

from app.config import env
from app.main import app


def test_existing_deployment_options_remain_effective(monkeypatch):
    monkeypatch.delenv('OPTIDAY_SOLVE_SECONDS', raising=False)
    monkeypatch.setenv('ATLAS_SOLVE_SECONDS', '17')
    assert env('OPTIDAY_SOLVE_SECONDS', '4') == '17'
    monkeypatch.setenv('OPTIDAY_SOLVE_SECONDS', '6')
    assert env('OPTIDAY_SOLVE_SECONDS', '4') == '6'


def test_public_health_identifies_product_without_exposing_credentials(monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER', 'deepseek')
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'TEST_ONLY_PRIVATE_VALUE')
    with TestClient(app) as client:
        response = client.get('/api/health')
    assert response.json()['product'] == 'OptiDay'
    assert response.json()['model_configured'] is True
    assert response.json()['parser_type'] == 'model'
    assert 'TEST_ONLY_PRIVATE_VALUE' not in response.text


def test_rule_parser_is_not_presented_as_a_configured_model(monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER', 'demo')
    with TestClient(app) as client:
        data = client.get('/api/health').json()
    assert data['model_configured'] is False
    assert data['parser_type'] == 'rules'
