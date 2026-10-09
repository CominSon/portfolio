"""Монтаж итогового видео интервью: слева демонстрация экрана, справа веб-камера."""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

logger = logging.getLogger(__name__)

# 1280×720 + 1 поток: на VPS ~2 GiB без swap 1920×1080 съедал ~1.5 GiB и ловил OOM-kill.
OUTPUT_W = 1280
OUTPUT_H = 720
LEFT_W = OUTPUT_W // 2
RIGHT_W = OUTPUT_W - LEFT_W
OUTPUT_FPS = 15
FFMPEG_THREADS = 1
FFMPEG_PRESET = "ultrafast"
FFMPEG_CRF = "28"


@dataclass
class MontageInputs:
    screen: Path
    camera: Path
    audio: Path | None


def resolve_ffmpeg() -> str:
    env = __import__("os").environ.get("FFMPEG_PATH", "").strip()
    if env and Path(env).is_file():
        return env
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:
        raise RuntimeError(
            "ffmpeg не найден. Установите ffmpeg или: pip install imageio-ffmpeg"
        ) from exc


def _probe_media_duration(ffmpeg: str, path: Path) -> float | None:
    """Реальная длительность декодирования (для WebM без Duration в заголовке)."""
    try:
        proc = subprocess.run(
            [
                ffmpeg,
                "-fflags",
                "+genpts",
                "-i",
                str(path),
                "-map",
                "0:v:0",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        # time=00:06:10.25 в stderr
        times = re.findall(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr or "")
        if times:
            h, mi, s = times[-1]
            return int(h) * 3600 + int(mi) * 60 + float(s)
    except Exception:
        pass
    return None


def _probe_duration(ffmpeg: str, path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        try:
            out = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=120,
            )
            val = float(out.stdout.strip())
            if val > 0.5:
                return val
        except Exception:
            pass
    try:
        probe = subprocess.run(
            [ffmpeg, "-i", str(path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        m = re.search(
            r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
            probe.stderr or "",
        )
        if m:
            h, mi, s = m.groups()
            return int(h) * 3600 + int(mi) * 60 + float(s)
    except Exception:
        pass
    decoded = _probe_media_duration(ffmpeg, path)
    if decoded and decoded > 0.5:
        return decoded
    logger.warning(
        "duration unknown for %s (WebM из MediaRecorder — берём длительность сессии)",
        path.name,
    )
    return 7200.0


def _has_audio_stream(ffmpeg: str, path: Path) -> bool:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return path.stat().st_size > 0
    try:
        out = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return "audio" in out.stdout
    except Exception:
        return False


def _format_duration(sec: float) -> str:
    sec = max(0, int(sec))
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h} ч {m} мин"
    if m:
        return f"{m} мин {s} с"
    return f"{s} с"


def _run_ffmpeg_with_progress(cmd: list[str], duration_sec: float, output: Path) -> None:
    """Запуск ffmpeg с выводом прогресса в консоль."""
    full_cmd = cmd[:]
    # -progress pipe:1 пишет out_time_ms в stdout
    insert_at = len(full_cmd) - 1  # перед output path
    full_cmd[insert_at:insert_at] = ["-progress", "pipe:1", "-nostats"]

    print(
        f"Кодирование ffmpeg (~{_format_duration(duration_sec)}), "
        f"файл: {output.name}",
        flush=True,
    )
    print("  (предупреждения «duration unknown» — норма для WebM из браузера; "
          "длительность взята из времени сессии)", flush=True)

    proc = subprocess.Popen(
        full_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    last_pct = -1
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if line.startswith("out_time_ms="):
            try:
                ms = int(line.split("=", 1)[1])
                if duration_sec > 0:
                    pct = min(100, int(ms / 1_000_000 / duration_sec * 100))
                    if pct >= last_pct + 5 or pct >= 99:
                        mb = output.stat().st_size / (1024 * 1024) if output.is_file() else 0
                        print(f"  … {pct}%  (~{mb:.1f} МБ)", flush=True)
                        last_pct = pct
            except (ValueError, OSError):
                pass
        elif line == "progress=end":
            break

    rc = proc.wait(timeout=7200)
    if rc != 0:
        raise subprocess.CalledProcessError(rc, full_cmd)


def _scale_pad(w: int, h: int) -> str:
    """Нормализация PTS и постоянный FPS — убирает «слайд-шоу» из-за битых таймкодов WebM."""
    return (
        f"setpts=PTS-STARTPTS,fps={OUTPUT_FPS},"
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )


def build_montage(
    inputs: MontageInputs,
    output: Path,
    *,
    work_dir: Path | None = None,
    max_duration_sec: float | None = None,
) -> Path:
    """Собрать MP4: слева демонстрация экрана, справа камера, звук — микрофон."""
    _ = work_dir  # зарезервировано для совместимости вызовов
    ffmpeg = resolve_ffmpeg()
    if not inputs.screen.is_file():
        raise FileNotFoundError(f"Нет записи экрана: {inputs.screen}")
    if not inputs.camera.is_file():
        raise FileNotFoundError(f"Нет записи камеры: {inputs.camera}")

    output.parent.mkdir(parents=True, exist_ok=True)
    # Не оставляем прошлый обрезок — иначе письмо/скачивание могут отдать «пустое» видео.
    if output.is_file():
        try:
            output.unlink()
        except OSError:
            pass

    duration = min(
        _probe_duration(ffmpeg, inputs.screen),
        _probe_duration(ffmpeg, inputs.camera),
    )
    if max_duration_sec and max_duration_sec > 1:
        duration = min(duration, max_duration_sec)
    duration = min(duration, 7200.0)

    logger.info(
        "montage duration %.1fs fps=%s (session cap=%s)",
        duration,
        OUTPUT_FPS,
        max_duration_sec,
    )

    left_vf = f"[0:v]{_scale_pad(LEFT_W, OUTPUT_H)}[L]"
    right_vf = f"[1:v]{_scale_pad(RIGHT_W, OUTPUT_H)}[R]"
    stack = "[L][R]hstack=inputs=2[vout]"
    filter_parts = [left_vf, right_vf, stack]

    cmd: list[str] = [
        ffmpeg,
        "-y",
        "-fflags",
        "+genpts",
        "-i",
        str(inputs.screen),
        "-fflags",
        "+genpts",
        "-i",
        str(inputs.camera),
    ]
    has_audio = (
        inputs.audio
        and inputs.audio.is_file()
        and _has_audio_stream(ffmpeg, inputs.audio)
    )
    if has_audio:
        cmd.extend(["-i", str(inputs.audio)])
        filter_parts.append(f"[2:a]asetpts=PTS-STARTPTS[aout]")

    cmd.extend(
        [
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[vout]",
        ]
    )
    if has_audio:
        cmd.extend(["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"])
    else:
        cmd.append("-an")

    cmd.extend(
        [
            "-shortest",
            "-threads",
            str(FFMPEG_THREADS),
            "-filter_threads",
            str(FFMPEG_THREADS),
            "-c:v",
            "libx264",
            "-preset",
            FFMPEG_PRESET,
            "-crf",
            FFMPEG_CRF,
            "-r",
            str(OUTPUT_FPS),
            "-vsync",
            "cfr",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )

    try:
        _run_ffmpeg_with_progress(cmd, duration, output)
    except (subprocess.CalledProcessError, OSError) as exc:
        err_hint = ""
        if output.is_file():
            err_hint = f"\nЧастичный файл удалён: {output} ({output.stat().st_size} байт)"
            try:
                output.unlink()
            except OSError:
                pass
        code = getattr(exc, "returncode", "?")
        raise RuntimeError(f"ffmpeg montage failed (code {code}){err_hint}") from exc
    logger.info("Montage saved: %s", output)
    return output


def paths_for_interview(recordings_dir: Path, interview_id: UUID) -> MontageInputs:
    base = recordings_dir / str(interview_id)
    audio = base / "audio" / "recording.webm"
    if not audio.is_file():
        audio = base / "microphone" / "recording.webm"
    return MontageInputs(
        screen=base / "screen" / "recording.webm",
        camera=base / "camera" / "recording.webm",
        audio=audio if audio.is_file() else None,
    )
