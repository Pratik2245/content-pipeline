"""CLI: one idea in, publish-ready LinkedIn posts out.

Usage:
    python main.py "ICPC / Competitive Programming"
    python main.py            # will prompt for an idea
"""

import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from pipeline.graph import app
from pipeline.images import generate_for_run


def render_markdown(result: dict, images: dict[str, str] | None = None) -> str:
    final = result["final"]
    lines = [f"# Pipeline output — {final.topic}", ""]
    for p in final.posts:
        lines += [
            f"## {p.style} — {p.pipeline_result}",
            "",
        ]
        if images and p.style in images:
            lines += [f"![{p.style}]({images[p.style]})", ""]
        lines += [
            p.text,
            "",
            f"_(editor rounds: {p.editor_rounds}, fact-check rounds: {p.factcheck_rounds}"
            + (f"; last feedback: {p.feedback})" if p.feedback else ")"),
            "_",
            "",
        ]
    return "\n".join(lines)


def main() -> int:
    load_dotenv()
    idea = " ".join(sys.argv[1:]).strip()
    if not idea:
        idea = input("Enter your content idea: ").strip()
    if not idea:
        print("No idea given — nothing to do.")
        return 1

    print(f"\n▶ pipeline starting for idea: {idea!r}\n")
    result = app.invoke({"topic": idea}, config={"recursion_limit": 60})

    print("\n=== Run log ===")
    for line in result["run_log"]:
        print(" ", line)

    final = result["final"]
    print("\n=== Posts ready to publish ===\n")
    published = [p for p in final.posts if p.pipeline_result == "published"]
    for i, p in enumerate(published, 1):
        print(f"--- Post {i} ({p.style}) ---\n{p.text}\n")
    dropped = len(final.posts) - len(published)
    if dropped:
        print(f"({dropped} post(s) did not survive review — see the output file for feedback)")

    out = Path("outputs")
    run_dir = out / f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    (run_dir / "images").mkdir(parents=True, exist_ok=True)

    # Images for every published post (Pollinations with local fallback).
    # The free image tier is ~1 image / 45s, so this step takes a few minutes.
    try:
        image_paths = generate_for_run(final, run_dir / "images")
        images_md = {p.style: f"images/{path.name}"
                     for p, path in zip(
                         (x for x in final.posts if x.pipeline_result == "published"),
                         image_paths)}
    except Exception as e:
        print(f"\n(image generation skipped: {e})")
        images_md = None

    report = run_dir / "report.md"
    report.write_text(render_markdown(result, images_md), encoding="utf-8")
    print(f"\nSaved report to {report}"
          + (f"\nSaved {len(images_md)} image(s) to {run_dir / 'images'}" if images_md else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
