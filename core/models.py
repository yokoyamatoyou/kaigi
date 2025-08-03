from typing import Optional, List, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict, ValidationInfo
from enum import Enum
from datetime import datetime


class AIProvider(str, Enum):
    """AI プロバイダーの種類"""
    OPENAI = "openai"
    CLAUDE = "claude"
    GEMINI = "gemini"


class ModelInfo(BaseModel):
    """AIモデルの情報"""
    name: str = Field(..., description="モデル名 (例: gpt-3.5-turbo)")
    provider: AIProvider = Field(..., description="プロバイダー")
    persona: str = Field(default="", description="ペルソナの説明")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="生成の温度")
    max_tokens: int = Field(default=1000, gt=0, description="最大トークン数")

    @field_validator('persona', mode='before')
    def validate_persona(cls, v):
        if v is None or len(str(v).strip()) == 0: # vがNoneの場合も考慮
            return "汎用的なアシスタント"
        return str(v).strip()


class MeetingSettings(BaseModel):
    """会議の設定"""
    participant_models: List[ModelInfo] = Field(default_factory=list, description="参加AIモデル")
    moderator_model: ModelInfo = Field(..., description="司会AIモデル")
    rounds_per_ai: int = Field(default=3, ge=1, le=10, description="各AIの発言回数")
    user_query: str = Field(..., description="ユーザーの質問・指示")
    document_path: Optional[str] = Field(default=None, description="アップロードされたドキュメントのパス")

    @field_validator('participant_models')
    def validate_participants(cls, v):
        if len(v) == 0:
            raise ValueError("参加AIモデルが1つ以上必要です")
        if len(v) > 5: # 最大参加者数の制限
            raise ValueError("参加AIモデルは5つまでです")
        return v


class ConversationEntry(BaseModel):
    """会話の1つのエントリ"""
    speaker: str = Field(..., description="発言者名")
    persona: str = Field(..., description="ペルソナ")
    content: str = Field(..., description="発言内容")
    timestamp: datetime = Field(default_factory=datetime.now, description="発言時刻")
    round_number: int = Field(default=1, description="発言ラウンド番号")
    model_name: str = Field(..., description="使用されたモデル名")


class DocumentSummary(BaseModel):
    """ドキュメント要約の結果"""
    original_length: int = Field(..., description="元テキストの文字数")
    summary: str = Field(..., description="要約テキスト")
    summary_length: int = Field(default=0, description="要約文字数")
    compression_ratio: float = Field(default=0.0, description="圧縮率") # デフォルト値設定
    tokens_used: int = Field(default=0, description="要約に使用されたトークン数")

    @field_validator('summary')
    def _set_summary_length_if_needed(cls, v, info: ValidationInfo):
        info.data['summary_length'] = len(v) if v else 0
        return v

    @field_validator('compression_ratio', mode='before')
    def calculate_compression_ratio(cls, v, info: ValidationInfo):
        original_length = info.data.get('original_length')
        summary_length_val = info.data.get('summary_length')
        if summary_length_val is None:
            summary_text = info.data.get('summary', '')
            summary_length_val = len(summary_text)
            info.data['summary_length'] = summary_length_val

        if original_length and original_length > 0 and summary_length_val > 0:
            return summary_length_val / original_length
        return 0.0


class MeetingResult(BaseModel):
    """会議の結果"""
    settings: MeetingSettings
    conversation_log: List[ConversationEntry] = Field(default_factory=list, description="会話ログ")
    final_summary: str = Field(..., description="最終要約")
    duration_seconds: float = Field(..., description="会議の所要時間（秒）")
    total_tokens_used: int = Field(default=0, description="使用トークン数の合計")
    document_summary: Optional[DocumentSummary] = Field(default=None, description="ドキュメント要約")
    participants_count: int

    @property
    def total_messages(self) -> int:
        """合計メッセージ数"""
        return len(self.conversation_log)


class AppConfig(BaseModel):
    """アプリケーション設定"""
    # API キー設定
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI APIキー")
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic APIキー") # Claudeのキー名としてanthropic_api_keyが一般的
    google_api_key: Optional[str] = Field(default=None, description="Google APIキー") # Geminiのキー名としてgoogle_api_keyが一般的

    # デフォルト設定
    default_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    default_max_tokens: int = Field(default=1000, gt=0) # 通常の発言用
    default_rounds_per_ai: int = Field(default=3, ge=1, le=10)

    # アプリケーション設定
    max_document_size_mb: int = Field(default=10, gt=0, description="アップロード可能なファイルサイズ上限(MB)")
    summarization_target_tokens: int = Field(default=500, gt=0, description="資料要約の目標トークン数 (DocumentProcessor用)")
    conversation_history_limit: int = Field(default=10, ge=0, description="AIに渡す会話履歴の最大件数")
    api_call_delay_seconds: float = Field(default=1.0, ge=0.0, description="API呼び出し間の遅延秒数")

    # タイムアウト設定
    api_timeout_seconds_default: int = Field(default=60, gt=0, description="Default API timeout in seconds") # 少し長めに変更
    api_timeout_seconds_summary: int = Field(default=180, gt=0, description="API timeout for summary generation in seconds") # 少し長めに変更

    # UI設定
    window_title: str = Field(default="マルチAIリサーチツール") # 名称変更
    window_width: int = Field(default=1200, gt=0)
    window_height: int = Field(default=800, gt=0)

    log_level: str = Field(default="INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")

    # --- MeetingManager で参照する追加設定 ---
    summary_max_tokens: int = Field(default=4000, gt=0, description="最終要約の最大生成トークン数")
    summary_conversation_log_max_tokens: int = Field(default=15000, gt=0, description="最終要約生成時に考慮する会話ログの最大トークン数")
    prompt_max_length_warning_threshold: int = Field(default=20000, gt=0, description="この文字数を超えると警告を出すプロンプト長（最終要約時など）")
    # --- ここまで追加 ---

    model_config: ConfigDict = ConfigDict(
        env_prefix="APP_",
        extra="ignore",
    )


class FileInfo(BaseModel):
    """アップロードされたファイルの情報"""
    filename: str = Field(..., description="ファイル名")
    filepath: str = Field(..., description="ファイルパス")
    file_type: Literal["docx", "pdf", "txt"] = Field(..., description="ファイル種別")
    size_bytes: int = Field(..., description="ファイルサイズ（バイト）")
    extracted_text: Optional[str] = Field(default=None, description="抽出されたテキスト")

    @property
    def size_mb(self) -> float:
        """ファイルサイズをMBで返す"""
        return self.size_bytes / (1024 * 1024)
