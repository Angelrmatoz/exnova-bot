"""is_open del adapter: schedule del bróker, no una tabla local."""

import time


def _active(name, active_id, schedule):
    return {
        "name": name,
        "id": active_id,
        "enabled": True,
        "is_suspended": False,
        "option": {"profit": {"commission": 20}},
        "schedule": schedule,
    }


def test_adapter_is_open_usa_schedule(adapter, mock_server):
    now = int(time.time())
    mock_server.init = {
        "binary": {
            "actives": {
                "100": _active("AAA", 100, [[now - 3600, now + 3600]]),
                "101": _active("BBB", 101, [[now - 7200, now - 3600]]),
            }
        }
    }
    adapter._client._start()

    assert adapter.is_open("AAA") is True
    assert adapter.is_open("BBB") is False
