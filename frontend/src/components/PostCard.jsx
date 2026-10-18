export default function PostCard({ post, imageUrl, loading }) {
  return (
    <article className="card">
      <div className="card-media">
        {imageUrl ? (
          <img src={imageUrl} alt={`illustration for ${post.style}`} />
        ) : (
          <div className="media-placeholder">
            {loading ? "🎨 generating illustration…" : "📄 no image"}
          </div>
        )}
      </div>
      <div className="card-body">
        <span className="badge">{post.style}</span>
        <p className="post-text">{post.text}</p>
        <p className="meta">
          editor rounds: {post.editor_rounds} · fact-check rounds:{" "}
          {post.factcheck_rounds}
        </p>
      </div>
    </article>
  );
}
