# Content Pipeline — Multi-Agent System

Turn one idea into several publish-ready LinkedIn posts using a pipeline of
specialized AI agents with **feedback loops**, built with **LangGraph** and the
free **Groq API**.

```
        ┌───────────── feedback loop #1 ─────────────┐
        ▼                                            │
INPUT ──► RESEARCHER ──► WRITER ──► EDITOR ──rejected─┘ (revise)
                          ▲           │approved
                          │           ▼
             (revise) ──rejected─ FACT-CHECKER
                                      │verified
                                      ▼
                                   OUTPUT (one post per persona)
```

## Agents

| Agent       | Job                                                                 |
|-------------|---------------------------------------------------------------------|
| Researcher  | Gathers angles, hooks and facts for the topic                       |
| Writer      | Drafts one LinkedIn post per audience persona                       |
| Editor      | Judges structure/tone/hook; rejects weak posts with feedback        |
| Fact-Checker| Verifies every claim against the researcher's material              |
| Finalize    | Reports which posts are publish-ready and which failed (and why)    |

Rejected posts are rewritten with the feedback and re-reviewed, up to
`MAX_EDITOR_ROUNDS` / `MAX_FACTCHECK_ROUNDS` (see `pipeline/agents.py`).

## Setup

```bash
cd content-pipeline
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env           # then paste your free key from https://console.groq.com/keys
```

## Run

### CLI

```bash
python main.py "ICPC / Competitive Programming"
# or just: python main.py  (it will prompt you)
```

Output: posts printed to the console + a run folder under `outputs/run-*/`
with `report.md` and one illustration per published post in `images/`.

### Web UI (Streamlit) — quick option

```bash
streamlit run app.py
```

### Web UI (React + FastAPI) — the polished one

```bash
# Terminal 1 — API server (streams agent events over SSE):
./.venv/bin/uvicorn api:api --port 8000

# Terminal 2 — React dev server (hot reload) at http://localhost:5173:
cd frontend
npm run dev
```

Open **http://localhost:5173**: type an idea, click Run pipeline, and watch the
agent log stream live; each post card fills in its AI illustration as it's
generated (free image tier is ~1 image/45s, so images take a couple of minutes).

**Production mode:** `cd frontend && npm run build`, then just run the API
server — it serves the built UI at http://localhost:8000.

```
POST /api/run              {idea} → {run_id}   starts the pipeline in background
GET  /api/stream/{run_id}  SSE: log events → posts → image events → done
GET  /api/image/{run_id}/{file}               generated illustrations
```



## What's worth studying here (interview talking points)

- **Feedback loops beat straight lines**: quality comes from the editor→writer
  and fact-checker→writer cycles, not a one-shot chain.
- **Structured outputs** (`with_structured_output` + Pydantic) make agents
  composable: each returns a typed object, not free text to be guessed at.
- **LangGraph state**: one `TypedDict` state with an appending `run_log`
  channel (`Annotated[..., operator.add]`) shows how channels merge updates.
- **Retry caps**: agent loops must terminate — routers count rounds and
  hard-stop, so the graph can never loop forever.

## Ideas to extend (good "v2" stories)

- Give the fact-checker a real web-search tool (Tavily) instead of research-only
- Human-in-the-loop: pause at a `human_review` node before publishing
- Add more personas / channels (X/Twitter thread, blog outline)
- Stream live progress (`app.stream(...)`) into a small web UI
