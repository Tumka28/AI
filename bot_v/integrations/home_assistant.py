"""Home Assistant over its REST API (direct JSON, no MCP in between).

Setup in Home Assistant: Profile -> Security -> Long-lived access tokens ->
Create token. Then:

    export BOTV_HA_URL=http://homeassistant.local:8123
    export BOTV_HA_TOKEN=<token>                       # never commit it

Safety:
- Reading states is allowed.
- Every service call (turn on a light...) needs approval.
- Services on dangerous domains (locks, alarms, covers such as garage doors,
  valves, sirens, and scripts/automations/scenes/buttons, which can run any
  other action) are blocked unless BOTV_HA_ALLOW_DANGEROUS=1, and even then
  need approval.
- BOTV_HA_ENTITIES (e.g. "light.*,switch.kitchen,sensor.*") limits which
  entities Bot V may see or control at all.
"""

from __future__ import annotations

import fnmatch
import re
from typing import Any, Dict, Iterable, List, Optional

import requests

from bot_v.tools.registry import Tool, ToolRegistry

# Physical security, plus things that can run arbitrary other actions (a script or
# scene can unlock a door; a button can open a garage).
DANGEROUS_DOMAINS = frozenset({"lock", "alarm_control_panel", "cover", "valve", "siren",
                               "script", "automation", "scene", "button", "input_button"})
# Domains whose services act on the HA system itself rather than one device.
BLOCKED_DOMAINS = frozenset({"homeassistant", "hassio", "recorder", "system_log", "shell_command",
                             "python_script", "rest_command", "persistent_notification"})
_ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
_SLUG_RE = re.compile(r"^[a-z0-9_]+$")

# Words that suggest a request is about the home (Mongolian + English).
HOME_KEYWORDS = (
    # Mongolian stems, incl. the forms inflection produces (гэрэл -> гэрлийг, хаалга -> хаалгыг)
    "гэрэл", "гэрл", "ламп", "асаа", "унтраа", "халаагуур", "агааржуулагч", "сэнс", "цоож",
    "хаалг",
    "температур", "чийгшил", "мэдрэгч", "розетк", "телевиз", "хөшиг", "home assistant",
    "light", "lamp", "turn on", "turn off", "switch", "thermostat", "heater", "fan", "sensor",
    "temperature", "humidity", "lock", "door", "garage", "blinds", "curtain",
)


class HomeAssistantError(RuntimeError):
    pass


class HomeAssistantClient:
    def __init__(self, url: str, token: str, *, entities: Optional[Iterable[str]] = None,
                 allow_dangerous: bool = False, timeout: float = 10.0, session: Any = None):
        if not url or not token:
            raise ValueError("Home Assistant needs both a URL and a token")
        self.url = url.rstrip("/")
        self.token = token
        self.patterns = [p.strip() for p in (entities or []) if p.strip()]
        self.allow_dangerous = allow_dangerous
        self.timeout = timeout
        self.session = session or requests.Session()

    # ------------------------------------------------------------- access
    def entity_allowed(self, entity_id: str) -> bool:
        if not _ENTITY_RE.match(entity_id or ""):
            return False
        if not self.patterns:
            return True
        return any(fnmatch.fnmatch(entity_id, p) for p in self.patterns)

    def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        try:
            res = self.session.request(method, f"{self.url}{path}", json=payload,
                                       headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise HomeAssistantError(f"cannot reach Home Assistant at {self.url}: {exc}") from exc
        if res.status_code == 401:
            raise HomeAssistantError("Home Assistant rejected the token (401)")
        if res.status_code == 404:
            raise HomeAssistantError(f"not found: {path}")
        if res.status_code >= 400:
            raise HomeAssistantError(f"Home Assistant returned HTTP {res.status_code}: {res.text[:200]}")
        try:
            return res.json()
        except ValueError:
            return {"text": res.text[:500]}

    # ---------------------------------------------------------------- API
    def ping(self) -> bool:
        return isinstance(self._request("GET", "/api/"), dict)

    @staticmethod
    def _compact(state: Dict[str, Any]) -> Dict[str, Any]:
        attrs = state.get("attributes") or {}
        out = {"entity_id": state.get("entity_id"), "state": state.get("state"),
               "name": attrs.get("friendly_name")}
        for key in ("unit_of_measurement", "device_class", "brightness", "temperature",
                    "current_temperature", "hvac_mode"):
            if key in attrs:
                out[key] = attrs[key]
        return out

    def list_entities(self, domain: Optional[str] = None, search: Optional[str] = None,
                      limit: int = 50) -> List[Dict[str, Any]]:
        states = self._request("GET", "/api/states")
        out = []
        needle = (search or "").lower()
        for state in states if isinstance(states, list) else []:
            entity_id = state.get("entity_id", "")
            if not self.entity_allowed(entity_id):
                continue
            if domain and not entity_id.startswith(domain + "."):
                continue
            item = self._compact(state)
            if needle and needle not in entity_id.lower() and needle not in str(item.get("name") or "").lower():
                continue
            out.append(item)
            if len(out) >= limit:
                break
        return out

    def get_state(self, entity_id: str) -> Dict[str, Any]:
        if not self.entity_allowed(entity_id):
            raise HomeAssistantError(f"Bot V may not access {entity_id}")
        return self._compact(self._request("GET", f"/api/states/{entity_id}"))

    def service_risk(self, domain: str, service: str, entity_id: str) -> str:
        if not (_SLUG_RE.match(domain or "") and _SLUG_RE.match(service or "")):
            return "blocked"
        if domain in BLOCKED_DOMAINS or not self.entity_allowed(entity_id):
            return "blocked"
        if not entity_id.startswith(domain + "."):
            # The service must belong to the entity's own domain (light.turn_on -> light.x).
            return "blocked"
        if domain in DANGEROUS_DOMAINS:
            return "dangerous" if self.allow_dangerous else "blocked"
        return "write"

    def call_service(self, domain: str, service: str, entity_id: str,
                     data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self.service_risk(domain, service, entity_id) == "blocked":
            raise HomeAssistantError(f"{domain}.{service} on {entity_id} is blocked by Bot V")
        payload = {**(data or {}), "entity_id": entity_id}
        changed = self._request("POST", f"/api/services/{domain}/{service}", payload)
        states = [self._compact(s) for s in changed if isinstance(s, dict)] if isinstance(changed, list) else []
        return {"called": f"{domain}.{service}", "entity_id": entity_id, "changed": states}


def register_home_assistant_tools(registry: ToolRegistry, client: HomeAssistantClient) -> None:
    registry.register(Tool(
        name="ha_list_entities",
        description="List Home Assistant devices/sensors with their current state. "
                    "Filter by domain (light, switch, sensor, climate...) or by a search word.",
        input_schema={"type": "object", "properties": {
            "domain": {"type": "string"}, "search": {"type": "string"}, "limit": {"type": "integer"},
        }, "additionalProperties": False},
        handler=lambda a: client.list_entities(a.get("domain"), a.get("search"), int(a.get("limit", 50))),
        source="homeassistant", risk="read", keywords=HOME_KEYWORDS, auto=True,
    ))
    registry.register(Tool(
        name="ha_get_state",
        description="Get the current state of one Home Assistant entity, e.g. sensor.living_room_temperature.",
        input_schema={"type": "object", "properties": {"entity_id": {"type": "string"}},
                      "required": ["entity_id"], "additionalProperties": False},
        handler=lambda a: client.get_state(a["entity_id"]),
        source="homeassistant", risk="read", keywords=HOME_KEYWORDS, auto=True,
    ))
    registry.register(Tool(
        name="ha_call_service",
        description="Control a Home Assistant entity, e.g. domain='light', service='turn_on', "
                    "entity_id='light.kitchen', data={'brightness_pct': 50}. Needs the user's approval.",
        input_schema={"type": "object", "properties": {
            "domain": {"type": "string"}, "service": {"type": "string"},
            "entity_id": {"type": "string"}, "data": {"type": "object"},
        }, "required": ["domain", "service", "entity_id"], "additionalProperties": False},
        handler=lambda a: client.call_service(a["domain"], a["service"], a["entity_id"], a.get("data")),
        source="homeassistant",
        classify=lambda a: client.service_risk(a.get("domain", ""), a.get("service", ""), a.get("entity_id", "")),
        keywords=HOME_KEYWORDS, auto=True,
    ))
