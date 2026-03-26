# EESD Handbook RAG Chat (Demo)

This project provides a conversational chatbot for the `EESD_Handbook_2024-2025AY-FINAL.pdf`.
It uses a RAG pipeline:

1. Ingest the PDF into a local vector index (Chroma).
2. Retrieve relevant handbook chunks for each question.
3. Ask an LLM to answer using only the retrieved handbook context.

## Quick start

1. Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Set environment variables:

```bash
cp .env.example .env
```

Then fill in `OPENAI_API_KEY` in `.env`.

3. Run the server (this will build the index on first run):

```bash
uvicorn backend.app:app --reload --port 8000
```

Open: `http://localhost:8000`

## Important notes

- Answers are intended to be grounded in the handbook context. If the LLM cannot find the answer, it should reply:
  `I can't find that in the handbook.`
- If the assistant mis-classifies chat vs handbook, check `ENABLE_INTENT_ROUTER` in `.env`.
- If retrieval is too strict or too loose, tune `RELEVANCE_THRESHOLD` in `.env`.
- The first run may take a short time to create the vector index.
- Voice mode is supported: click `Start Voice`, speak, then click `Stop Voice`. The assistant transcribes speech and speaks its reply.

