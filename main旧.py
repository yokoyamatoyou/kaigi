import sys
import os
# sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))) # 通常は不要

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

import flet as ft

# --- ロギング設定 ---
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(name)s - %(funcName)s - %(lineno)d - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("app_debug.log", encoding="utf-8", mode="w")
    ]
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("flet_core").setLevel(logging.INFO)
logging.getLogger("flet_runtime").setLevel(logging.INFO)
# --- ここまでロギング設定 ---

logger = logging.getLogger(__name__) # main.py 用のロガー

# 独自モジュール
from core.models import (
    ModelInfo, MeetingSettings, MeetingResult, ConversationEntry,
    AIProvider, AppConfig # AppConfig をインポート
)
from core.config_manager import get_config_manager
from core.meeting_manager import MeetingManager
from core.utils import format_duration, format_timestamp, sanitize_filename
# from core.client_factory import ClientFactory # MeetingManagerが内部で使うので直接は不要かも


class MultiAIResearchApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.config_manager = get_config_manager()
        # AppConfigインスタンスを取得して保持 (MeetingManagerなどに渡すため)
        self.app_config: AppConfig = self.config_manager.config
        
        # MeetingManager に AppConfig を渡して初期化 (DocumentProcessorも内部でAppConfigを使う)
        self.meeting_manager = MeetingManager() # MeetingManagerの__init__でAppConfigを取得する形にした
        
        self.file_picker = ft.FilePicker(on_result=self._on_file_picked)
        page.overlay.append(self.file_picker) # FilePickerをpageのoverlayに追加

        self.participant_models: List[ModelInfo] = []
        self.moderator_model: Optional[ModelInfo] = None
        self.uploaded_file_path: Optional[str] = None
        self.current_meeting_result: Optional[MeetingResult] = None

        self._init_ui_components()
        self._setup_page_from_config() # AppConfigからページ設定を読み込むように変更
        self._build_layout()
        logger.info("MultiAIResearchApp 初期化完了")

    def _setup_page_from_config(self):
        self.page.title = self.app_config.window_title
        self.page.window_width = self.app_config.window_width
        self.page.window_height = self.app_config.window_height
        self.page.window_min_width = 800
        self.page.window_min_height = 700
        self.page.theme_mode = ft.ThemeMode.LIGHT # または self.app_config.default_theme_mode など
        self.page.scroll = ft.ScrollMode.ADAPTIVE
        # self.page.vertical_alignment = ft.MainAxisAlignment.START # 必要に応じて

    def _init_ui_components(self):
        # APIステータス
        self.api_status_text = ft.Text("APIキー確認中...", size=14)
        
        # モデル追加セクション
        self.model_name_field = ft.TextField(
            label="参加AIモデル名 (例: gpt-4o-mini)",
            hint_text="モデル名を入力 (プロバイダプレフィックス不要)",
            width=300,
            # ここでサジェスチョン機能などを追加しても良い
        )
        self.model_provider_dropdown = ft.Dropdown(
            label="プロバイダ",
            width=150,
            options=[ft.dropdown.Option(key=p.value, text=p.name) for p in AIProvider]
        )
        if self.model_provider_dropdown.options: # デフォルト選択
            self.model_provider_dropdown.value = self.model_provider_dropdown.options[0].key

        self.add_model_button = ft.IconButton(
            icon=ft.icons.ADD_CIRCLE_OUTLINE, # アイコン変更
            tooltip="モデル追加",
            on_click=self._add_model_from_ui
        )
        self.models_list = ft.Column(scroll=ft.ScrollMode.ADAPTIVE, height=200, spacing=5)

        # 司会モデルと設定
        self.moderator_dropdown = ft.Dropdown(
            label="司会モデル",
            hint_text="司会を担当するモデルを選択",
            width=300, # 全幅にしても良いかも
            options=[] # 動的に生成
        )
        self.rounds_field = ft.TextField(
            label="各AIの発言回数",
            value=str(self.app_config.default_rounds_per_ai),
            width=150,
            input_filter=ft.InputFilter(allow=True, regex_string=r"^[1-9][0-9]*$"), # 1以上の整数
            keyboard_type=ft.KeyboardType.NUMBER
        )
        
        # 質問/指示
        self.query_field = ft.TextField(
            label="質問/指示",
            hint_text="AIに議論してもらいたい内容を入力",
            multiline=True,
            min_lines=3,
            max_lines=5,
            expand=True
        )
        
        # 資料ファイル
        self.upload_button = ft.ElevatedButton(
            text="資料ファイルを選択 (.txt, .md, .pdf, .docx)",
            icon=ft.icons.UPLOAD_FILE,
            on_click=lambda _: self.file_picker.pick_files(
                dialog_title="資料ファイルを選択",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["txt", "md", "pdf", "docx"], # 対応拡張子
                allow_multiple=False
            )
        )
        self.file_status_text = ft.Text("ファイルが選択されていません", size=12, selectable=True)

        # 会議開始ボタンと進捗
        self.start_button = ft.ElevatedButton(
            text="会議開始",
            icon=ft.icons.PLAY_ARROW,
            on_click=self._start_meeting_async, # _start_meeting は非同期なので名前変更
            style=ft.ButtonStyle(bgcolor=ft.colors.BLUE_ACCENT_700, color=ft.colors.WHITE),
            height=40
        )
        self.progress_ring = ft.ProgressRing(visible=False, width=24, height=24, stroke_width=3)
        self.progress_text = ft.Text("", size=12, weight=ft.FontWeight.BOLD, selectable=True)

        # 会話内容
        self.conversation_list = ft.ListView(
            expand=True, # 高さをコンテナに合わせる
            spacing=10,
            padding=ft.padding.all(10), 
            auto_scroll=True,
            # height=300 # expand=True の場合 height は不要なことが多い
        )
        
        # 最終結果
        self.result_text = ft.TextField(
            label="最終結果", value="", multiline=True,
            read_only=True, expand=True, min_lines=5,
            border_radius=ft.border_radius.all(5),
            border_color=ft.colors.OUTLINE_VARIANT
        )
        
        # 保存ボタン
        self.save_conversation_button = ft.ElevatedButton(
            text="会話内容を保存", icon=ft.icons.SAVE,
            on_click=self._save_conversation, # 非同期処理
            disabled=True
        )
        self.save_result_button = ft.ElevatedButton(
            text="結果を保存", icon=ft.icons.SAVE_ALT,
            on_click=self._save_result, # 非同期処理
            disabled=True
        )

    def _build_layout(self):
        # --- 設定エリア ---
        settings_content = ft.Column([
            ft.Text("会議設定", size=20, weight=ft.FontWeight.BOLD),
            ft.Row([ft.Icon(ft.icons.KEY), self.api_status_text], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=15),
            
            ft.Text("参加AIモデル", size=16, weight=ft.FontWeight.W_500),
            ft.Row([
                self.model_name_field,
                self.model_provider_dropdown, # プロバイダ選択追加
                self.add_model_button
            ], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.END),
            ft.Container(
                content=self.models_list, 
                border=ft.border.all(1, ft.colors.OUTLINE_VARIANT), 
                border_radius=5, 
                padding=5,
                height=200 # models_listのColumnにheightを指定したので、ここはなくても良いかも
            ),
            ft.Divider(height=15),

            ft.Row([
                ft.Column([self.moderator_dropdown], expand=True),
                ft.Column([self.rounds_field], width=160)
            ], vertical_alignment=ft.CrossAxisAlignment.START),
            
            ft.Text("質問/指示", size=16, weight=ft.FontWeight.W_500),
            self.query_field,
            ft.Divider(height=15),
            
            ft.Text("資料ファイル (オプション)", size=16, weight=ft.FontWeight.W_500),
            ft.Row([self.upload_button, self.file_status_text], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=20, thickness=2),
            
            ft.Row([
                self.start_button, 
                self.progress_ring, 
                self.progress_text
            ], alignment=ft.MainAxisAlignment.END, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        ], scroll=ft.ScrollMode.ADAPTIVE, spacing=10)

        settings_container = ft.Container(
            content=settings_content,
            padding=ft.padding.all(20),
            # bgcolor=ft.colors.SURFACE_VARIANT, # Themeで設定されることが多い
            border_radius=10,
            # width=450 # 固定幅より expand や Column の weight で調整推奨
        )

        # --- 会話・結果エリア ---
        conversation_container = ft.Container(
            content=ft.Column([
                ft.Text("会話内容", size=18, weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=self.conversation_list,
                    border=ft.border.all(1, ft.colors.OUTLINE),
                    border_radius=5,
                    padding=ft.padding.all(5),
                    expand=True, # 高さを確保
                    height=400 # expand=True と併用は注意、どちらか一つで調整
                )
            ], expand=True, spacing=5), # spacing調整
            padding=ft.padding.symmetric(horizontal=10, vertical=5), # パディング調整
            expand=True,
        )

        result_container = ft.Container(
            content=ft.Column([
                ft.Text("最終結果", size=18, weight=ft.FontWeight.BOLD),
                self.result_text,
                ft.Row([
                    self.save_conversation_button, self.save_result_button
                ], alignment=ft.MainAxisAlignment.END, spacing=10) # 右寄せ、間隔
            ], expand=True, spacing=5),
            padding=ft.padding.symmetric(horizontal=10, vertical=5),
            expand=True,
            # height=300 # expand=True なので不要なことが多い
        )
        
        # メインレイアウト (2カラム)
        # よりレスポンシブにするには Row より ResponsiveRow や GridView も検討
        main_layout = ft.Row(
            [
                ft.Column([settings_container], width=480, scroll=ft.ScrollMode.ADAPTIVE), # 設定エリアの幅を少し広げる
                ft.VerticalDivider(width=10, thickness=1),
                ft.Column([
                    conversation_container, 
                    ft.Divider(height=10), 
                    result_container
                ], expand=True, spacing=0) # 右側のエリアはexpand=True
            ],
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START, # 上揃え
            # spacing=0 # Row直下の子要素間のスペース
        )

        self.page.add(main_layout)
        self._update_api_status_display() # 初期APIステータス表示
        self.page.update()

    def _update_api_status_display(self): # メソッド名変更
        status_parts = []
        api_validation = self.config_manager.validate_api_keys()
        all_ok = True
        for provider, is_configured in api_validation.items():
            status_icon = ft.icons.CHECK_CIRCLE if is_configured else ft.icons.CANCEL
            status_color = ft.colors.GREEN_ACCENT_700 if is_configured else ft.colors.RED_ACCENT_700
            if not is_configured: all_ok = False
            status_parts.append(
                ft.Row([
                    ft.Icon(name=status_icon, color=status_color, size=18),
                    ft.Text(provider.name, size=14, weight=ft.FontWeight.NORMAL) # プロバイダ名を大文字で表示
                ], spacing=3)
            )
        
        # self.api_status_text を Row に変更して、アイコンとテキストを表示
        if isinstance(self.api_status_text, ft.Text): # 初回はTextなので置き換え
             status_row_content = [ft.Text("APIキー: ", weight=ft.FontWeight.BOLD, size=14)]
             status_row_content.extend(status_parts)
             self.api_status_text = ft.Row(status_row_content, spacing=10, wrap=True)
             # レイアウト更新のために、api_status_text を含む親コントロールを更新する必要がある
             # ここでは、_build_layout で配置した Row を更新する代わりに、
             # _build_layout 内で self.api_status_text を ft.Container に入れておき、
             # そのコンテナの content を差し替える方が簡単かもしれない。
             # 今回は簡易的に、もし可能なら update する。
        elif isinstance(self.api_status_text, ft.Row):
             self.api_status_text.controls = [ft.Text("APIキー: ", weight=ft.FontWeight.BOLD, size=14)] + status_parts
        
        if self.api_status_text.page:
             self.api_status_text.update()
        else:
             logger.warning("api_status_text is not on the page, cannot update its content directly.")
        
        # 全体的なステータスに応じてスタートボタンの有効/無効を制御しても良い
        # self.start_button.disabled = not all_ok # APIキーが一つでも未設定なら開始不可など
        # self.start_button.update()


    async def _add_model_from_ui(self, e): # メソッド名変更、非同期に
        model_name_raw = self.model_name_field.value.strip()
        selected_provider_value = self.model_provider_dropdown.value # "openai", "claude", etc.

        if not model_name_raw:
            self._show_snack_bar("モデル名を入力してください。")
            return
        if not selected_provider_value:
            self._show_snack_bar("プロバイダを選択してください。")
            return

        try:
            # AIProvider Enum の値から Enum メンバーを取得
            provider_enum = AIProvider(selected_provider_value)
        except ValueError:
            self._show_snack_bar(f"無効なプロバイダ値: {selected_provider_value}")
            return
            
        if not self.config_manager.is_api_key_configured(provider_enum):
            self._show_snack_bar(f"{provider_enum.name} のAPIキーが設定されていません。")
            return

        # モデル名の重複チェック (プロバイダとモデル名の組み合わせで)
        if any(m.name == model_name_raw and m.provider == provider_enum for m in self.participant_models):
            self._show_snack_bar("同じプロバイダの同じモデル名は既に追加されています。")
            return

        if len(self.participant_models) >= 5: # 上限は5モデルまで
            self._show_snack_bar("参加モデルは最大5つまでです。")
            return

        # ModelInfo を作成
        model_info = ModelInfo(
            name=model_name_raw,
            provider=provider_enum,
            temperature=self.app_config.default_temperature, # AppConfig から取得
            max_tokens=self.app_config.default_max_tokens,   # AppConfig から取得
            persona=f"{model_name_raw}としての意見" # デフォルトペルソナ
        )
        self.participant_models.append(model_info)
        
        self._update_models_list_ui() # UI更新
        self._update_moderator_options_ui() # UI更新
        
        self.model_name_field.value = ""
        # self.model_provider_dropdown.value = self.model_provider_dropdown.options[0].key # リセット
        self.model_name_field.focus()
        
        self._show_snack_bar(f"{provider_enum.name} の {model_name_raw} を追加しました。", success=True)
        if self.page: self.page.update()


    def _update_models_list_ui(self): # メソッド名変更
        self.models_list.controls.clear()
        for i, model in enumerate(self.participant_models):
            model_card = ft.Card(
                ft.Container(
                    ft.Column([
                        ft.Row([
                            ft.Text(f"{model.name}", weight=ft.FontWeight.BOLD, size=15, expand=True),
                            ft.Chip(
                                ft.Text(model.provider.name, size=11, weight=ft.FontWeight.W_500),
                                bgcolor=self._get_provider_chip_color(model.provider),
                                padding=ft.padding.symmetric(horizontal=6, vertical=3)
                            ),
                            ft.IconButton(
                                icon=ft.icons.DELETE_OUTLINE, tooltip="モデル削除", data=i,
                                on_click=self._on_remove_model_clicked,
                                icon_size=20, style=ft.ButtonStyle(padding=0)
                            )
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        ft.TextField(
                            label="ペルソナ", value=model.persona,
                            multiline=True, min_lines=1, max_lines=2, dense=True,
                            text_size=12, on_change=lambda e, idx=i: self._on_model_setting_changed(idx, "persona", e.control.value)
                        ),
                        ft.Text("Temperature:", size=11, weight=ft.FontWeight.W_500),
                        ft.Slider(
                            value=model.temperature, min=0, max=2, divisions=20,
                            label="{value:.2f}", # スライダーの値表示
                            data=i, on_change=lambda e, idx=i: self._on_model_setting_changed(idx, "temperature", e.control.value),
                            active_color=ft.colors.BLUE_ACCENT_200, inactive_color=ft.colors.BLUE_GREY_100
                        )
                        # max_tokens もUIで設定可能にする場合はここに追加
                    ], spacing=3), # Column内のスペース調整
                    padding=ft.padding.all(10)
                ),
                elevation=2, margin=ft.margin.only(bottom=5)
            )
            self.models_list.controls.append(model_card)
        if self.models_list.page: self.models_list.update()

    def _get_provider_chip_color(self, provider: AIProvider) -> Optional[str]:
        colors = {
            AIProvider.OPENAI: ft.colors.GREEN_ACCENT_100,
            AIProvider.CLAUDE: ft.colors.ORANGE_ACCENT_100,
            AIProvider.GEMINI: ft.colors.BLUE_ACCENT_100,
        }
        return colors.get(provider)

    def _on_model_setting_changed(self, index: int, field_name: str, value: Any):
        if 0 <= index < len(self.participant_models):
            model_to_update = self.participant_models[index]
            if field_name == "persona":
                model_to_update.persona = str(value)
            elif field_name == "temperature":
                model_to_update.temperature = round(float(value), 2)
            
            logger.debug(f"Model {model_to_update.name} setting '{field_name}' changed to: {value}")
            # カード内の特定のコントロールだけを更新するのは難しいので、リスト全体を更新するか、
            # カードオブジェクトを保持しておき、その中のコントロールを更新する
            # ここではリスト全体更新で対応 (_update_models_list_ui が呼ばれる想定)
            # self._update_models_list_ui() # 即時反映させたい場合
            # if self.page: self.page.update()

    async def _on_remove_model_clicked(self, e: ft.ControlEvent): # async に
        index_to_remove = e.control.data
        if 0 <= index_to_remove < len(self.participant_models):
            removed_model = self.participant_models.pop(index_to_remove)
            logger.info(f"Removed model: {removed_model.name}")
            self._update_models_list_ui()
            self._update_moderator_options_ui()
            self._show_snack_bar(f"{removed_model.name} を削除しました。")
            if self.page: self.page.update()

    def _update_moderator_options_ui(self): # メソッド名変更
        current_moderator_name = self.moderator_dropdown.value
        self.moderator_dropdown.options.clear()
        new_options: List[ft.dropdown.Option] = [ft.dropdown.Option(key="NONE", text="司会なし (言語チェックなし)")] # 司会なしオプション
        
        selected_value_still_exists = False
        for model in self.participant_models:
            option_text = f"{model.name} ({model.provider.name})"
            option = ft.dropdown.Option(key=model.name, text=option_text) # keyは一意なもの (nameでOK)
            new_options.append(option)
            if model.name == current_moderator_name:
                selected_value_still_exists = True
        
        self.moderator_dropdown.options = new_options
        
        if selected_value_still_exists and current_moderator_name != "NONE":
            self.moderator_dropdown.value = current_moderator_name
        elif self.participant_models: # 参加者がいれば、最初の参加者をデフォルト司会に
            self.moderator_dropdown.value = self.participant_models[0].name
        else: # 参加者がいなければ「司会なし」
            self.moderator_dropdown.value = "NONE"
            
        if self.moderator_dropdown.page: self.moderator_dropdown.update()

    async def _on_file_picked(self, e: ft.FilePickerResultEvent):
        logger.debug(f"File picked event: {e.files}")
        if e.files and e.files[0] and e.files[0].path:
            file_result = e.files[0]
            self.uploaded_file_path = file_result.path
            file_size_kb = (file_result.size or 0) / 1024
            self.file_status_text.value = f"選択: {Path(file_result.name).name} ({file_size_kb:.1f}KB)"
            self.file_status_text.color = ft.colors.GREEN_ACCENT_700
            logger.info(f"File selected: {self.uploaded_file_path}")
        elif e.files and e.files[0] and not e.files[0].path:
            self.uploaded_file_path = None
            self.file_status_text.value = "エラー: ファイルパスを取得できませんでした。"
            self.file_status_text.color = ft.colors.RED_ACCENT_700
            logger.warning("File picked, but path is None.")
            self._show_snack_bar("ファイルのパス取得に失敗しました。", error=True)
        else: # キャンセルまたはエラー
            self.uploaded_file_path = None
            self.file_status_text.value = "ファイルが選択されていません"
            self.file_status_text.color = None # デフォルト色
            logger.info("File selection cancelled or failed.")

        if self.file_status_text.page: self.file_status_text.update()
        if self.page: self.page.update() # FilePickerのダイアログを閉じるために必要かも

    def _set_ui_processing_state(self, processing: bool): # メソッド名変更
        self.start_button.disabled = processing
        self.query_field.disabled = processing
        self.upload_button.disabled = processing
        self.model_name_field.disabled = processing
        self.model_provider_dropdown.disabled = processing
        self.add_model_button.disabled = processing
        self.moderator_dropdown.disabled = processing
        self.rounds_field.disabled = processing
        
        # モデルリスト内の各コントロールも無効化
        for card_container in self.models_list.controls:
            if isinstance(card_container, ft.Card) and card_container.content and hasattr(card_container.content, 'controls'):
                for control_in_card in card_container.content.controls: # Card -> Container -> Column
                     if hasattr(control_in_card, 'controls'): # Rowなど
                         for sub_control in control_in_card.controls:
                             if hasattr(sub_control, 'disabled'): sub_control.disabled = processing
                     elif hasattr(control_in_card, 'disabled'): # TextField, Sliderなど
                        control_in_card.disabled = processing
        
        self.progress_ring.visible = processing
        self.progress_text.value = "会議を実行中..." if processing else ""
        
        if self.page: self.page.update()

    async def _start_meeting_async(self, e): # メソッド名変更
        logger.info("会議開始ボタンクリック。UI準備中...")
        if not self.participant_models:
            self._show_snack_bar("参加モデルを1つ以上追加してください。", error=True)
            return
        
        moderator_name_selected = self.moderator_dropdown.value
        if not moderator_name_selected: # "NONE" も許容するため、None のみチェック
            self._show_snack_bar("司会モデルを選択するか、「司会なし」を選んでください。", error=True)
            return
            
        if not self.query_field.value.strip():
            self._show_snack_bar("質問/指示を入力してください。", error=True)
            return

        self._set_ui_processing_state(True)
        self.result_text.value = ""
        self.conversation_list.controls.clear()
        if self.conversation_list.page: self.conversation_list.update()
        if self.result_text.page: self.result_text.update()

        self.current_meeting_result = None
        self.save_conversation_button.disabled = True
        self.save_result_button.disabled = True
        if self.save_conversation_button.page: self.save_conversation_button.update()
        if self.save_result_button.page: self.save_result_button.update()
        
        logger.info("会議設定の準備中...")
        
        selected_moderator_info: Optional[ModelInfo] = None
        if moderator_name_selected != "NONE":
            selected_moderator_info = next((m for m in self.participant_models if m.name == moderator_name_selected), None)
            if not selected_moderator_info:
                self._show_snack_bar(f"エラー: 選択された司会モデル '{moderator_name_selected}' が見つかりません。", error=True)
                self._set_ui_processing_state(False)
                return
            logger.info(f"司会モデルとして {selected_moderator_info.name} を使用します。")
        else:
            logger.info("司会なしで会議を実行します。言語チェックは行われません。")


        meeting_settings = MeetingSettings(
            participant_models=[m.model_copy(deep=True) for m in self.participant_models], # deep copy
            moderator_model=selected_moderator_info.model_copy(deep=True) if selected_moderator_info else None,
            rounds_per_ai=int(self.rounds_field.value or self.app_config.default_rounds_per_ai),
            user_query=self.query_field.value.strip(),
            document_path=self.uploaded_file_path
        )

        # MeetingManager のコールバックを設定
        self.meeting_manager.on_statement_added = self._on_statement_added
        self.meeting_manager.on_phase_changed = self._on_phase_changed
        # self.meeting_manager.on_error = self._on_meeting_error # 必要ならエラーコールバックも

        logger.info("MeetingManager.run_meeting を非同期で呼び出します...")
        try:
            # run_meeting は非同期メソッドである必要がある
            result_from_manager = await self.meeting_manager.run_meeting(
                settings=meeting_settings,
                progress_callback=self._on_progress_update
            )
            
            if result_from_manager:
                self.current_meeting_result = result_from_manager
                self.result_text.value = result_from_manager.final_summary or "最終要約がありませんでした。"
                logger.info(f"会議結果受け取り成功。要約冒頭: '{result_from_manager.final_summary[:70] if result_from_manager.final_summary else 'N/A'}'")
                
                if result_from_manager.total_tokens_used >= 0 : # トークン数が記録されていれば
                     self._show_snack_bar(
                        f"会議完了！所要時間: {format_duration(result_from_manager.duration_seconds)}, "
                        f"総トークン: {result_from_manager.total_tokens_used}",
                        success=True
                    )
                else: # トークン数が不明な場合
                     self._show_snack_bar(
                        f"会議完了！所要時間: {format_duration(result_from_manager.duration_seconds)} (トークン数不明)",
                        success=True
                    )

            else: # MeetingResult が None の場合 (致命的エラーなど)
                logger.error("MeetingManager.run_meeting から None が返されました。")
                self.result_text.value = "会議の実行に失敗しました (結果オブジェクトなし)。詳細はログを確認してください。"
                self._show_snack_bar("会議エラー: 結果を取得できませんでした。", error=True)

        except Exception as ex:
            logger.error(f"会議実行中に予期せぬ例外が発生: {ex}", exc_info=True)
            self.result_text.value = f"会議中に致命的なエラーが発生しました: {str(ex)}"
            self.current_meeting_result = None # エラー時は結果なし
            self._show_snack_bar(f"会議実行エラー: {str(ex)}", error=True)
        finally:
            logger.info("会議処理の finally ブロック実行。UI状態を更新します。")
            self._set_ui_processing_state(False)
            if self.result_text.page: self.result_text.update()

            can_save_conversation = bool(self.current_meeting_result and self.current_meeting_result.conversation_log)
            can_save_result = bool(self.current_meeting_result and self.current_meeting_result.final_summary and self.current_meeting_result.final_summary.strip())

            self.save_conversation_button.disabled = not can_save_conversation
            self.save_result_button.disabled = not can_save_result
            if self.save_conversation_button.page: self.save_conversation_button.update()
            if self.save_result_button.page: self.save_result_button.update()
            
            logger.info(f"Save Conversation Button - Disabled: {self.save_conversation_button.disabled}")
            logger.info(f"Save Result Button - Disabled: {self.save_result_button.disabled}")
            if self.page: self.page.update() # 全体更新

    def _on_phase_changed(self, phase: str):
        phase_messages = {
            "initializing_participants": "参加者とAIクライアントを初期化中...",
            "processing_document": "資料を処理・要約中...",
            "discussing": "議論を進行中...",
            "summarizing": "最終要約を生成中...",
            "completed": "会議完了",
            "error": "エラーが発生しました"
        }
        message = phase_messages.get(phase, f"フェーズ: {phase}")
        self.progress_text.value = message
        logger.info(f"Phase changed to: {phase} - UI message: {message}")
        if self.progress_text.page: self.progress_text.update()
        # if self.page: self.page.update() # 必要に応じて全体更新

    def _on_progress_update(self, phase_detail: str, current: int, total: int):
        # このコールバックは MeetingManager 内部のループから呼ばれる
        if phase_detail == "discussing_round":
            self.progress_text.value = f"議論中 - ラウンド {current}/{total}"
        elif phase_detail == "discussing_statement":
             self.progress_text.value = f"議論中 - 発言 {current}/{total}"
        else:
            self.progress_text.value = f"{phase_detail}: {current}/{total}"
        
        if self.progress_text.page: self.progress_text.update()

    def _show_snack_bar(self, message: str, error: bool = False, success: bool = False):
        if not self.page:
            logger.warning(f"SnackBar表示スキップ (pageなし): {message}")
            return
        
        bgcolor = None
        if error:
            bgcolor = ft.colors.RED_ACCENT_700
        elif success:
            bgcolor = ft.colors.GREEN_ACCENT_700

        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(message, color=ft.colors.WHITE if bgcolor else None), # 背景色があるなら文字は白
            open=True,
            bgcolor=bgcolor,
            duration=4000 # 表示時間 (ミリ秒)
        )
        try:
            self.page.update()
        except Exception as e:
            logger.error(f"SnackBar表示中のpage.update()でエラー: {e}", exc_info=True)


async def main_flet_app(page: ft.Page): # Fletのターゲット関数名を変更
    logger.info("Flet application instance starting...")
    # ここで AppConfig を初期化し、MultiAIResearchApp に渡すこともできる
    # config_manager = get_config_manager()
    # app_config = config_manager.config
    # app = MultiAIResearchApp(page, app_config) # app_configを渡す場合
    app = MultiAIResearchApp(page)
    # MultiAIResearchApp の __init__ で page.add が呼ばれていなければここで追加
    # if not page.controls: page.add(app) # 通常は __init__ でレイアウトをaddする

if __name__ == "__main__":
    logger.info("Starting Flet application...")
    ft.app(
        target=main_flet_app, # Fletが呼び出す関数
        assets_dir="assets", # アセットディレクトリ
        # view=ft.AppView.FLET_APP, # デスクトップアプリとして実行
        # port=8550 # 必要ならポート指定
    )