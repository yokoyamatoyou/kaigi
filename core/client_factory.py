from typing import Optional, Dict, Type, Any
import logging

from .models import ModelInfo, AIProvider, AppConfig # AppConfig をインポート
from .api_clients import BaseAIClient, OpenAIClient, ClaudeClient, GeminiClient
from .config_manager import get_config_manager

logger = logging.getLogger(__name__)


class ClientFactory:
    """AIクライアントファクトリークラス"""

    _client_classes: Dict[AIProvider, Type[BaseAIClient]] = {
        AIProvider.OPENAI: OpenAIClient,
        AIProvider.CLAUDE: ClaudeClient,
        AIProvider.GEMINI: GeminiClient,
    }

    @classmethod
    def create_client(
        cls,
        model_info: ModelInfo,
        api_key: Optional[str] = None,
        **kwargs: Any
    ) -> BaseAIClient:
        provider = model_info.provider
        if provider not in cls._client_classes:
            logger.error(f"サポートされていないプロバイダー試行: {provider}")
            raise ValueError(f"サポートされていないプロバイダー: {provider}")

        config_manager = get_config_manager() # ConfigManager を取得
        app_config: AppConfig = config_manager.config # AppConfig を取得

        if api_key is None:
            api_key = config_manager.get_api_key(provider)
            if not api_key:
                logger.error(f"{provider.value} APIキーが設定されていません (ConfigManagerから取得失敗)")
                raise RuntimeError(f"{provider.value} APIキーが設定されていません")

        client_class = cls._client_classes[provider]

        # プロバイダー固有のデフォルト引数を AppConfig から取得
        default_provider_kwargs = cls._get_default_kwargs_from_config(provider, app_config)
        
        # 渡されたkwargsでデフォルトを上書き
        final_kwargs = {**default_provider_kwargs, **kwargs}
        
        # 必須の引数を設定
        final_kwargs['api_key'] = api_key
        final_kwargs['model_info'] = model_info

        try:
            client = client_class(**final_kwargs)
            logger.info(f"AI クライアント作成完了: {provider.value} - {model_info.name} with args: {final_kwargs}")
            return client
        except TypeError as e:
            logger.error(
                f"AI クライアント作成時の TypeError ({provider.value} - {model_info.name}): {str(e)}. "
                f"渡された引数: {final_kwargs}", exc_info=True
            )
            raise RuntimeError(f"AI クライアント({model_info.name})作成失敗 (引数エラー): {str(e)}") from e
        except Exception as e:
            logger.error(f"AI クライアント作成失敗 ({provider.value} - {model_info.name}): {str(e)}", exc_info=True)
            raise RuntimeError(f"AI クライアント({model_info.name})作成失敗: {str(e)}") from e

    @classmethod
    def _get_default_kwargs_from_config(cls, provider: AIProvider, config: AppConfig) -> Dict[str, Any]:
        """
        AppConfig から各プロバイダーのクライアント初期化のためのデフォルトキーワード引数を返す。
        主にタイムアウトとリトライ回数を設定。レートリミットはBaseAIClientのデフォルトを使うか、
        AppConfigに設定があればそれを使う。
        """
        # 各クライアントの __init__ が受け取る引数名に合わせる
        # OpenAIClient の修正案では、default_timeout, max_retries, rate_limit_per_second を想定
        
        # BaseAIClient で rate_limit_per_second のデフォルトが決まる想定。
        # もし AppConfig でプロバイダ毎に設定したいなら、ここに追加。
        # "rate_limit_per_second": config.provider_specific_rate_limit.get(provider, 3.0) のような形

        # 各クライアントの __init__ が `default_timeout` と `max_retries` を
        # 受け取ることを期待。
        # (OpenAIClientの修正案では、__init__でsuperに渡す引数としてこれらを使用)
        provider_kwargs = {
            "default_timeout": config.api_timeout_seconds_default, # 全プロバイダ共通のデフォルトタイムアウト
            "max_retries": 3, # 全プロバイダ共通のリトライ回数 (これもAppConfigで設定可能にしても良い)
            # "rate_limit_per_second": 3.0 # もし設定するなら
        }
        
        # プロバイダ固有の調整があればここで行う (例: Claudeはタイムアウト長めなど)
        # if provider == AIProvider.CLAUDE:
        #     provider_kwargs["default_timeout"] = max(config.api_timeout_seconds_default, 60) # Claudeは最低60秒など

        return provider_kwargs

    # _get_default_kwargs メソッドは _get_default_kwargs_from_config に置き換えるか削除
    # @classmethod
    # def _get_default_kwargs(cls, provider: AIProvider) -> Dict[str, Any]:
    #     ... (旧実装) ...

    @classmethod
    def create_multiple_clients(
        cls,
        model_infos: list[ModelInfo],
        api_keys: Optional[Dict[AIProvider, str]] = None,
        common_kwargs: Optional[Dict[str, Any]] = None
    ) -> list[BaseAIClient]:
        clients = []
        api_keys_map = api_keys or {}
        kwargs_to_pass = common_kwargs or {}

        for model_info in model_infos:
            try:
                specific_api_key = api_keys_map.get(model_info.provider)
                client = cls.create_client(model_info, api_key=specific_api_key, **kwargs_to_pass)
                clients.append(client)
            except Exception as e:
                logger.warning(f"クライアント作成スキップ ({model_info.provider.value} - {model_info.name}): {str(e)}")
                continue
        logger.info(f"{len(clients)}/{len(model_infos)} のクライアントを作成しました")
        return clients

    @classmethod
    def get_supported_providers(cls) -> list[AIProvider]:
        return list(cls._client_classes.keys())

    @classmethod
    def is_provider_supported(cls, provider: AIProvider) -> bool:
        return provider in cls._client_classes

def create_ai_client(
    model_info: ModelInfo,
    api_key: Optional[str] = None,
    **kwargs: Any
) -> BaseAIClient:
    return ClientFactory.create_client(model_info, api_key, **kwargs)

def create_ai_clients_from_config() -> list[BaseAIClient]:
    config_manager = get_config_manager()
    app_config = config_manager.config # AppConfigを一度取得
    
    configured_providers_with_keys = config_manager.get_configured_providers()
    
    clients = []
    for provider in configured_providers_with_keys:
        default_model_name = config_manager.get_default_model_for_provider(provider)
        if default_model_name:
            model_info = ModelInfo(
                name=default_model_name,
                provider=provider,
                temperature=app_config.default_temperature,
                max_tokens=app_config.default_max_tokens,
            )
            try:
                # create_ai_client が AppConfig からデフォルト値を取得してクライアントに渡す想定
                client = create_ai_client(model_info) 
                clients.append(client)
                logger.info(f"設定からクライアント作成: {provider.value} - {default_model_name}")
            except Exception as e:
                logger.error(
                    f"{provider.value} のデフォルトモデル ({default_model_name}) 用クライアント作成失敗: {e}",
                    exc_info=True
                )
        else:
            logger.warning(f"{provider.value} のデフォルトモデルが設定されていません。クライアント作成をスキップ。")
    
    if not clients:
        logger.warning("設定から作成できるAIクライアントがありませんでした。APIキーとデフォルトモデル設定を確認してください。")
        
    return clients
