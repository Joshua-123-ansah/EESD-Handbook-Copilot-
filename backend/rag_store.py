import os
from pathlib import Path
from typing import List, Optional, Tuple

from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=str(PROJECT_ROOT / ".env"))
HANDBOOK_PATH = PROJECT_ROOT / "EESD_Handbook_2024-2025AY-FINAL.pdf"

_chroma_env = os.getenv("CHROMA_DIR", "chroma_db")
CHROMA_DIR = (
    Path(_chroma_env)
    if Path(_chroma_env).is_absolute()
    else (PROJECT_ROOT / _chroma_env)
)
TOP_K = int(os.getenv("TOP_K", "8"))

OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


def _require_openai_key() -> None:
    # OpenAIEmbeddings fails at construction time if this is missing; we make it clearer here.
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "Missing OPENAI_API_KEY. Create a `.env` file in the project root (same folder as `requirements.txt`) "
            "and set OPENAI_API_KEY there, or export it in your shell."
        )


def _build_vectorstore() -> Chroma:
    if not HANDBOOK_PATH.exists():
        raise FileNotFoundError(f"Handbook PDF not found at: {HANDBOOK_PATH}")

    loader = PyPDFLoader(str(HANDBOOK_PATH))
    # PyPDFLoader typically returns 0-based page numbers in metadata.
    page_docs = loader.load()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150,
    )
    chunks = splitter.split_documents(page_docs)

    for i, doc in enumerate(chunks):
        # Normalize page to 1-based for human-friendly citations.
        page = doc.metadata.get("page", 0)
        try:
            page = int(page) + 1
        except Exception:
            page = 1

        doc.metadata["page"] = page
        doc.metadata["chunk_id"] = str(i)

    _require_openai_key()
    embeddings = OpenAIEmbeddings(model=OPENAI_EMBEDDING_MODEL)
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(CHROMA_DIR),
    )
    vectorstore.persist()
    return vectorstore


def ensure_vectorstore() -> Tuple[Chroma, bool]:
    """
    Returns (vectorstore, built_new).
    """
    _require_openai_key()
    embeddings = OpenAIEmbeddings(model=OPENAI_EMBEDDING_MODEL)

    # Chroma persists multiple files; a non-empty directory usually means it exists.
    built_new = False
    if not CHROMA_DIR.exists() or not any(CHROMA_DIR.iterdir()):
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        vectorstore = _build_vectorstore()
        built_new = True
    else:
        vectorstore = Chroma(
            persist_directory=str(CHROMA_DIR),
            embedding_function=embeddings,
        )

    return vectorstore, built_new


def get_retriever(vectorstore: Chroma):
    # Return retriever with consistent top_k.
    return vectorstore.as_retriever(search_kwargs={"k": TOP_K})


def retrieve_with_scores(vectorstore: Chroma, query: str, k: int) -> List[Tuple[object, float]]:
    """
    Returns [(Document, relevance_score), ...]
    """
    # LangChain Chroma returns relevance_score where higher is more relevant.
    results = vectorstore.similarity_search_with_relevance_scores(query, k=k)
    return results

