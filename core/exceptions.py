# core/exceptions.py
from typing import Any
class BaseAIException(Exception):
    """AI関連のカスタム例外の基底クラス"""
    def __init__(self, message: str, status_code: int = None, request: Any = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.request = request # httpx.Request オブジェクトなど

    def __str__(self):
        return f"{self.__class__.__name__}: {self.message}"


class APITimeoutError(BaseAIException):
    """API呼び出しがタイムアウトしたことを示す例外"""
    pass


class APIConnectionError(BaseAIException):
    """APIへの接続に失敗したことを示す例外"""
    pass


class APIRequestError(BaseAIException):
    """APIリクエスト自体に問題があったことを示す例外 (例: 4xxエラー)"""
    pass


class APIResponseError(BaseAIException):
    """APIからのレスポンスに問題があったことを示す例外 (例: 5xxエラー、パース不能なレスポンス)"""
    pass


class APIStatusError(BaseAIException): # GeminiClientで使おうとしていたもの
    """APIがエラーを示すステータスコードを返した場合の例外"""
    def __init__(self, message: str, status_code: int, request: Any = None):
        super().__init__(message, status_code, request)
        self.status_code = status_code # status_codeを確実に保持


class RateLimitError(BaseAIException): # ClaudeClientで使おうとしていたもの
    """APIのレート制限に達したことを示す例外"""
    pass


class AuthenticationError(BaseAIException):
    """APIキーが無効など、認証に失敗したことを示す例外"""
    pass

# 必要に応じて他のカスタム例外を追加