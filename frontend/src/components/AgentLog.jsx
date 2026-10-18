export default function AgentLog({ logs, running, scrollerRef }) {
  return (
    <section className="agent-log">
      <h2>
        Agent activity{" "}
        {running && <span className="pulse">● live</span>}
      </h2>
      <div className="log-scroll" ref={scrollerRef}>
        {logs.length === 0 && <div className="log-line muted">waiting for agents…</div>}
        {logs.map((line, i) => (
          <div className="log-line" key={i}>
            {line}
          </div>
        ))}
      </div>
    </section>
  );
}
