import asyncio
import random
import logging
from typing import List, Dict, Optional, Tuple, Any, Callable
from datetime import datetime
from dataclasses import dataclass, field
import copy
import re # 日本語チェック用

from .models import (
    MeetingSettings, MeetingResult, ConversationEntry, DocumentSummary,
    ModelInfo, AIProvider, AppConfig
)
from .api_clients import BaseAIClient
from .client_factory import ClientFactory
from .document_processor import DocumentProcessor
from .utils import (
    Timer,
    format_duration,
    sanitize_filename,
    count_tokens,
    extract_content_and_tokens,
)
from .config_manager import get_config_manager
from .context_manager import save_carry_over
from .persona_enhancer import PersonaEnhancer
from .vector_store_manager import VectorStoreManager

logger = logging.getLogger(__name__)

@dataclass
class ParticipantInfo:
    client: BaseAIClient
    name: str
    internal_key: str
    persona: str
    model_info: ModelInfo
    round_count: int = 0
    total_statements: int = 0

@dataclass
class MeetingState:
    phase: str = "pending"
    current_round_overall: int = 0
    total_rounds_expected: int = 0
    active_participant_keys: List[str] = field(default_factory=list)
    conversation_history: List[ConversationEntry] = field(default_factory=list)
    error_message: Optional[str] = None
    total_tokens_this_meeting: int = 0

    def add_conversation_entry(self, entry: ConversationEntry):
        self.conversation_history.append(entry)
        logger.debug(f"会話ログ追加: {entry.speaker} - Round {entry.round_number} - {entry.content[:50]}...")

    def add_tokens_used(self, tokens: int):
        self.total_tokens_this_meeting += tokens

class MeetingManager:
    def __init__(
        self,
        document_processor: Optional[DocumentProcessor] = None,
        vector_store_manager: Optional[VectorStoreManager] = None,
        carry_over_context: Optional[str] = None,
    ):
        self.config_manager = get_config_manager()
        self.app_config: AppConfig = self.config_manager.config
        self.document_processor = document_processor or DocumentProcessor(config=self.app_config)
        self.vector_store_manager = vector_store_manager
        self.carry_over_context = carry_over_context
        self.participants: Dict[str, ParticipantInfo] = {}
        self.moderator: Optional[ParticipantInfo] = None
        self.state = MeetingState()
        self._system_prompt_context: str = ""

        self.on_statement_added: Optional[Callable[[ConversationEntry], None]] = None
        self.on_phase_changed: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.progress_callback_internal: Optional[Callable[[str, int, int], None]] = None
        logger.info("MeetingManager 初期化完了")

    def _update_phase(self, new_phase: str):
        self.state.phase = new_phase
        logger.info(f"会議フェーズ変更: {new_phase}")
        if self.on_phase_changed:
            try: self.on_phase_changed(new_phase)
            except Exception as e: logger.error(f"on_phase_changed コールバック実行エラー: {e}", exc_info=True)

    def _report_error(self, error_message: str, exc_info: bool = False):
        logger.error(error_message, exc_info=exc_info)
        self.state.error_message = error_message
        self._update_phase("error")
        if self.on_error:
            try: self.on_error(error_message)
            except Exception as e: logger.error(f"on_error コールバック実行エラー: {e}", exc_info=True)

    def initialize_participants(self, settings: MeetingSettings) -> bool:
        self._update_phase("initializing_participants")
        try:
            self.clear_meeting_state()
            for model_config in settings.participant_models:
                base_key = sanitize_filename(f"{model_config.provider.value}_{model_config.name}")
                internal_key = base_key
                suffix = 1
                while internal_key in self.participants:
                    internal_key = f"{base_key}_{suffix}"
                    suffix += 1
                try:
                    client = ClientFactory.create_client(model_info=model_config)
                    # ペルソナに「(日本語話者)」を自動付与
                    persona_with_language = f"{model_config.persona} (日本語話者)"
                    self.participants[internal_key] = ParticipantInfo(
                        client=client, name=model_config.name, internal_key=internal_key,
                        persona=persona_with_language, model_info=model_config
                    )
                    logger.info(f"参加者初期化成功: {internal_key} (表示名: {model_config.name}, ペルソナ: {persona_with_language})")
                except Exception as e:
                    self._report_error(f"参加者({model_config.name})の初期化に失敗: {e}", exc_info=True)
                    return False

            moderator_config = settings.moderator_model
            moderator_internal_key = sanitize_filename(f"moderator_{moderator_config.provider.value}_{moderator_config.name}")
            try:
                moderator_client = ClientFactory.create_client(model_info=moderator_config)
                # 司会者のペルソナにも日本語指示を暗に含める
                moderator_persona = "会議の司会者・進行役、議論のファシリテーター、最終要約作成者 (全てのコミュニケーションは日本語で行う)"
                self.moderator = ParticipantInfo(
                    client=moderator_client, name="司会AI", internal_key=moderator_internal_key,
                    persona=moderator_persona,
                    model_info=moderator_config
                )
                logger.info(f"司会者初期化成功: {self.moderator.name} (内部キー: {moderator_internal_key}, モデル: {moderator_config.name})")
            except Exception as e:
                self._report_error(f"司会者(モデル: {moderator_config.name})の初期化に失敗: {e}", exc_info=True)
                return False

            self.state.total_rounds_expected = settings.rounds_per_ai * len(self.participants)
            self.state.active_participant_keys = list(self.participants.keys())
            logger.info(f"全参加者・司会者の初期化完了。参加者{len(self.participants)}名、総発言予定: {self.state.total_rounds_expected}回。")
            return True
        except Exception as e:
            self._report_error(f"参加者初期化プロセス全体で予期せぬエラー: {e}", exc_info=True)
            return False

    async def _enhance_personas(self, topic: str, document_summary: Optional[DocumentSummary]):
        """OpenAIを用いて参加者および司会者のペルソナを強化する。"""
        api_key = self.config_manager.config.openai_api_key
        if not api_key:
            logger.info("OpenAI APIキーが未設定のため、ペルソナ強化をスキップします。")
            return
        try:
            enhancer = PersonaEnhancer(api_key=api_key)
        except Exception as e:
            logger.warning(f"PersonaEnhancerの初期化に失敗: {e}")
            return
        document_context = (
            document_summary.summary
            if document_summary and document_summary.summary
            else None
        )
        targets: List[ParticipantInfo] = list(self.participants.values())
        if self.moderator:
            targets.append(self.moderator)
        for participant in targets:
            try:
                enhanced = await asyncio.to_thread(
                    enhancer.enhance_persona,
                    participant.persona,
                    topic,
                    document_context,
                )
                if enhanced:
                    participant.persona = enhanced.strip()
            except Exception as e:
                logger.warning(f"{participant.name}のペルソナ強化に失敗: {e}")

    async def _ensure_japanese_output(
        self,
        text_to_check: str,
        client: BaseAIClient,
        original_provider: AIProvider,
        context_for_correction: str = "以下のテキストを、不自然な部分があれば修正し、完全に自然で流暢な日本語の文章にしてください。他の言語の要素は一切含めないでください。"
    ) -> Tuple[str, int]:
        if not text_to_check.strip():
            return text_to_check, 0

        non_japanese_char_threshold = 0.3
        min_japanese_char_ratio = 0.6
        ascii_chars = len(re.findall(r'[ -~]', text_to_check))
        total_chars = len(text_to_check)
        # より正確な日本語文字の判定 (ひらがな、カタカナ、漢字の範囲)
        japanese_chars = len(re.findall(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF々]', text_to_check))


        needs_correction = False
        if total_chars > 0:
            # 非日本語文字(ASCII)が多すぎるか、または日本語文字が少なすぎる場合
            # (ただし、URLやコード片などASCIIが多い正当なケースもあるため、この判定は完璧ではない)
            if (ascii_chars / total_chars) > non_japanese_char_threshold and japanese_chars < (total_chars * (1-non_japanese_char_threshold) * 0.8): # ASCIIが多くても日本語もそれなりにあればOKとする閾値
                needs_correction = True
                logger.info(f"日本語修正候補 (ASCII比率高/日本語比率低): 「{text_to_check[:100]}...」")
            elif (japanese_chars / total_chars) < min_japanese_char_ratio and total_chars > 20: # ある程度長さがあり日本語比率が低い
                needs_correction = True
                logger.info(f"日本語修正候補 (日本語比率低): 「{text_to_check[:100]}...」")


        if needs_correction:
            logger.warning(f"発言内容に日本語以外の言語が混じっている可能性があるため、修正を試みます。元テキスト: 「{text_to_check[:100]}...」")
            correction_prompt = f"{context_for_correction}\n\n修正対象テキスト:\n---\n{text_to_check}\n---\n\n修正後の日本語テキストのみを返してください。"
            try:
                correction_response = await client.request_completion(
                    user_message=correction_prompt,
                    system_message="あなたは高度な翻訳・校正AIです。指示されたテキストを完璧な日本語にしてください。"
                )
                corrected_text, tokens_for_correction = extract_content_and_tokens(
                    original_provider, correction_response
                )
                if corrected_text.strip():
                    logger.info(f"日本語への修正成功。修正後:「{corrected_text[:100]}...」 (追加トークン: {tokens_for_correction})")
                    self.state.add_tokens_used(tokens_for_correction)
                    return corrected_text, tokens_for_correction
                else:
                    logger.error("日本語への修正試行が空の応答を返しました。元のテキストを使用します。")
                    return text_to_check, 0
            except Exception as e:
                logger.error(f"日本語への修正処理中にエラーが発生: {e}。元のテキストを使用します。", exc_info=True)
                return text_to_check, 0
        return text_to_check, 0

    async def run_meeting(
        self, settings: MeetingSettings,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> MeetingResult:
        start_time = datetime.now()
        self.progress_callback_internal = progress_callback
        document_summary_obj = None

        try:
            with Timer("会議全体"):
                if not self.initialize_participants(settings):
                    return MeetingResult(
                        settings=copy.deepcopy(settings), conversation_log=self.state.conversation_history.copy(),
                        final_summary=f"会議を開始できませんでした: {self.state.error_message or '参加者初期化エラー'}",
                        duration_seconds=(datetime.now() - start_time).total_seconds(),
                        total_tokens_used=self.state.total_tokens_this_meeting,
                        document_summary=None, participants_count=len(self.participants)
                    )
                if settings.document_path:
                    self._update_phase("processing_document")
                    document_summary_obj = await self._process_document(settings.document_path)
                self._update_phase("enhancing_personas")
                await self._enhance_personas(settings.user_query, document_summary_obj)

                self._update_phase("discussing")
                await self._conduct_meeting(settings, document_summary_obj)

                self._update_phase("summarizing")
                final_summary_text = await self._generate_final_summary(settings.user_query, document_summary_obj)

                self._update_phase("completed")
                duration = (datetime.now() - start_time).total_seconds()

                meeting_result = MeetingResult(
                    settings=copy.deepcopy(settings), conversation_log=self.state.conversation_history.copy(),
                    final_summary=final_summary_text.strip(), duration_seconds=duration,
                    total_tokens_used=self.state.total_tokens_this_meeting,
                    document_summary=document_summary_obj,
                    participants_count=len(self.participants)
                )
                logger.info(f"会議正常終了。所要時間: {format_duration(duration)}, 総トークン: {self.state.total_tokens_this_meeting}")
                return meeting_result
        except Exception as e:
            self._report_error(f"会議実行中に致命的なエラーが発生: {e}", exc_info=True)
            return MeetingResult(
                settings=copy.deepcopy(settings), conversation_log=self.state.conversation_history.copy(),
                final_summary=f"会議中に致命的なエラー: {self.state.error_message or str(e)}",
                duration_seconds=(datetime.now() - start_time).total_seconds(),
                total_tokens_used=self.state.total_tokens_this_meeting,
                document_summary=document_summary_obj,
                participants_count=len(self.participants)
            )

    async def _process_document(self, document_path: str) -> Optional[DocumentSummary]:
        try:
            extraction_result = self.document_processor.extract_text(document_path)
            if not extraction_result.is_success or not extraction_result.extracted_text:
                self._report_error(f"資料からのテキスト抽出失敗: {extraction_result.error_message or '不明なエラー'}")
                return None
            if not self.moderator:
                logger.warning("司会者が未設定のため、資料要約をスキップ。")
                return None

            logger.info(f"資料テキスト抽出成功 ({len(extraction_result.extracted_text)}文字)。要約開始...")

            summary_obj = await self.document_processor.summarize_document_for_meeting(
                extraction_result.extracted_text, self.moderator.client
            )

            if summary_obj and summary_obj.summary:
                corrected_summary_text, correction_tokens_summary = await self._ensure_japanese_output(
                    summary_obj.summary,
                    self.moderator.client,
                    self.moderator.model_info.provider,
                    context_for_correction="以下の資料要約を、完全に自然で流暢な日本語にしてください。他の言語の要素は一切含めないでください。"
                )
                summary_obj.summary = corrected_summary_text
                if correction_tokens_summary > 0:
                     logger.info(f"資料要約の日本語修正に追加トークン: {correction_tokens_summary}")


            if summary_obj and summary_obj.tokens_used >= 0 :
                self.state.add_tokens_used(summary_obj.tokens_used)
                logger.info(f"資料要約成功。要約長: {len(summary_obj.summary)}文字, 初期トークン: {summary_obj.tokens_used}")
            elif summary_obj:
                 logger.warning("資料要約は成功しましたが、初期トークン数が記録されていません。")
            else:
                self._report_error("資料要約失敗。DocumentProcessorがNoneを返しました。")
                return None
            return summary_obj
        except RuntimeError as e:
            self._report_error(f"資料要約処理中にエラー: {e}", exc_info=True)
            return None
        except Exception as e:
            self._report_error(f"資料処理中に予期せぬエラー: {e}", exc_info=True)
            return None

    async def _conduct_meeting(
        self, settings: MeetingSettings, document_summary: Optional[DocumentSummary]
    ):
        self._system_prompt_context = self._build_initial_context(settings.user_query, document_summary)
        participant_internal_keys = list(self.participants.keys())
        current_overall_statement_num = 0
        for i in range(settings.rounds_per_ai):
            current_round_label = i + 1
            logger.info(f"議論ラウンド {current_round_label}/{settings.rounds_per_ai} を開始。")
            if self.progress_callback_internal:
                self.progress_callback_internal("discussing_round", current_round_label, settings.rounds_per_ai)
            random.shuffle(participant_internal_keys)
            for p_key in participant_internal_keys:
                participant = self.participants[p_key]
                if participant.round_count < settings.rounds_per_ai:
                    current_overall_statement_num +=1
                    if self.progress_callback_internal:
                         self.progress_callback_internal("discussing_statement", current_overall_statement_num, self.state.total_rounds_expected)
                    participant.round_count += 1
                    logger.info(f"  参加者 {participant.name} (キー: {p_key}) の発言 (AI別R{participant.round_count}, 全体{current_overall_statement_num}/{self.state.total_rounds_expected})")
                    await self._make_participant_statement(
                        participant, participant.round_count
                    )
                    await asyncio.sleep(self.app_config.api_call_delay_seconds)
            # ラウンド終了後に司会AIによる簡潔な要約を挿入
            if self.moderator:
                if self.progress_callback_internal:
                    self.progress_callback_internal("moderator_summary", current_round_label, settings.rounds_per_ai)
                await self._generate_round_summary(current_round_label)
                await asyncio.sleep(self.app_config.api_call_delay_seconds)
        logger.info("全議論ラウンド完了。")

    async def _make_participant_statement(
        self, participant: ParticipantInfo, ai_specific_round_num: int
    ):
        try:
            user_prompt_for_statement = self._build_statement_prompt(participant, ai_specific_round_num)
            api_conversation_history = self._prepare_conversation_history_for_api(
                limit=self.app_config.conversation_history_limit
            )
            rag_context = self._get_rag_context(user_prompt_for_statement)
            system_message = self._build_system_prompt(participant, rag_context)
            logger.debug(f"発言者: {participant.name}, AIラウンド: {ai_specific_round_num}, システムメッセージ: {system_message[:200]}...")

            raw_response = await participant.client.request_completion(
                user_message=user_prompt_for_statement,
                conversation_history=api_conversation_history,
                system_message=system_message
            )
            content, tokens_this_call = extract_content_and_tokens(
                participant.model_info.provider, raw_response
            )
            self.state.add_tokens_used(tokens_this_call)

            corrected_content, correction_tokens = await self._ensure_japanese_output(
                content,
                participant.client,
                participant.model_info.provider,
                context_for_correction=(
                    "以下の会議での発言を、完全に自然で流暢な日本語に修正してください。"
                    "元の発言の意図やニュアンスをできる限り保ちつつ、他の言語の要素は一切含めないでください。"
                )
            )

            entry = ConversationEntry(
                speaker=participant.name, persona=participant.persona, content=corrected_content,
                timestamp=datetime.now(), round_number=ai_specific_round_num, model_name=participant.model_info.name
            )
            self.state.add_conversation_entry(entry)
            participant.total_statements += 1
            if self.on_statement_added:
                try: self.on_statement_added(entry)
                except Exception as e: logger.error(f"on_statement_added コールバック実行エラー: {e}", exc_info=True)

            total_tokens_for_statement = tokens_this_call + correction_tokens
            logger.info(f"  {participant.name} 発言成功 (AI別R{ai_specific_round_num}, 消費トークン: {total_tokens_for_statement} (初期{tokens_this_call}, 修正{correction_tokens}))")

        except Exception as e:
            self._report_error(f"{participant.name} (AI別R{ai_specific_round_num}) の発言中にエラー: {e}", exc_info=True)
            error_entry = ConversationEntry(
                speaker=participant.name, persona=participant.persona,
                content=f"エラーにより発言できませんでした: {type(e).__name__}。詳細はログを確認してください。",
                timestamp=datetime.now(), round_number=ai_specific_round_num, model_name=participant.model_info.name
            )
            self.state.add_conversation_entry(error_entry)
            if self.on_statement_added: self.on_statement_added(error_entry)

    async def _generate_round_summary(self, round_number: int):
        if not self.moderator:
            logger.warning("ラウンド要約生成: 司会者が未設定のためスキップします。")
            return
        try:
            api_conversation_history = self._prepare_conversation_history_for_api(
                limit=self.app_config.conversation_history_limit
            )
            user_prompt = (
                f"これまでの議論の要点を日本語で150文字程度にまとめてください。\n"
                f"これはラウンド{round_number}終了時点の要約です。"
            )
            system_message = (
                "あなたは会議の司会者です。現在までの議論を簡潔に整理し、次のラウンドに備えます。"
            )
            raw_response = await self.moderator.client.request_completion(
                user_message=user_prompt,
                conversation_history=api_conversation_history,
                system_message=system_message,
            )
            content, tokens_this_call = extract_content_and_tokens(
                self.moderator.model_info.provider, raw_response
            )
            self.state.add_tokens_used(tokens_this_call)

            corrected_content, correction_tokens = await self._ensure_japanese_output(
                content,
                self.moderator.client,
                self.moderator.model_info.provider,
                context_for_correction="以下の要約を自然で流暢な日本語にしてください。その他の言語を含めないでください。",
            )

            entry = ConversationEntry(
                speaker=self.moderator.name,
                persona=f"{self.moderator.persona} (ラウンド要約)",
                content=corrected_content,
                timestamp=datetime.now(),
                round_number=round_number,
                model_name=self.moderator.model_info.name,
            )
            self.state.add_conversation_entry(entry)
            if self.on_statement_added:
                try:
                    self.on_statement_added(entry)
                except Exception as e:
                    logger.error(f"on_statement_added コールバック実行エラー: {e}", exc_info=True)

            total_tokens_for_summary = tokens_this_call + correction_tokens
            logger.info(
                f"ラウンド{round_number}要約生成成功。消費トークン: {total_tokens_for_summary}"
            )
        except Exception as e:
            self._report_error(f"ラウンド{round_number}要約生成中にエラー: {e}", exc_info=True)

    def _get_rag_context(self, query: str) -> Optional[str]:
        if not self.vector_store_manager:
            return None
        try:
            rag_chunks = self.vector_store_manager.get_relevant_documents(
                query, k=3, use_mmr=True
            )
            if rag_chunks:
                return "\n".join(rag_chunks)
        except Exception as e:
            logger.warning(f"RAGコンテキスト取得に失敗: {e}")
        return None

    def _build_system_prompt(self, participant: ParticipantInfo, rag_context: Optional[str]) -> str:
        parts = [self._system_prompt_context]
        if rag_context:
            parts.append("関連資料の抜粋:\n" + rag_context)
        parts.extend([
            f"あなたは「{participant.persona}」という役割でこの会議に参加しています。",
            "提供された情報とこれまでの議論を踏まえ、あなたの意見や考察を述べてください。",
            "**最重要指示: あなたの全ての返答は、完璧に自然で流暢な日本語で記述されなければなりません。**",
            "**他の言語（英語など）の単語、フレーズ、または構文が誤って混入した場合は、最終的な返答を生成する前に、必ずそれらを完全に適切な日本語に修正してください。**",
            "**出力は100%日本語である必要があります。いかなる状況でも他の言語の要素を含めてはなりません。**",
        ])
        return "\n\n".join(parts)

    def _build_initial_context(
        self, user_query: str, document_summary: Optional[DocumentSummary]
    ) -> str:
        context_parts = [
            "これは複数のAIが参加するオンライン会議です。",
            "**重要: この会議は全て日本語で進行され、全ての参加者は日本語で発言します。**",
            "会議の主要な議題は次の通りです:",
            f"「{user_query}」"
        ]
        if document_summary and document_summary.summary:
            context_parts.extend([
                "\n関連資料の要約は以下の通りです (この要約も日本語です):",
                "--- 資料要約 START ---",
                document_summary.summary,
                "--- 資料要約 END ---",
            ])
        rag_context = self._get_rag_context(user_query)
        if rag_context:
            context_parts.extend([
                "\nアップロード資料から抽出された関連情報:",
                "--- RAGコンテキスト START ---",
                rag_context,
                "--- RAGコンテキスト END ---",
            ])
        if self.carry_over_context:
            context_parts.extend([
                "\n前回の会議からの持ち越し事項",
                self.carry_over_context,
            ])
        context_parts.append(
            "\n各参加者は、自身の専門性や割り当てられたペルソナに基づいて、建設的な意見交換を日本語で行ってください。"
        )
        return "\n".join(context_parts)

    def _build_statement_prompt(
        self, participant: ParticipantInfo, ai_specific_round_number: int
    ) -> str:
        prompt_parts = [
            f"現在の会議の状況です。あなたは「{participant.persona}」として、これがあなたの{ai_specific_round_number}回目の発言機会となります。",
            "これまでの議論全体（提供されていれば会話履歴を参照）、会議の議題、およびあなたの役割を踏まえて、意見、分析、または具体的な提案を述べてください。",
            "他の参加者の意見と単純に重複するのではなく、新しい視点、深い洞察、または具体的な解決策を提示することを重視してください。",
            "発言は、簡潔かつ論理的に、300文字から500文字程度でまとめてください。",
            "**繰り返しになりますが、あなたの発言は全て完璧な日本語でなければなりません。**"
        ]
        if len(self.state.conversation_history) > 3:
            recent_points_summary = self._summarize_recent_discussion_points_for_prompt(count=3)
            if recent_points_summary:
                 prompt_parts.insert(1, f"\n直近の議論のポイント(これも日本語です):\n{recent_points_summary}\n")
        return "\n".join(prompt_parts)

    def _prepare_conversation_history_for_api(self, limit: int = 10) -> List[Dict[str, str]]:
        actual_limit = limit if limit > 0 else self.app_config.conversation_history_limit
        api_history = []
        if actual_limit <= 0: return []

        history_to_process = self.state.conversation_history
        valid_entries = [e for e in history_to_process if "エラーにより発言できませんでした" not in e.content]
        start_index = max(0, len(valid_entries) - actual_limit)

        for entry in valid_entries[start_index:]:
            api_history.append({
                "role": "user",
                "content": f"[スピーカー: {entry.speaker} (役割: {entry.persona}), ラウンド {entry.round_number}の発言]: {entry.content}"
            })
        return api_history

    def _summarize_recent_discussion_points_for_prompt(self, count: int =3) -> str:
        if not self.state.conversation_history: return ""
        points = []
        for entry in self.state.conversation_history[-(count):]:
            if "エラーにより発言できませんでした" not in entry.content:
                content_summary = entry.content[:60].strip().replace('\n', ' ') # 改行をスペースに
                points.append(f"- {entry.speaker} (役割: {entry.persona}) は「{content_summary}...」と述べました。")
        return "\n".join(points) if points else ""

    async def _generate_final_summary(
        self, user_query: str, document_summary: Optional[DocumentSummary]
    ) -> str:
        if not self.moderator:
            logger.warning("最終要約: 司会者がいません。")
            return "（最終要約エラー: 司会者が設定されていません）"
        try:
            conversation_text = self._format_conversation_for_summary()
            if not conversation_text.strip() or conversation_text.startswith("（会議中に"):
                logger.warning("最終要約: 有効な会話ログがないため、要約をスキップします。")
                return "（会議中に有効な発言がなかったため、最終要約は生成されませんでした）"

            summary_user_prompt = self._build_summary_prompt(user_query, conversation_text, document_summary)
            summary_system_prompt_parts = [
                "あなたは熟練した会議ファシリテーターであり、エグゼクティブサマリーの作成が専門です。",
                "提供された会議の議題、参考資料（あれば）、および議論内容全体を注意深く分析し、",
                "指示された構成要素に従って、客観的かつ網羅的な最終要約をプロフェッショナルなトーンで作成してください。",
                "**最重要指示: 生成する最終要約は、完璧に自然で流暢な日本語で記述されなければなりません。**",
                "**他の言語（英語など）の単語、フレーズ、または構文が誤って混入した場合は、最終的な要約を生成する前に、必ずそれらを完全に適切な日本語に修正してください。**",
                "**出力は100%日本語である必要があります。いかなる状況でも他の言語の要素を含めてはなりません。**",
                "**最終要約の文章が途中で終わってしまうことを厳しく禁止します。必ず完結した内容で、全ての指示された構成要素を網羅するように記述してください。**"
            ]
            summary_system_prompt = "\n\n".join(summary_system_prompt_parts)
            logger.info(f"最終要約生成API呼び出し開始... プロンプト長(概算): {len(summary_user_prompt)}文字")

            summary_timeout = self.app_config.api_timeout_seconds_summary
            logger.info(f"最終要約生成時のタイムアウト設定: {summary_timeout}秒")

            raw_response = await self.moderator.client.request_completion(
                user_message=summary_user_prompt,
                system_message=summary_system_prompt,
                override_timeout=summary_timeout,
                override_max_tokens=self.app_config.summary_max_tokens
            )
            content, tokens_this_call = extract_content_and_tokens(
                self.moderator.model_info.provider, raw_response
            )
            self.state.add_tokens_used(tokens_this_call)

            corrected_content, correction_tokens = await self._ensure_japanese_output(
                content,
                self.moderator.client,
                self.moderator.model_info.provider,
                context_for_correction=(
                    "以下の会議の最終要約案を、完全に自然で流暢な日本語に修正してください。"
                    "元の要約の構造や意図をできる限り保ちつつ、他の言語の要素は一切含めないでください。"
                    "また、内容が途中で途切れている場合は、文脈を考慮して自然に完結させてください。"
                )
            )

            total_tokens_for_summary = tokens_this_call + correction_tokens
            logger.info(f"最終要約生成API呼び出し完了。消費トークン: {total_tokens_for_summary} (初期{tokens_this_call}, 修正{correction_tokens})")
            match = re.search(r"## 4\. 未解決の課題と今後の検討事項\s*\n(.*?)(?=\n##|\Z)", corrected_content, re.DOTALL)
            if match:
                unresolved_issues = match.group(1).strip()
                save_carry_over(user_query, unresolved_issues)
            return corrected_content

        except Exception as e:
            self._report_error(f"最終要約生成中にエラー: {e}", exc_info=True)
            return f"（最終要約生成エラー: {type(e).__name__} が発生しました。詳細はログを確認してください。）"

    def _format_conversation_for_summary(self) -> str:
        formatted_lines = []
        if not self.state.conversation_history: return "（会議中に発言はありませんでした）"

        max_tokens = self.app_config.summary_conversation_log_max_tokens
        current_tokens = 0
        log_to_process = []

        reversed_valid_entries = [
            e for e in reversed(self.state.conversation_history)
            if "エラーにより発言できませんでした" not in e.content
        ]

        if not reversed_valid_entries: return "（会議中に有効な発言はありませんでした）"

        for entry in reversed_valid_entries:
            # entry.content内の改行をMarkdownの改行（スペース2つ + \n）に置換
            # バックスラッシュをf-stringの外で処理
            content_for_markdown = entry.content.replace('\n', '  \n')
            entry_text = f"- **ラウンド {entry.round_number}, {entry.speaker} (役割: {entry.persona}):**\n  {content_for_markdown}\n"
            model_name = self.moderator.model_info.name if self.moderator else "gpt-3.5-turbo"
            entry_tokens = count_tokens(entry_text, model_name)
            if max_tokens > 0 and current_tokens + entry_tokens > max_tokens and log_to_process:
                log_to_process.insert(0, "... (これより前の会話は、要約生成のトークン数制限のため省略されています) ...\n")
                break
            log_to_process.insert(0, entry_text)
            current_tokens += entry_tokens

        if not log_to_process: return "（会議中に有効な発言はありませんでした）"

        return "\n".join(log_to_process)


    def _build_summary_prompt(
        self, user_query: str, conversation_text: str, document_summary: Optional[DocumentSummary]
    ) -> str:
        prompt_parts = [
            "## 会議の最終要約作成指示\n",
            "あなたは、以下の情報に基づいて、この会議の包括的かつ実行可能な最終要約を**完璧な日本語で**作成する任務を負っています。\n",
            "### 1. 会議の主要な議題・問い (日本語)\n",
            f"「{user_query}」\n"
        ]
        if document_summary and document_summary.summary:
            prompt_parts.extend([
                "### 2. 会議前に共有された参考資料の要点 (日本語)\n",
                "--- 資料要約 START ---",
                document_summary.summary,
                "--- 資料要約 END ---\n",
            ])
        prompt_parts.extend([
            "### 3. 会議での主な議論内容（日本語での発言ログからの抜粋）\n",
            "--- 発言ログ START ---",
            conversation_text if conversation_text.strip() else "（特筆すべき発言はありませんでした）",
            "--- 発言ログ END ---\n",
            "### 4. 作成する最終要約に含めるべき構成要素 (全て日本語で記述)\n",
            "以下の各項目について、具体的かつ明確に記述し、会議の成果が明確に伝わるようにしてください。\n",
            "  - **A. 主要な論点と到達した結論:** 議論の中心となったトピックと、それらについてどのような結論（合意、見解の一致・不一致、方向性など）に至ったかを整理してください。",
            "  - **B. 特筆すべき意見や提案:** 会議中に出された特に重要、革新的、または注目に値する意見、アイデア、提案をピックアップしてください。",
            "  - **C. 正式な決定事項（あれば）:** 会議の結果として公式に決定された事項があれば記載してください。",
            "  - **D. 未解決の課題や今後の検討事項:** 議論の中で解決しなかった点、さらなる情報収集や検討が必要となった事項をリストアップしてください。",
            "  - **E. 推奨されるアクションアイテム:** 会議の結果を踏まえ、次に取るべき具体的な行動やステップがあれば提案してください（誰が、何を、いつまでに行うかなど）。",
            "\n### 5. 要約のスタイルと品質 (全て日本語で)\n",
            "- 記述はプロフェッショナルかつ客観的なトーンを維持し、**完全に自然な日本語で記述してください。**",
            "- 箇条書き、太字、小見出し（例: 上記A～E）を効果的に使用し、情報を構造化して提示してください。",
            "- 全体として800～2000文字程度を目安としますが、内容の質と網羅性を最優先してください。",
            "- **最重要: 生成する最終要約は、100%完璧な日本語でなければなりません。英語や他の言語の単語・フレーズ・構文が誤って混入した場合は、最終的な出力をする前に必ずそれらを適切な日本語に修正してください。いかなる状況でも他の言語の要素を含めてはなりません。**",
            "- **厳守事項: 文章は途中で終わらず、意味と文脈を考慮して会議の結論として明確に理解できる内容で終了させてください。文章の途中で終わることは絶対に禁止します。全ての構成要素を網羅し、完結した要約を作成してください。**"
        ])
        final_prompt = "\n".join(prompt_parts)
        if self.app_config.prompt_max_length_warning_threshold > 0 and \
           len(final_prompt) > self.app_config.prompt_max_length_warning_threshold:
            logger.warning(
                f"最終要約プロンプトが設定された閾値({self.app_config.prompt_max_length_warning_threshold}文字)を超えています "
                f"({len(final_prompt)}文字)。トークン制限や処理時間に影響する可能性があります。"
            )
        return final_prompt

    def get_meeting_statistics(self) -> Dict[str, Any]:
        return {
            "participants_count": len(self.participants),
            "total_statements_made": sum(p.total_statements for p in self.participants.values()),
            "conversation_log_length": len(self.state.conversation_history),
            "current_phase": self.state.phase,
            "error_message": self.state.error_message,
        }

    def clear_meeting_state(self):
        self.participants.clear()
        self.moderator = None
        self.state = MeetingState()
        logger.info("会議マネージャーの内部状態（参加者、司会者、会議状態）をクリアしました。")
