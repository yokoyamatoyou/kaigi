from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from typing import List, Optional

from .document_processor import DocumentProcessor
from .config_manager import ConfigManager


class VectorStoreManager:
    """ドキュメントのテキストをベクトル化し、FAISSによる高度な検索機能を提供するクラス。"""

    def __init__(self, openai_api_key: str):
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small", openai_api_key=openai_api_key
        )
        self.vector_store: Optional[FAISS] = None
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200
        )
        self.config_manager = ConfigManager()

    def create_from_file(self, file_path: str):
        try:
            processor = DocumentProcessor(config=self.config_manager.config)
            result = processor.extract_text(file_path)
            text = result.extracted_text if result.is_success else ""
            if not text:
                self.vector_store = None
                return
            chunks = self.text_splitter.split_text(text)
            self.vector_store = FAISS.from_texts(texts=chunks, embedding=self.embeddings)
            print("ベクトルストアの構築が完了しました。")
        except Exception as e:
            print(f"ベクトルストアの構築中にエラーが発生しました: {e}")
            self.vector_store = None

    def get_relevant_documents(self, query: str, k: int = 5, use_mmr: bool = False) -> List[str]:
        """クエリに関連するドキュメントのチャンクを取得する。MMR (Maximal Marginal Relevance) を使用して多様性を確保するオプションを追加。"""
        if not self.vector_store:
            return []

        if use_mmr:
            # MMR検索で、関連性と多様性を両立させる
            docs = self.vector_store.max_marginal_relevance_search(query, k=k, fetch_k=20)
        else:
            # 通常の類似度検索
            docs = self.vector_store.similarity_search(query, k=k)

        return [doc.page_content for doc in docs]

