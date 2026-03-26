from typing import List, Optional
from pydantic import BaseModel


class ChatMessage(BaseModel):
    user: str
    assistant: str


class ChatRequest(BaseModel):
    session_id: str
    message: str
    history: Optional[List[ChatMessage]] = None


class Citation(BaseModel):
    page: int
    chunk_id: str
    source: str


class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation] = []
    used_context: bool = True

