import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

from ..models import ModelInfo
from ..utils import RateLimiter

logger = logging.getLogger(__name__)

class BaseAIClient(ABC):
    """AIクライアントの抽象基底クラス"""

    def __init__(
        self,
        api_key: str,
        model_info: ModelInfo,
        rate_limit_per_second: float = 1.0,
        default_timeout: float = 60.0,
        max_retries: int = 3,
    ):
        self.api_key = api_key
        self.model_info = model_info
        self.rate_limiter = RateLimiter(calls_per_second=rate_limit_per_second)
        self.default_timeout = default_timeout
        self.max_retries = max_retries

        logger.info(
            f"BaseAIClient initialized for {model_info.provider.value} - {model_info.name} "
            f"with rate_limit={rate_limit_per_second}, default_timeout={self.default_timeout}, max_retries={self.max_retries}"
        )

    @abstractmethod
    async def _make_api_call(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int, # この max_tokens がAPIに渡される
        request_timeout: float
    ) -> Any:
        """実際にAPI呼び出しを行うメソッド（各サブクラスで実装）"""
        pass

    def _prepare_messages(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_message: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_message})
        return messages

    @abstractmethod
    async def _execute_request_with_retry(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int, # この max_tokens が _make_api_call に渡される
        request_specific_timeout: float
    ) -> Any:
        """
        リトライロジックを含めてAPI呼び出しを実行するメソッド。
        各具象クラスで、プロバイダ固有の例外を処理しながら _make_api_call を呼び出す。
        """
        pass

    async def request_completion(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_message: Optional[str] = None,
        override_timeout: Optional[float] = None,
        override_max_tokens: Optional[int] = None # <<< 引数追加
    ) -> Any:
        await self.rate_limiter.acquire()

        messages_for_api = self._prepare_messages(user_message, conversation_history, system_message)
        request_specific_timeout = override_timeout if override_timeout is not None else self.default_timeout

        # --- override_max_tokens を考慮して実際に使用する max_tokens を決定 ---
        effective_max_tokens = override_max_tokens if override_max_tokens is not None else self.model_info.max_tokens
        # --- ここまで追加 ---

        logger.info(
            f"Calling {self.model_info.provider.value} model {self.model_info.name} "
            f"with timeout {request_specific_timeout}s, max_tokens {effective_max_tokens}. " # max_tokens をログに追加
            f"System: {'Yes' if system_message else 'No'}, Hist: {len(conversation_history or [])} entries."
        )

        try:
            response = await self._execute_request_with_retry(
                messages=messages_for_api,
                temperature=self.model_info.temperature,
                max_tokens=effective_max_tokens, # <<< 決定した effective_max_tokens を渡す
                request_specific_timeout=request_specific_timeout
            )
            return response
        except Exception as e:
            logger.error(
                f"Final error after retries for {self.model_info.name} in request_completion: {type(e).__name__}: {e}",
                exc_info=False
            )
            raise

    @property
    def model_name(self) -> str:
        return self.model_info.name