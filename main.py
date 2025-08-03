import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from typing import List, Optional

import flet as ft
import logging

from core.models import ModelInfo, MeetingResult
from core.config_manager import get_config_manager
from core.meeting_manager import MeetingManager
from core.context_manager import ContextManager
from core.vector_store_manager import VectorStoreManager

from ui.components import ComponentsMixin
from ui.events import EventsMixin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MultiAIResearchApp(ComponentsMixin, EventsMixin):
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
        self.vector_store_manager: Optional[VectorStoreManager] = None

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
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.scroll = ft.ScrollMode.ADAPTIVE
        self.page.overlay.append(self.file_picker)


async def main(page: ft.Page):
    MultiAIResearchApp(page)


if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")
