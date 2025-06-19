import asyncio
import logging
from typing import List, Dict, Any, Optional
import httpx
from openai import AsyncOpenAI, APITimeoutError as OpenAPITimeoutError, APIConnectionError as OpenAIAPIConnectionError, APIStatusError as OpenAIAPIStatusError, RateLimitError as OpenAPIRateLimitError

from .base_client import BaseAIClient
from ..models import ModelInfo
# カスタム例外をインポートする場合 (必要に応じて)
# from ..exceptions import APITimeoutError, APIConnectionError, APIStatusError, RateLimitError


logger = logging.getLogger(__name__)

class OpenAIClient(BaseAIClient):
    """OpenAI API クライアント"""

    def __init__(
        self,
        api_key: str,
        model_info: ModelInfo,
        rate_limit_per_second: float = 3.0, # OpenAIは比較的寛容なため少し高め
        default_timeout: float = 60.0, # デフォルトタイムアウト延長
        max_retries: int = 3,
    ):
        super().__init__(
            api_key=api_key,
            model_info=model_info,
            rate_limit_per_second=rate_limit_per_second,
            default_timeout=default_timeout,
            max_retries=max_retries
        )
        try:
            self.async_client = AsyncOpenAI(
                api_key=self.api_key,
                # timeout はリクエスト毎に httpx.Timeout で指定するため、ここでは設定不要
            )
            logger.info(f"OpenAIClient 初期化完了: {self.model_info.name} (デフォルトタイムアウト: {self.default_timeout}s)")
        except Exception as e:
            logger.error(f"OpenAIClient の初期化に失敗: {e}", exc_info=True)
            raise

    async def _make_api_call(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int, # この max_tokens がAPIに渡される
        request_timeout: float
    ) -> Any:
        try:
            # logger.debug(f"OpenAI API _make_api_call: model={self.model_info.name}, messages_len={len(messages)}, temp={temperature}, max_tokens={max_tokens}, timeout={request_timeout}")
            response = await self.async_client.chat.completions.create(
                model=self.model_info.name,
                messages=messages, # type: ignore
                temperature=temperature,
                max_tokens=max_tokens, # ここで受け取った max_tokens を使用
                timeout=httpx.Timeout(request_timeout) # httpx.Timeoutオブジェクトを渡す
            )
            return response
        # openaiライブラリの例外をキャッチ
        except OpenAPITimeoutError as e:
            logger.error(f"OpenAI API Timeout Error (timeout={request_timeout}s): {e.message if hasattr(e, 'message') else str(e)}", exc_info=True)
            raise # そのままraise (リトライ処理は_execute_request_with_retryで行う)
        except OpenAIAPIConnectionError as e:
            logger.error(f"OpenAI API Connection Error: {e.message if hasattr(e, 'message') else str(e)}", exc_info=True)
            raise
        # httpxレベルのタイムアウトもキャッチ (OpenAIクライアントが内部でhttpxを使用しているため)
        except httpx.ReadTimeout as e:
            logger.error(f"OpenAI API (httpx) ReadTimeout (configured_timeout={request_timeout}s): {e}", exc_info=True)
            # OpenAIのAPITimeoutErrorにラップするか、カスタム例外を使用
            raise OpenAPITimeoutError(request=e.request, message=str(e)) from e # type: ignore
        except httpx.ConnectTimeout as e: # ConnectTimeoutも追加
            logger.error(f"OpenAI API (httpx) ConnectTimeout (configured_timeout={request_timeout}s): {e}", exc_info=True)
            raise OpenAIAPIConnectionError(request=e.request, message=str(e)) from e # type: ignore
        # その他のOpenAI APIエラー (ステータスコード関連など)
        except OpenAIAPIStatusError as e:
            logger.error(f"OpenAI API Status Error (status_code={e.status_code}): {e.message}", exc_info=True)
            raise # リトライしない想定が多い
        except Exception as e:
            logger.error(f"OpenAI API呼び出し中に予期せぬエラー (timeout_setting={request_timeout}s): {e}", exc_info=True)
            raise

    async def _execute_request_with_retry(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int, # BaseClientから渡されたmax_tokens
        request_specific_timeout: float
    ) -> Any:
        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._make_api_call(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens, # そのまま渡す
                    request_timeout=request_specific_timeout
                )
                return response
            # リトライ対象の例外 (OpenAIライブラリ固有のもの)
            except (OpenAPITimeoutError, OpenAIAPIConnectionError, OpenAPIRateLimitError) as e:
                last_exception = e
                logger.warning(
                    f"Attempt {attempt + 1}/{self.max_retries + 1} failed for OpenAI model {self.model_info.name} "
                    f"due to {type(e).__name__}. Retrying in {1 * (2**attempt)}s..."
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(1 * (2**attempt))
                else:
                    logger.error(
                        f"All {self.max_retries + 1} attempts failed for OpenAI model {self.model_info.name}. "
                        f"Last error: {type(e).__name__}: {e}"
                    )
                    raise
            # リトライしないOpenAI APIエラー
            except OpenAIAPIStatusError as e:
                logger.error(f"Non-retriable APIStatusError from OpenAI for model {self.model_info.name}: {e.status_code} {e.message}", exc_info=True)
                raise
            except Exception as e:
                logger.error(f"Non-retriable error during OpenAI API call for {self.model_info.name}: {e}", exc_info=True)
                raise

        if last_exception:
            raise last_exception
        raise Exception(f"OpenAI API call failed for {self.model_info.name} after multiple retries without specific exception.")
