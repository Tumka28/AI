import shutil
import subprocess

import pytest

from bot_v import updater

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *args],
                   cwd=cwd, check=True, capture_output=True)


def commit_file(repo, name, content, message="change", push=True):
    (repo / name).write_text(content, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-m", message)
    if push:
        git(repo, "push", "origin", "HEAD:main")


@pytest.fixture(autouse=True)
def no_fetch_throttle(monkeypatch):
    monkeypatch.setattr(updater, "FETCH_EVERY_SECONDS", 0)


@pytest.fixture
def repos(tmp_path):
    """A 'GitHub' (bare repo), your computer's checkout, and another clone that pushes changes."""
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    seed = tmp_path / "seed"
    git(tmp_path, "init", "-b", "main", str(seed))
    git(seed, "remote", "add", "origin", str(origin))
    commit_file(seed, "app.py", "print(1)\n", "init")
    commit_file(seed, "requirements.txt", "flask\n", "reqs")
    mine = tmp_path / "mine"
    git(tmp_path, "clone", "-b", "main", str(origin), str(mine))
    return mine, seed


def test_up_to_date(repos):
    mine, _ = repos
    info = updater.status(mine)
    assert info["can_update"] is False and info["reason"] == "up to date" and info["behind"] == 0


def test_fast_forward_update(repos):
    mine, github = repos
    commit_file(github, "app.py", "print(2)\n", "new feature")
    info = updater.status(mine)
    assert info["can_update"] is True and info["behind"] == 1

    result = updater.apply(mine)
    assert result["updated"] is True and result["commits"] == 1
    assert result["files"] == ["app.py"] and result["requirements_changed"] is False
    assert (mine / "app.py").read_text() == "print(2)\n"
    assert updater.status(mine)["reason"] == "up to date"


def test_requirements_change_is_reported(repos):
    mine, github = repos
    commit_file(github, "requirements.txt", "flask\nnumpy\n", "new dependency")
    assert updater.apply(mine)["requirements_changed"] is True


def test_local_changes_are_never_overwritten(repos):
    mine, github = repos
    commit_file(github, "app.py", "print(2)\n")
    (mine / "app.py").write_text("my own edit\n")
    info = updater.status(mine)
    assert info["can_update"] is False and "local changes" in info["reason"]
    assert updater.apply(mine)["updated"] is False
    assert (mine / "app.py").read_text() == "my own edit\n"


def test_untracked_files_do_not_block(repos):
    mine, github = repos
    commit_file(github, "app.py", "print(2)\n")
    (mine / "notes.txt").write_text("scratch")
    assert updater.apply(mine)["updated"] is True


def test_other_branch_and_local_commits_block(repos):
    mine, github = repos
    commit_file(github, "app.py", "print(2)\n")

    git(mine, "checkout", "-b", "experiment")
    assert "on branch 'experiment'" in updater.status(mine)["reason"]
    git(mine, "checkout", "main")

    commit_file(mine, "mine.txt", "local work", push=False)
    info = updater.status(mine)
    assert info["can_update"] is False and info["ahead"] == 1 and "local commit" in info["reason"]


def test_not_a_checkout(tmp_path):
    assert "not a git checkout" in updater.status(tmp_path)["reason"]


def test_fetch_is_throttled(repos, monkeypatch):
    mine, _ = repos
    monkeypatch.setattr(updater, "FETCH_EVERY_SECONDS", 60)
    updater._last_fetch.pop(str(mine.resolve()), None)
    assert updater.fetch(mine) is True
    assert updater.fetch(mine) is False  # F5 again right away: no new fetch
    assert updater.fetch(mine, force=True) is True
