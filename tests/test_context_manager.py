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
