"""Streamlit frontend for the multi-agent content pipeline.

Run with:  streamlit run app.py
"""

from datetime import datetime
from pathlib import Path

import streamlit as st

from dotenv import load_dotenv
load_dotenv()

from pipeline.graph import app
from pipeline.images import generate_for_run

st.set_page_config(page_title="AI Content Pipeline", page_icon="🤖", layout="wide")
st.title("🤖 Multi-Agent Content Pipeline")
st.caption("Idea → 🔍 Researcher → ✍️ Writer → 📝 Editor → 🛡 Fact-Checker → publish-ready LinkedIn posts")

with st.sidebar:
    st.header("Input")
    idea = st.text_area(
        "Your content idea",
        value="",
        placeholder="e.g. ICPC / Competitive Programming",
        height=110,
    )
    st.divider()
    st.markdown(
        "**The agents**\n"
        "- 🔍 **Researcher** — angles & facts\n"
        "- ✍️ **Writer** — one post per persona\n"
        "- 📝 **Editor** — structure & tone gate\n"
        "- 🛡 **Fact-Checker** — claim gate\n\n"
        "Rejected posts loop back to the Writer with feedback."
    )
    st.divider()
    st.caption("LLM: Groq (see .env) · Images: Pollinations.ai")

if not idea.strip():
    st.info("👋 Enter an idea in the sidebar and hit **Run pipeline**.")
    st.stop()

# --- Phase 1: run the agent pipeline with live progress ---------------------

logs, final = [], None
with st.status("Pipeline running...", expanded=True) as status:
    for chunk in app.stream(
        {"topic": idea.strip()}, config={"recursion_limit": 60}, stream_mode="updates"
    ):
        for node, update in chunk.items():
            if not update:
                continue
            for line in update.get("run_log", []):
                logs.append(line)
                st.write(f"`{line}`")
            if "final" in update:
                final = update["final"]
    if final is None:
        status.update(label="❌ Pipeline failed", state="error", expanded=False)
        st.error("Pipeline ended without a result (check API key / rate limits).")
        st.stop()
    status.update(label="✅ Pipeline finished", state="complete", expanded=False)

published = [p for p in final.posts if p.pipeline_result == "published"]
dropped = len(final.posts) - len(published)
st.success(f"{len(published)}/{len(final.posts)} posts ready to publish")

# --- Phase 2: generate an illustration per published post -------------------

stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
image_dir = Path("outputs") / f"run-{stamp}" / "images"
with st.spinner("🎨 Generating illustrations... (free image tier is ~1 image/45s, "
                "so this step can take a few minutes; placeholders are used if the "
                "service is saturated)"):
    image_paths = generate_for_run(final, image_dir)

# --- Phase 3: showcase --------------------------------------------------------

for i, (post, image_path) in enumerate(zip(published, image_paths), 1):
    with st.container(border=True):
        c1, c2 = st.columns([1, 1.1])
        with c1:
            st.image(str(image_path), use_container_width=True)
            st.caption(f"🎨 illustration · {post.style}")
        with c2:
            st.markdown(f"**{post.style}**")
            st.markdown(post.text.replace("\n", "  \n"))

if dropped:
    with st.expander(f"⚠️ {dropped} post(s) did not survive review"):
        for p in final.posts:
            if p.pipeline_result != "published":
                st.markdown(f"**{p.style}** — failed at *{p.pipeline_result}* "
                            f"(editor rounds: {p.editor_rounds}, fact-check rounds: {p.factcheck_rounds})")
                if p.feedback:
                    st.markdown(f"> Last feedback: {p.feedback}")
                st.text(p.text)
                st.divider()

with st.expander("📜 Full run log"):
    for line in logs:
        st.markdown(f"- `{line}`")

st.caption(f"Run folder: `outputs/run-{stamp}`")
