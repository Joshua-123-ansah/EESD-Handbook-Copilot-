import asyncio
import os
import threading
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from openai import OpenAI

from backend.prompts import (
    CONVERSATION_PROMPT,
    HANDBOOK_FALLBACK_PROMPT,
    REWRITE_TO_HANDBOOK_QUERY_PROMPT,
    ROUTING_PROMPT,
    SYSTEM_PROMPT,
)
from backend.rag_store import ensure_vectorstore, get_retriever
from backend.schemas import ChatMessage, ChatRequest, ChatResponse, Citation

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=str(PROJECT_ROOT / ".env"))
FRONTEND_DIR = PROJECT_ROOT / "frontend"

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "6"))
CONTEXT_DOCS = int(os.getenv("CONTEXT_DOCS", "8"))
RELEVANCE_THRESHOLD = float(os.getenv("RELEVANCE_THRESHOLD", "0.18"))
ENABLE_QUERY_REWRITE = os.getenv("ENABLE_QUERY_REWRITE", "1") == "1"
ENABLE_CONVERSATION_LLM = os.getenv("ENABLE_CONVERSATION_LLM", "1") == "1"
ENABLE_INTENT_ROUTER = os.getenv("ENABLE_INTENT_ROUTER", "1") == "1"
OPENAI_STT_MODEL = os.getenv("OPENAI_STT_MODEL", "gpt-4o-mini-transcribe")
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
OPENAI_TTS_VOICE = os.getenv("OPENAI_TTS_VOICE", "alloy")

_sessions: Dict[str, List[ChatMessage]] = {}

_retriever = None
_vectorstore = None
_llm = None
_openai_client = None
_built_new = False
_rag_lock = threading.Lock()
_rag_error: Optional[str] = None


def _load_rag_sync() -> None:
    """Build or load Chroma once. Safe to call from many threads; captures errors for /health."""
    global _vectorstore, _retriever, _built_new, _rag_error
    with _rag_lock:
        if _vectorstore is not None:
            return
        if _rag_error is not None:
            return
        try:
            vectorstore, built_new = ensure_vectorstore()
            _retriever = get_retriever(vectorstore)
            _vectorstore = vectorstore
            _built_new = built_new
        except Exception as exc:
            _rag_error = str(exc)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    global _llm, _openai_client
    _llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0.2)
    _openai_client = OpenAI()
    # Load RAG in a thread so /health and static pages respond while Chroma builds (important for cloud deploys).
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _load_rag_sync)
    yield


app = FastAPI(title="EESD Handbook RAG Chatbot", version="0.1.0", lifespan=_lifespan)

# If you later host frontend separately, this allows the browser to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = FRONTEND_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

portfolio_dir = PROJECT_ROOT / "portfolio"
if portfolio_dir.exists():
    app.mount(
        "/portfolio",
        StaticFiles(directory=str(portfolio_dir), html=True),
        name="portfolio",
    )

imgs_dir = PROJECT_ROOT / "imgs"
if imgs_dir.exists():
    app.mount("/imgs", StaticFiles(directory=str(imgs_dir)), name="imgs")


@app.get("/health")
def health():
    return {
        "ok": True,
        "rag_ready": _vectorstore is not None,
        "rag_error": _rag_error,
        "chroma_built_new": _built_new,
    }


@app.post("/speech-to-text")
async def speech_to_text(file: UploadFile = File(...)):
    if _openai_client is None:
        raise HTTPException(status_code=503, detail="Speech service not ready.")
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Uploaded audio is empty.")

    buffer = BytesIO(audio_bytes)
    buffer.name = file.filename

    try:
        transcript = _openai_client.audio.transcriptions.create(
            model=OPENAI_STT_MODEL,
            file=buffer,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Speech-to-text failed: {exc}")

    text = getattr(transcript, "text", "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Could not transcribe audio.")
    return {"text": text}


@app.post("/text-to-speech")
async def text_to_speech(payload: Dict[str, str]):
    if _openai_client is None:
        raise HTTPException(status_code=503, detail="Speech service not ready.")

    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text provided.")

    try:
        speech = _openai_client.audio.speech.create(
            model=OPENAI_TTS_MODEL,
            voice=OPENAI_TTS_VOICE,
            input=text,
            response_format="mp3",
        )
        audio_bytes = speech.read()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Text-to-speech failed: {exc}")

    return Response(content=audio_bytes, media_type="audio/mpeg")


@app.get("/")
def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


def _format_history(history: List[ChatMessage]) -> str:
    # Keep the most recent N turns for token control.
    trimmed = history[-MAX_HISTORY_TURNS:]
    lines = []
    for turn in trimmed:
        lines.append(f"User: {turn.user}")
        lines.append(f"Assistant: {turn.assistant}")
    return "\n".join(lines)


def _route_intent(message: str, history: List[ChatMessage], llm: ChatOpenAI) -> str:
    """
    Returns 'CHITCHAT' or 'HANDBOOK'.
    LLM router avoids false RAG on thanks, meta feedback, and follow-ups like 'are you sure?'.
    """
    history_text = _format_history(history)
    human = (
        f"Recent conversation:\n{history_text}\n\n" if history_text.strip() else ""
    ) + f"Latest user message:\n{message}\n\nReply with CHITCHAT or HANDBOOK only."
    messages = [
        SystemMessage(content=ROUTING_PROMPT),
        HumanMessage(content=human),
    ]
    router_llm = llm.bind(temperature=0.0)
    raw = router_llm.invoke(messages).content.strip().upper()
    tokens = raw.replace(",", " ").split()
    if "CHITCHAT" in tokens or raw.startswith("CHITCHAT"):
        return "CHITCHAT"
    return "HANDBOOK"


def _conversation_reply(
    message: str, history: List[ChatMessage], llm: ChatOpenAI
) -> ChatResponse:
    history_text = _format_history(history)
    user_block = (
        f"Recent chat:\n{history_text}\n\n" if history_text.strip() else ""
    ) + f"Student says:\n{message}"

    messages = [
        SystemMessage(content=CONVERSATION_PROMPT),
        HumanMessage(content=user_block),
    ]
    conv_llm = llm.bind(temperature=float(os.getenv("CONVERSATION_TEMPERATURE", "0.75")))
    answer = conv_llm.invoke(messages).content.strip()
    return ChatResponse(answer=answer, citations=[], used_context=False)


def _handbook_no_context_reply(
    message: str, history: List[ChatMessage], llm: ChatOpenAI
) -> ChatResponse:
    """When retrieval fails or is too weak — helpful text without fake page citations."""
    history_text = _format_history(history)
    human = (
        (f"Recent conversation:\n{history_text}\n\n" if history_text.strip() else "")
        + f"Student question:\n{message}\n\nRespond helpfully:"
    )
    messages = [
        SystemMessage(content=HANDBOOK_FALLBACK_PROMPT),
        HumanMessage(content=human),
    ]
    fb_llm = llm.bind(temperature=0.3)
    answer = fb_llm.invoke(messages).content.strip()
    return ChatResponse(answer=answer, citations=[], used_context=False)


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if _llm is None:
        return JSONResponse(
            status_code=503,
            content={"detail": "Server is not ready yet. Try again in a few seconds."},
        )

    # Resolve history from request or server session.
    if req.history is not None:
        history = req.history
    else:
        history = _sessions.get(req.session_id, [])

    # Route: conversation vs handbook lookup (fixes thanks/meta/"are you sure?" hitting RAG).
    intent = (
        _route_intent(req.message, history, _llm)
        if ENABLE_INTENT_ROUTER
        else "HANDBOOK"
    )
    if intent == "CHITCHAT":
        if ENABLE_CONVERSATION_LLM:
            conv_resp = _conversation_reply(req.message, history, _llm)
        else:
            conv_resp = ChatResponse(
                answer="Ask me anything from the EESD PhD Graduate Student Handbook when you're ready.",
                citations=[],
                used_context=False,
            )
        if req.history is None:
            _sessions[req.session_id] = history + [
                ChatMessage(user=req.message, assistant=conv_resp.answer)
            ]
        return conv_resp

    _load_rag_sync()
    if _rag_error and _vectorstore is None:
        return JSONResponse(
            status_code=503,
            content={"detail": f"Handbook index failed: {_rag_error}"},
        )
    if _vectorstore is None:
        return JSONResponse(
            status_code=503,
            content={"detail": "Server is still building the handbook index. Try again in a few seconds."},
        )

    # Retrieve handbook evidence for this question.
    # Step 1: Make the latest question standalone (helps follow-ups like "and exceptions?").
    history_text = _format_history(history)
    standalone_query = req.message
    if ENABLE_QUERY_REWRITE and _llm is not None:
        hist_block = (
            f"Chat history:\n{history_text}\n\n" if history_text.strip() else ""
        )
        rewrite_messages = [
            SystemMessage(content=REWRITE_TO_HANDBOOK_QUERY_PROMPT),
            HumanMessage(
                content=(
                    f"{hist_block}"
                    f"Latest question:\n{req.message}\n\n"
                    f"Rewritten query:"
                )
            ),
        ]
        standalone_query = _llm.invoke(rewrite_messages).content.strip() or req.message

    # Step 2: Similarity search with a relevance gate.
    results = _vectorstore.similarity_search_with_relevance_scores(standalone_query, k=CONTEXT_DOCS)
    if not results:
        fb = _handbook_no_context_reply(req.message, history, _llm)
        if req.history is None:
            _sessions[req.session_id] = history + [
                ChatMessage(user=req.message, assistant=fb.answer)
            ]
        return fb

    best_score = max(score for _, score in results) if results else 0.0
    if best_score < RELEVANCE_THRESHOLD:
        fb = _handbook_no_context_reply(req.message, history, _llm)
        if req.history is None:
            _sessions[req.session_id] = history + [
                ChatMessage(user=req.message, assistant=fb.answer)
            ]
        return fb

    docs = [doc for doc, _score in results]

    context_blocks = []
    citations: List[Citation] = []
    for i, d in enumerate(docs[:CONTEXT_DOCS], start=1):
        page = int(d.metadata.get("page", 1))
        chunk_id = str(d.metadata.get("chunk_id", i))
        source = "EESD Graduate Student Handbook"

        context_blocks.append(f"[Source {i} | Page {page}]\n{d.page_content}")
        citations.append(Citation(page=page, chunk_id=chunk_id, source=source))

    context = "\n\n".join(context_blocks)

    # Ask the LLM to ground strictly in the provided handbook context.
    history_prefix = ""
    if history_text:
        history_prefix = f"Previous conversation (most recent first):\n{history_text}\n\n"

    user_text = (
        f"{history_prefix}"
        f"Question: {req.message}\n\n"
        f"Handbook context:\n{context}\n\n"
        "Instructions: Follow the system rules. Use the context above for handbook facts."
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_text),
    ]

    llm_resp = _llm.invoke(messages)
    answer = llm_resp.content.strip()

    # Update server-side session history.
    if req.history is None:
        history = history + [ChatMessage(user=req.message, assistant=answer)]
        _sessions[req.session_id] = history

    # If the model claims it can't find the answer, omit citations.
    not_found_phrase = "i can't find that in the handbook"
    normalized_answer = answer.lower().replace("’", "'")
    not_found = not_found_phrase in normalized_answer
    if not_found:
        return ChatResponse(answer=answer, citations=[], used_context=False)

    # Return citations (the UI will show the pages).
    return ChatResponse(answer=answer, citations=citations, used_context=True)

