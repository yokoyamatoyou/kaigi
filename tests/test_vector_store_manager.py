import pytest
from langchain.docstore.document import Document
from langchain_community.vectorstores import FAISS
from langchain.embeddings.base import Embeddings

from core.config_manager import get_config_manager
from core.vector_store_manager import VectorStoreManager


class DummyVectorStore:
    """Simple vector store returning deterministic results."""

    def similarity_search(self, query: str, k: int):
        # Return duplicated content to show lack of diversity
        return [Document(page_content="dup") for _ in range(k)]

    def max_marginal_relevance_search(self, query: str, k: int, fetch_k: int = 20):
        # Return unique documents in deterministic order
        return [Document(page_content=f"mmr_{i}") for i in range(k)]


def test_mmr_diversity_and_reproducibility():
    manager = VectorStoreManager(openai_api_key="test", config_manager=get_config_manager())
    manager.vector_store = DummyVectorStore()

    # Similarity search produces duplicate results
    sim_results = manager.get_relevant_documents("query", k=2, use_mmr=False)
    assert len(sim_results) == 2
    assert len(set(sim_results)) == 1  # duplicates present

    # MMR search should be reproducible and diverse
    first = manager.get_relevant_documents("query", k=2, use_mmr=True, fetch_k=5)
    second = manager.get_relevant_documents("query", k=2, use_mmr=True, fetch_k=5)

    assert first == second  # reproducibility
    assert len(first) == 2
    assert len(set(first)) == 2  # diversity (unique items)


class FakeEmbeddings(Embeddings):
    """Embeddings that mark texts containing 'hello' as 1, others as 0."""

    def embed_documents(self, texts):
        return [[1.0 if "hello" in t else 0.0] for t in texts]

    def embed_query(self, text):
        return [1.0 if "hello" in text else 0.0]


def test_save_and_load(tmp_path):
    save_path = tmp_path / "store"
    fake = FakeEmbeddings()
    manager = VectorStoreManager(
        openai_api_key="test", persist_path=str(save_path), embeddings=fake
    )
    texts = ["hello world", "foo bar"]
    manager.vector_store = FAISS.from_texts(texts, embedding=fake)
    manager.save_to_disk()

    new_manager = VectorStoreManager(
        openai_api_key="test",
        persist_path=str(save_path),
        embeddings=fake,
        allow_dangerous_deserialization=True,
    )
    results = new_manager.get_relevant_documents("hello", k=1)
    assert results == ["hello world"]


def test_create_from_text():
    fake = FakeEmbeddings()
    manager = VectorStoreManager(openai_api_key="test", embeddings=fake)
    manager.create_from_text("hello world\n\nfoo bar")
    results = manager.get_relevant_documents("hello", k=1)
    assert results and "hello world" in results[0]
