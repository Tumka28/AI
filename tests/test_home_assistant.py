import pytest
import requests

from bot_v.config import load_settings
from bot_v.integrations.home_assistant import (
    HomeAssistantClient, HomeAssistantError, register_home_assistant_tools,
)
from bot_v.tools import build_default_tools
from bot_v.tools.registry import ToolRegistry

STATES = [
    {"entity_id": "light.kitchen", "state": "off", "attributes": {"friendly_name": "Гал тогооны гэрэл"}},
    {"entity_id": "sensor.living_temp", "state": "21.5",
     "attributes": {"friendly_name": "Зочны өрөөний температур", "unit_of_measurement": "°C"}},
    {"entity_id": "lock.front_door", "state": "locked", "attributes": {"friendly_name": "Front door"}},
    {"entity_id": "switch.heater", "state": "on", "attributes": {"friendly_name": "Heater"}},
]


class FakeResponse:
    def __init__(self, status, data):
        self.status_code = status
        self._data = data
        self.text = str(data)

    def json(self):
        return self._data


class FakeHA:
    """Stands in for requests.Session against Home Assistant's REST API."""

    def __init__(self, token="good"):
        self.token = token
        self.requests = []

    def request(self, method, url, json=None, headers=None, timeout=None):
        self.requests.append((method, url, json, headers))
        if headers.get("Authorization") != f"Bearer {self.token}":
            return FakeResponse(401, {"message": "unauthorized"})
        path = url.split("8123", 1)[1]
        if method == "GET" and path == "/api/":
            return FakeResponse(200, {"message": "API running."})
        if method == "GET" and path == "/api/states":
            return FakeResponse(200, STATES)
        if method == "GET" and path.startswith("/api/states/"):
            for s in STATES:
                if s["entity_id"] == path.rsplit("/", 1)[1]:
                    return FakeResponse(200, s)
            return FakeResponse(404, {"message": "Entity not found."})
        if method == "POST" and path.startswith("/api/services/"):
            entity = json["entity_id"]
            return FakeResponse(200, [{"entity_id": entity, "state": "on", "attributes": {}}])
        return FakeResponse(404, {})


def client(**kw):
    session = kw.pop("session", FakeHA())
    return HomeAssistantClient("http://ha.local:8123/", "good", session=session, **kw), session


def test_list_and_get_states():
    c, session = client()
    assert c.ping()
    items = c.list_entities()
    assert items[1] == {"entity_id": "sensor.living_temp", "state": "21.5",
                        "name": "Зочны өрөөний температур", "unit_of_measurement": "°C"}
    assert [i["entity_id"] for i in c.list_entities(domain="light")] == ["light.kitchen"]
    assert [i["entity_id"] for i in c.list_entities(search="температур")] == ["sensor.living_temp"]
    assert c.get_state("switch.heater")["state"] == "on"
    method, url, payload, headers = session.requests[-1]
    assert url == "http://ha.local:8123/api/states/switch.heater"
    assert headers["Authorization"] == "Bearer good"


def test_service_call_and_risks():
    c, session = client()
    assert c.service_risk("light", "turn_on", "light.kitchen") == "write"
    assert c.service_risk("lock", "unlock", "lock.front_door") == "blocked"  # dangerous, not enabled
    assert c.service_risk("light", "turn_on", "switch.heater") == "blocked"  # wrong domain
    assert c.service_risk("homeassistant", "restart", "light.kitchen") == "blocked"
    assert c.service_risk("light", "turn_on;rm", "light.kitchen") == "blocked"

    out = c.call_service("light", "turn_on", "light.kitchen", {"brightness_pct": 40})
    assert out["changed"][0]["state"] == "on"
    _, url, payload, _ = session.requests[-1]
    assert url.endswith("/api/services/light/turn_on")
    assert payload == {"brightness_pct": 40, "entity_id": "light.kitchen"}

    with pytest.raises(HomeAssistantError, match="blocked"):
        c.call_service("lock", "unlock", "lock.front_door")

    dangerous, _ = client(allow_dangerous=True)
    assert dangerous.service_risk("lock", "unlock", "lock.front_door") == "dangerous"


def test_entity_allowlist():
    c, _ = client(entities=["light.*", "sensor.*"])
    assert [i["entity_id"] for i in c.list_entities()] == ["light.kitchen", "sensor.living_temp"]
    with pytest.raises(HomeAssistantError, match="may not"):
        c.get_state("switch.heater")
    assert c.service_risk("switch", "turn_off", "switch.heater") == "blocked"


def test_errors():
    c, _ = client(session=FakeHA(token="other"))
    with pytest.raises(HomeAssistantError, match="401"):
        c.list_entities()
    c2, _ = client()
    with pytest.raises(HomeAssistantError, match="not found"):
        c2.get_state("light.missing")

    class Down:
        def request(self, *a, **k):
            raise requests.ConnectionError("refused")

    with pytest.raises(HomeAssistantError, match="cannot reach"):
        HomeAssistantClient("http://ha.local:8123", "t", session=Down()).list_entities()
    with pytest.raises(ValueError):
        HomeAssistantClient("", "t")


def test_tools_need_approval_for_actions():
    c, session = client()
    reg = ToolRegistry()
    register_home_assistant_tools(reg, c)
    assert reg.call("ha_get_state", {"entity_id": "sensor.living_temp"})["result"]["state"] == "21.5"
    pending = reg.call("ha_call_service", {"domain": "light", "service": "turn_on", "entity_id": "light.kitchen"})
    assert pending["status"] == "needs_approval"
    assert not any(r[0] == "POST" for r in session.requests)
    assert reg.approve(pending["action"]["id"])["status"] == "ok"
    assert reg.call("ha_call_service", {"domain": "lock", "service": "unlock",
                                        "entity_id": "lock.front_door"})["status"] == "denied"
    assert [t.name for t in reg.relevant("гал тогооны гэрлийг асаа", auto_only=True)]


def test_settings_wire_home_assistant():
    s = load_settings({"BOTV_HA_URL": "http://ha.local:8123", "BOTV_HA_TOKEN": "secret",
                       "BOTV_HA_ENTITIES": "light.*, sensor.*", "BOTV_HA_ALLOW_DANGEROUS": "1"})
    assert s.ha_entities == ["light.*", "sensor.*"] and s.ha_allow_dangerous is True
    assert "secret" not in repr(s)
    registry, mcp = build_default_tools(s)
    assert {"ha_list_entities", "ha_get_state", "ha_call_service", "calculate", "now"} <= {t.name for t in registry.list()}

    registry, _ = build_default_tools(load_settings({}))
    assert not any(t.source == "homeassistant" for t in registry.list())
