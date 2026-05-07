from __future__ import annotations
import asyncio
import copy
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.config import settings
from app.ws.manager import manager
from app.graph.contest import build_contest_graph
from app.graph.state import make_initial_state
from app.agents.base import RUNTIME_DEFAULTS
from app.agents.organizer import organizer_chat, parse_setup_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Shared contest session ────────────────────────────────────────────────────

class ContestSession:
    def __init__(self):
        self._init()

    def _init(self):
        # Only user + organizer in configs at contest start; others hired dynamically
        self.agent_configs = copy.deepcopy(RUNTIME_DEFAULTS)
        self.judging_mode = "sequential"
        self.checkpointer = MemorySaver()
        self.graph = build_contest_graph(
            self.checkpointer,
            model=self.agent_configs["organizer"]["model"],
        )
        self.thread_id = "contest-1"
        self.config = {
            "configurable": {"thread_id": self.thread_id},
            "recursion_limit": 200,
        }
        self.initial_state = make_initial_state(self.agent_configs)
        self.message_history: list[dict] = []
        self.running = False
        self._waiting_for_input = False
        self._resume_event: asyncio.Event = asyncio.Event()
        self._resume_payload: dict = {}

    def reset(self, preserve_configs: bool = False):
        saved_organizer = copy.deepcopy(self.agent_configs.get("organizer")) if preserve_configs else None
        saved_user = copy.deepcopy(self.agent_configs.get("user")) if preserve_configs else None
        saved_mode = self.judging_mode if preserve_configs else None
        self._init()
        if preserve_configs:
            # Preserve user + organizer configs (model/name/personality changes); all hired agents are cleared
            if saved_organizer:
                self.agent_configs["organizer"] = saved_organizer
            if saved_user:
                self.agent_configs["user"] = saved_user
            self.judging_mode = saved_mode
            # Rebuild graph with the preserved organizer model — _init() used the default
            self.graph = build_contest_graph(
                self.checkpointer,
                model=self.agent_configs["organizer"]["model"],
            )
            self.initial_state = make_initial_state(self.agent_configs)
            self.initial_state["judging_mode"] = saved_mode

    def resume(self, payload: dict):
        self._resume_payload = payload
        self._resume_event.set()

    async def wait_for_resume(self) -> dict:
        self._waiting_for_input = True
        await self._resume_event.wait()
        self._waiting_for_input = False
        self._resume_event.clear()
        payload = self._resume_payload
        self._resume_payload = {}
        return payload


session = ContestSession()

# Ordered fallback chain for Romano's model when rate-limited.
# Tried in sequence until one works or all are exhausted.
_ORGANIZER_FALLBACK_CHAIN = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "anthropic/claude-3.5-haiku",
]


def _next_organizer_model(current: str, tried: set[str]) -> str | None:
    """Return the next untried model from the fallback chain, or None if all exhausted."""
    for m in _ORGANIZER_FALLBACK_CHAIN:
        if m not in tried:
            return m
    return None


# ── Graph runner ──────────────────────────────────────────────────────────────

async def run_graph():
    """Run the contest graph, streaming custom events to all WebSocket clients.

    Automatically retries with the next model in _ORGANIZER_FALLBACK_CHAIN
    if Romano's model is rate-limited (429). Resets and restarts from scratch
    on each retry so state is clean.
    """
    import re as _re
    tried_models: set[str] = set()

    while True:
        session.running = True
        input_or_command: dict | Command = session.initial_state

        try:
            while True:
                interrupted = False
                async for mode, chunk in session.graph.astream(
                    input_or_command,
                    config=session.config,
                    stream_mode=["updates", "custom"],
                ):
                    if mode == "custom":
                        payload = chunk
                        if payload.get("type") == "agent_message" and "data" in payload:
                            payload["data"].setdefault(
                                "timestamp",
                                datetime.now(timezone.utc).strftime("%H:%M:%S")
                            )
                        session.message_history.append(payload)
                        await manager.broadcast(payload)

                        if payload.get("type") == "config_sync" and "data" in payload:
                            cfg = payload["data"]
                            agent_id = cfg.get("id")
                            if agent_id:
                                session.agent_configs[agent_id] = cfg

                    elif mode == "updates":
                        if "__interrupt__" in chunk:
                            interrupted = True
                            resume_payload = await session.wait_for_resume()
                            input_or_command = Command(resume=resume_payload)
                            break

                if not interrupted:
                    break  # graph reached END naturally

            break  # contest finished successfully

        except asyncio.CancelledError:
            break

        except Exception as exc:
            error_str = str(exc)
            if "429" in error_str:
                m = _re.search(r"([\w/.\-:]+(?::free)?)\s+is temporarily rate.limited", error_str)
                rl_model = m.group(1) if m else session.agent_configs.get("organizer", {}).get("model", "")
                tried_models.add(rl_model)

                next_model = _next_organizer_model(rl_model, tried_models)
                if next_model:
                    await manager.broadcast({"type": "error", "data": {
                        "message": f"Rate limited on {rl_model} — retrying with {next_model}…"
                    }})
                    session.agent_configs["organizer"]["model"] = next_model
                    await manager.broadcast({"type": "config_sync", "data": session.agent_configs["organizer"]})
                    # Reset state cleanly and retry
                    session.checkpointer = MemorySaver()
                    session.graph = build_contest_graph(session.checkpointer, model=next_model)
                    session.thread_id = "contest-1"
                    session.config = {"configurable": {"thread_id": session.thread_id}, "recursion_limit": 200}
                    session.message_history = []
                    session.initial_state = make_initial_state(session.agent_configs)
                    await manager.broadcast({"type": "history_sync", "data": []})
                    continue  # retry the outer while loop with new model
                else:
                    await manager.broadcast({"type": "error", "data": {
                        "message": "All fallback models are rate-limited. Please wait a moment and reset."
                    }})
                    break
            else:
                logger.exception("Graph error: %s", exc)
                await manager.broadcast({"type": "error", "data": {"message": str(exc)}})
                break

        finally:
            session.running = False


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)

    # Replay agent messages for reconnecting clients
    history_msgs = [
        m["data"] for m in session.message_history if m.get("type") == "agent_message"
    ]
    if history_msgs:
        await manager.send_to(ws, {"type": "history_sync", "data": history_msgs})

    # Sync current agent configs (user + organizer + any dynamically hired agents)
    for cfg in session.agent_configs.values():
        await manager.send_to(ws, {"type": "config_sync", "data": cfg})

    graph_task: asyncio.Task | None = None
    # Graph does NOT auto-start — user must click "Start Contest" in the UI.

    try:
        while True:
            msg = await ws.receive_json()
            msg_type = msg.get("type")
            data = msg.get("data", {})

            if msg_type in ("user_topic", "user_message"):
                content = data.get("content") or data.get("topic", "")
                user_name = session.agent_configs.get("user", {}).get("name", "Boss")
                ts = datetime.now(timezone.utc).strftime("%H:%M:%S")

                known_slots = [
                    m["data"].get("slot", 0)
                    for m in session.message_history
                    if m.get("type") == "agent_message" and "data" in m
                ]
                user_slot = (max(known_slots) + 1) if known_slots else len(session.message_history) + 1

                user_msg = {
                    "type": "agent_message",
                    "data": {
                        "slot": user_slot,
                        "agent_id": "user",
                        "agent_name": user_name,
                        "agent_role": "user",
                        "content": content,
                        "visibility": "organizer_only",
                        "round_number": 0,
                        "phase": "idle",
                        "timestamp": ts,
                    },
                }
                session.message_history.append(user_msg)
                await manager.broadcast(user_msg)

                if session._waiting_for_input:
                    session.resume({"message": content})
                elif session.running:
                    async def _chat(msg_content: str, uname: str):
                        visible = [
                            m["data"] for m in session.message_history
                            if m.get("type") == "agent_message"
                        ]
                        slot = len(session.message_history) + 1
                        response = await organizer_chat(
                            user_name=uname,
                            user_message=msg_content,
                            agent_cfg=session.agent_configs["organizer"],
                            recent_messages=visible,
                            slot=slot,
                        )
                        session.message_history.append(response)
                        await manager.broadcast(response)
                        # Update setup context: re-parse topics from combined message
                        try:
                            current = session.graph.get_state(session.config)
                            if current and current.values:
                                total_rounds = current.values.get("total_rounds", 3)
                                organizer_cfg = session.agent_configs.get("organizer", {})
                                loop = asyncio.get_event_loop()
                                parsed = await loop.run_in_executor(
                                    None, parse_setup_message,
                                    organizer_cfg, msg_content, total_rounds,
                                )
                                if parsed.get("topics"):
                                    session.graph.update_state(
                                        session.config, {
                                            "preset_topics": parsed["topics"],
                                            "line_limit": parsed.get("line_limit", 0) or current.values.get("line_limit", 0),
                                        }
                                    )
                        except Exception:
                            pass
                    asyncio.create_task(_chat(content, user_name))

            elif msg_type == "change_model":
                agent_id = data.get("agent_id")
                model = data.get("model")
                if agent_id and model and agent_id in session.agent_configs:
                    session.agent_configs[agent_id]["model"] = model
                    try:
                        current = session.graph.get_state(session.config)
                        if current and current.values:
                            cfgs = dict(current.values.get("agent_configs", {}))
                            if agent_id in cfgs:
                                cfgs[agent_id] = {**cfgs[agent_id], "model": model}
                                session.graph.update_state(
                                    session.config, {"agent_configs": cfgs}
                                )
                    except Exception:
                        pass
                    await manager.broadcast({"type": "config_sync", "data": session.agent_configs[agent_id]})

            elif msg_type == "change_personality":
                agent_id = data.get("agent_id")
                personality = data.get("personality", "")
                erase = data.get("erase_memory", False)
                new_name = data.get("name")
                if agent_id and agent_id in session.agent_configs:
                    if personality:
                        session.agent_configs[agent_id]["personality"] = personality
                    if new_name:
                        session.agent_configs[agent_id]["name"] = new_name
                    try:
                        current = session.graph.get_state(session.config)
                        if current and current.values:
                            cfgs = dict(current.values.get("agent_configs", {}))
                            mems = dict(current.values.get("agent_memories", {}))
                            if agent_id in cfgs:
                                updates = {}
                                if personality:
                                    updates["personality"] = personality
                                if new_name:
                                    updates["name"] = new_name
                                cfgs[agent_id] = {**cfgs[agent_id], **updates}
                            if erase:
                                mems[agent_id] = []
                            session.graph.update_state(
                                session.config,
                                {"agent_configs": cfgs, "agent_memories": mems},
                            )
                    except Exception:
                        pass
                    await manager.broadcast({"type": "config_sync", "data": session.agent_configs[agent_id]})

            elif msg_type == "change_judging_mode":
                mode = data.get("mode", "sequential")
                if mode in ("sequential", "autogen"):
                    session.judging_mode = mode
                    try:
                        current = session.graph.get_state(session.config)
                        if current and current.values:
                            session.graph.update_state(session.config, {"judging_mode": mode})
                    except Exception:
                        pass
                    await manager.broadcast({"type": "state_update", "data": {"judging_mode": mode}})

            elif msg_type == "reset_contest":
                if graph_task and not graph_task.done():
                    graph_task.cancel()
                    try:
                        await graph_task
                    except (asyncio.CancelledError, Exception):
                        pass
                session.reset(preserve_configs=True)
                await manager.broadcast({"type": "history_sync", "data": []})
                await manager.broadcast({"type": "state_update", "data": {
                    "phase": "idle", "current_round": 0,
                    "waiting_for_user": False, "waiting_prompt": "",
                }})
                # Only sync user + organizer after reset (hired agents cleared)
                for cfg in session.agent_configs.values():
                    await manager.broadcast({"type": "config_sync", "data": cfg})
                graph_task = None

            elif msg_type == "start_contest":
                if graph_task and not graph_task.done():
                    graph_task.cancel()
                    try:
                        await graph_task
                    except (asyncio.CancelledError, Exception):
                        pass
                if not session.running:
                    session.reset(preserve_configs=True)
                    await manager.broadcast({"type": "history_sync", "data": []})
                    await manager.broadcast({"type": "state_update", "data": {
                        "phase": "idle", "current_round": 0,
                        "waiting_for_user": False, "waiting_prompt": "",
                    }})
                    for cfg in session.agent_configs.values():
                        await manager.broadcast({"type": "config_sync", "data": cfg})
                    graph_task = asyncio.create_task(run_graph())

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)
        if not manager.active and graph_task and not graph_task.done():
            graph_task.cancel()
            try:
                await graph_task
            except (asyncio.CancelledError, Exception):
                pass


# ── Models endpoint ───────────────────────────────────────────────────────────

_CURATED_MODELS = [
    # ── Anthropic ────────────────────────────────────────────────────────────
    {"id": "anthropic/claude-sonnet-4-5",                   "name": "Claude Sonnet 4.5"},
    {"id": "anthropic/claude-3.5-sonnet",                   "name": "Claude 3.5 Sonnet"},
    {"id": "anthropic/claude-3.5-haiku",                    "name": "Claude 3.5 Haiku"},
    # ── Google ───────────────────────────────────────────────────────────────
    {"id": "google/gemini-2.5-flash-lite",                  "name": "Gemini 2.5 Flash Lite"},
    {"id": "google/gemini-2.0-flash-exp:free",              "name": "Gemini 2.0 Flash (free)"},
    # ── Meta ─────────────────────────────────────────────────────────────────
    {"id": "meta-llama/llama-3.3-70b-instruct:free",        "name": "Llama 3.3 70B (free)"},
    {"id": "meta-llama/llama-3.2-3b-instruct:free",         "name": "Llama 3.2 3B (free)"},
    # ── Mistral ──────────────────────────────────────────────────────────────
    {"id": "mistralai/mistral-small-3.1-24b-instruct:free", "name": "Mistral Small 3.1 24B (free)"},
]


@app.get("/api/models")
async def list_models():
    return {"models": _CURATED_MODELS}
