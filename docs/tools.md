# Tool-ууд: JSON, MCP ба Home Assistant

## Нэг давхарга, нэг хэл: JSON

Bot V-ийн бүх tool, хаана ч байрласан, загварт ижилхэн харагдана:

```json
{"tool": "ha_call_service", "args": {"domain": "light", "service": "turn_on", "entity_id": "light.kitchen"}}
```

| Эх сурвалж | Хэрхэн дуудагдах | Хурд (хэмжсэн) |
|---|---|---|
| **native**: Bot V дотор Python функц (`calculate`, `now`) | шууд дуудна | ~0.03 ms |
| **homeassistant**: Home Assistant REST API | шууд JSON, HTTP | ~2–3 ms (LAN) |
| **mcp:<сервер>**: MCP сервер | JSON-RPC, байнга нээлттэй stdio pipe | ~1.5–3 ms дуудлага бүр |
| MCP серверийг **эхлүүлэх** | нэг удаа | ~0.6 s (Python SDK). `npx` сервер хэдэн секунд |

Локал загвар (Ollama / llama-server) Bot V-тэй **JSON-оор** ярина. Загвар нэг удаадаа нэг JSON объект буцаана: `{"tool": ..., "args": ...}` эсвэл `{"answer": ...}`. Энэ нь function-calling-гүй загвар дээр ч ажилладаг (`bot_v/core/tool_agent.py`).

### MCP яагаад "удаан" санагддаг вэ?

MCP өөрөө JSON-RPC буюу JSON. Нэг дуудлага ердөө 1–3 ms. Удаашрал дараах гурван газраас гардаг:

1. **Сервер эхлүүлэх**: хүсэлт бүрт серверийг шинээр асаавал секунд алдана. → Bot V серверийг **нэг удаа** асааж, pipe-ийг нээлттэй байлгана. Tool-ийн жагсаалтыг **кэшлэнэ**.
2. **Prompt-д хэт олон tool**: 50 tool-ийн тайлбар prompt-д орвол локал загвар түүнийг унших гэж удаан болно. → Bot V зөвхөн хүсэлтэд **хамааралтай tool-уудыг** (дээд тал нь 12) загварт харуулна.
3. **Хурд чухал газар**: Home Assistant-ийг MCP-ээр биш, түүний REST API-аар **шууд JSON**-оор удирдана.

## Аюулгүй байдал: tool дуудлага бүр шалгагдана

| Эрсдэл | Жишээ | Юу болох |
|---|---|---|
| `read` | `calculate`, `ha_get_state`, `allow` жагсаалтад орсон MCP tool | шууд ажиллана |
| `write` | гэрэл асаах, MCP-ийн бусад tool | **таны зөвшөөрлийг хүлээнэ** |
| `dangerous` | цоож, дохиолол, гаражийн хаалга (тусгайлан зөвшөөрсөн үед) | зөвшөөрөл + ⚠️ анхааруулга |
| `blocked` | зөвшөөрөгдөөгүй аюултай үйлдэл, HA-г унтраах/restart | хэзээ ч ажиллахгүй |

Вэб UI дээр зөвшөөрөл шаардсан үйлдэлд баталгаажуулах цонх гарна. Хүлээгдэж буй үйлдлүүд **15 минутын** дараа хүчингүй болно. Зөвшөөрсөн үйлдэл нэг л удаа ажиллана. API: `GET /actions`, `POST /actions/approve {"id"}`, `POST /actions/deny {"id"}`.

Python-оос approver тохируулбал (жишээ нь CLI дээр асуух) queue-гүйгээр шууд асууна:

```python
from bot_v.core.brain import BotV
from bot_v.core.permissions import PermissionGate
bot = BotV(gate=PermissionGate(approver=lambda task, tools: input(f"{task}\nЗөвшөөрөх үү? [y/N] ") == "y"))
```

## Home Assistant

1. Home Assistant дээр: **Profile → Security → Long-lived access tokens → Create token**.
2. Bot V-д:

   ```bash
   export BOTV_HA_URL=http://homeassistant.local:8123
   export BOTV_HA_TOKEN=<token>          # нууц: git-д хэзээ ч битгий оруул
   python -m bot_v.server
   ```

3. Chat-д "Гал тогооны гэрлийг асаа" гэж бичихэд Bot V tool-уудыг өөрөө сонгоно ("auto" горим). Дараа нь зөвшөөрөл асууна.

Tool-ууд:
- `ha_list_entities`: төхөөрөмж, мэдрэгчүүд ба тэдгээрийн төлөв (domain эсвэл үгээр шүүнэ)
- `ha_get_state`: нэг entity-ийн төлөв
- `ha_call_service`: удирдах (`light.turn_on`, `switch.turn_off`, `climate.set_temperature`…)

Хамгаалалт:
- Үйлчилгээ (service) нь entity-ийнхээ domain-д хамаарах ёстой (`light.turn_on` → `light.*`).
- `homeassistant`, `hassio`, `shell_command`, `python_script`… зэрэг системийн domain **үргэлж хаалттай**.
- `lock`, `alarm_control_panel`, `cover` (гаражийн хаалга, хөшиг), `valve`, `siren`, мөн бусад үйлдлийг ажиллуулж чаддаг `script`, `automation`, `scene`, `button` анхдагчаар **хаалттай**. Нээх бол `BOTV_HA_ALLOW_DANGEROUS=1`. Тэгсэн ч зөвшөөрөл шаардана.
- `BOTV_HA_ENTITIES="light.*,switch.kitchen,sensor.*"`: Bot V зөвхөн эдгээрийг харж, удирдана.
- Анхаар: `switch` ч гэсэн гаражийн хаалганы реле байж болно. Ийм тохиолдолд `BOTV_HA_ENTITIES`-ээр нарийн хязгаарлана уу.

## MCP серверүүд

`config/mcp.example.json`-ийг `config/mcp.json` болгон хуулж засна (`config/mcp.json` нь git-д орохгүй). Формат нь Claude Desktop-тойгоо ижил, нэмэлт хоёр түлхүүртэй:

```json
{
  "mcpServers": {
    "files": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/YOU/Documents"],
      "allow": ["read_file", "list_directory"],
      "disabled": false
    }
  }
}
```

- `allow`: зөвшөөрөлгүй ажиллаж болох (зөвхөн уншдаг) tool-ууд. Бусад нь бүгд `write` буюу зөвшөөрөл шаардана.
- Tool-ууд `mcp__<сервер>__<tool>` нэрээр бүртгэгдэнэ.
- Одоогоор зөвхөн **stdio** серверүүд (локал процесс). HTTP (`url`) серверүүд дараагийн алхам.
- Протокол: `initialize` handshake, `2024-11-05` … `2025-11-25` хувилбарууд. MCP Python SDK 2.3.0-ийн сервертэй ажиллахыг шалгасан.
- Серверүүд Bot V-ийг асаахад биш, **tool анх хэрэгтэй болоход** эхэлнэ.

## API

| Endpoint | Юу хийх |
|---|---|
| `GET /tools` | бүх tool, эрсдэл, дуудлагын тоо, дундаж хурд (ms), MCP серверүүдийн төлөв |
| `POST /tools/call {"tool", "args"}` | tool-ийг шууд дуудах (`write` бол 202 + зөвшөөрлийн хүсэлт) |
| `GET /actions` | зөвшөөрөл хүлээж буй үйлдлүүд |
| `POST /actions/approve` / `deny` | `{"id": "..."}` |
| `POST /chat {"backend": "tools"}` | tool-уудыг заавал ашиглуулах |
