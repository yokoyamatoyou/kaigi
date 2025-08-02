import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

import flet as ft

# 独自モジュール
from core.models import (
    ModelInfo, MeetingSettings, MeetingResult, ConversationEntry,
    AIProvider, AppConfig
)
from core.config_manager import get_config_manager
from core.meeting_manager import MeetingManager
from core.utils import format_duration, format_timestamp, sanitize_filename
from core.context_manager import ContextManager

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MultiAIResearchApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.config_manager = get_config_manager()
        self.context_manager = ContextManager()
        self.meeting_manager = MeetingManager()
        self.file_picker = ft.FilePicker(on_result=self._on_file_picked)

        self.participant_models: List[ModelInfo] = []
        self.moderator_model: Optional[ModelInfo] = None
        self.uploaded_file_path: Optional[str] = None
        self.current_meeting_result: Optional[MeetingResult] = None

        self._init_ui_components()
        self._setup_page()
        self._build_layout()
        logger.info("MultiAIResearchApp 初期化完了")

    def _setup_page(self):
        self.page.title = self.config_manager.config.window_title
        self.page.window_width = self.config_manager.config.window_width
        self.page.window_height = self.config_manager.config.window_height
        self.page.window_min_width = 800
        self.page.window_min_height = 700
        self.page.theme_mode = ft.ThemeMode.LIGHT # または "light"
        self.page.scroll = ft.ScrollMode.ADAPTIVE
        self.page.overlay.append(self.file_picker)

    def _init_ui_components(self):
        self.api_status_text = ft.Text("APIキー確認中...", size=14)
        self.model_name_field = ft.TextField(
            label="参加AIモデル名 (例: gpt-3.5-turbo)",
            hint_text="モデル名を入力",
            width=300
        )
        self.add_model_button = ft.IconButton(
            icon="add",
            tooltip="モデル追加",
            on_click=self._add_model
        )
        self.models_list = ft.Column(scroll=ft.ScrollMode.ADAPTIVE, height=200)

        self.moderator_dropdown = ft.Dropdown(
            label="司会モデル",
            hint_text="司会を担当するモデルを選択",
            width=300,
            options=[]
        )
        self.rounds_field = ft.TextField(
            label="各AIの発言回数",
            value=str(self.config_manager.config.default_rounds_per_ai),
            width=150,
            input_filter=ft.InputFilter(allow=True, regex_string=r"[0-9]")
        )
        self.query_field = ft.TextField(
            label="質問/指示",
            hint_text="AIに議論してもらいたい内容を入力",
            multiline=True,
            min_lines=3,
            max_lines=5,
            expand=True
        )
        self.upload_button = ft.ElevatedButton(
            text="資料ファイルを選択",
            icon="upload_file",
            on_click=self._on_upload_clicked
        )
        self.file_status_text = ft.Text("ファイルが選択されていません", size=12)

        # デフォルトで「なし」を選択肢に追加（持ち越し事項を読み込まない場合）
        carry_over_options = [ft.dropdown.Option(key="none", text="なし")]
        for ctx in self.context_manager.list_carry_overs():
            carry_over_options.append(
                ft.dropdown.Option(key=ctx["id"], text=ctx["display_name"])
            )
        self.carry_over_dropdown = ft.Dropdown(
            label="前回の持ち越し事項を読み込む",
            options=carry_over_options,
            value="none",
        )

        self.start_button = ft.ElevatedButton(
            text="会議開始",
            icon="play_arrow",
            on_click=self._start_meeting,
            style=ft.ButtonStyle(bgcolor="primary", color="white") # 文字列で指定
        )
        self.progress_ring = ft.ProgressRing(visible=False)
        self.progress_text = ft.Text("", size=12)

        self.conversation_list = ft.ListView(
            expand=False, height=250, spacing=10,
            padding=ft.padding.all(10), auto_scroll=True
        )
        self.result_text = ft.TextField(
            label="最終結果", value="", multiline=True,
            read_only=True, expand=True, min_lines=5
        )
        self.save_conversation_button = ft.ElevatedButton(
            text="会話内容を保存", icon="save",
            on_click=self._save_conversation,
            disabled=True
        )
        self.save_result_button = ft.ElevatedButton(
            text="結果を保存", icon="save_alt",
            on_click=self._save_result,
            disabled=True
        )

    def _build_layout(self):
        settings_column = ft.Column([
            ft.Text("設定", size=18, weight=ft.FontWeight.BOLD),
            ft.Row([ft.Icon("key"), self.api_status_text]),
            ft.Divider(height=10),
            ft.Text("参加AIモデル", size=16, weight=ft.FontWeight.W_500),
            ft.Row([self.model_name_field, self.add_model_button]),
            self.models_list,
            ft.Divider(height=10),
            self.moderator_dropdown,
            ft.Divider(height=10),
            ft.Text("質問/指示", size=16, weight=ft.FontWeight.W_500),
            self.query_field,
            ft.Divider(height=10),
            ft.Row([
                ft.Column([
                    ft.Text("資料ファイル", size=16, weight=ft.FontWeight.W_500),
                    self.upload_button, self.file_status_text,
                ], expand=True),
                ft.Column([self.rounds_field,], width=170),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(height=20),
            self.carry_over_dropdown,
            ft.Row([
                self.start_button, self.progress_ring, self.progress_text
            ], alignment=ft.MainAxisAlignment.START)
        ], scroll=ft.ScrollMode.ADAPTIVE)

        settings_area = ft.Container(
            content=settings_column, padding=ft.padding.all(15),
            bgcolor="surfacevariant", border_radius=10, # 文字列で指定 (Fletが認識する名前)
        )
        conversation_area = ft.Container(
            content=ft.Column([
                ft.Text("会話内容", size=18, weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=self.conversation_list, border=ft.border.all(1, "outline"), # 文字列で指定
                    border_radius=5, padding=ft.padding.all(5)
                )
            ], tight=True), padding=ft.padding.all(15),
        )
        result_area = ft.Container(
            content=ft.Column([
                ft.Text("最終結果", size=18, weight=ft.FontWeight.BOLD),
                self.result_text,
                ft.Row([
                    self.save_conversation_button, self.save_result_button
                ], alignment=ft.MainAxisAlignment.CENTER)
            ]), padding=ft.padding.all(15), expand=True
        )
        main_content = ft.Row([
            ft.Container(content=settings_area, width=420, expand=False),
            ft.Container(
                content=ft.Column([conversation_area, result_area], expand=True, spacing=10),
                expand=True
            )
        ], expand=True, vertical_alignment=ft.CrossAxisAlignment.START)

        self.page.add(main_content)
        self._update_api_status() # 初期表示のためにAPIステータス更新
        # self.page.update() # _build_layout の最後やaddの後には通常不要

    def _update_api_status(self):
        status_parts = []
        api_validation = self.config_manager.validate_api_keys()
        for provider, is_configured in api_validation.items():
            status_icon = "✅" if is_configured else "❌"
            status_parts.append(f"{status_icon} {provider.value}")
        self.api_status_text.value = " | ".join(status_parts)
        if self.api_status_text.page:
            self.api_status_text.update()
        else:
            logger.warning("api_status_text is not on the page, cannot update.")

    async def _add_model(self, e):
        model_name = self.model_name_field.value.strip()
        if not model_name:
            self._show_snack_bar("モデル名を入力してください")
            return
        provider = self._detect_provider(model_name)
        if not provider:
            self._show_snack_bar(f"サポートされていないか、不明なモデルです: {model_name}")
            return
        if not self.config_manager.is_api_key_configured(provider):
            self._show_snack_bar(f"{provider.value} のAPIキーが設定されていません")
            return
        if any(model.name == model_name for model in self.participant_models):
            self._show_snack_bar("既に追加されているモデルです")
            return
        if len(self.participant_models) >= 5: # 上限チェック
            self._show_snack_bar("参加モデルは最大5つまでです")
            return

        model_info = ModelInfo(
            name=model_name, provider=provider,
            temperature=self.config_manager.config.default_temperature,
            max_tokens=self.config_manager.config.default_max_tokens
        )
        self.participant_models.append(model_info)
        self._update_models_list() # リストUI更新
        self._update_moderator_options() # 司会者ドロップダウン更新
        self.model_name_field.value = ""
        self.model_name_field.focus()
        # self.model_name_field.update() # page.update() でまとめて更新
        self._show_snack_bar(f"{model_name} を追加しました")
        self.page.update()

    def _detect_provider(self, model_name: str) -> Optional[AIProvider]:
        model_lower = model_name.lower()
        if any(p_keyword in model_lower for p_keyword in ["gpt", "openai"]):
            return AIProvider.OPENAI
        elif any(p_keyword in model_lower for p_keyword in ["claude", "anthropic"]):
            return AIProvider.CLAUDE
        elif any(p_keyword in model_lower for p_keyword in ["gemini", "google"]):
            return AIProvider.GEMINI
        return None

    def _update_models_list(self):
        self.models_list.controls.clear()
        for i, model in enumerate(self.participant_models):
            model_card = ft.Card(ft.Container(ft.Column([
                ft.Row([
                    ft.Text(f"{model.name} ({model.provider.value})", weight=ft.FontWeight.BOLD, expand=True),
                    ft.IconButton(
                        icon="delete", tooltip="削除", data=i,
                        on_click=self._on_remove_model_clicked,
                        icon_size=18, style=ft.ButtonStyle(padding=ft.padding.all(5))
                    )
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.TextField(
                    label="ペルソナ", value=model.persona, multiline=True, min_lines=1, max_lines=2,
                    data=i, on_change=self._on_persona_changed, dense=True
                ),
                ft.Text("温度:", size=12, weight=ft.FontWeight.W_500),
                ft.Slider(
                    value=model.temperature, min=0, max=2, divisions=20, data=i,
                    on_change=self._on_temperature_changed,
                )
            ]), padding=ft.padding.all(8)))
            self.models_list.controls.append(model_card)
        self.models_list.update() # モデルリスト個別の更新

    def _on_remove_model_clicked(self, e: ft.ControlEvent):
        index_to_remove = e.control.data
        self._remove_model(index_to_remove) # 内部で page.update() は不要
        self.page.update() # ここでUI全体を更新

    def _on_persona_changed(self, e: ft.ControlEvent):
        index_to_update = e.control.data
        new_persona = e.control.value
        self._update_persona(index_to_update, new_persona)
        # 必要に応じて self.page.update()

    def _on_temperature_changed(self, e: ft.ControlEvent):
        index_to_update = e.control.data
        new_temperature = e.control.value
        self._update_temperature(index_to_update, new_temperature)
        # 必要に応じて self.page.update()

    def _remove_model(self, index: int):
        if 0 <= index < len(self.participant_models):
            removed_model = self.participant_models.pop(index)
            self._update_models_list()
            self._update_moderator_options()
            if not self.participant_models:
                self.moderator_dropdown.value = None
                self.moderator_dropdown.update() # Dropdownが空になったことを反映
            self._show_snack_bar(f"{removed_model.name} を削除しました")
            # page.update() は呼び出し元で行う

    def _update_persona(self, index: int, persona: str):
        if 0 <= index < len(self.participant_models):
            self.participant_models[index].persona = persona

    def _update_temperature(self, index: int, temperature: float):
        if 0 <= index < len(self.participant_models):
            self.participant_models[index].temperature = round(temperature, 2)

    def _update_moderator_options(self):
        current_moderator_name = self.moderator_dropdown.value
        self.moderator_dropdown.options.clear()
        new_options = []
        selected_value_still_exists = False
        for model in self.participant_models:
            option = ft.dropdown.Option(key=model.name, text=f"{model.name} ({model.provider.value})")
            new_options.append(option)
            if model.name == current_moderator_name:
                selected_value_still_exists = True
        self.moderator_dropdown.options = new_options
        if self.participant_models:
            if selected_value_still_exists and current_moderator_name:
                self.moderator_dropdown.value = current_moderator_name
            elif self.moderator_dropdown.options:
                self.moderator_dropdown.value = self.moderator_dropdown.options[0].key
            else:
                self.moderator_dropdown.value = None
        else:
            self.moderator_dropdown.value = None
        self.moderator_dropdown.update()

    def _on_upload_clicked(self, e): # async は不要
        logger.info("Upload button clicked. Opening file picker...")
        self.file_picker.pick_files( # pick_files_async から変更
            dialog_title="資料ファイルを選択",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["docx", "pdf", "txt"],
            allow_multiple=False
        )
        # self.page.update() # ダイアログ表示トリガーのための即時更新は必ずしも必要ない場合がある

    async def _on_file_picked(self, e: ft.FilePickerResultEvent):
        logger.info(f"File picked result: {e.files}")
        if e.files and e.files[0] and e.files[0].path: # e.files[0] の存在も確認
            file_result = e.files[0]
            self.uploaded_file_path = file_result.path
            file_size_kb = file_result.size / 1024 if file_result.size is not None else 0.0
            self.file_status_text.value = f"選択: {Path(file_result.name).name} ({file_size_kb:.1f}KB)"
            self.file_status_text.color = "green" # 文字列で指定
            logger.info(f"File selected: {self.uploaded_file_path}")
        else:
            self.uploaded_file_path = None
            self.file_status_text.value = "ファイルが選択されていません"
            self.file_status_text.color = None
            if e.files and e.files[0] and not e.files[0].path: # ファイルは選択されたがパスがない場合
                logger.warning("File picked, but path is None.")
                self._show_snack_bar("ファイルのパス取得に失敗しました。", error=True)
            elif not e.files: # ファイル選択がキャンセルされた場合
                 logger.info("File selection cancelled.")
            else: # その他の予期せぬケース
                 logger.warning(f"File selection failed or unexpected result: {e.files}")

        self.file_status_text.update()
        self.page.update()

    async def _start_meeting(self, e):
        logger.info("会議開始ボタンクリック。UI準備中...")
        # ... (バリデーションは変更なし) ...
        if not self.participant_models: self._show_snack_bar("参加モデルを1つ以上追加してください"); return
        moderator_name_selected = self.moderator_dropdown.value
        if not moderator_name_selected: self._show_snack_bar("司会モデルを選択してください"); return
        if not self.query_field.value.strip(): self._show_snack_bar("質問/指示を入力してください"); return

        self._set_ui_processing(True)
        self.result_text.value = ""
        self.conversation_list.controls.clear() # 会話ログクリア
        self.current_meeting_result = None
        
        # 保存ボタンは会議開始時に無効化、finallyで状態更新
        self.save_conversation_button.disabled = True
        self.save_result_button.disabled = True
        # self.save_conversation_button.update() # _set_ui_processing内のpage.updateでまとめて
        # self.save_result_button.update()
        # self.result_text.update()
        # self.conversation_list.update()
        
        logger.info("会議設定の準備中...")
        result_from_manager: Optional[MeetingResult] = None
        carry_over_context = None
        selected_context_id = self.carry_over_dropdown.value
        if selected_context_id and selected_context_id != "none":
            carry_over_context = self.context_manager.load_carry_over(selected_context_id)

        try:
            moderator_model_info = next((m for m in self.participant_models if m.name == moderator_name_selected), None)
            if not moderator_model_info:
                self._show_snack_bar(f"エラー: 選択された司会モデル '{moderator_name_selected}' が参加者リストに見つかりません。")
                # finally は実行されるが、UI処理状態は戻しておく
                self._set_ui_processing(False)
                return

            settings = MeetingSettings(
                participant_models=[m.model_copy(deep=True) for m in self.participant_models],
                moderator_model=moderator_model_info.model_copy(deep=True),
                rounds_per_ai=int(self.rounds_field.value or self.config_manager.config.default_rounds_per_ai),
                user_query=self.query_field.value.strip(),
                document_path=self.uploaded_file_path
            )
            self.meeting_manager = MeetingManager(carry_over_context=carry_over_context)
            self.meeting_manager.on_statement_added = self._on_statement_added
            self.meeting_manager.on_phase_changed = self._on_phase_changed

            logger.info("MeetingManager.run_meeting を呼び出します...")
            result_from_manager = await self.meeting_manager.run_meeting(settings, progress_callback=self._on_progress_update)
            
            if result_from_manager:
                logger.info(f"会議結果受け取り成功。要約冒頭: '{result_from_manager.final_summary[:50] if result_from_manager.final_summary else 'N/A'}'")
                self.current_meeting_result = result_from_manager
                self.result_text.value = result_from_manager.final_summary or "最終要約がありません。"
            else:
                logger.error("MeetingManager.run_meeting から None が返されました。")
                self.result_text.value = "会議の実行に失敗しました (結果オブジェクトなし)。"
                self._show_snack_bar("会議エラー: 結果を取得できませんでした。", error=True)

        except Exception as ex:
            logger.error(f"会議実行中に予期せぬ例外が発生: {ex}", exc_info=True)
            self.result_text.value = f"会議中に致命的なエラーが発生しました: {str(ex)}"
            self.current_meeting_result = None
            self._show_snack_bar(f"会議実行エラー: {str(ex)}", error=True)
        finally:
            logger.info("会議処理の finally ブロック開始。UI状態を更新します。")
            self._set_ui_processing(False) 
            # self.result_text.update() # _set_ui_processing内のpage.updateでまとめて

            can_save_conversation = False
            can_save_result = False

            if self.current_meeting_result:
                logger.info("current_meeting_result が存在します。保存ボタンの有効性を評価します。")
                logger.info(f"DEBUG: current_meeting_result.conversation_log is not None: {self.current_meeting_result.conversation_log is not None}")
                if self.current_meeting_result.conversation_log:
                    logger.info(f"DEBUG: len(current_meeting_result.conversation_log): {len(self.current_meeting_result.conversation_log)}")
                    can_save_conversation = True
                else:
                    logger.info("会話ログが空です。会話保存ボタンは無効のままです。")

                logger.info(f"DEBUG: current_meeting_result.final_summary: '{self.current_meeting_result.final_summary[:50] if self.current_meeting_result.final_summary else 'None or Empty'}'")
                if self.current_meeting_result.final_summary and self.current_meeting_result.final_summary.strip():
                    can_save_result = True
                else:
                    logger.info("最終要約が空またはNoneです。結果保存ボタンは無効のままです。")
                
                if (not self.result_text.value.startswith("会議中に致命的なエラー")) and \
                   (not self.result_text.value.startswith("会議の実行に失敗しました")) and \
                   can_save_result: # 正常に要約が取れた場合のみ完了メッセージ
                    self._show_snack_bar(
                        f"会議完了！所要時間: {format_duration(self.current_meeting_result.duration_seconds)}, "
                        f"使用トークン: {self.current_meeting_result.total_tokens_used}"
                    )
            else:
                logger.info("current_meeting_result が None のため、保存ボタンは無効のままです。")

            self.save_conversation_button.disabled = not can_save_conversation
            self.save_result_button.disabled = not can_save_result
            
            logger.info(f"DEBUG: Save Conversation Button - Disabled: {self.save_conversation_button.disabled}, Visible: {self.save_conversation_button.visible if hasattr(self.save_conversation_button, 'visible') else 'N/A'}")
            logger.info(f"DEBUG: Save Result Button - Disabled: {self.save_result_button.disabled}, Visible: {self.save_result_button.visible if hasattr(self.save_result_button, 'visible') else 'N/A'}")

            self.save_conversation_button.update()
            self.save_result_button.update()
            # self.page.update() # _set_ui_processingで呼ばれるので必須ではないが、ボタン状態更新のため明示しても良い
            logger.info("会議処理の finally ブロック完了。")

    def _set_ui_processing(self, processing: bool):
        self.start_button.disabled = processing
        self.query_field.disabled = processing
        self.upload_button.disabled = processing
        self.model_name_field.disabled = processing
        self.add_model_button.disabled = processing
        self.moderator_dropdown.disabled = processing
        self.rounds_field.disabled = processing
        
        for ctrl in self.models_list.controls:
            if isinstance(ctrl, ft.Card) and ctrl.content:
                if hasattr(ctrl.content, 'controls'): # Container -> Column
                    for item_in_col in ctrl.content.controls:
                        if isinstance(item_in_col, ft.Row) and hasattr(item_in_col, 'controls'):
                            for sub_item in item_in_col.controls: # Row -> Text, IconButton
                                if hasattr(sub_item, 'disabled'):
                                    sub_item.disabled = processing
                        elif hasattr(item_in_col, 'disabled'): # Column -> TextField, Text, Slider
                            item_in_col.disabled = processing
        
        self.progress_ring.visible = processing
        self.progress_text.value = "会議を開始しています..." if processing else ""
        
        self.page.update() # 最後にまとめてページ全体を更新

    def _on_statement_added(self, entry: ConversationEntry):
        statement_card = ft.Card(ft.Container(ft.Column([
            ft.Row([
                ft.Text(f"{entry.speaker}", weight=ft.FontWeight.BOLD, color="primary"), # 文字列指定
                ft.Text(f"({entry.persona})", size=12, color="outline", italic=True), # 文字列指定
                ft.Text(f"Round {entry.round_number}", size=10, color="outline") # 文字列指定
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Markdown(
                entry.content, selectable=True,
                extension_set=ft.MarkdownExtensionSet.COMMON_MARK,
            ),
            ft.Text(format_timestamp(entry.timestamp), size=10, color="outline", text_align=ft.TextAlign.RIGHT) # 文字列指定
        ]), padding=ft.padding.all(10)))
        self.conversation_list.controls.append(statement_card)
        self.conversation_list.update()
        # self.page.update() # ListViewの更新は個別のupdateで十分な場合が多い

    def _on_phase_changed(self, phase: str):
        phase_messages = {
            "initializing_participants": "参加者を初期化中...",
            "processing_document": "資料を処理中...",
            "discussing": "議論を進行中...",
            "summarizing": "最終要約を生成中...",
            "completed": "会議完了",
            "error": "エラーが発生しました"
        }
        message = phase_messages.get(phase, f"フェーズ: {phase}")
        self.progress_text.value = message
        self.progress_text.update()

    def _on_progress_update(self, phase_detail: str, current: int, total: int):
        if phase_detail == "discussing_round":
            self.progress_text.value = f"議論中 - ラウンド {current}/{total}"
        elif phase_detail == "discussing_statement":
             self.progress_text.value = f"議論中 - {current}/{total} 発言目"
        elif phase_detail == "moderator_summary":
             self.progress_text.value = f"司会要約作成中 ({current}/{total})"
        self.progress_text.update()

    # --- _save_conversation (デバッグログ付き) ---
    async def _save_conversation(self, e):
        logger.info(">>> _save_conversation: Method called.")
        if not self.current_meeting_result:
            self._show_snack_bar("保存する会話内容がありません (結果オブジェクトなし)", error=True)
            logger.warning(">>> _save_conversation: Aborted - current_meeting_result is None.")
            return
        logger.info(f">>> _save_conversation: current_meeting_result type: {type(self.current_meeting_result)}")
        logger.info(f">>> _save_conversation: hasattr(settings): {hasattr(self.current_meeting_result, 'settings')}")
        if hasattr(self.current_meeting_result, 'settings') and self.current_meeting_result.settings:
            logger.info(f">>> _save_conversation: settings.user_query: {self.current_meeting_result.settings.user_query[:50] if self.current_meeting_result.settings.user_query else 'N/A'}")
        
        if not self.current_meeting_result.conversation_log:
            self._show_snack_bar("保存する会話ログがありません (ログ空)", error=True)
            logger.warning(">>> _save_conversation: Aborted - conversation_log is empty or None.")
            return
        logger.info(f">>> _save_conversation: Conversation log count: {len(self.current_meeting_result.conversation_log)}")
        
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        query_for_filename = "unknown_query"
        try:
            if hasattr(self.current_meeting_result, 'settings') and self.current_meeting_result.settings and \
               hasattr(self.current_meeting_result.settings, 'user_query') and self.current_meeting_result.settings.user_query:
                query_for_filename = self.current_meeting_result.settings.user_query[:30]
            elif self.query_field.value.strip():
                query_for_filename = self.query_field.value.strip()[:30]
            logger.info(f">>> _save_conversation: Query for filename: '{query_for_filename}'")
        except Exception as ex_fn:
            logger.error(f">>> _save_conversation: Error getting query for filename: {ex_fn}", exc_info=True)
            # ファイル名取得でエラーがあってもデフォルト名で続行
            
        filename_base = sanitize_filename(query_for_filename or "conversation")
        filename = f"{filename_base}_{timestamp_str}.md"
        logger.info(f">>> _save_conversation: Attempting to save to filename: {filename}")
        
        lines = []
        lines.append(f"# マルチAI会議 会話ログ - {format_timestamp(datetime.now())}")
        if hasattr(self.current_meeting_result, 'settings') and self.current_meeting_result.settings:
            settings_data = self.current_meeting_result.settings
            if hasattr(settings_data, 'user_query'): lines.append(f"- **質問/指示:** {settings_data.user_query}")
            if hasattr(settings_data, 'document_path') and settings_data.document_path: lines.append(f"- **資料ファイル:** {Path(settings_data.document_path).name}")
        else: logger.warning(">>> _save_conversation: MeetingResult.settings is missing.")
        if hasattr(self.current_meeting_result, 'participants_count'): lines.append(f"- **参加者数:** {self.current_meeting_result.participants_count}")
        if hasattr(self.current_meeting_result, 'duration_seconds'): lines.append(f"- **所要時間:** {format_duration(self.current_meeting_result.duration_seconds)}")
        if hasattr(self.current_meeting_result, 'total_tokens_used'): lines.append(f"- **使用トークン:** {self.current_meeting_result.total_tokens_used}")
        lines.append("\n## 会話内容\n")
        for entry in self.current_meeting_result.conversation_log:
            speaker = getattr(entry, 'speaker', "不明な発言者")
            persona = getattr(entry, 'persona', "不明なペルソナ")
            model_name = getattr(entry, 'model_name', "不明なモデル")
            round_num = getattr(entry, 'round_number', "N/A")
            timestamp = getattr(entry, 'timestamp', datetime.now())
            content = getattr(entry, 'content', "[内容なし]")
            lines.append(f"### [{format_timestamp(timestamp)}] Round {round_num} - {speaker} (ペルソナ: {persona}, モデル: {model_name})\n")
            content_for_md = content.replace('\n', '  \n')
            lines.append(f"{content_for_md}\n")
            lines.append("---\n")
            
        logger.info(">>> _save_conversation: Markdown content generated. Attempting to write file...")
        try:
            save_dir = Path("saved_conversations")
            save_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f">>> _save_conversation: Save directory: {save_dir.resolve()}")
            file_path = save_dir / filename
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            self._show_snack_bar(f"会話内容を保存しました: {file_path}")
            logger.info(f">>> _save_conversation: Successfully saved conversation to: {file_path}")
        except Exception as ex:
            self._show_snack_bar(f"会話内容の保存エラー: {str(ex)}", error=True)
            logger.error(f">>> _save_conversation: Error saving conversation: {ex}", exc_info=True)
    # --- ここまで _save_conversation ---

    # --- _save_result (デバッグログ付き) ---
    async def _save_result(self, e):
        logger.info(">>> _save_result: Method called.")
        if not self.current_meeting_result:
            self._show_snack_bar("保存する結果がありません (結果オブジェクトなし)", error=True)
            logger.warning(">>> _save_result: Aborted - current_meeting_result is None.")
            return
        logger.info(f">>> _save_result: current_meeting_result type: {type(self.current_meeting_result)}")
        logger.info(f">>> _save_result: hasattr(settings): {hasattr(self.current_meeting_result, 'settings')}")
        
        final_summary_to_save = ""
        if hasattr(self.current_meeting_result, 'final_summary') and self.current_meeting_result.final_summary:
            final_summary_to_save = self.current_meeting_result.final_summary.strip()
            
        logger.info(f">>> _save_result: Final summary to save (first 50 chars): '{final_summary_to_save[:50]}'")
        if not final_summary_to_save:
            self._show_snack_bar("保存する最終要約がありません (要約空)", error=True)
            logger.warning(">>> _save_result: Aborted - final_summary_to_save is empty.")
            return
            
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        query_for_filename = "unknown_query"
        try:
            if hasattr(self.current_meeting_result, 'settings') and self.current_meeting_result.settings and \
               hasattr(self.current_meeting_result.settings, 'user_query') and self.current_meeting_result.settings.user_query:
                query_for_filename = self.current_meeting_result.settings.user_query[:30]
            elif self.query_field.value.strip():
                query_for_filename = self.query_field.value.strip()[:30]
            logger.info(f">>> _save_result: Query for filename: '{query_for_filename}'")
        except Exception as ex_fn:
            logger.error(f">>> _save_result: Error getting query for filename: {ex_fn}", exc_info=True)
            
        filename_base = sanitize_filename(query_for_filename or "meeting_result")
        filename = f"{filename_base}_{timestamp_str}.md"
        logger.info(f">>> _save_result: Attempting to save to filename: {filename}")
        
        lines = []
        lines.append(f"# マルチAI会議 最終結果 - {format_timestamp(datetime.now())}")
        if hasattr(self.current_meeting_result, 'settings') and self.current_meeting_result.settings:
            settings_data = self.current_meeting_result.settings
            if hasattr(settings_data, 'user_query'): lines.append(f"- **質問/指示:** {settings_data.user_query}")
            if hasattr(settings_data, 'document_path') and settings_data.document_path: lines.append(f"- **資料ファイル:** {Path(settings_data.document_path).name}")
        else: logger.warning(">>> _save_result: MeetingResult.settings is missing.")
        if hasattr(self.current_meeting_result, 'duration_seconds'): lines.append(f"- **所要時間:** {format_duration(self.current_meeting_result.duration_seconds)}")
        if hasattr(self.current_meeting_result, 'total_tokens_used'): lines.append(f"- **使用トークン:** {self.current_meeting_result.total_tokens_used}")
        lines.append("\n## 【最終要約】\n")
        lines.append(final_summary_to_save)
        
        logger.info(">>> _save_result: Markdown content generated. Attempting to write file...")
        try:
            save_dir = Path("saved_results")
            save_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f">>> _save_result: Save directory: {save_dir.resolve()}")
            file_path = save_dir / filename
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            self._show_snack_bar(f"結果を保存しました: {file_path}")
            logger.info(f">>> _save_result: Successfully saved result to: {file_path}")
        except Exception as ex:
            self._show_snack_bar(f"結果の保存エラー: {str(ex)}", error=True)
            logger.error(f">>> _save_result: Error saving result: {ex}", exc_info=True)
    # --- ここまで _save_result ---

    def _show_snack_bar(self, message: str, error: bool = False):
        if not self.page:
            logger.warning(f"SnackBar表示スキップ (pageなし): {message}")
            return
            
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(message),
            open=True,
            bgcolor="error" if error else None # 文字列で指定
        )
        try:
            self.page.update()
        except Exception as e: # FletがPageオブジェクトを内部で再利用するケースなどでエラーになることがある
            logger.error(f"SnackBar表示中のpage.update()でエラー: {e}", exc_info=True)

async def main(page: ft.Page):
    app = MultiAIResearchApp(page)

if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")
