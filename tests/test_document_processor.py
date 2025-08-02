from core.document_processor import DocumentProcessor
from core.models import AppConfig, ModelInfo, AIProvider
from types import SimpleNamespace
import pytest


TEST_CASES = [
    (
        AIProvider.OPENAI,
        SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="openai"))],
            usage=SimpleNamespace(total_tokens=5),
        ),
        5,
        "openai",
    ),
    (
        AIProvider.CLAUDE,
        SimpleNamespace(
            content=[SimpleNamespace(text="claude")],
            usage=SimpleNamespace(input_tokens=3, output_tokens=4),
        ),
        7,
        "claude",
    ),
    (
        AIProvider.GEMINI,
        SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    content=SimpleNamespace(parts=[SimpleNamespace(text="gemini")])
                )
            ],
            usage_metadata=SimpleNamespace(prompt_token_count=2, candidates_token_count=3),
        ),
        5,
        "gemini",
    ),
]


def test_extract_text_from_txt(tmp_path):
    content = "Hello world\nsecond line"
    txt_file = tmp_path / "sample.txt"
    txt_file.write_text(content, encoding="utf-8")
    config = AppConfig(max_document_size_mb=1)
    processor = DocumentProcessor(config)
    valid, err = processor.validate_file(str(txt_file))
    assert valid, err
    result = processor.extract_text(str(txt_file))
    assert result.is_success
    assert result.extracted_text == content


def test_validate_file_extension(tmp_path):
    file_path = tmp_path / "bad.xyz"
    file_path.write_text("data", encoding="utf-8")
    processor = DocumentProcessor(AppConfig())
    valid, err = processor.validate_file(str(file_path))
    assert not valid
    assert "サポートされていない" in err


class DummyClient:
    def __init__(self, provider: AIProvider, response: SimpleNamespace):
        self.model_info = ModelInfo(name="dummy", provider=provider)
        self._response = response

    async def request_completion(self, *args, **kwargs):
        return self._response


@pytest.mark.parametrize(
    "provider,response,expected_tokens,expected_content",
    TEST_CASES,
)
def test_extract_content_and_tokens(provider, response, expected_tokens, expected_content):
    processor = DocumentProcessor(AppConfig())
    content, tokens = processor._extract_content_and_tokens(provider, response)
    assert content == expected_content
    assert tokens == expected_tokens


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,response,expected_tokens,expected_content",
    TEST_CASES,
)
async def test_summarize_document_for_meeting_with_various_providers(provider, response, expected_tokens, expected_content):
    config = AppConfig(summarization_target_tokens=10)
    processor = DocumentProcessor(config)
    text = "word " * 100
    client = DummyClient(provider, response)
    summary = await processor.summarize_document_for_meeting(text, client)
    assert summary.summary == expected_content
    assert summary.tokens_used == expected_tokens

