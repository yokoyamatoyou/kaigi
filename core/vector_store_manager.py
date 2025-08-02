import faiss  # noqa: F401
import numpy as np  # noqa: F401
from pathlib import Path
from typing import List, Optional

from langchain.docstore.document import Document
from langchain.embeddings.base import Embeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

from .config_manager import ConfigManager
from .document_processor import DocumentProcessor


class VectorStoreManager:
    """ドキュメントのテキストをベクトル化し、FAISSによる高度な検索機能を提供するクラス。"""

    def __init__(
        self,
        openai_api_key: str,
        persist_path: Optional[str] = None,
        embeddings: Optional[Embeddings] = None,
    ):
        self.embeddings = embeddings or OpenAIEmbeddings(
            model="text-embedding-3-small", openai_api_key=openai_api_key
        )
        self.persist_path = persist_path
        self.vector_store: Optional[FAISS] = None
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200
        )
        self.config_manager = ConfigManager()

        if self.persist_path and Path(self.persist_path).exists():
            self.load_from_disk()

    def create_from_file(self, file_path: str):
        try:
            processor = DocumentProcessor(config=self.config_manager.config)
            result = processor.extract_text(file_path)
            text = result.extracted_text if result.is_success else ""
            if not text:
                self.vector_store = None
                return

            document = Document(page_content=text, metadata=result.metadata)
            docs = self.text_splitter.split_documents([document])
            self.vector_store = FAISS.from_documents(docs, embedding=self.embeddings)
            print("ベクトルストアの構築が完了しました。")
        except Exception as e:
            print(f"ベクトルストアの構築中にエラーが発生しました: {e}")
            self.vector_store = None

    def create_from_text(self, text: str) -> None:
        """生の文字列からベクトルストアを構築する。"""
        try:
            if not text.strip():
                self.vector_store = None
                return
            chunks = self.text_splitter.split_text(text)
            self.vector_store = FAISS.from_texts(chunks, embedding=self.embeddings)
            print("ベクトルストアの構築が完了しました。")
        except Exception as e:
            print(f"ベクトルストアの構築中にエラーが発生しました: {e}")
            self.vector_store = None

    def save_to_disk(self, path: Optional[str] = None) -> None:
        """FAISSベクトルストアをディスクに保存"""
        if not self.vector_store:
            print("保存するベクトルストアがありません。")
            return
        target_path = path or self.persist_path
        if not target_path:
            print("保存先が指定されていません。")
            return
        try:
            Path(target_path).mkdir(parents=True, exist_ok=True)
            self.vector_store.save_local(target_path)
            print(f"ベクトルストアを保存しました: {target_path}")
        except Exception as e:
            print(f"ベクトルストアの保存中にエラーが発生しました: {e}")

    def load_from_disk(self, path: Optional[str] = None) -> None:
        """ディスクからFAISSベクトルストアを読み込み"""
        target_path = path or self.persist_path
        if not target_path:
            print("読み込み先が指定されていません。")
            self.vector_store = None
            return
        try:
            self.vector_store = FAISS.load_local(
                target_path, self.embeddings, allow_dangerous_deserialization=True
            )
            print(f"ベクトルストアを読み込みました: {target_path}")
        except Exception as e:
            print(f"ベクトルストアの読み込みに失敗しました: {e}")
            self.vector_store = None

    def get_relevant_documents(
        self,
        query: str,
        k: int = 5,
        use_mmr: bool = False,
        fetch_k: int = 20,
    ) -> List[str]:
        """クエリに関連するドキュメントのチャンクを取得する。

        Parameters
        ----------
        query:
            検索クエリ。
        k:
            返すドキュメント数。
        use_mmr:
            True の場合、Maximal Marginal Relevance 検索を使用して多様性を確保する。
        fetch_k:
            MMR 検索時に内部で取得する上位候補数。"""
        if not self.vector_store:
            return []

        if use_mmr:
            # MMR検索で、関連性と多様性を両立させる
            docs = self.vector_store.max_marginal_relevance_search(
                query, k=k, fetch_k=fetch_k
            )
        else:
            # 通常の類似度検索
            docs = self.vector_store.similarity_search(query, k=k)

        return [doc.page_content for doc in docs]

