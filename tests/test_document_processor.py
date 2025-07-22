from core.document_processor import DocumentProcessor
from core.models import AppConfig


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

