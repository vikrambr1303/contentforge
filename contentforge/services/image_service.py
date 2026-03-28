import logging
import os
import random
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

from config import get_settings


def _data_paths(content_id: int) -> tuple[Path, Path]:
    settings = get_settings()
    root = Path(settings.data_dir)
    img_dir = root / "images"
    bg_dir = root / "backgrounds"
    img_dir.mkdir(parents=True, exist_ok=True)
    bg_dir.mkdir(parents=True, exist_ok=True)
    background = bg_dir / f"{content_id}_background.jpg"
    composed = img_dir / f"{content_id}_composed.jpg"
    return background, composed


def generate_background(
    diffusers_model_path: str,
    prompt: str,
    out_path: Path,
    height: int = 1920,
    width: int = 1080,
    *,
    negative_prompt: str | None = None,
    on_diffusion_step: Callable[[int, int], None] | None = None,
    reference_image_path: Path | None = None,
    reference_strength: float = 0.38,
) -> None:
    """
    Stable Diffusion via diffusers (txt2img, or img2img when reference_image_path is set).
    Falls back to gradient placeholder if model unavailable.

    reference_strength: img2img only; lower keeps more of the reference (typical 0.25–0.45),
    higher lets the prompt change the image more (up to ~0.75).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import gc

        import torch
        from diffusers import StableDiffusionImg2ImgPipeline, StableDiffusionPipeline

        if not os.path.isdir(diffusers_model_path):
            raise FileNotFoundError(diffusers_model_path)

        settings = get_settings()
        cuda = torch.cuda.is_available() and not settings.force_sd_cpu
        dtype = torch.float16 if cuda else torch.float32

        out_w, out_h = width, height
        if cuda:
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
            torch.backends.cudnn.benchmark = True
            infer_w, infer_h = out_w, out_h
            steps = max(18, min(60, int(settings.sd_inference_steps_gpu)))
            try:
                logger.info("SD using GPU %s (%s)", torch.cuda.current_device(), torch.cuda.get_device_name(0))
            except Exception:
                logger.info("SD using CUDA")
        else:
            infer_w, infer_h = 512, 896
            steps = 18

        use_ref = reference_image_path is not None and reference_image_path.is_file()
        # img2img + VAE decode peaks RAM on CPU; infer smaller than txt2img to avoid SIGKILL (OOM).
        if not cuda and use_ref:
            infer_w, infer_h = 384, 704
            steps = min(steps, 16)
        strength = float(reference_strength)
        strength = max(0.12, min(0.92, strength))

        if use_ref:
            logger.info(
                "SD img2img with style reference (strength=%.2f, ref=%s)",
                strength,
                reference_image_path,
            )
            pipe = StableDiffusionImg2ImgPipeline.from_pretrained(
                diffusers_model_path,
                torch_dtype=dtype,
                safety_checker=None,
                low_cpu_mem_usage=True,
            )
        else:
            pipe = StableDiffusionPipeline.from_pretrained(
                diffusers_model_path,
                torch_dtype=dtype,
                safety_checker=None,
                low_cpu_mem_usage=True,
            )

        if cuda:
            pipe = pipe.to("cuda")
        else:
            pipe.enable_attention_slicing()
            try:
                pipe.enable_vae_slicing()
            except Exception:
                pass
            try:
                pipe.enable_vae_tiling()
            except Exception:
                pass

        def _step_end(_pipeline, step_index: int, _timestep, callback_kwargs):  # noqa: ANN001
            if on_diffusion_step:
                try:
                    on_diffusion_step(step_index + 1, steps)
                except Exception:
                    pass
            return callback_kwargs

        pipe_kw: dict = {
            "prompt": prompt,
            "num_inference_steps": steps,
            "guidance_scale": 7.5,
        }
        if negative_prompt:
            pipe_kw["negative_prompt"] = negative_prompt
        if on_diffusion_step:
            pipe_kw["callback_on_step_end"] = _step_end

        with torch.inference_mode():
            if use_ref:
                init_image = Image.open(reference_image_path).convert("RGB")
                init_image = init_image.resize((infer_w, infer_h), Image.Resampling.LANCZOS)
                pipe_kw["image"] = init_image
                pipe_kw["strength"] = strength
                result = pipe(**pipe_kw)
            else:
                pipe_kw["height"] = infer_h
                pipe_kw["width"] = infer_w
                result = pipe(**pipe_kw)

        image = result.images[0]
        del result
        del pipe
        gc.collect()
        if cuda:
            torch.cuda.empty_cache()

        if image.size != (out_w, out_h):
            image = image.resize((out_w, out_h), Image.Resampling.LANCZOS)
        image.save(out_path, quality=92)
        del image

        gc.collect()
        if cuda:
            torch.cuda.empty_cache()
    except Exception as e:
        logger.warning(
            "Stable Diffusion skipped; using gradient placeholder (%s: %s). "
            "Install model weights in the worker container and set Settings → Diffusers model path, "
            "or mount a host directory that contains a diffusers model.",
            type(e).__name__,
            e,
        )
        _placeholder_gradient(out_path, width, height)


def _placeholder_gradient(out_path: Path, width: int, height: int) -> None:
    """Fallback when Diffusers is unavailable — vertical gradient with warmer tones (fast, one line per row)."""
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / max(height - 1, 1)
        r = int(32 + t * 48)
        g = int(36 + t * 72)
        b = int(78 + t * 55)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    img.save(out_path, quality=92)


def _resize_cover_rgb(img: Image.Image, tw: int, th: int) -> Image.Image:
    img = img.convert("RGB")
    iw, ih = img.size
    if iw <= 0 or ih <= 0:
        raise ValueError("Invalid image dimensions from download")
    scale = max(tw / iw, th / ih)
    nw = max(1, int(round(iw * scale)))
    nh = max(1, int(round(ih * scale)))
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - tw) // 2
    top = (nh - th) // 2
    return img.crop((left, top, left + tw, top + th))


def fetch_unsplash_background(
    search_query: str,
    out_path: Path,
    *,
    access_key: str,
    width: int = 1080,
    height: int = 1920,
) -> None:
    """
    Search Unsplash (portrait), download one result, crop/resize to width×height (cover).
    Requires a Developer access key (free tier); set UNSPLASH_ACCESS_KEY in the environment.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    q = " ".join((search_query or "").split())[:120]
    if not q:
        q = "abstract landscape nature"

    headers = {"Authorization": f"Client-ID {access_key}"}
    timeout = httpx.Timeout(connect=15.0, read=120.0, write=60.0, pool=10.0)

    def _search(query: str) -> list[dict]:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(
                "https://api.unsplash.com/search/photos",
                params={
                    "query": query,
                    "per_page": 15,
                    "orientation": "portrait",
                    "order_by": "relevant",
                },
                headers=headers,
            )
            r.raise_for_status()
            return list(r.json().get("results") or [])

    results = _search(q)
    if not results:
        logger.info("Unsplash: no hits for %r, trying fallback query", q)
        results = _search("moody nature texture abstract sky")
    if not results:
        raise RuntimeError("Unsplash search returned no photos. Check UNSPLASH_ACCESS_KEY and network.")

    choice = random.choice(results[: min(10, len(results))])
    pid = str(choice.get("id") or "")
    photographer = (choice.get("user") or {}).get("name") or "unknown"
    logger.info("Unsplash selected photo id=%s by %s", pid, photographer)
    urls = choice.get("urls") or {}
    raw_url = urls.get("raw") or urls.get("regular")
    if not raw_url or not pid:
        raise RuntimeError("Unsplash result missing image URL")

    with httpx.Client(timeout=timeout) as client:
        try:
            tr = client.get(f"https://api.unsplash.com/photos/{pid}/download", headers=headers)
            tr.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Unsplash download tracking request failed (non-fatal): %s", e)

    sep = "&" if "?" in raw_url else "?"
    dl = f"{raw_url}{sep}w={width}&h={height}&fit=crop&q=82"
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        ir = client.get(dl)
        ir.raise_for_status()
        img = Image.open(BytesIO(ir.content))

    img = _resize_cover_rgb(img, width, height)
    img.save(out_path, quality=92)
    logger.info("Unsplash background saved to %s (query=%r)", out_path, q)


def _load_quote_fonts(size_quote: int, size_author: int) -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    paths_bold = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    )
    paths_italic = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    )
    font_q = None
    for p in paths_bold:
        try:
            font_q = ImageFont.truetype(p, size_quote)
            break
        except OSError:
            continue
    font_a = None
    for p in paths_italic:
        try:
            font_a = ImageFont.truetype(p, size_author)
            break
        except OSError:
            continue
    if font_q is None:
        font_q = ImageFont.load_default()
    if font_a is None:
        font_a = font_q
    return font_q, font_a


def _draw_text_shadowed(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    *,
    offset: int = 3,
) -> None:
    x, y = xy
    shadow = (15, 18, 28)
    for dx, dy in ((offset, offset), (0, offset), (offset, 0)):
        draw.text((x + dx, y + dy), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)


def composite_quote(
    background_path: Path,
    out_path: Path,
    quote: str,
    author: str,
) -> None:
    """Quote + author vertically centered with a center-peaked scrim; font sizes scale with image (9:16 friendly)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bg = Image.open(background_path).convert("RGBA")
    w, h = bg.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    mid_y = (h - 1) * 0.5
    half_h = max(h * 0.5, 1.0)
    floor_a, peak_a = 38, 178
    for y in range(h):
        dist = abs(y - mid_y) / half_h
        alpha = int(floor_a + (peak_a - floor_a) * ((1.0 - min(dist, 1.0)) ** 1.2))
        od.line([(0, y), (w, y)], fill=(0, 0, 0, min(255, alpha)))

    combined = Image.alpha_composite(bg, overlay).convert("RGB")
    draw = ImageDraw.Draw(combined)

    base = min(w, h)
    size_quote = max(52, min(96, int(base * 0.062)))
    size_author = max(34, int(size_quote * 0.52))
    font_q, font_a = _load_quote_fonts(size_quote, size_author)

    margin_x = int(w * 0.06)
    text_max_w = w - 2 * margin_x
    lines = _wrap_text(quote, font_q, draw, text_max_w)

    line_heights: list[int] = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font_q)
        line_heights.append(bbox[3] - bbox[1])
    line_gap = max(12, int(size_quote * 0.22))

    auth = f"— {author}"
    abox = draw.textbbox((0, 0), auth, font=font_a)
    author_h = abox[3] - abox[1]
    gap_before_author = max(20, int(size_quote * 0.38))

    block_h = sum(line_heights) + line_gap * max(0, len(lines) - 1) + gap_before_author + author_h
    pad_v = max(int(h * 0.035), 8)
    y_centered = (h - block_h) // 2
    y = max(pad_v, min(y_centered, h - pad_v - block_h))

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font_q)
        tw = bbox[2] - bbox[0]
        lx = margin_x + (text_max_w - tw) // 2
        _draw_text_shadowed(draw, (lx, y), line, font_q, (255, 255, 255))
        y += line_heights[i] + (line_gap if i < len(lines) - 1 else 0)

    y += gap_before_author
    bbox = draw.textbbox((0, 0), auth, font=font_a)
    tw = bbox[2] - bbox[0]
    lx = margin_x + (text_max_w - tw) // 2
    _draw_text_shadowed(draw, (lx, y), auth, font_a, (235, 238, 245))

    combined.save(out_path, quality=92)


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, draw: ImageDraw.ImageDraw, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur: list[str] = []
    for word in words:
        trial = " ".join(cur + [word])
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width:
            cur.append(word)
        else:
            if cur:
                lines.append(" ".join(cur))
            cur = [word]
    if cur:
        lines.append(" ".join(cur))
    return lines or [text[:80]]


def paths_for_content(content_id: int) -> tuple[Path, Path]:
    return _data_paths(content_id)
