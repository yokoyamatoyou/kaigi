import pytest
from datetime import datetime

from core.meeting_manager import MeetingManager, ParticipantInfo, ConversationEntry
from core.models import ModelInfo, MeetingSettings, AIProvider
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

