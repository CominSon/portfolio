# Монтаж видео интервью

Итоговый кадр **1920×1080** — два столбца по **960×1080**:

```
┌──────────────────┬──────────────────┐
│  Демонстрация    │   Веб-камера     │
│  экрана (вся)    │   (кандидат)     │
└──────────────────┴──────────────────┘
```

Каждая половина **целиком вмещается** (масштаб с сохранением пропорций, поля при необходимости).

## Запись

- **screen** — демонстрация экрана (вся вкладка/окно).
- **camera** — веб-камера.
- **audio** — микрофон на всю сессию (`recordings/<id>/audio/recording.webm`).

## Сборка

```bash
cd "/home/my_profile/Документы/OthersProjects/AITechnicalInterview"
backend/.venv/bin/pip install imageio-ffmpeg   # один раз
backend/.venv/bin/python scripts/build_interview_video.py
# или с ID:
backend/.venv/bin/python scripts/build_interview_video.py 115f90c1-037b-4d0c-a3ec-73d97c666e9e
```

Результат: `exports/video_<interview_id>.mp4` (или `-o путь.mp4`).

### Параметры

| Параметр | Описание |
|----------|----------|
| `--max-duration 300` | Укоротить итог (сек) |
| `-o path.mp4` | Путь к выходному файлу |

После интервью автоматически пишется `recordings/<id>/montage.mp4` и в письме одна ссылка на `/recordings/montage`.

## Звук

Только дорожка **микрофона** (`audio/recording.webm`). Старые интервью без этой папки — без звука.

## Плавность видео

- Монтаж нормализует таймкоды WebM (`fps=25`, `-vsync cfr`, `-shortest`) — без растягивания до длительности сессии.
- Захват в браузере запрашивает **до 30 FPS** для экрана и камеры (Chrome иначе даёт ~5–15 FPS на статичном экране — «слайд-шоу»).
- Уже записанные интервью пересоберите: `MONTAGE_FORCE_REBUILD=true` или `scripts/resend_report_email.py … --video-only`.

## Требования

- `imageio-ffmpeg` (в `requirements-local.txt`) или системный `ffmpeg` / `FFMPEG_PATH` в `.env`.
