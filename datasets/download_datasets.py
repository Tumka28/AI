"""
Нээлттэй өгөгдлийн сангуудыг өөрийн компьютер дээр татаж JSONL болгох скрипт.

Суулгах:
    pip install -r datasets/requirements.txt

Ашиглах:
    python datasets/download_datasets.py --list                 # бүх өгөгдлийг харах
    python datasets/download_datasets.py mn_wiki                # нэгийг татах
    python datasets/download_datasets.py mn_wiki dolly alpaca   # хэдийг зэрэг
    python datasets/download_datasets.py --preset mongol        # Монгол багц
    python datasets/download_datasets.py fineweb_sample --max-rows 100000

Үр дүн: data/<нэр>.jsonl  (мөр бүр нэг JSON: {"text": ...} эсвэл
{"instruction": ..., "response": ...})
"""

import argparse
import json
import os
import sys

# name -> (hf_repo, config, split, approx_size, kind, description)
DATASETS = {
    # --- Монгол хэлний текст (pretraining) ---
    "mn_wiki": ("wikimedia/wikipedia", "20231101.mn", "train", "~90 MB", "text",
                "Монгол Википедиа (~25 мянган нийтлэл)"),
    "mn_fineweb2": ("HuggingFaceFW/fineweb-2", "khk_Cyrl", "train", "~2.8 GB", "text",
                    "FineWeb-2 Монгол (кирилл) вэб текст, цэвэрлэсэн"),
    # --- Англи текст (pretraining), зөвхөн дээж ---
    "fineweb_sample": ("HuggingFaceFW/fineweb", "sample-10BT", "train", "~30 GB (бүтэн)", "text",
                       "FineWeb 10 тэрбум токены дээж — --max-rows ашиглана уу"),
    "en_wiki": ("wikimedia/wikipedia", "20231101.en", "train", "~20 GB", "text",
                "Англи Википедиа"),
    # --- Fine-tuning (заавар / чат) ---
    "dolly": ("databricks/databricks-dolly-15k", None, "train", "~13 MB", "instruct",
              "15 мянган асуулт-хариулт (хүн бичсэн)"),
    "alpaca": ("tatsu-lab/alpaca", None, "train", "~25 MB", "instruct",
               "52 мянган заавар-хариулт"),
    "oasst2": ("OpenAssistant/oasst2", None, "train", "~100 MB", "oasst",
               "OpenAssistant олон хэлний чат мессежүүд"),
    "hh_rlhf": ("Anthropic/hh-rlhf", None, "train", "~300 MB", "preference",
                "Хүний сонголтын өгөгдөл (chosen / rejected)"),
}

PRESETS = {
    "mongol": ["mn_wiki", "mn_fineweb2"],
    "small": ["mn_wiki", "dolly", "alpaca"],
    "finetune": ["dolly", "alpaca", "oasst2"],
}


def convert(kind, row):
    """Мөр бүрийг энгийн, нэгдсэн хэлбэрт оруулна."""
    if kind == "text":
        out = {"text": row["text"]}
        if row.get("title"):
            out["title"] = row["title"]
        return out
    if kind == "instruct":
        instruction = row.get("instruction", "")
        context = row.get("context") or row.get("input") or ""
        if context:
            instruction = f"{instruction}\n\n{context}"
        return {"instruction": instruction,
                "response": row.get("response") or row.get("output", "")}
    if kind == "oasst":
        return {"text": row["text"], "role": row["role"], "lang": row["lang"],
                "message_id": row["message_id"], "parent_id": row["parent_id"]}
    if kind == "preference":
        return {"chosen": row["chosen"], "rejected": row["rejected"]}
    return dict(row)


def download(name, out_dir, max_rows=None, lang=None):
    from datasets import load_dataset

    repo, config, split, size, kind, desc = DATASETS[name]
    path = os.path.join(out_dir, f"{name}.jsonl")
    print(f"\n==> {name}: {desc} ({size})")
    print(f"    {repo}" + (f" [{config}]" if config else "") + f" -> {path}")

    # streaming=True: бүх файлыг дискэнд хадгалахгүй, шууд уншиж бичнэ
    ds = load_dataset(repo, config, split=split, streaming=True)

    n = 0
    with open(path, "w", encoding="utf-8") as f:
        for row in ds:
            if lang and kind == "oasst" and row.get("lang") != lang:
                continue
            f.write(json.dumps(convert(kind, row), ensure_ascii=False) + "\n")
            n += 1
            if n % 10000 == 0:
                print(f"    {n:,} мөр...", flush=True)
            if max_rows and n >= max_rows:
                break

    mb = os.path.getsize(path) / 1e6
    print(f"    Дууслаа: {n:,} мөр, {mb:,.1f} MB")


def main():
    p = argparse.ArgumentParser(description="Нээлттэй AI сургалтын өгөгдөл татагч")
    p.add_argument("names", nargs="*", help="Өгөгдлийн нэр(үүд)")
    p.add_argument("--preset", choices=PRESETS, help="Бэлэн багц: " + ", ".join(
        f"{k}={'+'.join(v)}" for k, v in PRESETS.items()))
    p.add_argument("--max-rows", type=int, help="Нэг өгөгдлөөс авах дээд мөрийн тоо")
    p.add_argument("--out", default="data", help="Хадгалах хавтас (анхдагч: data)")
    p.add_argument("--lang", help="oasst2-г хэлээр шүүх, жишээ нь: en, ru")
    p.add_argument("--list", action="store_true", help="Боломжит өгөгдлүүдийг харуулах")
    args = p.parse_args()

    if args.list or (not args.names and not args.preset):
        print(f"{'Нэр':<16}{'Хэмжээ':<18}Тайлбар")
        for k, v in DATASETS.items():
            print(f"{k:<16}{v[3]:<18}{v[5]}")
        print("\nБагцууд:", ", ".join(f"{k} ({'+'.join(v)})" for k, v in PRESETS.items()))
        return

    names = list(args.names) + (PRESETS[args.preset] if args.preset else [])
    unknown = [n for n in names if n not in DATASETS]
    if unknown:
        sys.exit(f"Мэдэгдэхгүй нэр: {', '.join(unknown)}. --list ашиглаж харна уу.")

    os.makedirs(args.out, exist_ok=True)
    for name in dict.fromkeys(names):
        download(name, args.out, args.max_rows, args.lang)


if __name__ == "__main__":
    main()
