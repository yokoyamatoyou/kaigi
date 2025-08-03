import pytest
from datetime import datetime

from core.meeting_manager import MeetingManager, ParticipantInfo, ConversationEntry
import core.meeting_manager as meeting_manager
import core.context_manager as context_manager
from core.models import ModelInfo, MeetingSettings, AIProvider, MeetingResult
from core.config_manager import initialize_config_manager


class DummyMeetingManager(MeetingManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial_context_built = None

    def initialize_participants(self, settings: MeetingSettings) -> bool:
        self.clear_meeting_state()
        for idx, model in enumerate(settings.participant_models):
            key = f"p{idx}"
            self.participants[key] = ParticipantInfo(
                client=None,
                name=model.name,
                internal_key=key,
                persona=model.persona,
                model_info=model,
            )
        self.moderator = ParticipantInfo(
            client=None,
            name="moderator",
            internal_key="mod",
            persona="moderator",
            model_info=settings.moderator_model,
        )
        self.state.total_rounds_expected = settings.rounds_per_ai * len(self.participants)
        self.state.active_participant_keys = list(self.participants.keys())
        return True

    async def run_meeting(self, settings: MeetingSettings, progress_callback=None):
        if not self.initialize_participants(settings):
            raise RuntimeError("failed to init participants")
        self.initial_context_built = self._build_initial_context(settings.user_query, None)
        self._system_prompt_context = self.initial_context_built
        await self._enhance_personas(settings.user_query, None)
        for idx, key in enumerate(self.participants.keys(), start=1):
            participant = self.participants[key]
            await self._make_participant_statement(participant, idx)
        if self.moderator:
            await self._generate_round_summary(1)
        final = await self._generate_final_summary(settings.user_query, None)
        self.state.phase = "completed"
        return MeetingResult(
            settings=settings,
            conversation_log=self.state.conversation_history.copy(),
            final_summary=final,
            duration_seconds=0,
            total_tokens_used=self.state.total_tokens_this_meeting,
            document_summary=None,
            participants_count=len(self.participants),
        )

    async def _make_participant_statement(self, participant: ParticipantInfo, ai_specific_round_num: int):
        entry = ConversationEntry(
            speaker=participant.name,
            persona=participant.persona,
            content=f"Statement {participant.name}",
            timestamp=datetime.now(),
            round_number=ai_specific_round_num,
            model_name=participant.model_info.name,
        )
        self.state.add_conversation_entry(entry)
        participant.total_statements += 1

    async def _generate_round_summary(self, round_number: int):
        entry = ConversationEntry(
            speaker=self.moderator.name,
            persona="summary",
            content=f"Summary {round_number}",
            timestamp=datetime.now(),
            round_number=round_number,
            model_name=self.moderator.model_info.name,
        )
        self.state.add_conversation_entry(entry)

    async def _generate_final_summary(self, user_query: str, document_summary):
        meeting_manager.save_carry_over(user_query, "dummy unresolved")
        return "final summary"


@pytest.mark.asyncio
async def test_run_meeting_basic(monkeypatch):
    monkeypatch.setenv("API_CALL_DELAY_SECONDS", "0")
    initialize_config_manager()
    saved = {}

    def fake_save(topic, issues):
        saved["topic"] = topic
        saved["issues"] = issues

    monkeypatch.setattr(meeting_manager, "save_carry_over", fake_save)
    settings = MeetingSettings(
        participant_models=[
            ModelInfo(name="modelA", provider=AIProvider.OPENAI, persona="p1"),
            ModelInfo(name="modelB", provider=AIProvider.OPENAI, persona="p2"),
        ],
        moderator_model=ModelInfo(name="mod", provider=AIProvider.OPENAI, persona="m"),
        rounds_per_ai=1,
        user_query="topic",
    )
    manager = DummyMeetingManager(carry_over_context="previous context")
    result = await manager.run_meeting(settings)
    assert result.participants_count == 2
    assert len(result.conversation_log) == 3
    assert result.final_summary == "final summary"
    assert manager.state.phase == "completed"
    assert "previous context" in manager.initial_context_built
    assert saved == {"topic": "topic", "issues": "dummy unresolved"}


class DummyEnhancer:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def enhance_persona(self, base_persona: str, topic: str, document_context: str):
        return f"{base_persona}-enhanced"


@pytest.mark.asyncio
async def test_persona_enhancement(monkeypatch):
    monkeypatch.setenv("API_CALL_DELAY_SECONDS", "0")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    initialize_config_manager()
    monkeypatch.setattr(meeting_manager, "PersonaEnhancer", DummyEnhancer)
    monkeypatch.setattr(meeting_manager, "save_carry_over", lambda *args, **kwargs: None)

    settings = MeetingSettings(
        participant_models=[
            ModelInfo(name="modelA", provider=AIProvider.OPENAI, persona="p1"),
        ],
        moderator_model=ModelInfo(name="mod", provider=AIProvider.OPENAI, persona="m"),
        rounds_per_ai=1,
        user_query="topic",
    )

    manager = DummyMeetingManager()
    await manager.run_meeting(settings)

    assert manager.participants["p0"].persona == "p1-enhanced"
    assert manager.moderator.persona == "moderator-enhanced"


class DummyVectorStore:
    def get_relevant_documents(self, query, k=3, use_mmr=True):
        return ["chunk1", "chunk2"]


def test_system_prompt_includes_rag_context():
    manager = MeetingManager(vector_store_manager=DummyVectorStore())
    manager._system_prompt_context = "base context"
    participant = ParticipantInfo(
        client=None,
        name="p",
        internal_key="p",
        persona="persona",
        model_info=ModelInfo(name="m", provider=AIProvider.OPENAI, persona="persona"),
    )
    rag = manager._get_rag_context("query")
    system_prompt = manager._build_system_prompt(participant, rag)
    assert "chunk1\nchunk2" in system_prompt
    assert "関連資料の抜粋" in system_prompt
    assert "base context" in system_prompt


@pytest.mark.asyncio
async def test_carry_over_created(tmp_path, monkeypatch):
    monkeypatch.setenv("API_CALL_DELAY_SECONDS", "0")
    initialize_config_manager()

    cm = context_manager.ContextManager(context_dir=str(tmp_path))
    monkeypatch.setattr(context_manager, "_default_manager", cm)

    class DummyClient:
        async def request_completion(self, *args, **kwargs):
            return None

    manager = MeetingManager(document_processor=object())
    manager.moderator = ParticipantInfo(
        client=DummyClient(),
        name="mod",
        internal_key="mod",
        persona="mod",
        model_info=ModelInfo(name="mod", provider=AIProvider.OPENAI, persona="m"),
    )

    final_summary = (
        "## 1. サマリー\n内容\n"
        "## 4. 未解決の課題と今後の検討事項\n課題A\n課題B\n"
    )

    def fake_extract(provider, response):
        return final_summary, 0

    async def fake_ensure(content, client, provider, context_for_correction):
        return content, 0

    monkeypatch.setattr(meeting_manager, "extract_content_and_tokens", fake_extract)
    monkeypatch.setattr(manager, "_ensure_japanese_output", fake_ensure)
    monkeypatch.setattr(manager, "_format_conversation_for_summary", lambda: "log")
    monkeypatch.setattr(manager, "_build_summary_prompt", lambda u, c, d: "prompt")

    summary = await manager._generate_final_summary("topic", None)
    assert "未解決" in summary

    files = list(tmp_path.glob("context_*.json"))
    assert len(files) == 1

    carry_overs = cm.list_carry_overs()
    assert len(carry_overs) == 1
    assert carry_overs[0]["id"] == files[0].name

