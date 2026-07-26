from __future__ import annotations

import gc
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)
APP_DIR = Path(__file__).resolve().parent
VENV_SITE_PACKAGES = APP_DIR / ".venv" / "Lib" / "site-packages"

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

if hasattr(os, "add_dll_directory"):
    for folder in (
        VENV_SITE_PACKAGES / "nvidia" / "cublas" / "bin",
        VENV_SITE_PACKAGES / "nvidia" / "cudnn" / "bin",
    ):
        if folder.exists():
            try:
                os.add_dll_directory(str(folder))
                os.environ["PATH"] = f"{folder}{os.pathsep}{os.environ.get('PATH', '')}"
                LOGGER.info("Directorio CUDA añadido: %s", folder)
            except OSError:
                LOGGER.exception("No se pudo añadir directorio CUDA: %s", folder)


@dataclass
class ModelResult:
    text: str
    language: str
    probability: float
    model: str
    device: str
    compute_type: str
    processing_seconds: float
    warning: str | None = None


class ModelService:
    def __init__(self) -> None:
        self._model = None
        self._config: tuple[str, str, str] | None = None
        self._warning: str | None = None
        self._model_lock = threading.RLock()
        self._inference_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._warmup_state: dict[str, Any] = {
            "state": "idle",
            "stage": "idle",
            "message": "Sin preparar",
            "detail": "El modelo se preparará en segundo plano.",
            "model": None,
            "device": None,
            "compute_type": None,
            "progress": 0,
            "indeterminate": False,
            "started_at": None,
            "finished_at": None,
        }
        self._warmup_thread: threading.Thread | None = None

    @staticmethod
    def _imports() -> tuple[Any, Any]:
        try:
            import ctranslate2
            from faster_whisper import WhisperModel

            return ctranslate2, WhisperModel
        except Exception as exc:
            raise RuntimeError(
                "Faltan dependencias de Whisper. Ejecuta instalar.bat y revisa logs/install.log."
            ) from exc

    def _set_state(self, **updates: Any) -> None:
        with self._state_lock:
            self._warmup_state.update(updates)

    def _state_snapshot(self) -> dict[str, Any]:
        with self._state_lock:
            state = dict(self._warmup_state)
        started = state.get("started_at")
        finished = state.get("finished_at")
        if isinstance(started, (int, float)):
            end = finished if isinstance(finished, (int, float)) else time.time()
            state["elapsed_seconds"] = round(max(0.0, end - started), 1)
        else:
            state["elapsed_seconds"] = 0.0
        return state

    def cuda_available(self) -> bool:
        try:
            ctranslate2, _ = self._imports()
            return ctranslate2.get_cuda_device_count() > 0
        except Exception:
            return False

    def status(self) -> dict[str, Any]:
        current = None
        if self._config:
            current = {
                "model": self._config[0],
                "device": self._config[1],
                "compute_type": self._config[2],
            }
        return {
            "current": current,
            "cuda_available": self.cuda_available(),
            "warmup": self._state_snapshot(),
        }

    def _resolve_device(self, preference: str) -> tuple[str, str]:
        preference = preference if preference in {"auto", "cpu", "cuda"} else "auto"
        if preference != "cpu" and self.cuda_available():
            return "cuda", "float16"
        return "cpu", "int8"

    def _mark_ready(
        self,
        model_name: str,
        device: str,
        compute_type: str,
        warning: str | None,
    ) -> None:
        self._set_state(
            state="ready",
            stage="ready",
            message="Modelo preparado",
            detail=warning or f"{model_name} está listo en {device.upper()}.",
            model=model_name,
            device=device,
            compute_type=compute_type,
            progress=100,
            indeterminate=False,
            finished_at=time.time(),
        )

    def load_model(self, model_name: str, device_preference: str = "auto"):
        _, WhisperModel = self._imports()
        target_device, compute_type = self._resolve_device(device_preference)
        config = (model_name, target_device, compute_type)
        with self._model_lock:
            if self._model is not None and self._config == config:
                self._mark_ready(model_name, target_device, compute_type, self._warning)
                return self._model, target_device, compute_type, self._warning

            started_at = time.time()
            self._set_state(
                state="working",
                stage="preparing",
                message="Preparando el modelo…",
                detail=f"Comprobando {model_name} y el motor de ejecución.",
                model=model_name,
                device=device_preference,
                compute_type=None,
                progress=8,
                indeterminate=False,
                started_at=started_at,
                finished_at=None,
            )
            if self._model is not None and self._config != config:
                LOGGER.info("Liberando modelo anterior | config=%s", self._config)
                self._set_state(
                    stage="releasing",
                    message="Liberando el modelo anterior…",
                    detail="Limpiando memoria antes de cargar el nuevo modelo.",
                    progress=18,
                    indeterminate=False,
                )
                self._model = None
                self._config = None
                gc.collect()

            LOGGER.info(
                "Cargando modelo | model=%s | device=%s | compute=%s",
                model_name,
                target_device,
                compute_type,
            )
            self._set_state(
                stage="loading",
                message="Descargando o cargando el modelo…",
                detail="La primera vez puede descargar varios archivos. La barra se anima mientras no existe un porcentaje fiable.",
                device=target_device,
                compute_type=compute_type,
                progress=None,
                indeterminate=True,
            )
            started = time.perf_counter()
            warning = None
            try:
                model = WhisperModel(
                    model_name, device=target_device, compute_type=compute_type
                )
            except Exception as exc:
                if target_device != "cuda":
                    LOGGER.exception("No se pudo cargar el modelo en CPU")
                    self._set_state(
                        state="error",
                        stage="error",
                        message="No se pudo cargar el modelo",
                        detail=str(exc),
                        progress=0,
                        indeterminate=False,
                        finished_at=time.time(),
                    )
                    raise
                LOGGER.exception("Fallo CUDA; reintentando en CPU")
                target_device, compute_type = "cpu", "int8"
                config = (model_name, target_device, compute_type)
                warning = f"CUDA falló y se cambió a CPU automáticamente: {exc}"
                self._set_state(
                    stage="fallback",
                    message="CUDA falló · cambiando a CPU…",
                    detail="El modelo seguirá funcionando, aunque puede transcribir más lento.",
                    device=target_device,
                    compute_type=compute_type,
                    progress=None,
                    indeterminate=True,
                )
                try:
                    model = WhisperModel(
                        model_name, device=target_device, compute_type=compute_type
                    )
                except Exception as cpu_exc:
                    self._set_state(
                        state="error",
                        stage="error",
                        message="No se pudo cargar el modelo",
                        detail=str(cpu_exc),
                        progress=0,
                        indeterminate=False,
                        finished_at=time.time(),
                    )
                    raise

            self._set_state(
                stage="finalizing",
                message="Finalizando la carga…",
                detail="Verificando el modelo y preparando la memoria.",
                progress=92,
                indeterminate=False,
            )
            self._model = model
            self._config = config
            self._warning = warning
            elapsed = time.perf_counter() - started
            self._mark_ready(model_name, target_device, compute_type, warning)
            LOGGER.info(
                "Modelo listo | model=%s | device=%s | seconds=%.2f",
                model_name,
                target_device,
                elapsed,
            )
            return model, target_device, compute_type, warning

    def warmup_async(
        self, model_name: str, device_preference: str = "auto"
    ) -> dict[str, Any]:
        with self._state_lock:
            if self._warmup_thread and self._warmup_thread.is_alive():
                return self._state_snapshot()

            def runner() -> None:
                try:
                    self.load_model(model_name, device_preference)
                except Exception:
                    LOGGER.exception("Warmup del modelo falló")

            self._warmup_thread = threading.Thread(
                target=runner, name="model-warmup", daemon=True
            )
            self._warmup_thread.start()
        return self._state_snapshot()

    def transcribe(
        self,
        audio_path: Path,
        model_name: str,
        language: str | None,
        device_preference: str,
        mode: str,
    ) -> ModelResult:
        started = time.perf_counter()
        is_live = mode in {"live", "dictation"}
        with self._inference_lock:
            model, device, compute_type, warning = self.load_model(
                model_name, device_preference
            )
            LOGGER.info(
                "Transcripción start | mode=%s | model=%s | device=%s | file=%s | bytes=%s",
                mode,
                model_name,
                device,
                audio_path.name,
                audio_path.stat().st_size,
            )
            segments, info = model.transcribe(
                str(audio_path),
                language=language,
                vad_filter=True,
                vad_parameters={
                    "threshold": 0.46 if is_live else 0.5,
                    "min_speech_duration_ms": 120 if is_live else 280,
                    "min_silence_duration_ms": 260 if is_live else 600,
                    "speech_pad_ms": 160,
                },
                beam_size=1 if is_live else 10,
                best_of=1 if is_live else 10,
                condition_on_previous_text=not is_live,
                without_timestamps=is_live,
                temperature=0.0,
                patience=0.5 if is_live else 2.0,
                compression_ratio_threshold=2.4,
                no_repeat_ngram_size=5 if is_live else 3,
                repetition_penalty=1.1 if is_live else 1.2,
            )
            text = " ".join(
                segment.text.strip() for segment in segments if segment.text.strip()
            )
        elapsed = round(time.perf_counter() - started, 3)
        LOGGER.info(
            "Transcripción done | chars=%s | language=%s | probability=%.3f | seconds=%.3f",
            len(text),
            getattr(info, "language", ""),
            float(getattr(info, "language_probability", 0.0)),
            elapsed,
        )
        return ModelResult(
            text=text,
            language=getattr(info, "language", ""),
            probability=round(float(getattr(info, "language_probability", 0.0)), 3),
            model=model_name,
            device=device,
            compute_type=compute_type,
            processing_seconds=elapsed,
            warning=warning,
        )
