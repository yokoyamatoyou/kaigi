import pytest
from langchain.docstore.document import Document

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
    manager = VectorStoreManager(openai_api_key="test")
    manager.vector_store = DummyVectorStore()

    # Similarity search produces duplicate results
    sim_results = manager.get_relevant_documents("query", k=2, use_mmr=False)
    assert len(sim_results) == 2
    assert len(set(sim_results)) == 1  # duplicates present

    # MMR search should be reproducible and diverse
    first = manager.get_relevant_documents("query", k=2, use_mmr=True)
    second = manager.get_relevant_documents("query", k=2, use_mmr=True)

    assert first == second  # reproducibility
    assert len(first) == 2
    assert len(set(first)) == 2  # diversity (unique items)
