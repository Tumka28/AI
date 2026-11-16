# Нээлттэй AI сургалтын өгөгдөл татах

Claude, GPT-г сургасан өгөгдөл нийтэд нээлттэй биш. Энэ скрипт Hugging Face дээрх
ижил төрлийн **нээлттэй** өгөгдлүүдийг таны компьютер дээр JSONL болгон татна.

## Суулгах

```bash
git clone https://github.com/tumka28/ai.git
cd ai
pip install -r datasets/requirements.txt
```

## Ашиглах

```bash
python datasets/download_datasets.py --list              # жагсаалт
python datasets/download_datasets.py mn_wiki             # Монгол Википедиа (~90 MB)
python datasets/download_datasets.py --preset mongol     # Монгол бүх текст (~3 GB+)
python datasets/download_datasets.py --preset finetune   # чат/заавар өгөгдөл
python datasets/download_datasets.py fineweb_sample --max-rows 100000   # том өгөгдлөөс хэсэг
```

Файлууд `data/` хавтаст хадгалагдана (git-д орохгүй).

| Нэр | Хэмжээ | Тайлбар |
|---|---|---|
| mn_wiki | ~90 MB | Монгол Википедиа, 24 мянган нийтлэл |
| mn_fineweb2 | ~3+ GB | FineWeb-2 Монгол вэб текст |
| fineweb_sample | ~30 GB | Англи вэб текст (`--max-rows` ашигла) |
| en_wiki | ~20 GB | Англи Википедиа |
| dolly | ~13 MB | 15k асуулт-хариулт |
| alpaca | ~25 MB | 52k заавар-хариулт |
| oasst2 | ~100 MB | Олон хэлний чат (`--lang en` гэх мэт шүүж болно) |
| hh_rlhf | ~300 MB | Хүний сонголтын өгөгдөл |

Өгөгдөл бүр өөрийн лицензтэй тул арилжааны зорилгоор ашиглахаас өмнө Hugging Face
хуудсан дээрх лицензийг нь шалгаарай.
