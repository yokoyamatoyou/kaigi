import flet as ft


class ComponentsMixin:
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
            on_click=self._add_model,
        )
        self.models_list = ft.Column(scroll=ft.ScrollMode.ADAPTIVE, height=200)

        self.moderator_dropdown = ft.Dropdown(
            label="司会モデル",
            hint_text="司会を担当するモデルを選択",
            width=300,
            options=[],
        )
        self.rounds_field = ft.TextField(
            label="各AIの発言回数",
            value=str(self.config_manager.config.default_rounds_per_ai),
            width=150,
            input_filter=ft.InputFilter(allow=True, regex_string=r"[0-9]"),
        )
        self.query_field = ft.TextField(
            label="質問/指示",
            hint_text="AIに議論してもらいたい内容を入力",
            multiline=True,
            min_lines=3,
            max_lines=5,
            expand=True,
        )
        self.upload_button = ft.ElevatedButton(
            text="資料ファイルを選択",
            icon="upload_file",
            on_click=self._on_upload_clicked,
        )
        self.file_status_text = ft.Text("ファイルが選択されていません", size=12)

        carry_over_options = [ft.dropdown.Option(key="none", text="なし")]
        for ctx in self.context_manager.list_carry_overs():
            carry_over_options.append(
                ft.dropdown.Option(key=ctx["id"], text=ctx["display_name"])
            )
        self.carry_over_dropdown = ft.Dropdown(
            label="前回の持ち越し事項を読み込む",
            options=carry_over_options,
            value="none",
            on_change=self._on_carry_over_changed,
        )
        self.clear_carry_over_button = ft.IconButton(
            icon="clear",
            tooltip="Clear",
            on_click=self._clear_carry_over,
            visible=False,
        )
        self.carry_over_info_text = ft.Text("", size=12)
        self.carry_over_banner = ft.Container(
            content=self.carry_over_info_text,
            bgcolor=ft.Colors.AMBER_100,
            padding=ft.padding.symmetric(vertical=5, horizontal=10),
            border_radius=5,
            visible=False,
        )

        self.start_button = ft.ElevatedButton(
            text="会議開始",
            icon="play_arrow",
            on_click=self._start_meeting,
            style=ft.ButtonStyle(bgcolor="primary", color="white"),
        )
        self.progress_ring = ft.ProgressRing(visible=False)
        self.progress_text = ft.Text("", size=12)

        self.conversation_list = ft.ListView(
            expand=False,
            height=250,
            spacing=10,
            padding=ft.padding.all(10),
            auto_scroll=True,
        )
        self.result_text = ft.TextField(
            label="最終結果",
            value="",
            multiline=True,
            read_only=True,
            expand=True,
            min_lines=5,
        )
        self.save_conversation_button = ft.ElevatedButton(
            text="会話内容を保存",
            icon="save",
            on_click=self._save_conversation,
            disabled=True,
        )
        self.save_result_button = ft.ElevatedButton(
            text="結果を保存",
            icon="save_alt",
            on_click=self._save_result,
            disabled=True,
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
                    self.upload_button,
                    self.file_status_text,
                ], expand=True),
                ft.Column([self.rounds_field], width=170),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(height=20),
            ft.Row([
                self.carry_over_dropdown,
                self.clear_carry_over_button,
            ]),
            self.carry_over_banner,
            ft.Row([
                self.start_button,
                self.progress_ring,
                self.progress_text,
            ], alignment=ft.MainAxisAlignment.START),
        ], scroll=ft.ScrollMode.ADAPTIVE)

        settings_area = ft.Container(
            content=settings_column,
            padding=ft.padding.all(15),
            bgcolor="surfacevariant",
            border_radius=10,
        )
        conversation_area = ft.Container(
            content=ft.Column([
                ft.Text("会話内容", size=18, weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=self.conversation_list,
                    border=ft.border.all(1, "outline"),
                    border_radius=5,
                    padding=ft.padding.all(5),
                ),
            ], tight=True),
            padding=ft.padding.all(15),
        )
        result_area = ft.Container(
            content=ft.Column([
                ft.Text("最終結果", size=18, weight=ft.FontWeight.BOLD),
                self.result_text,
                ft.Row([
                    self.save_conversation_button,
                    self.save_result_button,
                ], alignment=ft.MainAxisAlignment.CENTER),
            ]),
            padding=ft.padding.all(15),
            expand=True,
        )
        main_content = ft.Row([
            ft.Container(content=settings_area, width=420, expand=False),
            ft.Container(
                content=ft.Column([conversation_area, result_area], expand=True, spacing=10),
                expand=True,
            ),
        ], expand=True, vertical_alignment=ft.CrossAxisAlignment.START)

        self.page.add(main_content)
        self._update_api_status()

