# Bot V

**Bot V** нь хувийн AI туслах. Bot V бол **тархи** нь: юу хийх, хэн хийх, ямар хэрэгслийг ашиглахыг өөрөө шийднэ. Ажлыг өөрийн локал модель, өөрийн agent-ууд эсвэл **OpenJarvis**-ээр гүйцэтгүүлнэ. Өөрөөсөө хүчтэй **багш** (teacher) модельноос суралцаж, гаднаас **skill** импортлоно.

```
                 ┌─────────────────────────────────────────┐
  Хэрэглэгч  →   │                 BOT V                   │
  (IDE / API)    │ brain.py: шийдвэр, чиглүүлэлт           │
                 │ permissions.py: tool-ийн зөвшөөрөл      │
                 │ skills/: батлагдсан skill-ийн заавар    │
                 │ experience_log + learning: туршлага     │
                 └───┬──────────────┬──────────────┬───────┘
                     │              │              │ зөвшөөрөгдсөн даалгавар
                     ▼              ▼              ▼
             ┌──────────────┐ ┌────────────┐ ┌──────────────────────┐
             │ Локал LLM    │ │ Teacher    │ │ OpenJarvis adapter   │
             │ Ollama /     │ │ Claude эсвэл│ │ → 22 agent, 43 tool, │
             │ llama-server │ │ том модель │ │   memory, ...        │
             └──────────────┘ └─────┬──────┘ └──────────────────────┘
                                    ▼
                         data/learning/examples.jsonl
                         → fine-tune (SFT / DPO) өгөгдөл
```

OpenJarvis нь Bot V-ийн кодонд **хуулагдаагүй**. Тусдаа сан хэвээр үлдэж, Bot V түүнийг adapter-аар дамжуулан удирдана. Яагаад ингэснийг [docs/openjarvis.md](docs/openjarvis.md)-ээс уншина уу.

## Бүтэц

| Хавтас | Юу байгаа |
|---|---|
| `bot_v/core/` | **brain.py** (Bot V-ийн тархи), **permissions.py** (зөвшөөрлийн хаалга), ReAct, Tree-of-Thought, task |
| `bot_v/teacher/` | **Teacher**: Claude (`claude.py`) эсвэл өөрийн том модель (`llm_teacher.py`) |
| `bot_v/learning/` | Багшаас сурсан жишээнүүд, SFT/DPO dataset export |
| `bot_v/skills/` | **library.py**: гадны skill импорт (quarantine → шалгалт → зөвшөөрөл), **scanner.py**: хор илрүүлэгч. Мөн кодноос skill гаргах (`expansion/`) |
| `bot_v/integrations/` | **openjarvis_adapter.py**: OpenJarvis-ийг удирдах adapter |
| `bot_v/llm/` | LLM client (Ollama + OpenAI-тэй нийцтэй серверүүд), JSON задлагч |
| `bot_v/agents/` | Planner, Coder, Reviewer, Debug, Vision, Memory agent-ууд, chatroom, `multi_agent/` |
| `bot_v/autogpt/` | AutoGPT давталт: төлөвлөх → гүйцэтгэх → сайжруулах |
| `bot_v/debugger/` | Sandbox-д код ажиллуулж, алдааг өөрөө засах |
| `bot_v/memory/` | Урт хугацааны санах ой (vector store), **experience_log** |
| `bot_v/search/`, `project/`, `feature_impact/`, `self_optimize/` | Кодын хайлт, төсөл үүсгэх, нөлөөллийн шинжилгээ, өөрийгөө сайжруулах |
| `bot_v/server.py` | Flask сервер (IDE + JSON API) |
| `ui/` | Вэб IDE (Monaco editor, chat, terminal) |
| `config/openjarvis.toml` | Bot V-ийн OpenJarvis-д өгөх тохиргоо |
| `docs/` | [OpenJarvis судалгаа](docs/openjarvis.md), [Суралцах ба fine-tune](docs/learning.md), [Skill импорт](docs/skills.md) |
| `tests/` | Тестүүд (`pytest`) |
| `legacy/`, `docs/notes/` | Хуучин ноорог файлууд (лавлагаа болгон хадгалсан) |

## Эхлүүлэх

### 1. Суулгах

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt                 # Bot V
pip install -r requirements-openjarvis.txt      # + OpenJarvis (заавал биш)
pip install -r requirements-teacher.txt         # + Claude багш (заавал биш)
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
- **Bot V (auto)**: эхлээд локал модель хариулна. Тэр ажиллахгүй бол багш, дараа нь OpenJarvis руу шилжинэ.
- **Local model**: зөвхөн локал модель.
- **OpenJarvis**: шууд OpenJarvis.
- **Teacher**: шууд багш (хариултыг нь сургалтын өгөгдөлд хадгална).

## Багш (Teacher): өөрөөсөө хүчтэй модельноос суралцах

```bash
pip install -r requirements-teacher.txt
export BOTV_TEACHER=claude
export ANTHROPIC_API_KEY=...            # эсвэл: ant auth login
python -m bot_v.server
```

| `BOTV_TEACHER_MODE` | Юу хийх |
|---|---|
| `fallback` (анхдагч) | Локал модель алдаа гаргавал багшаас асууна |
| `review` | Локал хариулт бүрийг багш үнэлнэ (1–10). Сул хариултыг багшийн зассан хариултаар сольж, **зөв/буруу хос** (DPO) хадгална |
| `manual` | Зөвхөн "Teacher" сонгосон үед асууна |

- Claude багш анхдагчаар **`claude-opus-5-5`** загварыг `effort: high` тохиргоотой ашиглана. **Server-side fallback** (`fallbacks: "default"`) асаалттай: Claude-ийн аюулгүй байдлын шүүлтүүр хүсэлтийг андуурч татгалзвал API өөр тохирох загвар дээр дахин ажиллуулна. Хүсэхгүй бол хэлээрэй, унтраах боломжтой.
- **Нууцлал:** `BOTV_TEACHER=claude` үед багш руу явуулсан асуулт Anthropic-ийн сервер рүү очно. Үүнийг хүсэхгүй бол өөрийн том моделиор солино: `BOTV_TEACHER=ollama` (эсвэл `openai`), `BOTV_TEACHER_MODEL=qwen2.5:72b`, `BOTV_TEACHER_HOST=http://<том машин>:11434`.
- Сурсан жишээнүүд `data/learning/examples.jsonl`-д хадгалагдана. Fine-tune хийх dataset болгох:

```bash
python -m bot_v.learning stats
python -m bot_v.learning export --format sft --out data/learning/train_sft.jsonl
python -m bot_v.learning export --format dpo --out data/learning/train_dpo.jsonl
```

LoRA fine-tune хийж llama-server-т ачаалах зааврыг [docs/learning.md](docs/learning.md)-ээс үзнэ үү.

## Гадны skill импортлох

Skill гэдэг нь `SKILL.md` файлтай хавтас. agentskills.io стандартыг OpenJarvis, Hermes, OpenClaw, Anthropic-ийн skill-үүд ашигладаг. Bot V нь skill-ийг шууд суулгахгүй:

```bash
python -m bot_v.skills fetch https://github.com/anthropics/skills/tree/main/skills/pdf   # → quarantine + шалгалт
python -m bot_v.skills report pdf          # олдсон зүйлсийг уншина
python -m bot_v.skills approve pdf         # хүн зөвшөөрнө → суулгана
python -m bot_v.skills list | verify | reject <нэр> | remove <нэр>
```

- **Шалгалт:** `curl … | sh`, reverse shell, `~/.ssh` гэх мэт нууц файлд хандах, "өмнөх зааврыг үл тоо" гэх мэт prompt injection, нуугдмал Unicode, miner олдвол **blocked** болно (`--allow-high-risk`-ээр л суулгана). Script, сүлжээний дуудлага, package суулгалт, binary файл олдвол **review** (хүн уншиж шийднэ).
- **Хамгаалалт:** symlink болон 1 MB-аас том файл хуулагдахгүй. Executable эрх хасагдана. Суулгасан skill-ийн хэш `skills.lock.json`-д бичигдэх ба өөрчлөгдвөл тэр skill ашиглагдахгүй.
- **Хэрэглээ:** суулгасан skill бол **зөвхөн заавар**. Хүсэлтэд тохирох skill-ийн зааврыг Bot V локал моделийн system prompt болон OpenJarvis-д өгөх даалгаварт нэмнэ. Skill дотор ирсэн script-ийг Bot V **хэзээ ч ажиллуулахгүй**.

Дэлгэрэнгүй: [docs/skills.md](docs/skills.md).

## OpenJarvis-ийг удирдах

**Python-оос:**

```python
from bot_v.core.brain import BotV

bot = BotV()
bot.handle("Сайн уу!")                                   # Bot V өөрөө шийднэ
bot.handle("Сайн уу!", backend="teacher")                # шууд багшаас
bot.delegate("2+3 хэд вэ?", tools=["calculator"])        # OpenJarvis orchestrator agent
bot.delegate("Энэ сэдвийг судал", agent="deep_research", tools=["web_search"])
bot.delegate("ls ажиллуул", tools=["shell_exec"])         # → status "denied": Bot V хаасан
```

**HTTP API-аас:**

```bash
curl -X POST localhost:5000/openjarvis/ask -H 'Content-Type: application/json' \
     -d '{"task": "2+3?", "tools": ["calculator"]}'
curl localhost:5000/openjarvis/tools     # tool бүр зөвшөөрөл шаардах эсэх
curl localhost:5000/status               # LLM, OpenJarvis, багш, skill, сургалтын өгөгдөл
curl localhost:5000/experience           # Bot V-ийн туршлагын бүртгэл
curl localhost:5000/learning/stats
curl localhost:5000/skills
```

### Зөвшөөрлийн дүрэм

Bot V нь OpenJarvis-д ямар tool ашиглуулахыг **даалгавар OpenJarvis-д хүрэхээс өмнө** шалгана (`bot_v/core/permissions.py`):

- **Шууд зөвшөөрөгдөнө** (зөвхөн уншдаг): `calculator`, `think`, `web_search`, `file_read`, `memory_search`, `git_status` гэх мэт.
- **Зөвшөөрөл шаардана**: файл бичих, код/shell ажиллуулах, мессеж илгээх, git commit, HTTP хүсэлт, skill суулгах (`skill_manage`), мөн **жагсаалтад байхгүй бүх tool**.

Зөвшөөрөл өгөх механизм (approver) тохируулаагүй бол эрсдэлтэй tool-ууд **хориглогдоно**:

```python
from bot_v.core.permissions import PermissionGate
bot = BotV(gate=PermissionGate(approver=lambda task, tools: input(f"{tools} зөвшөөрөх үү? [y/N] ") == "y"))
```

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
| `BOTV_TEACHER` | (унтраалттай) | `claude`, `openai` эсвэл `ollama` |
| `BOTV_TEACHER_MODEL` | `claude-opus-5-5` (claude) | Багшийн загвар |
| `BOTV_TEACHER_HOST` | `:11434` / `:8080` | `openai`/`ollama` багшийн сервер |
| `BOTV_TEACHER_EFFORT` | `high` | Claude: `low` … `max` |
| `BOTV_TEACHER_MODE` | `fallback` | `fallback`, `review`, `manual` |
| `BOTV_DATA_DIR` | `./data` | Bot V-ийн өгөгдөл (санах ой, туршлага, skill, сургалтын өгөгдөл) |
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
| 2 | Локал LLM (Ollama / llama-server) | ✅ |
| 3 | OpenJarvis-ийг adapter-аар удирдах + зөвшөөрлийн хаалга | ✅ |
| 4 | Гадны skill-ийг аюулгүй импортлох (quarantine, шалгалт, зөвшөөрөл, hash lock) | ✅ эхний хувилбар. MCP tool нэмэх нь дараагийн алхам |
| 5 | **Teacher**: багшаас суралцах, SFT/DPO dataset | ✅ эхний хувилбар. LoRA сургалтыг өөрийн GPU дээр хийнэ ([docs/learning.md](docs/learning.md)) |
| 6 | Home Assistant, дараа нь компьютер/утас удирдах | алсын зорилго |

## Лиценз

OpenJarvis нь [Apache-2.0](https://github.com/open-jarvis/OpenJarvis/blob/main/LICENSE) лицензтэй бөгөөд энэ repo-д хуулагдаагүй, pip-ээр суудаг. Гаднаас импортолсон skill бүр өөрийн лицензтэй байдаг. Суулгахаасаа өмнө `report` гаргаж шалгана уу.
