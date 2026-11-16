# Гадны skill импортлох

## Skill гэж юу вэ?

Skill гэдэг нь `SKILL.md` файлтай хавтас ([agentskills.io](https://agentskills.io) стандарт):

```markdown
---
name: pdf-merge                  # жижиг үсэг, тоо, нэг зураас; ≤ 64 тэмдэгт
description: Merge several PDF files into one document.   # хэзээ хэрэглэхийг тайлбарлана
---

# Заавар
Хэрхэн хийх тухай markdown заавар...
```

Энэ форматыг OpenJarvis, Hermes Agent (~150 skill), OpenClaw (~13,700 skill), [Anthropic-ийн skill-үүд](https://github.com/anthropics/skills) ашигладаг.

## Урсгал

```
fetch ──► data/skills/quarantine/<нэр>/   (итгэгдээгүй)
              │  scanner.py: файл бүрийг уншиж шалгана (юу ч ажиллуулахгүй)
              ▼
          report: clean / review / blocked
              │  хүн уншиж шийднэ
              ▼
approve ─► data/skills/installed/<нэр>/  +  skills.lock.json (эх сурвалж, commit, hash)
```

| Тушаал | Юу хийх |
|---|---|
| `python -m bot_v.skills fetch <https git URL эсвэл хавтас> [--subdir …] [--ref …]` | Татаж quarantine-д хийж шалгана. `https://github.com/<o>/<r>/tree/<branch>/<path>` холбоос шууд ажиллана |
| `python -m bot_v.skills report <нэр>` | Файл бүр, олдсон асуудал бүрийг харуулна |
| `python -m bot_v.skills approve <нэр> [--allow-high-risk]` | Суулгана. Шалгасны дараа файл өөрчлөгдсөн бол татгалзана |
| `python -m bot_v.skills reject <нэр>` | Quarantine-аас устгана |
| `python -m bot_v.skills remove <нэр>` | Суулгасан skill-ийг устгана |
| `python -m bot_v.skills list` | Суулгасан болон хүлээгдэж буй skill-үүд |
| `python -m bot_v.skills verify` | Суулгасан файлууд батлагдсан hash-тайгаа таарч байгааг шалгана |

Вэб UI-ийн **Skills → Import Skill** товч нь ижил урсгалыг ажиллуулна: татах → тайлан → баталгаажуулах цонх.

## Шалгалтын дүрэм

**High → blocked** (`--allow-high-risk`-гүйгээр суулгахгүй):
- `curl … | sh`, `iex(...)`: интернетээс татаж шууд ажиллуулах
- base64/hex-ээр нуусан кодыг `eval`/`exec`-ээр ажиллуулах
- `rm -rf /`, `rm -rf ~`
- reverse shell (`/dev/tcp/`, `nc -e`, `bash -i >&`)
- нууц файлд хандах: `~/.ssh`, `id_rsa`, `.aws/credentials`, `.netrc`, `/etc/shadow`…
- prompt injection: "ignore previous instructions", "reveal the system prompt", "do not tell the user"…
- текстийн чиглэл өөрчлөх Unicode тэмдэгт (Trojan Source)
- crypto miner

**Medium → review** (хүн уншиж шийднэ):
- script файл (`.py`, `.sh`, `.js`…), сүлжээний дуудлага, `subprocess`/`eval`
- `pip/npm/apt install`, `sudo`, `chmod 777`
- binary файл, symlink (хуулагдахгүй), 1 MB-аас том файл (хуулагдахгүй)
- харагдахгүй HTML comment, zero-width тэмдэгт
- нууц мэдээлэл илгээх тухай өгүүлбэр
- spec-ийн хязгаараас урт description

Шалгалт бол **шүүлтүүр**, аюулгүйн баталгаа биш. Түгээмэл аюултай хэв маягийг барьж, хүн шийдвэр гаргахын өмнө харах боломж олгоно. Аюулгүй байдлын тухай өгүүлдэг skill (жишээ нь ийм хэв маягийг жишээ болгон бичсэн баримт бичиг) ч бас "blocked" болж болно. Ийм үед тайланг уншаад шийднэ.

## Bot V skill-ийг хэрхэн ашигладаг вэ?

- Хүсэлтэд тохирох skill-ийг сонгоно. Хүсэлтэд skill-ийн нэр (`pdf-merge`) орсон эсвэл тайлбартай нь 2-оос олон үг давхцсан тохиолдолд сонгогдоно. Нэг хүсэлтэд дээд тал нь 2 skill.
- Сонгосон skill-ийн зааврыг локал моделийн system prompt-д нэмнэ. OpenJarvis руу даалгавар өгөхдөө зааврыг даалгаврын өмнө хавсаргана. OpenJarvis-ийн Python SDK skill-ийг өөрөө ачаалдаггүй (зөвхөн `jarvis` CLI ачаалдаг) тул Bot V ингэж дамжуулна.
- **Script-ийг хэзээ ч ажиллуулахгүй.** Skill бол Bot V-ийн хувьд зөвхөн заавар.
- Сонголт нь үгийн давхцалд тулгуурладаг. Тайлбар нь англиар бичигдсэн skill монгол хүсэлтэд автоматаар сонгогдохгүй байж болно. Тэр үед skill-ийн нэрийг хүсэлтдээ шууд бичнэ үү (жишээ нь "pdf-merge ашиглаад…").

## Анхаарах зүйл

- OpenJarvis-ийн `skill_manage` tool-оор OpenJarvis өөрөө skill суулгаж чадна. Энэ нь Bot V-ийн quarantine-ийг тойрч гардаг тул Bot V-ийн зөвшөөрлийн хаалга түүнийг **эрсдэлтэй** гэж ангилсан. Skill-ийг Bot V-ээр импортлоно уу.
- Skill бүр өөрийн лицензтэй. Тайлангийн файлын жагсаалтаас `LICENSE`-ийг шалгана уу.
