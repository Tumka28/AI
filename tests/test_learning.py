import json

import pytest

from bot_v.learning.__main__ import main as learning_cli
from bot_v.learning.dataset import TrainingStore


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def store(tmp_path):
    s = TrainingStore(tmp_path / "examples.jsonl")
    s.add("Нийслэл?", "Улаанбаатар", source="teacher_answer", teacher="claude", model="m")
    s.add("Нийслэл?", "Улаанбаатар", source="teacher_answer")  # duplicate
    s.add("2+2?", "4", source="teacher_correction", rejected="5", score=2)
    s.add("Hi", "Hello!", source="local_verified", score=9)
    return s


def test_stats(store):
    stats = store.stats()
    assert stats["total"] == 4
    assert stats["by_source"] == {"teacher_answer": 2, "teacher_correction": 1, "local_verified": 1}
    assert stats["preference_pairs"] == 1


def test_export_sft_dedupes_and_adds_system(store, tmp_path):
    out = tmp_path / "sft.jsonl"
    assert store.export_sft(out, system="You are Bot V.") == 3
    rows = read_jsonl(out)
    assert rows[0]["messages"] == [
        {"role": "system", "content": "You are Bot V."},
        {"role": "user", "content": "Нийслэл?"},
        {"role": "assistant", "content": "Улаанбаатар"},
    ]


def test_export_sft_filters_sources(store, tmp_path):
    out = tmp_path / "sft.jsonl"
    assert store.export_sft(out, sources=["local_verified"]) == 1
    assert read_jsonl(out)[0]["messages"][-1]["content"] == "Hello!"


def test_export_dpo(store, tmp_path):
    out = tmp_path / "dpo.jsonl"
    assert store.export_dpo(out) == 1
    assert read_jsonl(out) == [{"prompt": "2+2?", "chosen": "4", "rejected": "5"}]


def test_add_validates(tmp_path):
    s = TrainingStore(tmp_path / "e.jsonl")
    with pytest.raises(ValueError):
        s.add("q", "a", source="internet")
    with pytest.raises(ValueError):
        s.add("q", "  ", source="teacher_answer")


def test_corrupt_lines_are_skipped(tmp_path):
    path = tmp_path / "e.jsonl"
    s = TrainingStore(path)
    s.add("q", "a", source="teacher_answer")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("{broken\n")
    assert s.stats()["total"] == 1


def test_cli_export(tmp_path, capsys):
    TrainingStore().add("q", "a", source="teacher_answer")  # default store in the test data dir
    out = tmp_path / "train.jsonl"
    assert learning_cli(["export", "--format", "sft", "--out", str(out)]) == 0
    assert "sft examples" in capsys.readouterr().out
    assert read_jsonl(out)
