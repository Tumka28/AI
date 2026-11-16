# Bot V суралцах нь: багш → dataset → fine-tune

## 1. Өгөгдөл цуглуулах

Bot V-д багш тохируулна ([README](../README.md#багш-teacher-өөрөөсөө-хүчтэй-модельноос-суралцах)). Багш хариулах эсвэл засах бүрд `data/learning/examples.jsonl`-д нэг жишээ нэмэгдэнэ:

| `source` | Хэзээ | Юунд хэрэглэгдэх |
|---|---|---|
| `teacher_answer` | Локал модель алдаа гаргаж багш хариулсан, эсвэл "Teacher"-ийг шууд сонгосон | SFT |
| `teacher_correction` | `review` горимд багш локал хариултыг сул гэж үзэж засварласан | SFT + DPO (`rejected` = локал хариулт) |
| `local_verified` | `review` горимд багш локал хариултыг "good" (≥8/10) гэж үнэлсэн | SFT (локал загвар зөв хийж байгааг бэхжүүлнэ) |

Хэдэн жишээ цугласныг шалгах:

```bash
python -m bot_v.learning stats
```

**Анхаар:** жишээнүүд хэрэглэгчийн асуултыг агуулдаг. `data/` хавтас git-д орохгүй (`.gitignore`). Fine-tune хийхээсээ өмнө хувийн мэдээлэлтэй жишээнүүдийг шалгаж хасна уу.

## 2. Dataset гаргах

```bash
# SFT: {"messages": [system?, user, assistant]}: TRL, Unsloth, axolotl, LLaMA-Factory уншдаг формат
python -m bot_v.learning export --format sft --out data/learning/train_sft.jsonl \
       --system "You are Bot V, a personal AI assistant."

# Зөвхөн тодорхой эх сурвалжаас
python -m bot_v.learning export --format sft --source teacher_answer --source teacher_correction \
       --out data/learning/train_sft.jsonl

# DPO: {"prompt", "chosen", "rejected"}: багшийн засвар (chosen) локал хариултаас (rejected) дээр
python -m bot_v.learning export --format dpo --out data/learning/train_dpo.jsonl
```

Ижил асуулт-хариултын давхардлыг export хийхдээ хасна.

## 3. LoRA fine-tune (өөрийн GPU эсвэл түрээсийн GPU дээр)

> Энэ хэсгийг Bot V-ийн орчинд шалгаагүй (GPU байхгүй). Доорх нь түгээмэл замнал.

1. **Суурь загвар сонгох.** llama-server-т ажиллуулж байгаа GGUF-ийн **яг ижил** суурь загварын Hugging Face хувилбар хэрэгтэй (жишээ нь Qwen2.5-7B-Instruct). LoRA adapter нь зөвхөн өөрийн суурь загвар дээр ажилладаг.
2. **Сургах.** `train_sft.jsonl` нь [Unsloth](https://github.com/unslothai/unsloth), [LLaMA-Factory](https://github.com/hiyouga/LLaMA-Factory), [TRL](https://github.com/huggingface/trl)-ийн SFTTrainer шууд уншдаг `messages` форматтай. 7–8B загварыг 4-bit QLoRA-аар 16 GB орчим VRAM-д сургаж болдог. Түүнээс том загварт түрээсийн GPU (Colab, RunPod г.м.) хэрэгтэй.
3. **DPO (заавал биш).** `train_dpo.jsonl`-ийг TRL-ийн `DPOTrainer`-т SFT-ийн дараа өгнө.
4. **GGUF болгож ачаалах.** llama.cpp-ийн `convert_lora_to_gguf.py`-аар adapter-аа GGUF болгоод суурь загвартайгаа хамт ачаална:

   ```bash
   llama-server -m base-model.gguf --lora bot-v-lora.gguf --port 8080
   ```

5. **Шалгах.** Хуучин болон шинэ загварт ижил асуултууд өгч хариултыг харьцуулна. Bot V-ийн `review` горим энд бас тусална: багшийн оноо дээшилж байвал загвар сайжирсан гэсэн үг.

## Хэдэн жишээ хэрэгтэй вэ?

Хэдхэн арван жишээ загварт мэдэгдэхүйц нөлөө үзүүлэхгүй. Ихэвчлэн хэдэн зуугаас хэдэн мянган **чанартай**, давхардалгүй жишээ хэрэгтэй. Тоо хэмжээнээс илүү олон төрлийн, бодит хэрэглээний асуулт чухал.
