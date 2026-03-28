from pathlib import Path

from PIL import Image as PILImage

# MoviePy 1.0.x passes Image.ANTIALIAS to PIL; Pillow 10+ removed it (use LANCZOS).
if not hasattr(PILImage, "ANTIALIAS"):
    PILImage.ANTIALIAS = PILImage.Resampling.LANCZOS

from moviepy.editor import ImageClip


def make_ken_burns_video(
    image_path: Path,
    out_path: Path,
    duration: float = 8.0,
    fps: int = 30,
) -> None:
    """§9.4 — portrait 1080×1920 MP4; fade in/out."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    clip = ImageClip(str(image_path)).set_duration(duration)
    clip = clip.resize(height=1920)
    w, h = clip.size
    if w > 1080:
        x1 = int((w - 1080) / 2)
        clip = clip.crop(x1=x1, y1=0, width=1080, height=1920)
    elif w < 1080:
        clip = clip.resize(width=1080)
    clip = clip.fadein(0.5).fadeout(0.5)
    clip.write_videofile(
        str(out_path),
        fps=fps,
        codec="libx264",
        audio=False,
        preset="medium",
        ffmpeg_params=["-pix_fmt", "yuv420p"],
    )
