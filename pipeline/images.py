"""Illustration generation for pipeline posts.

Primary source: Pollinations.ai (free, no API key, handles prompts over URL).
Fallback: a locally generated Pillow placeholder so the pipeline always has
something to show even when offline.
"""

import hashlib
import textwrap
import time
from pathlib import Path
from urllib.parse import quote

import requests

POLLINATIONS_URL = (
    "https://image.pollinations.ai/prompt/{prompt}"
    "?width=1024&height=1024&nologo=true&seed={seed}"
)

# Visual direction per post style keyword.
MOODS = {
    "story": "warm cinematic light, hopeful human moment, shallow depth of field",
    "listicle": "clean minimal flat design, geometric shapes, calm pastel palette",
    "hot-take": "bold high-contrast duotone, energetic diagonal composition",
}
DEFAULT_MOOD = "modern editorial illustration, tech-forward, balanced composition"


def _mood_for(style: str) -> str:
    lowered = style.lower()
    for key, mood in MOODS.items():
        if key in lowered:
            return mood
    return DEFAULT_MOOD


def _image_prompt_for(post, topic: str) -> str:
    """Short prompts succeed more often on the free tier than long ones."""
    headline = post.text.strip().splitlines()[0][:80]
    prompt = f"{topic}, {headline}, {_mood_for(post.style)}"
    return POLLINATIONS_URL.format(
        prompt=quote(prompt, safe=""),
        seed=int(hashlib.md5(post.text.encode()).hexdigest()[:8], 16) % 99999,
    )


def _fallback_image(out_path: Path, label: str, headline: str) -> None:
    """Local placeholder: hashed gradient + headline text (always works)."""
    from PIL import Image, ImageDraw, ImageFont

    digest = int(hashlib.md5(label.encode()).hexdigest(), 16)
    c1 = (digest >> 16 & 255, digest >> 8 & 255, digest & 255)
    c2 = (255 - c1[0], 255 - c1[1], 255 - c1[2])
    width, height = 1024, 1024

    img = Image.new("RGB", (width, height))
    gradient = Image.new("RGB", (width, 1))  # 1px-tall gradient stretched vertically
    for x in range(width):
        t = x / width
        gradient.putpixel((x, 0), tuple(int(a + (b - a) * t) for a, b in zip(c1, c2)))
    img.paste(gradient.resize((width, height)), (0, 0))

    draw = ImageDraw.Draw(img, "RGBA")
    for i in range(6):  # soft translucent circles for depth
        r = 120 + (digest >> (i * 3)) % 200
        x = (digest * (i + 7)) % width
        y = (digest * (i + 11)) % height
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 24))

    accent = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    adraw = ImageDraw.Draw(accent)
    adraw.rectangle([0, 0, 14, height], fill=(255, 255, 255, 200))  # accent bar
    img = Image.alpha_composite(img.convert("RGBA"), accent)

    draw = ImageDraw.Draw(img, "RGBA")
    big = ImageFont.load_default(size=64)
    small = ImageFont.load_default(size=40)
    draw.text((70, 80), label.upper(), font=big, fill=(255, 255, 255, 235))
    wrapped = "\n".join(textwrap.wrap(headline, width=26)[:6])
    draw.multiline_text((70, height // 2), wrapped, font=small,
                        fill=(255, 255, 255, 210), spacing=16)
    draw.text((70, height - 90), "— content-pipeline illustration —",
              font=ImageFont.load_default(size=24), fill=(255, 255, 255, 140))
    img.convert("RGB").save(out_path, "JPEG", quality=88)


def _fetch_image(url: str, path: Path, attempts: int = 3) -> None:
    """Download honoring the Pollinations free tier: 1 image / 45s per IP."""
    last_exc = None
    for attempt in range(attempts):
        try:
            response = requests.get(url, timeout=180)
            if response.status_code == 200 and response.headers.get(
                    "content-type", "").startswith("image"):
                path.write_bytes(response.content)
                return
            # 402 = FREE_LIMIT reached, 503 = server busy -> wait and retry
            wait = 46 if response.status_code in (402, 429) else 15
            try:
                detail = response.json().get("error", {}).get("message", "")
            except Exception:
                detail = response.text[:120]
            last_exc = RuntimeError(f"HTTP {response.status_code}: {detail}")
            if attempt < attempts - 1:
                time.sleep(wait if response.status_code != 503 else 12)
        except Exception as exc:
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(15)
    raise last_exc


def iter_images(final, out_dir: Path):
    """Generator: yields (index, path) as each published post's image is ready.

    The free image tier is ~1 image / 45s per IP, so this intentionally paces
    itself. Always produces a file (fallback placeholder on failure).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    published = [p for p in final.posts if p.pipeline_result == "published"]

    for i, post in enumerate(published, start=1):
        slug = "post-{}-{}".format(i, post.style.replace(" ", "_").lower())
        path = out_dir / f"{slug}.jpg"
        if i > 1:
            time.sleep(46)  # free tier: 1 image per 45s per IP
        try:
            _fetch_image(_image_prompt_for(post, final.topic), path)
        except Exception as exc:  # offline / rate-limited / blocked -> placeholder
            print(f"[images] fallback for {post.style!r}: {exc}")
            _fallback_image(path, post.style, post.text.strip().splitlines()[0])
        yield i - 1, path


def generate_for_run(final, out_dir: Path) -> list[Path]:
    """Generate one image per published post, in order. Returns matching paths."""
    return [path for _, path in iter_images(final, out_dir)]
