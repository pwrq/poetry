from __future__ import annotations
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field


AgentRole = Literal["organizer", "contestant", "judge", "scorekeeper", "user"]
Visibility = Literal["all", "judges_only", "organizer_only"]
Phase = Literal[
    "idle", "setup", "performance", "deliberation", "scoring", "post_contest"
]


class AgentConfig(BaseModel):
    id: str
    name: str
    role: AgentRole
    model: str
    personality: str


class AgentMessage(BaseModel):
    slot: int
    agent_id: str
    agent_name: str
    agent_role: AgentRole
    content: str
    visibility: Visibility = "all"
    round_number: int
    phase: Phase
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).strftime("%H:%M:%S"))


class Poem(BaseModel):
    contestant_id: str
    contestant_name: str
    text: str
    round_number: int


class RoundScore(BaseModel):
    contestant_id: str
    contestant_name: str
    on_topic: float
    originality: float
    artistic_value: float
    total: float


class CumulativeScore(BaseModel):
    contestant_id: str
    contestant_name: str
    total: float
    rank: int


# WebSocket client→server messages
class UserTopicMsg(BaseModel):
    type: Literal["user_topic"]
    data: dict  # {topic: str}


class UserMessageMsg(BaseModel):
    type: Literal["user_message"]
    data: dict  # {content: str}


class ChangeModelMsg(BaseModel):
    type: Literal["change_model"]
    data: dict  # {agent_id: str, model: str}


class ChangePersonalityMsg(BaseModel):
    type: Literal["change_personality"]
    data: dict  # {agent_id: str, personality: str, erase_memory: bool}


class StartContestMsg(BaseModel):
    type: Literal["start_contest"]
    data: dict


class ResetContestMsg(BaseModel):
    type: Literal["reset_contest"]
    data: dict
