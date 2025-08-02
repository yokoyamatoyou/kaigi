import os
import json
from datetime import datetime
from typing import List, Dict, Optional


class ContextManager:
    """会議の持ち越し事項（コンテキスト）を管理するクラス。"""

    def __init__(self, context_dir: str = "saved_contexts"):
        self.context_dir = context_dir
        if not os.path.exists(self.context_dir):
            os.makedirs(self.context_dir)
        # Remove any corrupted context files at startup
        self.cleanup_invalid_contexts()

    def cleanup_invalid_contexts(self, remove: bool = True) -> List[str]:
        """Validate stored contexts and optionally remove corrupted files.

        Args:
            remove (bool): Whether to delete corrupted JSON files.

        Returns:
            List[str]: Filenames identified as invalid.
        """
        invalid_files: List[str] = []
        for filename in os.listdir(self.context_dir):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(self.context_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    json.load(f)
            except (json.JSONDecodeError, OSError):
                invalid_files.append(filename)
                if remove:
                    try:
                        os.remove(filepath)
                    except OSError:
                        pass
        return invalid_files

    def save_carry_over(self, topic: str, unresolved_issues: str) -> None:
        """未解決の課題をJSONファイルとして保存する。"""
        if not unresolved_issues.strip():
            print("持ち越し事項がないため、保存をスキップしました。")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"context_{timestamp}.json"
        filepath = os.path.join(self.context_dir, filename)
        data = {
            "topic": topic,
            "unresolved_issues": unresolved_issues,
            "created_at": timestamp,
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"持ち越し事項を {filepath} に保存しました。")

    def list_carry_overs(self, remove_invalid: bool = False) -> List[Dict[str, str]]:
        """保存されている持ち越し事項のリストを取得する。"""
        contexts: List[Dict[str, str]] = []
        for filename in sorted(os.listdir(self.context_dir), reverse=True):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(self.context_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                contexts.append(
                    {
                        "id": filename,
                        "display_name": f"[{data['created_at']}] {data['topic']}",
                    }
                )
            except (json.JSONDecodeError, OSError):
                if remove_invalid:
                    try:
                        os.remove(filepath)
                    except OSError:
                        pass
                continue
        return contexts

    def load_carry_over(self, context_id: str) -> Optional[str]:
        """指定されたIDの持ち越し事項を読み込む。"""
        filepath = os.path.join(self.context_dir, context_id)
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("unresolved_issues")


_default_manager = ContextManager()


def save_carry_over(topic: str, unresolved_issues: str) -> None:
    """持ち越し事項を保存するモジュールレベルのラッパー。"""
    _default_manager.save_carry_over(topic, unresolved_issues)


def list_carry_overs(remove_invalid: bool = False) -> List[Dict[str, str]]:
    """保存されている持ち越し事項の一覧を返す。"""
    return _default_manager.list_carry_overs(remove_invalid=remove_invalid)


def load_carry_over(context_id: str) -> Optional[str]:
    """指定IDの持ち越し事項を読み込む。"""
    return _default_manager.load_carry_over(context_id)

