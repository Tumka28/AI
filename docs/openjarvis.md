# OpenJarvis судалгаа ба Bot V-тэй холбох зураглал

Судалсан хувилбар: **OpenJarvis 1.0.4** (PyPI, 2026). Эх сурвалж: <https://github.com/open-jarvis/OpenJarvis>. Stanford-ийн Hazy Research болон Scaling Intelligence Lab хөгжүүлдэг.

## Үндсэн дүгнэлт

| Асуулт | Хариулт |
|---|---|
| Лиценз | **Apache-2.0**: ашиглах, өөрчлөх, хуулах боломжтой. Хуулбал LICENSE болон эх сурвалжийг заавал дурдана. |
| Хэмжээ | ~680 Python файл, 30 гаруй дэд модуль |
| Python | 3.10–3.13 |
| Хэрхэн дуудах | `from openjarvis import Jarvis` → `Jarvis(config_path=...).ask_full(query, agent=..., tools=[...])` |
| Локал модель | `ollama`, `llamacpp` (llama-server, порт 8080), `vllm`, `sglang`, `lmstudio`, `mlx`, … |
| Аналитик | **Анхдагчаар асаалттай**: OpenJarvis хөгжүүлэгчид рүү нэргүй хэрэглээний мэдээлэл (PostHog) илгээдэг. Bot V-ийн `config/openjarvis.toml` үүнийг **унтраадаг** (`[analytics] enabled = false`). Харин телеметр (`telemetry.db`) нь зөвхөн локал SQLite файл. |

## Яагаад файлуудыг тарааж хуулаагүй вэ?

1. **Удирдлага**: Bot V тархи, OpenJarvis гүйцэтгэгч. Кодыг нь холбол хэн хэнийг удирдаж байгаа нь ялгагдахгүй болно.
2. **Шинэчлэл**: OpenJarvis хурдан хөгжиж байна (1.0.0 → 1.0.4). Тусад нь байлгавал `pip install -U` хийхэд л хангалттай. Хуулсан кодыг гараар нэгтгэх шаардлагагүй.
3. **Солих боломж**: өөр framework сайн болвол зөвхөн `bot_v/integrations/`-д шинэ adapter нэмнэ.
4. **Лиценз**: хуулаагүй тул Apache-2.0-ийн NOTICE/өөрчлөлтийн шаардлага Bot V-ийн кодонд хамаарахгүй.

## OpenJarvis-ийн бүтэц → Bot V-д хэрхэн ашиглах

| OpenJarvis модуль | Юу хийдэг | Bot V-д |
|---|---|---|
| `engine/` | Inference: ollama, llamacpp, vllm, cloud, litellm… | ✅ adapter-аар (OpenJarvis өөрөө engine-ээ сонгоно) |
| `agents/` (22) | `simple`, `orchestrator` (tool автоматаар сонгоно), `native_react`, `deep_research`, `native_openhands` (CodeAct), `operative`, `monitor_operative`, `morning_digest`, `claude_code`, `minions`, `conductor`… | ✅ `bot.delegate(task, agent=...)` |
| `tools/` (43) | calculator, web_search, file_read/write, shell_exec, code_interpreter, git_*, http_request, memory_*, kg_* (knowledge graph), pdf_extract, text_to_speech… | ✅ `bot.delegate(task, tools=[...])` + **Bot V-ийн зөвшөөрлийн хаалга** |
| `memory/`, `tools/storage/` | sqlite, bm25, faiss, dense, hybrid, knowledge_graph санах ой | ✅ `adapter.index_path()`, `adapter.search_memory()` |
| `skills/` | agentskills.io стандарт. Hermes (~150), OpenClaw (~13,700) skill импортлох | ✅ Bot V ижил форматаар өөрөө импортолно (quarantine → шалгалт → зөвшөөрөл, [docs/skills.md](skills.md)). OpenJarvis-ийн SDK skill ачаалдаггүй (`cli/ask.py` л ачаалдаг) тул Bot V зааврыг даалгавартай хамт дамжуулна |
| `learning/` | Trace-ээс суралцах, DSPy-аар prompt/skill оновчлох | ⏳ Bot V өөрийн багш + SFT/DPO dataset-тэй боллоо ([docs/learning.md](learning.md)). OpenJarvis-ийн learning-тэй холбох нь дараагийн алхам |
| `mcp/`, `a2a/` | MCP сервер/клиент, agent-to-agent протокол | ✅ Bot V өөрийн MCP client-тэй боллоо ([docs/tools.md](tools.md)): серверийг нэг удаа асааж, tool бүрийг Bot V-ийн зөвшөөрлөөр дуудна. a2a нь дараа |
| `channels/` | Telegram, Slack, Discord, Twilio, Gmail… | ⏳ утсаар Bot V-тэй ярих (6-р үе) |
| `speech/` | Whisper STT, TTS | ⏳ дуут удирдлага |
| `scheduler/`, `daemon/` | Хуваарьт ажил, байнгын agent | ⏳ |
| `security/` | Capability policy, rate limit, audit log | OpenJarvis дотооддоо ажиллуулдаг. Bot V нэмж өөрийн хаалгатай. |
| `server/`, `cli/` | OpenJarvis-ийн өөрийн API/CLI (`jarvis`) | ✗ хэрэглэхгүй: Bot V-ийн өөрийн сервер байгаа |
| `analytics/` | PostHog | ✗ **унтраасан** |

## Bot V-ийн модулиуд ба OpenJarvis давхцал

| Bot V | OpenJarvis | Цаашид |
|---|---|---|
| `core/react_engine.py` | `native_react` agent | Хоёулаа үлдэнэ. Bot V-ийнх нь Bot V-ийн өөрийн tool-уудад, OpenJarvis-ийнх нь түүний 43 tool-д. |
| `memory/` (JSON vector store) | sqlite/faiss/hybrid memory | OpenJarvis-ийн санах ой илүү хүчтэй. 4-р үед Bot V-ийн санах ойг түүн рүү шилжүүлэх эсэхийг шийднэ. |
| `skills/` (regex-ээр skill гаргах) | agentskills.io skill catalog | OpenJarvis-ийн стандартыг хэрэглэж, Bot V-ийн үүсгэсэн skill-ийг тэр форматаар хадгалах |
| `self_optimize/` | `learning/` (DSPy, trace) | experience log → OpenJarvis learning |
| `debugger/sandbox_runner.py` | `sandbox/`, `code_interpreter_docker` | Docker sandbox руу шилжих |

## Шалгасан зүйлс

Энэ PR дээр бодитоор шалгасан:
- `openjarvis==1.0.4` суулгаж, `config/openjarvis.toml` уншигдаж байгаа (engine = llamacpp, analytics = false).
- llama-server-ийг дуурайсан туршилтын сервертэй **Bot V → adapter → OpenJarvis → llamacpp engine** бүтэн зам ажилласан: шууд асуулт, `simple` agent, `orchestrator` + `calculator`.
- `shell_exec` хүссэн даалгавар OpenJarvis-д хүрэхээс өмнө Bot V дээр хориглогдсон. Approver тохируулсан үед `file_write` зөвшөөрөгдсөн.
- OpenJarvis `openjarvis_rust` өргөтгөл байхгүй үед *"Failed to set up rate limiter"* гэсэн анхааруулга гаргадаг. Ажиллагаанд нөлөөлөхгүй.

Бодит llama-server, Ollama дээр **шалгаагүй** (энэ орчинд GPU/модель байхгүй).
