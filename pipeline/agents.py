"""Agent nodes. Each agent = one focused LLM call with structured output.

Posts move through statuses:
    draft -> editor_pass | failed_editor -> factcheck_pass | failed_factcheck

Rejected posts get feedback attached and are revised by the Writer Agent
until approved or until retry limits (MAX_*_ROUNDS) are exhausted.
"""

import os

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from .prompts import (
    RESEARCHER,
    WRITER,
    WRITER_REVISION,
    EDITOR,
    FACT_CHECKER,
    FACT_CHECKER_USER,
    PERSONAS,
)
from .schemas import Research, Draft, Review, FactCheck, FinalPost, PipelineResult, Post

load_dotenv()

# How many revision loops a post gets at each gate before it is dropped.
MAX_EDITOR_ROUNDS = 2
MAX_FACTCHECK_ROUNDS = 2


def _llm(temperature: float = 0.7) -> ChatGroq:
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError(
            "GROQ_API_KEY is not set. Copy .env.example to .env and add your free "
            "key from https://console.groq.com/keys"
        )
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    return ChatGroq(model=model, temperature=temperature)


def _structured(schema, temperature: float = 0.7):
    """LLM bound to a Pydantic schema.

    Uses Groq's native json_schema response format instead of tool-calling:
    some models (e.g. gpt-oss) occasionally emit text without calling the
    tool, which hard-fails the request; json_schema mode is more reliable.
    """
    return _llm(temperature).with_structured_output(schema, method="json_schema")


# --- Agent 1: Researcher ----------------------------------------------------

def research_node(state) -> dict:
    research: Research = _structured(Research).invoke(
        [SystemMessage(content=RESEARCHER.format(topic=state["topic"])),
         HumanMessage(content="Do the research now.")]
    )
    return {
        "research": research,
        "run_log": [f"[research] {len(research.angles)} angles, "
                    f"{len(research.key_facts)} key facts"],
    }


# --- Agent 2: Writer ---------------------------------------------------------

def write_node(state) -> dict:
    personas_block = "\n".join(f"- {p}" for p in PERSONAS)
    draft = _structured(Draft).invoke(
        [SystemMessage(content=WRITER.format(
            n_posts=len(PERSONAS), personas=personas_block)),
         HumanMessage(content=f"Research material:\n{state['research'].model_dump_json()}")]
    )
    posts = [
        {"style": p.style, "text": p.text, "status": "draft",
         "feedback": "", "editor_rounds": 0, "factcheck_rounds": 0}
        for p in draft.posts
    ]
    return {
        "posts": posts[:len(PERSONAS)],
        "run_log": [f"[write] drafted {len(posts)} posts"],
    }


def revise_node(state) -> dict:
    """Writer rewrites rejected posts (both editor and fact-checker rejections)."""
    posts = state["posts"]
    targets = [p for p in posts if p["status"] in ("draft", "editor_pass") and p["feedback"]]
    if not targets:
        return {"posts": posts, "run_log": ["[revise] nothing to revise"]}
    # editor rejections -> status stays 'draft'; fact-checker rejections -> 'editor_pass'
    reviewer = "the Editor Agent (gate: structure, tone, hook)" \
        if targets[0]["status"] == "draft" else "the Fact-Checker Agent (gate: unsupported claims)"
    revised = _structured(Post).batch(
        [
            [
                SystemMessage(content=WRITER_REVISION.format(
                    post=p["text"], reviewer=reviewer, feedback=p["feedback"])),
                HumanMessage(content="Revise the post now."),
            ]
            for p in targets
        ],
        return_exceptions=True,
    )
    rewritten = 0
    for p, r in zip(targets, revised):
        if isinstance(r, Exception) or r is None:
            try:  # single synchronous retry before giving up on this post
                r = _structured(Post).invoke(
                    [SystemMessage(content=WRITER_REVISION.format(
                        post=p["text"], reviewer=reviewer, feedback=p["feedback"])),
                     HumanMessage(content="Revise the post now.")])
            except Exception:
                continue  # keep old text; next review round decides again
        p["text"] = r.text
        p["feedback"] = ""
        rewritten += 1
    return {"posts": posts,
            "run_log": [f"[revise] writer rewrote {rewritten}/{len(targets)} posts"]}


# --- Agent 3: Editor ---------------------------------------------------------

def editor_node(state) -> dict:
    posts = state["posts"]
    targets = [p for p in posts if p["status"] == "draft"]
    if not targets:
        return {"posts": posts, "run_log": ["[editor] nothing to review"]}
    reviews: list = _structured(Review, temperature=0.2).batch(
        [[SystemMessage(content=EDITOR),
          HumanMessage(content=f"Post:\n---\n{p['text']}\n---")] for p in targets],
        return_exceptions=True,
    )
    results = []
    for p, r in zip(targets, reviews):
        p["editor_rounds"] += 1
        if isinstance(r, Exception) or r is None:
            r = Review(verdict="reject", feedback="Review could not be parsed; revise and resubmit.")
        if r.verdict == "publish":
            p["status"], p["feedback"] = "editor_pass", ""
            results.append(f"'{p.style if hasattr(p, 'style') else p['style']}': publish")
        elif p["editor_rounds"] >= MAX_EDITOR_ROUNDS:
            p["status"], p["feedback"] = "failed_editor", r.feedback
            results.append(f"'{p['style']}': REJECTED (max editor retries)")
        else:
            p["status"], p["feedback"] = "draft", r.feedback
            results.append(f"'{p['style']}': rejected -> revise")
    passed = sum(1 for r in results if "publish" in r)
    return {"posts": posts} | {"run_log": [f"[editor] round done: {passed}/{len(targets)} "
                                           f"passed ({'; '.join(results)})"]}


def route_after_editor(state) -> str:
    """Feedback loop #1: rejected posts go back to the Writer, else move on."""
    if any(p["status"] == "draft" for p in state["posts"]):
        return "revise"
    return "factcheck"


# --- Agent 4: Fact-Checker ---------------------------------------------------

def factcheck_node(state) -> dict:
    posts = state["posts"]
    targets = [p for p in posts if p["status"] == "editor_pass"]
    if not targets:
        return {"posts": posts, "run_log": ["[factcheck] nothing to verify"]}
    research_json = state["research"].model_dump_json()
    checks: list = _structured(FactCheck, temperature=0.2).batch(
        [[SystemMessage(content=FACT_CHECKER),
          HumanMessage(content=FACT_CHECKER_USER.format(post=p["text"], research=research_json))]
         for p in targets],
        return_exceptions=True,
    )
    results = []
    for p, c in zip(targets, checks):
        p["factcheck_rounds"] += 1
        if isinstance(c, Exception) or c is None:
            c = FactCheck(verdict="reject", unsupported_claims=[], note="Verification failed to parse; revise.")
        if c.verdict == "publish":
            p["status"], p["feedback"] = "factcheck_pass", ""
            results.append(f"'{p['style']}': verified")
        elif p["factcheck_rounds"] >= MAX_FACTCHECK_ROUNDS:
            p["status"] = "failed_factcheck"
            p["feedback"] = "; ".join(c.unsupported_claims) or c.note
            results.append(f"'{p['style']}': REJECTED (max fact-check retries)")
        else:
            p["status"] = "editor_pass"  # stays in the fact-check loop after revision
            p["feedback"] = "; ".join(c.unsupported_claims) or c.note
            results.append(f"'{p['style']}': claims not substantiated -> revise")
    verified = sum(1 for r in results if "verified" in r)
    return {"posts": posts,
            "run_log": [f"[factcheck] round done: {verified}/{len(targets)} verified "
                        f"({'; '.join(results)})"]}


def route_after_factcheck(state) -> str:
    """Feedback loop #2: posts failing verification go back for revision."""
    if any(p["status"] == "editor_pass" and p["factcheck_rounds"] > 0 and p["feedback"]
           for p in state["posts"]):
        return "revise"
    return "finalize"


# --- Agent 5: Final assembly --------------------------------------------------

def finalize_node(state) -> dict:
    posts = [
        FinalPost(
            style=p["style"], text=p["text"], feedback=p["feedback"],
            editor_rounds=p["editor_rounds"], factcheck_rounds=p["factcheck_rounds"],
            pipeline_result=("published" if p["status"] == "factcheck_pass"
                             else "failed_editor" if p["status"] == "failed_editor"
                             else "failed_factcheck"),
        )
        for p in state["posts"]
    ]
    published = sum(1 for p in posts if p.pipeline_result == "published")
    return {
        "final": PipelineResult(topic=state["topic"], posts=posts),
        "run_log": [f"[finalize] {published}/{len(posts)} posts ready to publish"],
    }
