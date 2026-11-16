# Bot V

**Bot V** нь хувийн AI туслах. Bot V бол **тархи** нь: юу хийх, хэн хийх, ямар хэрэгслийг ашиглахыг өөрөө шийднэ. Ажлыг өөрийн локал модель, өөрийн agent-ууд эсвэл **OpenJarvis**-ээр гүйцэтгүүлнэ.

```
              ┌───────────────────────────────────┐
 Хэрэглэгч →  │              BOT V                │
 (IDE / API)  │  brain.py: шийдвэр, чиглүүлэлт    │
              │  permissions.py: зөвшөөрөл        │
              │  experience_log: туршлагын бүртгэл│
              └───────┬───────────────┬───────────┘
                      │               │ зөвшөөрөгдсөн даалгавар
                      ▼               ▼
            ┌────────────────┐  ┌──────────────────────────┐
            │ Локал LLM      │  │ OpenJarvisAdapter        │
            │ (Ollama /      │  │  → OpenJarvis: 22 agent, │
            │  llama-server) │  │    43 tool, memory, ...  │
            │ + Bot V-ийн    │  └──────────────────────────┘
            │   agent-ууд    │
            └────────────────┘
```

OpenJarvis нь Bot V-ийн кодонд **хуулагдаагүй**. Тусдаа сан хэвээр үлдэж, Bot V түүнийг adapter-аар дамжуулан удирдана. Яагаад ингэснийг [docs/openjarvis.md](docs/openjarvis.md)-ээс уншина уу.

## Бүтэц

| Хавтас | Юу байгаа |
|---|---|
| `bot_v/core/` | **brain.py** (Bot V-ийн тархи), **permissions.py** (зөвшөөрлийн хаалга), ReAct, Tree-of-Thought, task |
| `bot_v/integrations/` | **openjarvis_adapter.py**: OpenJarvis-ийг удирдах adapter |
| `bot_v/llm/` | LLM client (Ollama + OpenAI-тэй нийцтэй серверүүд), JSON задлагч |
| `bot_v/agents/` | Planner, Coder, Reviewer, Debug, Vision, Memory agent-ууд, chatroom, `multi_agent/` (мэтгэлцээн, зөвшилцөл) |
| `bot_v/autogpt/` | AutoGPT давталт: төлөвлөх → гүйцэтгэх → сайжруулах |
| `bot_v/debugger/` | Sandbox-д код ажиллуулж, алдааг өөрөө засах |
| `bot_v/memory/` | Урт хугацааны санах ой (vector store), **experience_log** |
| `bot_v/skills/` | Кодноос skill гаргаж авах, tool үүсгэх (`expansion/`) |
| `bot_v/search/` | Кодын семантик хайлт |
| `bot_v/project/` | Шинэ төсөл үүсгэх, refactor хийх |
| `bot_v/feature_impact/` | Өөрчлөлтийн нөлөөллийн шинжилгээ |
| `bot_v/self_optimize/` | Өөрийн гаралтыг үнэлж сайжруулах |
| `bot_v/server.py` | Flask сервер (IDE + JSON API) |
| `ui/` | Вэб IDE (Monaco editor, chat, terminal) |
| `config/openjarvis.toml` | Bot V-ийн OpenJarvis-д өгөх тохиргоо |
| `tests/` | Тестүүд (`pytest`) |
| `legacy/`, `docs/notes/` | Хуучин ноорог файлууд (лавлагаа болгон хадгалсан) |

## Эхлүүлэх

### 1. Суулгах

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt                 # Bot V
pip install -r requirements-openjarvis.txt      # + OpenJarvis (заавал биш)
```

OpenJarvis-д Python 3.10–3.13 хэрэгтэй.

### 2. Локал модель асаах

**llama-server (llama.cpp)**: 16 GB машинд Qwen GGUF зэрэг загвар:

```bash
llama-server -m /path/to/model.gguf --port 8080
export BOTV_LLM_BACKEND=openai
export BOTV_LLM_HOST=http://localhost:8080
export BOTV_MODEL_GENERAL=<серверийн model нэр>
```

**эсвэл Ollama:**

```bash
ollama serve
export BOTV_LLM_BACKEND=ollama          # анхдагч
export BOTV_MODEL_GENERAL=qwen2.5:14b   # жишээ
```

`config/openjarvis.toml` нь анхдагчаар llama-server (`localhost:8080`)-ийг заадаг. Ollama ашиглавал тэнд `default = "ollama"` болгоно.

### 3. Bot V асаах

```bash
python -m bot_v.server
```

Хөтөч дээр **http://127.0.0.1:5000** нээнэ. Chat-ийн хажууд хэн хариулахыг сонгоно:
- **Bot V (auto)**: эхлээд локал модель хариулна. Тэр ажиллахгүй бол OpenJarvis руу шилжинэ.
- **Local model**: зөвхөн локал модель.
- **OpenJarvis**: шууд OpenJarvis.

Баруун талын **OpenJarvis** хэсгээс agent, tool сонгож даалгавар өгч болно.

## OpenJarvis-ийг удирдах

**Python-оос:**

```python
from bot_v.core.brain import BotV

bot = BotV()
bot.handle("Сайн уу!")                                   # Bot V өөрөө шийднэ
bot.delegate("2+3 хэд вэ?", tools=["calculator"])        # OpenJarvis orchestrator agent
bot.delegate("Энэ сэдвийг судал", agent="deep_research", tools=["web_search"])
bot.delegate("ls ажиллуул", tools=["shell_exec"])         # → status "denied": Bot V хаасан
```

**HTTP API-аас:**

```bash
curl -X POST localhost:5000/openjarvis/ask -H 'Content-Type: application/json' \
     -d '{"task": "2+3?", "tools": ["calculator"]}'
curl localhost:5000/openjarvis/tools     # tool бүр зөвшөөрөл шаардах эсэх
curl localhost:5000/openjarvis/agents
curl localhost:5000/status
curl localhost:5000/experience           # Bot V-ийн туршлагын бүртгэл
```

### Зөвшөөрлийн дүрэм

Bot V нь OpenJarvis-д ямар tool ашиглуулахыг **даалгавар OpenJarvis-д хүрэхээс өмнө** шалгана (`bot_v/core/permissions.py`):

- **Шууд зөвшөөрөгдөнө** (зөвхөн уншдаг): `calculator`, `think`, `web_search`, `file_read`, `memory_search`, `git_status` гэх мэт.
- **Зөвшөөрөл шаардана**: файл бичих, код/shell ажиллуулах, мессеж илгээх, git commit, HTTP хүсэлт, skill суулгах, мөн **жагсаалтад байхгүй бүх tool**.

Зөвшөөрөл өгөх механизм (approver) тохируулаагүй бол эрсдэлтэй tool-ууд **хориглогдоно**. Approver нэмэх:

```python
from bot_v.core.permissions import PermissionGate
bot = BotV(gate=PermissionGate(approver=lambda task, tools: input(f"{tools} зөвшөөрөх үү? [y/N] ") == "y"))
```

Bot V хийсэн бүх зүйлээ `data/experience.jsonl`-д бичнэ: юу асуусан, хэн хариулсан, аль tool зөвшөөрөгдсөн/хориглогдсон, үр дүн. Энэ бол дараа нь **багшаас суралцах, fine-tune хийх** өгөгдлийн эх үүсвэр.

## Тохиргоо (орчны хувьсагч)

| Хувьсагч | Анхдагч | Тайлбар |
|---|---|---|
| `BOTV_LLM_BACKEND` | `ollama` | `ollama` эсвэл `openai` (llama-server, LM Studio, vLLM…) |
| `BOTV_LLM_HOST` | `:11434` / `:8080` | LLM серверийн хаяг |
| `BOTV_LLM_API_KEY` | – | Шаардлагатай бол bearer token |
| `BOTV_MODEL_GENERAL` | `deepseek-v2:16b` | Ерөнхий бодолт, chat |
| `BOTV_MODEL_CODER` | `deepseek-coder-v2:16b` | Код бичих, засах |
| `BOTV_MODEL_VISION` | `llava:7b` | Зураг |
| `BOTV_MODEL_EMBED` | = GENERAL | Embedding (санах ой, хайлт) |
| `BOTV_DATA_DIR` | `./data` | Bot V-ийн өгөгдөл |
| `BOTV_OPENJARVIS_CONFIG` | `config/openjarvis.toml` | OpenJarvis-ийн тохиргоо |
| `BOTV_SERVER_HOST` / `PORT` | `127.0.0.1` / `5000` | Вэб сервер |

Код дотор модулиуд загварыг **үүргээр** нь дууддаг (`"general"`, `"coder"`, `"vision"`, `"embed"`). Тиймээс загвар солихын тулд кодыг өөрчлөх шаардлагагүй, зөвхөн хувьсагч солино.

## Тест

```bash
pip install -r requirements-dev.txt
pytest
```

## Замын зураг

| Үе | Агуулга | Төлөв |
|---|---|---|
| 1 | Repo-г `bot_v/` бүтэц рүү цэгцлэх, ажилладаг сервер | ✅ |
| 2 | Локал LLM (Ollama / llama-server) | ✅ client бэлэн |
| 3 | OpenJarvis-ийг adapter-аар удирдах + зөвшөөрлийн хаалга | ✅ эхний хувилбар |
| 4 | Tool/skill registry-г нэгтгэх, MCP, гадны skill (agentskills.io) аюулгүй импортлох | дараа |
| 5 | **Teacher**: локал модель чадахгүй үед том моделиос асууж, experience log-оос dataset бэлдэж LoRA fine-tune хийх | дараа |
| 6 | Home Assistant, дараа нь компьютер/утас удирдах | алсын зорилго |

## Лиценз

OpenJarvis нь [Apache-2.0](https://github.com/open-jarvis/OpenJarvis/blob/main/LICENSE) лицензтэй бөгөөд энэ repo-д хуулагдаагүй, pip-ээр суудаг.
