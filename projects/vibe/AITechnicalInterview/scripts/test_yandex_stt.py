#!/usr/bin/env python3
"""
Проверка Yandex SpeechKit STT (синхронный API v1 — короткие файлы до ~30 с).

Использование:
  cd /path/to/AITechnicalInterview
  # в .env должны быть YANDEX_FOLDER_ID и YANDEX_API_KEY (см. docs/YANDEX_STT_SETUP.md)
  backend/.venv/bin/python scripts/test_yandex_stt.py path/to/audio.ogg
  backend/.venv/bin/python scripts/test_yandex_stt.py path/to/answer.webm
  backend/.venv/bin/python scripts/test_yandex_stt.py recordings/.../audio/recording.webm --seconds 25
  backend/.venv/bin/python scripts/test_yandex_stt.py --check-auth
  backend/.venv/bin/python scripts/test_yandex_stt.py --sample          # авто-поиск речи в recordings/
  backend/.venv/bin/python scripts/test_yandex_stt.py path.webm --offset 90 --seconds 25

Переменные окружения (.env в корне репозитория):
  YANDEX_FOLDER_ID   — идентификатор каталога (b1g...)
  YANDEX_API_KEY     — API-ключ сервисного аккаунта (AQVN...)
  YANDEX_STT_LANG    — по умолчанию ru-RU
  YANDEX_STT_TOPIC   — general | maps | dates | names | numbers (опционально)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"

STT_SYNC_URL = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if not key:
            continue
        # Перезаписываем пустые значения из shell — иначе .env «не виден»
        if key not in os.environ or not (os.environ.get(key) or "").strip():
            os.environ[key] = val


def require_env(name: str) -> str:
    val = (os.environ.get(name) or "").strip()
    if not val:
        print(f"Ошибка: не задан {name}")
        print(f"  Ожидается в {ENV_FILE}")
        if ENV_FILE.is_file():
            found = any(
                line.strip().startswith(f"{name}=")
                for line in ENV_FILE.read_text(encoding="utf-8").splitlines()
                if not line.strip().startswith("#")
            )
            if found:
                print(
                    f"  В файле строка {name}=... есть, но значение пустое "
                    "или переменная уже задана в shell пустой строкой."
                )
            else:
                print(f"  В файле нет строки {name}=...")
        else:
            print("  Файл .env в корне репозитория не найден.")
        print("Инструкция: docs/YANDEX_STT_SETUP.md")
        sys.exit(1)
    return val


def guess_format(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in (".ogg", ".opus"):
        return "oggopus"
    if ext in (".wav",):
        return "lpcm"
    if ext in (".mp3",):
        return "mp3"
    return "oggopus"


def convert_to_ogg_opus(
    src: Path,
    *,
    max_seconds: float | None = None,
    offset_seconds: float = 0,
) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print(
            "Для webm/m4a/mp4 нужен ffmpeg в PATH. Установите: sudo apt install ffmpeg\n"
            "Или передайте готовый .ogg / .wav файл."
        )
        sys.exit(1)
    tmp = Path(tempfile.mkstemp(suffix=".ogg")[1])
    cmd = [
        ffmpeg,
        "-y",
    ]
    if max_seconds and max_seconds > 0:
        cmd.extend(["-t", str(max_seconds)])
    if offset_seconds > 0:
        cmd.extend(["-ss", str(offset_seconds)])
    cmd.extend(
        [
            "-i",
            str(src),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "48000",
            "-c:a",
            "libopus",
            str(tmp),
        ]
    )
    clip = ""
    if offset_seconds > 0:
        clip += f", с {offset_seconds:.0f} с"
    if max_seconds:
        clip += f", длина {max_seconds:.0f} с"
    print(f"Конвертация {src.name} → ogg/opus{clip}…")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print("ffmpeg ошибка:", proc.stderr[-500:] if proc.stderr else proc.stdout)
        sys.exit(1)
    return tmp


def find_sample_audio() -> Path:
    """Последний audio/recording.webm из recordings/ (реальная речь кандидата)."""
    recordings = ROOT / "recordings"
    if not recordings.is_dir():
        print(f"Папка recordings не найдена: {recordings}")
        sys.exit(1)
    candidates = sorted(
        recordings.glob("*/audio/recording.webm"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        print("Нет recordings/*/audio/recording.webm — укажите путь к файлу вручную.")
        sys.exit(1)
    return candidates[0]


def list_sample_candidates(limit: int = 5) -> list[Path]:
    recordings = ROOT / "recordings"
    return sorted(
        recordings.glob("*/audio/recording.webm"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]


def recognize_file_segment(
    path: Path,
    *,
    folder_id: str,
    auth_header: str,
    lang: str,
    topic: str | None,
    offset_seconds: float,
    max_seconds: float,
) -> str:
    audio_bytes, fmt, temp = prepare_audio(
        path,
        max_seconds=max_seconds,
        offset_seconds=offset_seconds,
    )
    try:
        return recognize_sync_v1(
            audio_bytes,
            folder_id=folder_id,
            auth_header=auth_header,
            lang=lang,
            topic=topic,
            fmt=fmt,
        )
    finally:
        if temp and temp.exists():
            temp.unlink(missing_ok=True)


def run_sample_recognition(
    *,
    folder_id: str,
    auth_header: str,
    lang: str,
    topic: str | None,
    max_seconds: float,
    preferred_offset: float,
) -> tuple[str, Path, float]:
    """Подобрать фрагмент с речью: несколько смещений и последние записи."""
    offsets = []
    for off in (preferred_offset, 120.0, 90.0, 60.0, 30.0, 0.0):
        if off not in offsets:
            offsets.append(off)

    for path in list_sample_candidates():
        for offset in offsets:
            print(
                f"\nПробуем {path.relative_to(ROOT)} "
                f"(с {offset:.0f} с, {max_seconds:.0f} с)…"
            )
            text = recognize_file_segment(
                path,
                folder_id=folder_id,
                auth_header=auth_header,
                lang=lang,
                topic=topic,
                offset_seconds=offset,
                max_seconds=max_seconds,
            )
            if text.strip():
                return text.strip(), path, offset
    return "", list_sample_candidates()[0], preferred_offset


def parse_args(argv: list[str]) -> tuple[Path | None, float | None, float, bool, bool]:
    args = [a for a in argv if a]
    check_auth = "--check-auth" in args
    use_sample = "--sample" in args
    if check_auth:
        args.remove("--check-auth")
    if use_sample:
        args.remove("--sample")
    max_seconds: float | None = None
    offset_seconds = 0.0
    if "--seconds" in args:
        idx = args.index("--seconds")
        if idx + 1 >= len(args):
            print("Укажите число после --seconds, например: --seconds 25")
            sys.exit(1)
        try:
            max_seconds = float(args[idx + 1])
        except ValueError:
            print("Некорректное значение --seconds")
            sys.exit(1)
        del args[idx : idx + 2]
    if "--offset" in args:
        idx = args.index("--offset")
        if idx + 1 >= len(args):
            print("Укажите число после --offset, например: --offset 90")
            sys.exit(1)
        try:
            offset_seconds = float(args[idx + 1])
        except ValueError:
            print("Некорректное значение --offset")
            sys.exit(1)
        del args[idx : idx + 2]
    if check_auth and use_sample:
        print("Используйте либо --check-auth, либо --sample.")
        sys.exit(1)
    if check_auth:
        if args:
            print("С --check-auth не передавайте путь к файлу.")
            sys.exit(1)
        return None, max_seconds, offset_seconds, True, False
    if use_sample:
        if args:
            print("С --sample не передавайте путь к файлу.")
            sys.exit(1)
        return find_sample_audio(), max_seconds or 25.0, offset_seconds or 90.0, False, True
    if len(args) != 1:
        print(__doc__)
        sys.exit(1)
    return Path(args[0]).expanduser().resolve(), max_seconds, offset_seconds, False, False


def prepare_audio(
    path: Path,
    *,
    max_seconds: float | None = None,
    offset_seconds: float = 0,
) -> tuple[bytes, str, Path | None]:
    """Вернуть (bytes, format, temp_file_to_delete)."""
    if not path.is_file():
        print(f"Файл не найден: {path}")
        sys.exit(1)
    temp: Path | None = None
    audio_path = path
    if path.suffix.lower() in (".webm", ".m4a", ".mp4", ".mkv"):
        audio_path = convert_to_ogg_opus(
            path,
            max_seconds=max_seconds,
            offset_seconds=offset_seconds,
        )
        temp = audio_path
    elif (max_seconds and max_seconds > 0) or offset_seconds > 0:
        print("Флаги --seconds/--offset работают для webm/m4a/mp4/mkv; для ogg/wav обрежьте файл вручную.")
    fmt = guess_format(audio_path)
    data = audio_path.read_bytes()
    if len(data) < 200:
        print("Слишком короткий аудиофайл.")
        sys.exit(1)
    return data, fmt, temp


def mask_secret(value: str, visible: int = 4) -> str:
    value = (value or "").strip()
    if len(value) <= visible * 2:
        return "***"
    return f"{value[:visible]}...{value[-visible:]}"


def probe_folder_id(api_key: str, folder_id: str) -> bool:
    """Проверить folderId и авторизацию. True = OK."""
    bogus = folder_id[:-1] + ("0" if folder_id[-1] != "0" else "1")
    headers = {"Authorization": f"Api-Key {api_key}"}
    probe_audio = make_silent_ogg(0.5)
    with httpx.Client(timeout=30.0) as client:
        ok = client.post(
            STT_SYNC_URL,
            headers=headers,
            params={"folderId": folder_id, "lang": "ru-RU", "format": "oggopus"},
            content=probe_audio,
        )
        bad = client.post(
            STT_SYNC_URL,
            headers=headers,
            params={"folderId": bogus, "lang": "ru-RU", "format": "oggopus"},
            content=probe_audio,
        )
    ok_msg = ""
    bad_msg = ""
    try:
        ok_msg = str(ok.json().get("error_message") or "")
    except Exception:
        ok_msg = ok.text[:120]
    try:
        bad_msg = str(bad.json().get("error_message") or "")
    except Exception:
        bad_msg = bad.text[:120]

    print(f"  folderId {folder_id}: HTTP {ok.status_code}")
    if "InvalidArgument" in ok_msg and "folder ID" in ok_msg:
        print("  ⚠ Похоже, ID каталога неверный (API не принимает folderId).")
    elif "PermissionDenied" in ok_msg or "Permission denied" in ok_msg:
        print("  ⚠ Нет прав на STT (роль SA на каталоге / scope ключа / биллинг).")
    elif ok.status_code == 200:
        print("  ✓ Авторизация и folderId в порядке.")
    if "InvalidArgument" in bad_msg and "folder ID" in bad_msg:
        print("  ✓ Контрольная проверка: заведомо неверный folderId отклоняется — формат ID верный.")
    return ok.status_code == 200


def print_permission_help() -> None:
    print(
        """
--- Что проверить в console.cloud.yandex.ru ---

1) Роль на КАТАЛОГЕ для СЕРВИСНОГО АККАУНТА (не ваш логин!)
   → Каталог default → Права доступа → Назначить роли
   → субъект: сервисный аккаунт maxai → роль: ai.speechkit-stt.user
   НЕ путать с «Права доступа» внутри карточки SA — там другая страница.

2) API-ключ создан у ЭТОГО сервисного аккаунта
   → вкладка «API-ключи» → при создании scope ОБЯЗАТЕЛЕН:
   → yc.ai.speechkitStt.execute  (в UI: «Распознавание речи» / SpeechKit STT)
   Если scope другой (только TTS, monitoring и т.д.) — будет Permission denied.

3) Биллинг
   → Биллинг → платёжный аккаунт привязан к облаку, статус Active.

4) Проще всего: удалить старый API-ключ → создать новый
   → scope: yc.ai.speechkitStt.execute
   → сразу скопировать в .env → сохранить файл (Ctrl+S).

Подсказка: последние 6 символов ключа в консоли (masked secret) должны совпадать
с концом вашего YANDEX_API_KEY — так вы убедитесь, что ключ тот самый.
"""
    )


def recognize_sync_v1(
    audio_bytes: bytes,
    *,
    folder_id: str,
    auth_header: str,
    lang: str,
    topic: str | None,
    fmt: str,
) -> str:
    params: dict[str, str] = {
        "folderId": folder_id,
        "lang": lang,
        "format": fmt,
    }
    if topic:
        params["topic"] = topic

    headers = {"Authorization": auth_header}

    print(f"Запрос: POST {STT_SYNC_URL}")
    print(f"  folderId={folder_id}, lang={lang}, format={fmt}, size={len(audio_bytes) // 1024} КБ")

    with httpx.Client(timeout=120.0) as client:
        resp = client.post(STT_SYNC_URL, params=params, headers=headers, content=audio_bytes)

    if resp.status_code >= 400:
        print(f"HTTP {resp.status_code}")
        try:
            payload = resp.json()
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            err = str(payload.get("error_message") or "")
        except Exception:
            err = resp.text[:800]
            print(err)
        if resp.status_code in (401, 403) and (
            "PermissionDenied" in err or "Permission denied" in err
        ):
            print_permission_help()
        sys.exit(1)

    try:
        payload = resp.json()
    except Exception:
        return resp.text.strip()

    if isinstance(payload, dict):
        if payload.get("error_code"):
            print("Ошибка API:", json.dumps(payload, ensure_ascii=False, indent=2))
            sys.exit(1)
        return str(payload.get("result") or "").strip()
    return str(payload).strip()


def make_silent_ogg(seconds: float = 1.0) -> bytes:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return b"\x00" * 300
    tmp = Path(tempfile.mkstemp(suffix=".ogg")[1])
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=mono",
            "-t",
            str(seconds),
            "-c:a",
            "libopus",
            str(tmp),
        ],
        capture_output=True,
    )
    data = tmp.read_bytes()
    tmp.unlink(missing_ok=True)
    return data


def main() -> None:
    load_dotenv(ENV_FILE)

    audio_path, max_seconds, offset_seconds, check_auth, use_sample = parse_args(sys.argv[1:])
    folder_id = require_env("YANDEX_FOLDER_ID")
    api_key = require_env("YANDEX_API_KEY")
    iam_token = (os.environ.get("YANDEX_IAM_TOKEN") or "").strip()
    lang = os.environ.get("YANDEX_STT_LANG", "ru-RU").strip() or "ru-RU"
    topic = (os.environ.get("YANDEX_STT_TOPIC") or "").strip() or None

    auth_header = f"Bearer {iam_token}" if iam_token else f"Api-Key {api_key}"
    auth_mode = "IAM token" if iam_token else "API key"

    print("Диагностика:")
    print(f"  .env: {ENV_FILE}")
    print(f"  folderId: {folder_id}")
    print(f"  auth: {auth_mode} ({mask_secret(iam_token or api_key)})")
    auth_ok = True
    if not iam_token:
        auth_ok = probe_folder_id(api_key, folder_id)

    if check_auth:
        if auth_ok:
            print("\nOK: авторизация Yandex STT работает (ключи и каталог настроены).")
            print("Для проверки распознавания речи: backend/.venv/bin/python scripts/test_yandex_stt.py --sample")
        else:
            print_permission_help()
            sys.exit(1)
        return

    assert audio_path is not None
    if use_sample:
        print("\nРежим --sample: ищем фрагмент с речью в recordings/…")
        text, used_path, used_offset = run_sample_recognition(
            folder_id=folder_id,
            auth_header=auth_header,
            lang=lang,
            topic=topic,
            max_seconds=max_seconds or 25.0,
            preferred_offset=offset_seconds or 90.0,
        )
        if used_path:
            print(
                f"\nИспользован фрагмент: {used_path.relative_to(ROOT)} "
                f"(с {used_offset:.0f} с, {max_seconds or 25:.0f} с)"
            )
    else:
        if max_seconds is None and audio_path.suffix.lower() in (".webm", ".m4a", ".mp4", ".mkv"):
            print(
                "Подсказка: в начале записи часто брифинг/тишина. "
                "Добавьте --offset 90 --seconds 25 или запустите --sample"
            )
        audio_bytes, fmt, temp = prepare_audio(
            audio_path,
            max_seconds=max_seconds,
            offset_seconds=offset_seconds,
        )
        try:
            text = recognize_sync_v1(
                audio_bytes,
                folder_id=folder_id,
                auth_header=auth_header,
                lang=lang,
                topic=topic,
                fmt=fmt,
            )
        finally:
            if temp and temp.exists():
                temp.unlink(missing_ok=True)

    print("\n--- Распознанный текст ---")
    if text:
        print(text)
    else:
        print("(пусто — возьмите фрагмент с речью: --sample или другой файл / --seconds)")
        sys.exit(2)

    print("\nOK: Yandex STT отвечает, распознавание работает.")


if __name__ == "__main__":
    main()
