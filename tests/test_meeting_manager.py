import pytest
from datetime import datetime

from core.meeting_manager import MeetingManager, ParticipantInfo, ConversationEntry
import core.meeting_manager as meeting_manager
from core.models import ModelInfo, MeetingSettings, AIProvider, MeetingResult
from core.config_manager import initialize_config_manager


class DummyMeetingManager(MeetingManager):
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
        await self._enhance_personas(settings.user_query, None)
        for idx, key in enumerate(self.participants.keys(), start=1):
            participant = self.participants[key]
            await self._make_participant_statement(participant, "", idx)
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

    async def _make_participant_statement(self, participant: ParticipantInfo, system_prompt_context: str, ai_specific_round_num: int):
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
        return "final summary"


@pytest.mark.asyncio
async def test_run_meeting_basic(monkeypatch):
    monkeypatch.setenv("API_CALL_DELAY_SECONDS", "0")
    initialize_config_manager()
    settings = MeetingSettings(
        participant_models=[
            ModelInfo(name="modelA", provider=AIProvider.OPENAI, persona="p1"),
            ModelInfo(name="modelB", provider=AIProvider.OPENAI, persona="p2"),
        ],
        moderator_model=ModelInfo(name="mod", provider=AIProvider.OPENAI, persona="m"),
        rounds_per_ai=1,
        user_query="topic",
    )
    manager = DummyMeetingManager()
    result = await manager.run_meeting(settings)
    assert result.participants_count == 2
    assert len(result.conversation_log) == 3
    assert result.final_summary == "final summary"
    assert manager.state.phase == "completed"


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

