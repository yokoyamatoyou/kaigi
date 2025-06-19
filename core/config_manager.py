
import os
import json
from typing import Optional, Dict, Any
from pathlib import Path
from dotenv import load_dotenv
import logging

from .models import AppConfig, AIProvider # AppConfig は pydantic.BaseModel を継承している想定

logger = logging.getLogger(__name__)


class ConfigManager:
    """設定管理クラス"""
    
    def __init__(self, config_file_path: Optional[str] = None):
        """
        初期化
        
        Args:
            config_file_path: 設定ファイルのパス（Noneの場合はデフォルトを使用）
        """
        # .envファイルを読み込み
        load_dotenv()
        
        # 設定ファイルのパス
        self.config_file_path = Path(config_file_path) if config_file_path else Path("config.json")
        
        # 設定を初期化
        self._config = self._load_config()
        
        # ログレベルを設定
        self._setup_logging()
    
    def _load_config(self) -> AppConfig:
        """設定を読み込み"""
        # 環境変数から基本設定を作成
        config_data = {
            "openai_api_key": os.getenv("OPENAI_API_KEY"),
            "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
            "google_api_key": os.getenv("GOOGLE_API_KEY"),
            "default_temperature": float(os.getenv("DEFAULT_TEMPERATURE", "0.7")),
            "default_max_tokens": int(os.getenv("DEFAULT_MAX_TOKENS", "1000")),
            "default_rounds_per_ai": int(os.getenv("DEFAULT_ROUNDS_PER_AI", "3")),
            # 新しい設定項目: 最終要約生成時のタイムアウト（秒）
            "api_timeout_seconds_default": int(os.getenv("API_TIMEOUT_SECONDS_DEFAULT", "30")),
            "api_timeout_seconds_summary": int(os.getenv("API_TIMEOUT_SECONDS_SUMMARY", "90")), # デフォルト90秒
            "window_title": os.getenv("WINDOW_TITLE", "マルチAIディープリサーチツール"),
            "window_width": int(os.getenv("WINDOW_WIDTH", "1200")),
            "window_height": int(os.getenv("WINDOW_HEIGHT", "800")),
            "api_call_delay_seconds": float(os.getenv("API_CALL_DELAY_SECONDS", "1.0")),
            "conversation_history_limit": int(os.getenv("CONVERSATION_HISTORY_LIMIT", "10")),
            "log_level": os.getenv("LOG_LEVEL", "INFO").upper(),
        }
        
        # 設定ファイルが存在する場合は読み込みマージ
        if self.config_file_path.exists():
            try:
                with open(self.config_file_path, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                    # ファイルの設定で環境変数の設定を上書き（Noneでない場合のみ）
                    for key, value in file_config.items():
                        if value is not None:
                            # 型変換を考慮 (特に数値型)
                            if key in ["default_temperature", "api_call_delay_seconds"] and isinstance(value, (int, str)):
                                try: config_data[key] = float(value)
                                except ValueError: logger.warning(f"設定ファイルの値 {key}:{value} をfloatに変換できませんでした。")
                            elif key in ["default_max_tokens", "default_rounds_per_ai", 
                                         "api_timeout_seconds_default", "api_timeout_seconds_summary",
                                         "window_width", "window_height", "conversation_history_limit"] and isinstance(value, (float, str)):
                                try: config_data[key] = int(value)
                                except ValueError: logger.warning(f"設定ファイルの値 {key}:{value} をintに変換できませんでした。")
                            else:
                                config_data[key] = value
                logger.info(f"設定ファイルを読み込みました: {self.config_file_path}")
            except Exception as e:
                logger.warning(f"設定ファイルの読み込みに失敗しました: {e}")
        
        # AppConfigに渡す前に、必須だが.envやファイルにない可能性のあるキーのデフォルトを再度確認
        # (AppConfigのフィールド定義にデフォルト値があれば、そちらが優先される)
        # 例えば AppConfig に api_timeout_seconds_default = 30 のように定義されていれば、
        # ここでの config_data["api_timeout_seconds_default"] の値が優先される。

        # 既存の AppConfig のフィールドに合わせて不足分を補う
        # (これは AppConfig の定義によります。元の AppConfig に存在しないキーはエラーになるため注意)
        expected_keys = AppConfig.model_fields.keys() # Pydantic v2
        # expected_keys = AppConfig.__fields__.keys() # Pydantic v1
        
        final_config_data = {k: v for k, v in config_data.items() if k in expected_keys}
        
        # 不足している必須キーがあれば警告 (AppConfig側でデフォルト値がない場合)
        for key in expected_keys:
            if key not in final_config_data and AppConfig.model_fields[key].is_required():
            # if key not in final_config_data and AppConfig.__fields__[key].required: # Pydantic v1
                logger.warning(f"AppConfigの必須フィールド '{key}' が設定ソースに見つかりません。AppConfigのデフォルト値が使用されます（あれば）。")


        try:
            return AppConfig(**final_config_data)
        except Exception as e:
            logger.error(f"AppConfigのインスタンス化に失敗しました。データ: {final_config_data}, エラー: {e}", exc_info=True)
            # 最低限のデフォルト値でフォールバックするAppConfigを返すか、例外を再raiseする
            logger.warning("フォールバックとしてデフォルトのAppConfigを生成します。")
            return AppConfig() # AppConfigがデフォルト値を持つ前提


    def _setup_logging(self):
        """ログレベルを設定"""
        # _load_configでconfig.log_levelが設定されるので、それを使用
        numeric_level = getattr(logging, self._config.log_level, logging.INFO)
        # ルートロガーだけでなく、アプリケーション固有のロガーにも適用する場合はここで調整
        logging.basicConfig(
            level=numeric_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        logger.setLevel(numeric_level) # このモジュールのロガーにも適用
    
    def save_config(self) -> bool:
        """現在の設定をファイルに保存"""
        try:
            # APIキーは保存しない（セキュリティのため）
            save_data = self._config.model_dump() # Pydantic v2
            # save_data = self._config.dict() # Pydantic v1

            save_data.pop("openai_api_key", None)
            save_data.pop("anthropic_api_key", None)
            save_data.pop("google_api_key", None)
            
            with open(self.config_file_path, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=2, ensure_ascii=False)
            logger.info(f"設定をファイルに保存しました: {self.config_file_path}")
            return True
        except Exception as e:
            logger.error(f"設定の保存に失敗しました: {e}")
            return False
    
    @property
    def config(self) -> AppConfig:
        """現在の設定を取得"""
        return self._config
    
    def get_api_key(self, provider: AIProvider) -> Optional[str]:
        """指定されたプロバイダーのAPIキーを取得"""
        key_mapping = {
            AIProvider.OPENAI: self._config.openai_api_key,
            AIProvider.CLAUDE: self._config.anthropic_api_key,
            AIProvider.GEMINI: self._config.google_api_key,
        }
        return key_mapping.get(provider)
    
    def is_api_key_configured(self, provider: AIProvider) -> bool:
        """指定されたプロバイダーのAPIキーが設定されているかチェック"""
        key = self.get_api_key(provider)
        return key is not None and key.strip() != ""
    
    def get_configured_providers(self) -> list[AIProvider]:
        """設定されているプロバイダーのリストを取得"""
        return [provider for provider in AIProvider if self.is_api_key_configured(provider)]
    
    def validate_api_keys(self) -> Dict[AIProvider, bool]:
        """全てのAPIキーの設定状況を検証"""
        return {
            provider: self.is_api_key_configured(provider)
            for provider in AIProvider
        }
    
    def update_setting(self, key: str, value: Any) -> bool:
        """設定を更新"""
        try:
            if hasattr(self._config, key):
                # 型変換を試みる (Pydanticモデルが検証してくれるが、事前にある程度行う)
                field_type = type(getattr(self._config, key))
                try:
                    converted_value = field_type(value)
                    setattr(self._config, key, converted_value)
                    logger.info(f"設定を更新しました: {key} = {converted_value}")
                    return True
                except (ValueError, TypeError) as e:
                    logger.warning(f"設定 '{key}' の値を型 '{field_type.__name__}' に変換できませんでした: {value}, エラー: {e}")
                    # 元の値を保持するか、エラーとするか
                    setattr(self._config, key, value) # Pydanticのバリデーションに任せる
                    logger.info(f"設定を更新しました (Pydanticバリデーションに委任): {key} = {value}")
                    return True

            else:
                logger.warning(f"不正な設定キー: {key}")
                return False
        except Exception as e:
            logger.error(f"設定の更新に失敗しました: {e}")
            return False
    
    def get_model_names_for_provider(self, provider: AIProvider) -> list[str]:
        """プロバイダー別の利用可能モデル名リストを取得"""
        # 将来的にはAPIから動的に取得するなどの拡張も考えられる
        model_mapping = {
            AIProvider.OPENAI: [
                "gpt-4o",
                "gpt-4o-mini", # 追加例
                "gpt-4-turbo",
                "gpt-4-turbo-preview",
                "gpt-4-0125-preview",
                "gpt-4-1106-preview",
                "gpt-4",
                "gpt-3.5-turbo-0125",
                "gpt-3.5-turbo",
                "gpt-3.5-turbo-1106",
                "gpt-3.5-turbo-16k" # 古いかも
            ],
            AIProvider.CLAUDE: [
                "claude-3-opus-20240229",
                "claude-3-sonnet-20240229",
                "claude-3-haiku-20240307",
                "claude-3-5-sonnet-20240620", # 更新
                # "claude-3-5-sonnet-20241022" # typo or future?
            ],
            AIProvider.GEMINI: [
                "gemini-1.5-pro-latest", # "gemini-1.5-pro" or "gemini-1.5-pro-001"
                "gemini-1.5-flash-latest", # "gemini-1.5-flash" or "gemini-1.5-flash-001"
                "gemini-pro", # gemini-1.0-pro
                "gemini-pro-vision" # 廃止予定、gemini-1.5-flash/pro で代替
            ]
        }
        return model_mapping.get(provider, [])
    
    def get_default_model_for_provider(self, provider: AIProvider) -> Optional[str]:
        """プロバイダーのデフォルトモデルを取得"""
        default_mapping = {
            AIProvider.OPENAI: "gpt-4o-mini", # より高速なモデルをデフォルトに
            AIProvider.CLAUDE: "claude-3-haiku-20240307", # より高速なモデルをデフォルトに
            AIProvider.GEMINI: "gemini-1.5-flash-latest" # より高速なモデルをデフォルトに
        }
        return default_mapping.get(provider)


# グローバルなConfigManagerインスタンス（シングルトンパターン）
_config_manager_instance: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """ConfigManagerのシングルトンインスタンスを取得"""
    global _config_manager_instance
    if _config_manager_instance is None:
        _config_manager_instance = ConfigManager()
    return _config_manager_instance


def initialize_config_manager(config_file_path: Optional[str] = None) -> ConfigManager:
    """ConfigManagerを初期化（テスト時などで明示的に初期化したい場合）"""
    global _config_manager_instance
    _config_manager_instance = ConfigManager(config_file_path)
    return _config_manager_instance
