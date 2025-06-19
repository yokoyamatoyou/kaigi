"""
ユーティリティ関数群

アプリケーション全体で使用される共通機能を提供します。
"""

import asyncio
import time
import hashlib
import json
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable, TypeVar
from pathlib import Path
import logging
import tiktoken
from functools import wraps

logger = logging.getLogger(__name__)

# 型ヒント用
T = TypeVar('T')
F = TypeVar('F', bound=Callable[..., Any])


def count_tokens(text: str, model_name: str = "gpt-3.5-turbo") -> int:
    """
    指定されたモデルでのトークン数をカウント
    
    Args:
        text: カウント対象のテキスト
        model_name: モデル名（エンコーディング推定に使用）
    
    Returns:
        トークン数
    """
    try:
        # モデル名からエンコーディングを推定
        if "gpt-4" in model_name.lower():
            encoding_name = "cl100k_base"
        elif "gpt-3.5" in model_name.lower():
            encoding_name = "cl100k_base"
        elif "claude" in model_name.lower():
            # Claudeの場合はGPTのエンコーディングで近似
            encoding_name = "cl100k_base"
        elif "gemini" in model_name.lower():
            # Geminiの場合もGPTのエンコーディングで近似
            encoding_name = "cl100k_base"
        else:
            encoding_name = "cl100k_base"
        
        encoding = tiktoken.get_encoding(encoding_name)
        return len(encoding.encode(text))
    except Exception as e:
        logger.warning(f"トークンカウントに失敗しました: {e}")
        # フォールバック: 文字数を4で割った値を返す（大雑把な近似）
        return len(text) // 4


def format_timestamp(timestamp: datetime) -> str:
    """
    タイムスタンプを読みやすい形式でフォーマット
    
    Args:
        timestamp: フォーマット対象のタイムスタンプ
    
    Returns:
        フォーマットされた文字列
    """
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def format_duration(seconds: float) -> str:
    """
    秒数を読みやすい形式でフォーマット
    
    Args:
        seconds: 秒数
    
    Returns:
        フォーマットされた文字列 (例: "2分30秒", "1時間15分")
    """
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}分{secs}秒" if secs > 0 else f"{minutes}分"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}時間{minutes}分" if minutes > 0 else f"{hours}時間"


def calculate_compression_ratio(original_text: str, compressed_text: str) -> float:
    """
    圧縮率を計算
    
    Args:
        original_text: 元のテキスト
        compressed_text: 圧縮後のテキスト
    
    Returns:
        圧縮率（0.0-1.0）
    """
    if len(original_text) == 0:
        return 0.0
    return len(compressed_text) / len(original_text)


def sanitize_filename(filename: str) -> str:
    """
    ファイル名から不正な文字を除去
    
    Args:
        filename: 元のファイル名
    
    Returns:
        サニタイズされたファイル名
    """
    # 不正な文字を置換
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # 先頭末尾の空白とピリオドを除去
    filename = filename.strip('. ')
    
    # 長すぎる場合は切り詰め
    if len(filename) > 255:
        name, ext = Path(filename).stem, Path(filename).suffix
        max_name_len = 255 - len(ext)
        filename = name[:max_name_len] + ext
    
    return filename


def generate_file_hash(file_path: str) -> str:
    """
    ファイルのSHA256ハッシュを生成
    
    Args:
        file_path: ファイルパス
    
    Returns:
        ハッシュ値（16進数文字列）
    """
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except Exception as e:
        logger.error(f"ファイルハッシュ生成に失敗: {e}")
        return ""


def retry_with_exponential_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: tuple = (Exception,)
) -> Callable[[F], F]:
    """
    指数バックオフ付きリトライデコレータ
    
    Args:
        max_retries: 最大リトライ回数
        base_delay: 初期遅延秒数
        max_delay: 最大遅延秒数
        exceptions: リトライ対象の例外
    
    Returns:
        デコレータ関数
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    if asyncio.iscoroutinefunction(func):
                        return await func(*args, **kwargs)
                    else:
                        return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        raise e
                    
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    logger.warning(f"リトライ {attempt + 1}/{max_retries}: {delay}秒後に再実行")
                    await asyncio.sleep(delay)
            
            # ここに到達することはないはずだが、念のため
            if last_exception:
                raise last_exception
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        raise e
                    
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    logger.warning(f"リトライ {attempt + 1}/{max_retries}: {delay}秒後に再実行")
                    time.sleep(delay)
            
            if last_exception:
                raise last_exception
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


class RateLimiter:
    """簡単なレート制限クラス"""
    
    def __init__(self, calls_per_second: float = 1.0):
        self.min_interval = 1.0 / calls_per_second
        self.last_call_time = 0.0
    
    async def acquire(self):
        """レート制限を適用して処理を実行"""
        current_time = time.time()
        time_since_last_call = current_time - self.last_call_time
        
        if time_since_last_call < self.min_interval:
            wait_time = self.min_interval - time_since_last_call
            await asyncio.sleep(wait_time)
        
        self.last_call_time = time.time()


def chunk_text(text: str, max_chunk_size: int = 1000, overlap: int = 100) -> List[str]:
    """
    テキストを指定されたサイズでチャンクに分割
    
    Args:
        text: 分割対象のテキスト
        max_chunk_size: 最大チャンクサイズ（文字数）
        overlap: チャンク間のオーバーラップ文字数
    
    Returns:
        分割されたチャンクのリスト
    """
    if len(text) <= max_chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + max_chunk_size
        
        if end >= len(text):
            chunks.append(text[start:])
            break
        
        # 文の境界で分割を試行
        last_period = text.rfind('。', start, end)
        last_newline = text.rfind('\n', start, end)
        split_point = max(last_period, last_newline)
        
        if split_point > start:
            chunks.append(text[start:split_point + 1])
            start = split_point + 1 - overlap
        else:
            chunks.append(text[start:end])
            start = end - overlap
        
        # 次のスタート地点が負の値にならないようにする
        start = max(0, start)
    
    return chunks


def load_prompts_from_file(file_path: str) -> Dict[str, str]:
    """
    プロンプトファイルからプロンプトテンプレートを読み込み
    
    Args:
        file_path: プロンプトファイルのパス
    
    Returns:
        プロンプト名をキーとした辞書
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            prompts = json.load(f)
        logger.info(f"プロンプトファイルを読み込みました: {file_path}")
        return prompts
    except Exception as e:
        logger.error(f"プロンプトファイルの読み込みに失敗: {e}")
        return {}


def format_conversation_for_display(conversation_log: List[Dict[str, Any]]) -> str:
    """
    会話ログを表示用の文字列に整形
    
    Args:
        conversation_log: 会話ログのリスト
    
    Returns:
        整形された会話文字列
    """
    lines = []
    for entry in conversation_log:
        timestamp = format_timestamp(entry.get('timestamp', datetime.now()))
        speaker = entry.get('speaker', '不明')
        persona = entry.get('persona', '')
        content = entry.get('content', '')
        
        persona_text = f" ({persona})" if persona else ""
        lines.append(f"[{timestamp}] {speaker}{persona_text}:")
        lines.append(content)
        lines.append("")  # 空行
    
    return "\n".join(lines)


class Timer:
    """処理時間計測用のコンテキストマネージャー"""
    
    def __init__(self, name: str = "処理"):
        self.name = name
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        logger.info(f"{self.name}を開始しました")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        elapsed = self.end_time - self.start_time
        logger.info(f"{self.name}が完了しました（所要時間: {format_duration(elapsed)}）")
    
    @property
    def elapsed_seconds(self) -> float:
        """経過時間を秒で取得"""
        if self.start_time is None:
            return 0.0
        if self.end_time is None:
            return time.time() - self.start_time
        return self.end_time - self.start_time