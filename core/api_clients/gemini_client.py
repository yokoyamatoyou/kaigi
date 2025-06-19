import asyncio
import logging
from typing import List, Dict, Any, Optional
import google.generativeai as genai
# Content と Part の直接インポートを削除 (またはコメントアウト)
# from google.generativeai.types import Content, Part
from google.generativeai.types import GenerationConfig, HarmCategory, HarmBlockThreshold # これらは通常存在
from google.api_core import exceptions as google_exceptions

from .base_client import BaseAIClient
from ..models import ModelInfo
# カスタム例外のインポート (もしあれば)
from ..exceptions import APITimeoutError, APIConnectionError, APIStatusError


logger = logging.getLogger(__name__)

class GeminiClient(BaseAIClient):
    """Google Gemini API クライアント"""

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
            genai.configure(api_key=self.api_key)
            # モデル名は self.model_info.name を使用
            self.model = genai.GenerativeModel(self.model_info.name)
            logger.info(f"GeminiClient 初期化完了: {self.model_info.name} (デフォルトタイムアウト: {self.default_timeout}s)")
        except Exception as e:
            logger.error(f"GeminiClient の初期化に失敗: {e}", exc_info=True)
            raise


    async def _make_api_call(
        self,
        messages: List[Dict[str, str]], # OpenAI形式
        temperature: float,
        max_tokens: int,
        request_timeout: float
    ) -> Any:
        system_instruction_str: Optional[str] = None
        # Content オブジェクトではなく、辞書のリストとして contents を構築
        gemini_contents_for_api: List[Dict[str, Any]] = []

        # メッセージをGemini形式 (辞書のリスト) に変換
        current_parts_list: List[Dict[str, str]] = []
        current_role_str: Optional[str] = None

        for msg in messages:
            msg_role = msg["role"]
            msg_content = msg["content"]

            if msg_role == "system":
                system_instruction_str = (system_instruction_str + "\n" + msg_content) if system_instruction_str else msg_content
                continue

            mapped_role = "user" if msg_role == "user" else "model"

            if current_role_str != mapped_role and current_parts_list:
                gemini_contents_for_api.append({"role": current_role_str, "parts": current_parts_list})
                current_parts_list = []

            current_parts_list.append({"text": msg_content})
            current_role_str = mapped_role

        if current_parts_list: # 最後のロールのパーツを追加
            gemini_contents_for_api.append({"role": current_role_str, "parts": current_parts_list})

        if not gemini_contents_for_api and not system_instruction_str:
            raise ValueError("Gemini API call: No messages or system instruction provided.")
        # ユーザーメッセージが一つもない場合 (システム指示のみはAPIレベルで非推奨またはエラーになることが多い)
        if not any(c.get("role") == "user" for c in gemini_contents_for_api) and not system_instruction_str:
            if not gemini_contents_for_api:
                 raise ValueError("Gemini API call: No user messages found and no system instruction.")


        generation_config_dict = { # GenerationConfigオブジェクトではなく辞書で渡す
            "temperature": temperature,
            "max_output_tokens": max_tokens,
            # "candidate_count": 1, # 通常は1
            # "top_p": 0.95, # 必要に応じて
            # "top_k": 40,   # 必要に応じて
        }
        safety_settings_list: List[Dict[str, Any]] = [ # HarmCategory, HarmBlockThreshold を使用
            {"category": HarmCategory.HARM_CATEGORY_HARASSMENT, "threshold": HarmBlockThreshold.BLOCK_NONE}, # より緩やかな設定例
            {"category": HarmCategory.HARM_CATEGORY_HATE_SPEECH, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, "threshold": HarmBlockThreshold.BLOCK_NONE},
            {"category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, "threshold": HarmBlockThreshold.BLOCK_NONE},
        ]

        request_options = {"timeout": request_timeout} if request_timeout > 0 else {}

        try:
            # logger.debug(f"Gemini API _make_api_call: model={self.model.model_name}, system='{system_instruction_str}', contents_len={len(gemini_contents_for_api)}, temp={temperature}, max_tokens={max_tokens}, timeout={request_timeout}")
            response = await self.model.generate_content_async(
                contents=gemini_contents_for_api, # 辞書のリストを渡す
                generation_config=generation_config_dict, # 辞書として渡す
                safety_settings=safety_settings_list,
                system_instruction=system_instruction_str if system_instruction_str else None,
                request_options=request_options if request_options else None # type: ignore
            )
            return response
        except google_exceptions.DeadlineExceeded as e:
            logger.error(f"Gemini API DeadlineExceeded (timeout={request_timeout}s): {e}", exc_info=True)
            raise APITimeoutError(message=f"Gemini API DeadlineExceeded: {str(e)}") from e
        except google_exceptions.RetryError as e:
            logger.error(f"Gemini API RetryError: {e}", exc_info=True)
            raise APIConnectionError(message=f"Gemini API RetryError: {str(e)}") from e
        except google_exceptions.GoogleAPIError as e:
            logger.error(f"Gemini API GoogleAPIError: {e}", exc_info=True)
            status_code = e.code if hasattr(e, 'code') else 500
            # APIStatusError を使用 (カスタム例外)
            raise APIStatusError(message=f"Gemini API GoogleAPIError: {str(e)}", status_code=status_code, request=None) from e # type: ignore
        except Exception as e:
            logger.error(f"Gemini API呼び出し中に予期せぬエラー (timeout_setting={request_timeout}s): {e}", exc_info=True)
            raise

    async def _execute_request_with_retry(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        request_specific_timeout: float
    ) -> Any:
        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._make_api_call(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    request_timeout=request_specific_timeout
                )
                return response
            # _make_api_call 内で Google の例外はカスタム例外にラップされているはず
            except (APITimeoutError, APIConnectionError, google_exceptions.ResourceExhausted, google_exceptions.Unavailable) as e: # google_exceptionsも直接キャッチ
                last_exception = e
                logger.warning(
                    f"Attempt {attempt + 1}/{self.max_retries + 1} failed for Gemini model {self.model_info.name} "
                    f"due to {type(e).__name__}. Retrying in {1 * (2**attempt)}s..."
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(1 * (2**attempt))
                else:
                    logger.error(
                        f"All {self.max_retries + 1} attempts failed for Gemini model {self.model_info.name}. "
                        f"Last error: {type(e).__name__}: {e}"
                    )
                    raise
            except APIStatusError as e: # カスタム例外
                logger.error(f"Non-retriable APIStatusError from Gemini for model {self.model_info.name}: {e.status_code} {e.message}", exc_info=True)
                raise
            except Exception as e:
                logger.error(f"Non-retriable error during Gemini API call for {self.model_info.name}: {e}", exc_info=True)
                raise

        if last_exception:
            raise last_exception
        raise Exception(f"Gemini API call failed for {self.model_info.name} after multiple retries without specific exception.")