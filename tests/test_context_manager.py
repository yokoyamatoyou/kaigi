from datetime import datetime

from core.context_manager import ContextManager


class FixedDateTime:
    @classmethod
    def now(cls):
        return datetime(2024, 1, 1, 12, 0, 0)


def test_save_list_load(tmp_path, monkeypatch):
    monkeypatch.setattr("core.context_manager.datetime", FixedDateTime)
    manager = ContextManager(context_dir=str(tmp_path))

    manager.save_carry_over("topic", "unresolved items")

    contexts = manager.list_carry_overs()
    assert len(contexts) == 1
    context = contexts[0]
    assert context["display_name"].startswith("[20240101_120000] topic")

    loaded = manager.load_carry_over(context["id"])
    assert loaded == "unresolved items"


def test_skip_and_remove_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr("core.context_manager.datetime", FixedDateTime)
    manager = ContextManager(context_dir=str(tmp_path))

    manager.save_carry_over("topic", "issue")

    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text("{invalid", encoding="utf-8")

    contexts = manager.list_carry_overs()
    assert len(contexts) == 1
    assert invalid_file.exists()

    contexts = manager.list_carry_overs(remove_invalid=True)
    assert len(contexts) == 1
    assert not invalid_file.exists()
