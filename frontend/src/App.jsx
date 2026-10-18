import { useCallback, useRef, useState } from "react";
import AgentLog from "./components/AgentLog.jsx";
import PostCard from "./components/PostCard.jsx";
import { startRun, openStream } from "./api.js";

const IDLE = "idle";
const RUNNING = "running";
const DONE = "done";
const ERROR_STATE = "error";

export default function App() {
  const [idea, setIdea] = useState("");
  const [status, setStatus] = useState(IDLE);
  const [logs, setLogs] = useState([]);
  const [posts, setPosts] = useState([]);
  const [publishedCount, setPublishedCount] = useState(null);
  const [images, setImages] = useState({}); // index -> url
  const [error, setError] = useState("");
  const logRef = useRef(null);

  const run = useCallback(async () => {
    if (!idea.trim() || status === RUNNING) return;
    setLogs([]);
    setPosts([]);
    setImages({});
    setPublishedCount(null);
    setError("");
    setStatus(RUNNING);

    let runId;
    try {
      runId = await startRun(idea.trim());
    } catch (e) {
      setStatus(ERROR_STATE);
      setError(`Could not start pipeline: ${e.message}`);
      return;
    }

    const es = openStream(runId, {
      onLog: (line) => {
        setLogs((prev) => [...prev, line]);
        requestAnimationFrame(() => {
          logRef.current?.scrollTo({ top: 1e6, behavior: "smooth" });
        });
      },
      onPosts: ({ posts: allPosts, published }) => {
        setPosts(allPosts);
        setPublishedCount(published);
      },
      onImage: ({ index, url }) => {
        setImages((prev) => ({ ...prev, [index]: url }));
      },
      onDone: () => {
        setStatus(DONE);
        es.close();
      },
      onError: (message) => {
        setStatus(ERROR_STATE);
        setError(message);
        es.close();
      },
      onClosed: () => es.close(),
    });
  }, [idea, status]);

  const running = status === RUNNING;
  const published = posts.filter((p) => p.pipeline_result === "published");
  const dropped = posts.filter((p) => p.pipeline_result !== "published");

  return (
    <div className="layout">
      <header>
        <h1>🤖 Multi-Agent Content Pipeline</h1>
        <p className="subtitle">
          Idea → 🔍 Researcher → ✍️ Writer → 📝 Editor → 🛡 Fact-Checker →
          publish-ready LinkedIn posts with AI illustrations
        </p>
      </header>

      <section className="input-panel">
        <textarea
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          placeholder="e.g. ICPC / Competitive Programming"
          rows={3}
          disabled={running}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) run();
          }}
        />
        <button className="run-btn" onClick={run} disabled={running || !idea.trim()}>
          {running ? "⏳ Pipeline running…" : "🚀 Run pipeline"}
        </button>
      </section>

      {status === DONE && publishedCount !== null && (
        <div className="banner success">
          ✅ {publishedCount}/{posts.length} posts ready to publish
        </div>
      )}
      {status === ERROR_STATE && <div className="banner error">❌ {error}</div>}

      {(running || logs.length > 0) && (
        <AgentLog logs={logs} running={running} scrollerRef={logRef} />
      )}

      {running && (
        <div className="pending-banner">
          🎨 Illustrations generate at the free image tier&apos;s pace (~1 per 45s) —
          cards fill in below automatically.
        </div>
      )}

      {published.length > 0 && (
        <section>
          <h2>Ready to publish</h2>
          <div className="post-grid">
            {published.map((post, i) => (
              <PostCard
                key={post.style + i}
                post={post}
                imageUrl={images[i]}
                loading={!images[i]}
              />
            ))}
          </div>
        </section>
      )}

      {dropped.length > 0 && (
        <section>
          <details>
            <summary>
              ⚠️ {dropped.length} post(s) did not survive review — click to inspect
            </summary>
            {dropped.map((p, i) => (
              <div className="dropped" key={p.style + i}>
                <strong>{p.style}</strong> — failed at{" "}
                <em>{p.pipeline_result}</em> (editor rounds: {p.editor_rounds},
                fact-check rounds: {p.factcheck_rounds})
                {p.feedback && <blockquote>{p.feedback}</blockquote>}
                <pre>{p.text}</pre>
              </div>
            ))}
          </details>
        </section>
      )}
    </div>
  );
}
