# Poetry Contest — Multi-Agent AI Competition

A real-time multi-agent system where LLM-powered poets compete in a poetry contest, judged by three critics, orchestrated by a theatrical MC, and scored by a meticulous scorekeeper. You set the rules and watch it unfold live.

All agents run on LLMs via [OpenRouter](https://openrouter.ai). Free-tier models are supported.

---

## Quick Start

### 1. Get an OpenRouter API key

Sign up at [openrouter.ai](https://openrouter.ai) and create an API key.

To use free models, go to [openrouter.ai/settings/privacy](https://openrouter.ai/settings/privacy) and enable **"Allow free model publication"**.

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env`:

```env
OPENROUTER_API_KEY=sk-or-your-key-here
DEFAULT_MODEL=meta-llama/llama-3.3-70b-instruct:free
```

`DEFAULT_MODEL` is the fallback used if an agent's chosen model fails. Any OpenRouter model ID works. Free models are recommended — the whole contest can run at zero cost.

### 3. Run

```bash
docker compose up --build
```

- **Frontend:** http://localhost:5173
- **Backend API:** http://localhost:8001

---

## Setting Up the Contest

When you click **▶ Start Contest**, MC Romano will greet you and ask a single setup question. Reply in plain English — Romano understands:

| What you type | What happens |
|---|---|
| `2 rounds` | 2 rounds, Romano picks topics live |
| `3 rounds: love, war, nature` | 3 rounds with pre-set topics |
| `2 rounds, first about cats, max 8 lines` | 2 rounds, first topic set, 8-line limit |
| `1 round about robots, 12 lines max` | 1 round, fixed topic and line limit |
| `3 rounds, all live, no limit` | 3 rounds, Romano invents all topics |

After setup, Romano hires the contestants, judges, and scorekeeper autonomously — no further input needed. You can still type messages mid-contest to chat with Romano.

---

## Agents

**The entire contest runs on free models.** No OpenRouter credits required — just enable the data publication setting.

Last-known-good free model choices:

| Role | Default cast | Model |
|---|---|---|
| MC (orchestrator) | Romano | `meta-llama/llama-3.3-70b-instruct:free` |
| Contestants | Shakespeare, Bashō, Ginsberg, Mayakovsky | Llama 3.3 70B · Mistral Small 3.1 · Llama 3.2 3B (rotated) |
| Judges | Prof. Stern, Rosa Heart, Eminem | Llama 3.3 70B · Mistral Small 3.1 (rotated) |
| Scorekeeper | The Abacus | `meta-llama/llama-3.3-70b-instruct:free` |

You can swap any agent's model or rewrite their personality from the **Agent Panel** before or between contests. If you have OpenRouter credits, `anthropic/claude-3.5-haiku` is a reliable and affordable paid option.

---

## Scoring

Each judge rates every poem on three dimensions (1–10):

- **On-topic** — how well the poem addresses the round's theme
- **Originality** — creative freshness
- **Artistic value** — craft and aesthetic impact

Scores are averaged across judges. Judges who fail to respond are excluded (they don't drag scores toward neutral). The scorekeeper tallies cumulative standings after each round and crowns the overall winner.

---

## Judging Modes

Switch in the UI before the contest starts:

- **Sequential** — judges score one at a time and see each other's comments. Up to 2 deliberation rounds if scores diverge.
- **AutoGen** — judges score concurrently (first to respond appears first). Sequential discussion only if consensus isn't reached.

---

## Architecture

```
Browser (React + Vite, port 5173)
  └─ WebSocket /ws
Backend (FastAPI, port 8001)
  └─ MC Romano — create_react_agent (LangGraph)
       Tools: ask_audience · setup_contest · hire_* · start_round
              run_performance · start_deliberation · tally_scores · crown_winner
  └─ OpenRouter → LLM providers
```

MC Romano is the only true agent (a LangGraph `create_react_agent`). Contestants, judges, and the scorekeeper are LLMs invoked inside tool implementations. All messages stream to the browser via WebSocket custom events.

---

## Available Models

The UI model dropdown offers a curated list of free and paid options. Any OpenRouter model ID can also be set directly in `backend/app/agents/base.py` or via the personality editor.

**Confirmed free models that work well:**
- `meta-llama/llama-3.3-70b-instruct:free` — best overall quality free option
- `mistralai/mistral-small-3.1-24b-instruct:free` — solid alternative
- `meta-llama/llama-3.2-3b-instruct:free` — lightweight, fast
- `google/gemini-2.0-flash-exp:free` — Google option

> Free model availability can change on OpenRouter's end. If a model stops working, swap it in the Agent Panel or in `base.py`.

---

## Troubleshooting

| Error | Fix |
|---|---|
| "No endpoints found matching your data policy" | Enable free model publication at [openrouter.ai/settings/privacy](https://openrouter.ai/settings/privacy) |
| "402 spend limit exceeded" | Increase limit at [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys) |
| "400 Developer instruction not enabled" | Model doesn't support system prompts — switch model in the agent panel |

---

## License

MIT
