from fastapi.testclient import TestClient
from app.main import create_app

def test_api_flow(tmp_path):
    with TestClient(create_app(tmp_path / 'api.sqlite3')) as client:
        assert client.get('/health').json()['delivery'] == 'simulated'
        data = {'payload': {'order': 'demo-1'}}
        headers = {'Idempotency-Key': 'test-1'}
        created = client.post('/events', json=data, headers=headers)
        assert created.status_code == 201
        assert client.post('/events', json=data, headers=headers).status_code == 200
        assert client.post('/events', json={'payload': {'order': 'other'}}, headers=headers).status_code == 409
        event_id = created.json()['id']
        assert client.post(f'/events/{event_id}/simulate', json={'succeeds': True}).json()['status'] == 'delivered'
        assert client.get('/events/999').status_code == 404
        assert client.post('/events', json=data).status_code == 422
