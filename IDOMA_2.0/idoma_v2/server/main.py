from __future__ import annotations

import secrets
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..config import APP_NAME, APP_VERSION, CORS_ORIGINS
from ..db import (
    init_db, list_conversations, get_messages, get_legacy_memories, list_memory_facts, conversation_exists,
    agent_heartbeat, claim_agent_task, finish_agent_task, get_agent_task, agent_is_online,
    create_reminder, list_reminders, complete_reminder, snooze_reminder, delete_reminder,
)
from ..security import get_api_token
from ..services.assistant import process_message, new_conversation, tool_catalog

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
TOKEN = get_api_token()

app = FastAPI(title=f"{APP_NAME} API", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS != ["*"] else ["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

bearer = HTTPBearer(auto_error=False)


@app.on_event("startup")
def startup() -> None:
    init_db()


def require_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> None:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Token mancante.")
    if not secrets.compare_digest(credentials.credentials, TOKEN):
        raise HTTPException(status_code=403, detail="Token non valido.")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    conversation_id: str | None = None


class ReminderRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    due_at: str = Field(min_length=10, max_length=64)


class ReminderSnooze(BaseModel):
    minutes: int = Field(default=10, ge=1, le=10080)


class AgentHeartbeat(BaseModel):
    device_id: str = Field(min_length=1, max_length=100)
    device_name: str = Field(min_length=1, max_length=100)


class AgentResult(BaseModel):
    task_id: int
    result: str = Field(max_length=12000)
    success: bool


class VoiceToggleRequest(BaseModel):
    enabled: bool


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION}


@app.get("/api/status", dependencies=[Depends(require_token)])
def runtime_status() -> dict:
    controller = getattr(app.state, "idoma_controller", None)
    voice_enabled = bool(controller and controller.voice_action.isChecked())
    voice_status = str(getattr(controller, "voice_status", "Servizio vocale desktop non collegato"))
    return {
        "version": APP_VERSION,
        "agent_online": agent_is_online(),
        "voice_enabled": voice_enabled,
        "voice_status": voice_status,
    }


@app.post("/api/voice/toggle", dependencies=[Depends(require_token)])
def toggle_voice(request: VoiceToggleRequest) -> dict:
    controller = getattr(app.state, "idoma_controller", None)
    if controller is None:
        raise HTTPException(status_code=503, detail="Controllo vocale desktop non disponibile.")
    controller.request_voice_enabled(request.enabled)
    return {"accepted": True, "enabled": request.enabled}


@app.post("/api/voice/listen", dependencies=[Depends(require_token)])
def request_voice_listen() -> dict:
    controller = getattr(app.state, "idoma_controller", None)
    if controller is None:
        raise HTTPException(status_code=503, detail="Controllo vocale desktop non disponibile.")
    controller.request_manual_voice()
    return {"accepted": True, "mode": "push_to_talk"}


@app.get("/api/conversations", dependencies=[Depends(require_token)])
def conversations() -> list[dict]:
    return list_conversations()


@app.post("/api/conversations", dependencies=[Depends(require_token)])
def create_new_conversation() -> dict:
    return new_conversation()


@app.get("/api/conversations/{conversation_id}/messages", dependencies=[Depends(require_token)])
def conversation_messages(conversation_id: str) -> list[dict]:
    if not conversation_exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversazione non trovata.")
    return get_messages(conversation_id, 100)


@app.post("/api/chat", dependencies=[Depends(require_token)])
def chat(request: ChatRequest) -> dict:
    try:
        return process_message(request.message, request.conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/api/memory", dependencies=[Depends(require_token)])
def memory() -> list[dict]:
    return get_legacy_memories(100) + list_memory_facts(100)


@app.get("/api/reminders", dependencies=[Depends(require_token)])
def reminders() -> list[dict]:
    return list_reminders(False, 100)


@app.post("/api/reminders", dependencies=[Depends(require_token)])
def add_reminder(request: ReminderRequest) -> dict:
    try:
        return create_reminder(request.title, request.due_at)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/reminders/{reminder_id}/complete", dependencies=[Depends(require_token)])
def finish_reminder(reminder_id: int) -> dict:
    if not complete_reminder(reminder_id):
        raise HTTPException(status_code=404, detail="Promemoria non trovato o già completato.")
    return {"status": "completed", "id": reminder_id}


@app.post("/api/reminders/{reminder_id}/snooze", dependencies=[Depends(require_token)])
def postpone_reminder(reminder_id: int, request: ReminderSnooze) -> dict:
    item = snooze_reminder(reminder_id, request.minutes)
    if item is None:
        raise HTTPException(status_code=404, detail="Promemoria non trovato.")
    return item


@app.delete("/api/reminders/{reminder_id}", dependencies=[Depends(require_token)])
def remove_reminder(reminder_id: int) -> dict:
    if not delete_reminder(reminder_id):
        raise HTTPException(status_code=404, detail="Promemoria non trovato.")
    return {"status": "deleted", "id": reminder_id}


@app.get("/api/tools", dependencies=[Depends(require_token)])
def available_tools() -> list[dict]:
    """List capabilities available through the connected Windows agent."""
    return tool_catalog()


@app.post("/api/agent/heartbeat", dependencies=[Depends(require_token)])
def desktop_agent_heartbeat(request: AgentHeartbeat) -> dict:
    agent_heartbeat(request.device_id, request.device_name)
    return {"status": "online"}


@app.post("/api/agent/claim", dependencies=[Depends(require_token)])
def desktop_agent_claim(request: AgentHeartbeat) -> dict:
    agent_heartbeat(request.device_id, request.device_name)
    return {"task": claim_agent_task()}


@app.post("/api/agent/result", dependencies=[Depends(require_token)])
def desktop_agent_result(request: AgentResult) -> dict:
    finish_agent_task(request.task_id, request.result, request.success)
    return {"status": "recorded"}


@app.get("/api/agent/tasks/{task_id}", dependencies=[Depends(require_token)])
def desktop_agent_task_status(task_id: int) -> dict:
    task = get_agent_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Attività non trovata.")
    return task


@app.get("/")
def home():
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
