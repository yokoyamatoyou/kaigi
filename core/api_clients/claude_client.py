import asyncio
import logging
from typing import List, Dict, Any
import httpx
import anthropic
from anthropic import APITimeoutError, APIConnectionError, RateLimitError, APIStatusError

from .base_client import BaseAIClient
from ..models import ModelInfo

logger = logging.getLogger(__name__)

class ClaudeClient(BaseAIClient):
    """Anthropic Claude API クライアント"""

    def __init__(
        self,
        api_key: str,
        model_info: ModelInfo,
        rate_limit_per_second: float = 1.0,
        default_timeout: float = 60.0,
        max_retries: int = 3,
    ):
        super().__init__(
            api_key, model_info, rate_limit_per_second, default_timeout, max_retries
        )
        try:
            self.async_client_instance = anthropic.AsyncAnthropic(
                api_key=self.api_key
            )
            logger.info(f"ClaudeClient 初期化完了: {self.model_info.name} (デフォルトタイムアウト: {self.default_timeout}s)")
        except Exception as e:
            logger.error(f"ClaudeClient の初期化に失敗: {e}", exc_info=True)
            raise

    async def _make_api_call(
        self,
        messages: List[Dict[str, str]], # OpenAI形式
        temperature: float,
        max_tokens: int, # この max_tokens がAPIに渡される
        request_timeout: float
    ) -> Any:
        system_prompt = ""
        claude_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            elif msg["role"] == "user" or msg["role"] == "assistant": # Claudeは'assistant'ロールを期待
                claude_messages.append({"role": msg["role"], "content": msg["content"]})
            else:
                logger.warning(f"Unsupported role '{msg['role']}' in ClaudeClient _make_api_call, skipping message.")

        if not claude_messages and not system_prompt: # システムプロンプトのみでもOKな場合がある
             raise ValueError("Claude API call: No messages or system prompt provided.")
        # ユーザー/アシスタントメッセージがないがシステムプロンプトはある場合、
        # claude_messages が空でもAPIが受け付けるか確認が必要。
        # 通常は少なくとも1つのユーザーメッセージが必要。
        if not any(m["role"] == "user" for m in claude_messages) and not system_prompt:
            raise ValueError("Claude API call: At least one user message or a system prompt is required.")


        try:
            # logger.debug(f"Claude API _make_api_call: model={self.model_info.name}, system_len={len(system_prompt)}, messages_len={len(claude_messages)}, temp={temperature}, max_tokens={max_tokens}, timeout={request_timeout}")
            response = await self.async_client_instance.messages.create(
                model=self.model_info.name,
                system=system_prompt if system_prompt else None, # systemプロンプトを渡す
                messages=claude_messages, # type: ignore
                temperature=temperature,
                max_tokens=max_tokens, # ここで受け取った max_tokens を使用
                timeout=httpx.Timeout(request_timeout)
            )
            return response
        except APITimeoutError as e:
            logger.error(f"Claude API Timeout Error (timeout={request_timeout}s): {e.message if hasattr(e, 'message') else str(e)}", exc_info=True)
            raise
        except APIConnectionError as e:
            logger.error(f"Claude API Connection Error: {e.message if hasattr(e, 'message') else str(e)}", exc_info=True)
            raise
        except httpx.ReadTimeout as e:
            logger.error(f"Claude API (httpx) ReadTimeout (configured_timeout={request_timeout}s): {e}", exc_info=True)
            raise APITimeoutError(request=e.request, message=str(e)) from e # type: ignore
        except httpx.ConnectError as e:
            logger.error(f"Claude API (httpx) ConnectError: {e}", exc_info=True)
            raise APIConnectionError(request=e.request, message=str(e)) from e # type: ignore
        except APIStatusError as e:
            logger.error(f"Claude API Status Error (status_code={e.status_code}): {e.message}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Claude API呼び出し中に予期せぬエラー (timeout_setting={request_timeout}s): {e}", exc_info=True)
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
            except (APITimeoutError, APIConnectionError, RateLimitError) as e:
                last_exception = e
                logger.warning(
                    f"Attempt {attempt + 1}/{self.max_retries + 1} failed for Claude model {self.model_info.name} "
                    f"due to {type(e).__name__}. Retrying in {1 * (2**attempt)}s..."
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(1 * (2**attempt))
                else:
                    logger.error(
                        f"All {self.max_retries + 1} attempts failed for Claude model {self.model_info.name}. "
                        f"Last error: {type(e).__name__}: {e}"
                    )
                    raise
            except APIStatusError as e:
                logger.error(f"Non-retriable APIStatusError from Claude for model {self.model_info.name}: {e.status_code} {e.message}", exc_info=True)
                raise
            except Exception as e:
                logger.error(f"Non-retriable error during Claude API call for {self.model_info.name}: {e}", exc_info=True)
                raise

        if last_exception: # ループを抜けたが last_exception がある場合 (通常はループ内でraiseされる)
            raise last_exception
        # フォールバック (通常到達しないはず)
        raise Exception(f"Claude API call failed for {self.model_info.name} after multiple retries without specific exception.")
