from backend.rag_store import ensure_vectorstore


if __name__ == "__main__":
    vectorstore, built_new = ensure_vectorstore()
    print("Vector store ready.")
    print("Built new:", built_new)
    print("Handbook ingestion complete.")

