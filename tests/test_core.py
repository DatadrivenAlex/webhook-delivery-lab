from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import pytest
from app import core

@pytest.fixture
def db(tmp_path):
    path = tmp_path / 'test.sqlite3'
    core.initialize(path)
    return path

def test_idempotency_and_conflict(db):
    first, created = core.enqueue(db, 'order-1', {'amount': 15, 'currency': 'EUR'})
    assert created
    second, created = core.enqueue(db, 'order-1', {'currency': 'EUR', 'amount': 15})
    assert not created and first['id'] == second['id']
    with pytest.raises(core.Conflict):
        core.enqueue(db, 'order-1', {'amount': 16})

def test_retry_backoff_and_terminal_state(db):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    event, _ = core.enqueue(db, 'x', {}, now)
    for attempt in range(1, core.MAX_ATTEMPTS + 1):
        event = core.deliver_one(db, event['id'], False, now)
        assert event['attempts'] == attempt
        assert event['status'] == ('failed' if attempt == core.MAX_ATTEMPTS else 'pending')
        if attempt < core.MAX_ATTEMPTS:
            assert core.deliver_one(db, event['id'], True, now)['attempts'] == attempt
        now += timedelta(seconds=2 ** attempt * 10)
    assert core.deliver_one(db, event['id'], True, now)['status'] == 'failed'

def test_success_does_not_repeat(db):
    event, _ = core.enqueue(db, 'x', {})
    done = core.deliver_one(db, event['id'], True)
    assert done['status'] == 'delivered' and done['attempts'] == 1
    assert core.deliver_one(db, event['id'], False)['attempts'] == 1

def test_hmac_tampering():
    signature = core.sign('{"a":1}', 'demo-key')
    assert core.verify('{"a":1}', 'demo-key', signature)
    assert not core.verify('{"a":2}', 'demo-key', signature)
    assert not core.verify('{"a":1}', 'other', signature)

def test_concurrent_idempotent_enqueue(db):
    with ThreadPoolExecutor(max_workers=5) as pool:
        events = list(pool.map(lambda _: core.enqueue(db, 'same', {'x': 1}), range(5)))
    assert len({e['id'] for e, _ in events}) == 1
    assert sum(created for _, created in events) == 1
