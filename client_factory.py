
from typing import Optional, Dict, Type
import logging

from .models import ModelInfo, AIProvider
from .api_clients import BaseAIClient, OpenAIClient, ClaudeClient, GeminiClient
from .config_manager import get_config_manager

logger = logging.getLogger(__name__)


class ClientFactory:
    """AIクライアントファクトリークラス"""
    
    # プロバイダーごとのクライアントクラスマッピング
    _client_classes: Dict[AIProvider, Type[BaseAIClient]] = {
        AIProvider.OPENAI: OpenAIClient,
        AIProvider.CLAUDE: ClaudeClient,
        AIProvider.GEMINI: GeminiClient,
    }
    
    @classmethod
    def create_client(
        self,
        model_info: ModelInfo,
        api_key: Optional[str] = None,
        **kwargs
    ) -> BaseAIClient:
        """
        モデル情報からAIクライアントを作成
        
        Args:
            model_info: モデル情報
            api_key: APIキー（Noneの場合は設定から取得）
            **kwargs: クライアント固有の追加パラメータ
        
        Returns:
            作成されたAIクライアント
        
        Raises:
            ValueError: サポートされていないプロバイダーの場合
            RuntimeError: APIキーが設定されていない場合
        """
        provider = model_info.provider
        
        # サポートされているプロバイダーかチェック
        if provider not in self._client_classes:
            raise ValueError(f"サポートされていないプロバイダー: {provider}")
        
        # APIキーを取得（指定されていない場合は設定から取得）
        if api_key is None:
            config_manager = get_config_manager()
            api_key = config_manager.get_api_key(provider)
            
            if not api_key:
                raise RuntimeError(f"{provider.value} APIキーが設定されていません")
        
        # クライアントクラスを取得
        client_class = self._client_classes[provider]
        
        # プロバイダー固有のデフォルト設定を適用
        default_kwargs = self._get_default_kwargs(provider)
        default_kwargs.update(kwargs)
        
        try:
            # クライアントインスタンスを作成
            client = client_class(
                api_key=api_key,
                model_info=model_info,
                **default_kwargs
            )
            
            logger.info(f"AI クライアント作成完了: {provider.value} - {model_info.name}")
            return client
            
        except Exception as e:
            logger.error(f"AI クライアント作成失敗: {provider.value} - {str(e)}")
            raise RuntimeError(f"AI クライアント作成失敗: {str(e)}")
    
    @classmethod
    def _get_default_kwargs(cls, provider: AIProvider) -> Dict:
        """プロバイダー固有のデフォルト設定を取得"""
        defaults = {
            AIProvider.OPENAI: {
                "rate_limit_per_second": 3.0,
                "timeout": 30.0
            },
            AIProvider.CLAUDE: {
                "rate_limit_per_second": 1.0,
                "timeout": 60.0
            },
            AIProvider.GEMINI: {
                "rate_limit_per_second": 2.0,
                "timeout": 30.0
            }
        }
        return defaults.get(provider, {})
    
    @classmethod
    def create_multiple_clients(
        cls,
        model_infos: list[ModelInfo],
        api_keys: Optional[Dict[AIProvider, str]] = None
    ) -> list[BaseAIClient]:
        """
        複数のモデル情報から複数のクライアントを一括作成
        
        Args:
            model_infos: モデル情報のリスト
            api_keys: プロバイダーごとのAPIキー辞書
        
        Returns:
            作成されたクライアントのリスト
        """
        clients = []
        api_keys = api_keys or {}
        
        for model_info in model_infos:
            try:
                api_key = api_keys.get(model_info.provider)
                client = cls.create_client(model_info, api_key)
                clients.append(client)
            except Exception as e:
                logger.error(f"クライアント作成スキップ: {model_info.name} - {str(e)}")
                continue
        
        logger.info(f"{len(clients)}/{len(model_infos)} のクライアントを作成しました")
        return clients
    
    @classmethod
    def get_supported_providers(cls) -> list[AIProvider]:
        """サポートされているプロバイダー一覧を取得"""
        return list(cls._client_classes.keys())
    
    @classmethod
    def is_provider_supported(cls, provider: AIProvider) -> bool:
        """プロバイダーがサポートされているかチェック"""
        return provider in cls._client_classes


# 便利関数として外部に公開
def create_ai_client(
    model_info: ModelInfo,
    api_key: Optional[str] = None,
    **kwargs
) -> BaseAIClient:
    """
    AIクライアントを作成するヘルパー関数
    
    Args:
        model_info: モデル情報
        api_key: APIキー（オプション）
        **kwargs: 追加パラメータ
    
    Returns:
        作成されたAIクライアント
    """
    return ClientFactory.create_client(model_info, api_key, **kwargs)


def create_ai_clients_from_config() -> list[BaseAIClient]:
    """
    設定マネージャーから設定を読み込んでクライアントを作成
    
    Returns:
        設定済みプロバイダーのクライアントリスト
    """
    config_manager = get_config_manager()
    configured_providers = config_manager.get_configured_providers()
    
    clients = []
    for provider in configured_providers:
        # 各プロバイダーのデフォルトモデルでクライアントを作成
        default_model = config_manager.get_default_model_for_provider(provider)
        if default_model:
            model_info = ModelInfo(
                name=default_model,
                provider=provider,
                temperature=config_manager.config.default_temperature,
                max_tokens=config_manager.config.default_max_tokens
            )
            
            try:
                client = create_ai_client(model_info)
                clients.append(client)
            except Exception as e:
                logger.error(f"{provider.value} クライアント作成失敗: {e}")
    
    return clients