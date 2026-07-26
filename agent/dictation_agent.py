from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import signal
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.audio_capture import AudioStreamInfo, open_input_stream
from agent.overlay import CapsuleOverlay
from agent.windows_integration import (
    get_foreground_window,
    restore_foreground_window,
    send_ctrl_v,
    set_clipboard_text,
)
from audio_pipeline import pcm16_to_wav_bytes
from config_manager import CONFIG_PATH, load_config, normalize_hotkey
from logging_setup import configure_logging
from text_utils import merge_transcript

LOGGER = configure_logging("agent")
CHANNELS = 1
SAMPLE_WIDTH = 2
MIN_FINAL_SECONDS = 0.18
OVERLAP_SECONDS = 0.22


class DictationAgent:
    def __init__(self, server_url: str, state_path: Path, config_path: Path) -> None:
        self.server_url = server_url.rstrip("/")
        self.state_path = state_path
        self.config_path = config_path
        self.config = load_config(config_path)
        self.settings = self.config["dictation"]
        self.hotkey = normalize_hotkey(self.settings["hotkey"])
        self.overlay = CapsuleOverlay(
            self.settings.get("overlay_position", "bottom-center")
        )
        self.overlay.post("hotkey", value=self.hotkey)
        self.overlay_enabled = self.settings.get("show_overlay", True)
        self.recording = False
        self.stopping = False
        self.session_id = ""
        self.stream = None
        self.stream_info: AudioStreamInfo | None = None
        self.sample_rate = 16000
        self.buffer = bytearray()
        self.buffer_lock = threading.Lock()
        self.audio_queue: queue.Queue[tuple[int, bytes] | None] | None = None
        self.worker_thread: threading.Thread | None = None
        self.chunk_thread: threading.Thread | None = None
        self.transcript_parts: list[str] = []
        self.target_window = None
        self.last_error = ""
        self.status = "starting"
        self.model_state: dict = {}
        self._shutdown = threading.Event()
        self._hotkey_hooks = []
        self._state_lock = threading.Lock()
        self._hotkey_lock = threading.Lock()
        self._operation_lock = threading.RLock()
        self._hotkey_down = False
        self._last_level_post = 0.0
        self._chunk_counter = 0
        self._model_was_loading = False

    def _write_state(self, **updates) -> None:
        with self._state_lock:
            microphone = None
            if self.stream_info:
                microphone = {
                    "index": self.stream_info.device_index,
                    "name": self.stream_info.device_name,
                    "hostapi": self.stream_info.hostapi_name,
                    "sample_rate": self.stream_info.sample_rate,
                    "channels": self.stream_info.channels,
                    "latency": self.stream_info.latency,
                    "active": bool(self.stream),
                }
            state = {
                "pid": os.getpid(),
                "status": self.status,
                "hotkey": self.hotkey,
                "hotkey_down": self._hotkey_down,
                "recording": self.recording,
                "session_id": self.session_id,
                "last_error": self.last_error,
                "updated_at": time.time(),
                "server_url": self.server_url,
                "microphone": microphone,
                "model": self.model_state,
            }
            state.update(updates)
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.state_path.with_suffix(".tmp")
            temp.write_text(
                json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(temp, self.state_path)

    def _heartbeat(self) -> None:
        while not self._shutdown.wait(2.0):
            try:
                self._write_state()
            except Exception:
                LOGGER.exception("No se pudo escribir heartbeat")

    def _warmup(self) -> None:
        try:
            import requests

            response = requests.post(
                f"{self.server_url}/api/model/warmup",
                json={"model": self.config["model"], "device": self.config["device"]},
                timeout=10,
            )
            LOGGER.info(
                "Warmup solicitado | status=%s | body=%s",
                response.status_code,
                response.text[:500],
            )
        except Exception:
            LOGGER.exception("No se pudo solicitar warmup; se intentará al dictar")

    def _model_monitor(self) -> None:
        try:
            import requests
        except Exception:
            return
        while not self._shutdown.wait(0.65):
            try:
                response = requests.get(f"{self.server_url}/api/status", timeout=2.5)
                response.raise_for_status()
                warmup = (response.json().get("model") or {}).get("warmup") or {}
                self.model_state = warmup
                working = warmup.get("state") == "working"
                progress = warmup.get("progress")
                self.overlay.post(
                    "progress",
                    value=progress,
                    indeterminate=bool(warmup.get("indeterminate", progress is None)),
                )
                if working:
                    self._model_was_loading = True
                    model = warmup.get("model") or self.config["model"]
                    elapsed = warmup.get("elapsed_seconds", 0)
                    if self.recording:
                        text = "Escuchando · modelo cargando"
                        detail = f"{model} · {elapsed:.0f} s · sigue hablando"
                    elif self.stopping:
                        text = "Cargando modelo para transcribir…"
                        detail = f"{model} · {elapsed:.0f} s"
                    else:
                        text = warmup.get("message") or "Cargando modelo…"
                        detail = f"{model} · {elapsed:.0f} s"
                    if self.overlay_enabled:
                        self.overlay.post(
                            "show", text=text, detail=detail, state="loading"
                        )
                    if not self.recording and not self.stopping:
                        self.status = "model_loading"
                elif self._model_was_loading and warmup.get("state") == "ready":
                    self._model_was_loading = False
                    if not self.recording and not self.stopping:
                        self.status = "idle"
                        if self.overlay_enabled:
                            self.overlay.post(
                                "status",
                                text="Modelo listo",
                                detail=f"{warmup.get('model') or self.config['model']} preparado",
                                state="done",
                            )
                            self.overlay.post(
                                "progress", value=100, indeterminate=False
                            )
                            threading.Timer(
                                1.15, lambda: self.overlay.post("hide")
                            ).start()
                self._write_state()
            except Exception as exc:
                LOGGER.debug("No se pudo consultar el progreso del modelo: %r", exc)

    def _register_hotkey(self) -> None:
        try:
            import keyboard
        except Exception as exc:
            raise RuntimeError(
                "No está instalada la dependencia keyboard. Ejecuta instalar.bat."
            ) from exc
        parts = self.hotkey.split("+")
        trigger = parts[-1]
        modifiers = parts[:-1]

        def modifiers_active() -> bool:
            return all(keyboard.is_pressed(item) for item in modifiers)

        def on_press(_event):
            if not modifiers_active():
                return
            with self._hotkey_lock:
                if self._hotkey_down:
                    return
                self._hotkey_down = True
            LOGGER.debug("Hotkey down | hotkey=%s", self.hotkey)
            threading.Thread(
                target=self.start_recording,
                name="dictation-start",
                daemon=True,
            ).start()

        def on_release(_event):
            with self._hotkey_lock:
                if not self._hotkey_down:
                    return
                self._hotkey_down = False
            LOGGER.debug("Hotkey up | hotkey=%s", self.hotkey)
            threading.Thread(
                target=self.stop_recording,
                name="dictation-stop",
                daemon=True,
            ).start()

        self._hotkey_hooks.append(
            keyboard.on_press_key(trigger, on_press, suppress=True)
        )
        self._hotkey_hooks.append(
            keyboard.on_release_key(trigger, on_release, suppress=True)
        )
        LOGGER.info(
            "Hotkey global registrada | hotkey=%s | trigger=%s | modifiers=%s",
            self.hotkey,
            trigger,
            modifiers,
        )

    def _unregister_hotkey(self) -> None:
        try:
            import keyboard

            for hook in self._hotkey_hooks:
                keyboard.unhook(hook)
            self._hotkey_hooks.clear()
        except Exception:
            LOGGER.exception("No se pudo liberar el hotkey")

    def _audio_callback(self, indata, frames, _time_info, status) -> None:
        if status:
            LOGGER.warning("PortAudio status: %s", status)
        if not self.recording:
            return
        raw = bytes(indata)
        if not raw:
            return
        with self.buffer_lock:
            self.buffer.extend(raw)
        now = time.monotonic()
        if now - self._last_level_post < 0.04:
            return
        self._last_level_post = now
        try:
            import audioop

            rms = audioop.rms(raw, 2)
            level = min(1.0, max(0.0, rms / 6500.0))
            self.overlay.post("level", value=level)
        except Exception:
            pass

    def _open_stream(self):
        requested = self.settings.get("input_device")
        LOGGER.info("Resolviendo micrófono | requested=%s", requested)
        stream, info = open_input_stream(self._audio_callback, requested)
        self.stream_info = info
        self.sample_rate = info.sample_rate
        return stream

    def _to_wav_bytes(self, pcm: bytes) -> bytes:
        return pcm16_to_wav_bytes(pcm, sample_rate=self.sample_rate, channels=CHANNELS)

    def _chunk_loop(self, session_id: str) -> None:
        threshold = int(
            self.sample_rate
            * SAMPLE_WIDTH
            * float(self.settings.get("chunk_seconds", 3.0))
        )
        overlap = int(self.sample_rate * SAMPLE_WIDTH * OVERLAP_SECONDS)
        advance = max(1, threshold - overlap)
        while self.recording and session_id == self.session_id:
            chunk = None
            with self.buffer_lock:
                if len(self.buffer) >= threshold:
                    chunk = bytes(self.buffer[:threshold])
                    del self.buffer[:advance]
            if chunk:
                self._chunk_counter += 1
                self.audio_queue.put((self._chunk_counter, self._to_wav_bytes(chunk)))
                LOGGER.debug(
                    "Chunk encolado | session=%s | index=%s | pcm_bytes=%s | rate=%s",
                    session_id,
                    self._chunk_counter,
                    len(chunk),
                    self.sample_rate,
                )
            else:
                time.sleep(0.05)

    def _append_transcript(self, text: str) -> None:
        existing = " ".join(self.transcript_parts)
        merged, overlap = merge_transcript(existing, text)
        if merged != existing:
            self.transcript_parts = [merged]
        LOGGER.debug(
            "Texto fusionado | incoming_words=%s | overlap=%s | total_words=%s",
            len(text.split()),
            overlap,
            len(merged.split()),
        )

    def _wait_hotkey_release(self, timeout: float = 2.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._hotkey_lock:
                if not self._hotkey_down:
                    return
            time.sleep(0.03)

    def _post_chunk(self, index: int, wav_bytes: bytes) -> str:
        import requests

        files = {"audio": (f"dictado-{index}.wav", wav_bytes, "audio/wav")}
        data = {
            "model": self.config["model"],
            "language": self.config["language"],
            "device": self.config["device"],
            "mode": "dictation",
        }
        started = time.perf_counter()
        response = requests.post(
            f"{self.server_url}/api/transcribe",
            files=files,
            data=data,
            timeout=(10, 3600),
        )
        elapsed = time.perf_counter() - started
        LOGGER.info(
            "Chunk response | index=%s | status=%s | seconds=%.3f | bytes=%s",
            index,
            response.status_code,
            elapsed,
            len(wav_bytes),
        )
        try:
            payload = response.json()
        except Exception as exc:
            raise RuntimeError(
                f"El servidor devolvió una respuesta inválida ({response.status_code})."
            ) from exc
        if not response.ok:
            error = payload.get("error")
            if isinstance(error, dict):
                error = error.get("message")
            raise RuntimeError(str(error or f"Error HTTP {response.status_code}"))
        return str(payload.get("text") or "").strip()

    def _worker(self, session_id: str) -> None:
        try:
            while session_id == self.session_id:
                item = self.audio_queue.get()
                if item is None:
                    break
                index, wav_bytes = item
                warm = self.model_state or {}
                loading = warm.get("state") == "working"
                if self.overlay_enabled:
                    self.overlay.post(
                        "status",
                        text=(
                            "Cargando modelo para transcribir…"
                            if loading
                            else f"Transcribiendo fragmento {index}…"
                        ),
                        detail=(
                            f"{warm.get('model') or self.config['model']} · no cierres la aplicación"
                            if loading
                            else "Procesando el audio localmente"
                        ),
                        state="loading" if loading else "processing",
                    )
                text = self._post_chunk(index, wav_bytes)
                if text:
                    self._append_transcript(text)
                    preview = " ".join(self.transcript_parts)[-82:]
                    if self.overlay_enabled:
                        self.overlay.post(
                            "status",
                            text=preview,
                            detail="Sigue hablando o suelta la tecla para terminar",
                            state="recording" if self.recording else "processing",
                        )
            self._finalize(session_id)
        except Exception as exc:
            LOGGER.exception("Falló el worker de dictado")
            self._fail(str(exc))

    def start_recording(self) -> None:
        with self._operation_lock:
            if self.recording or self.stopping or self._shutdown.is_set():
                return
            with self._hotkey_lock:
                if not self._hotkey_down:
                    return
            self.session_id = uuid.uuid4().hex[:10]
            self.transcript_parts = []
            self.last_error = ""
            self.target_window = get_foreground_window()
            self.audio_queue = queue.Queue()
            self._chunk_counter = 0
            with self.buffer_lock:
                self.buffer.clear()
            try:
                if self.overlay_enabled:
                    self.overlay.post(
                        "show",
                        text="Preparando micrófono…",
                        detail="El sonido de inicio no se incluirá en el dictado",
                        state="loading",
                    )
                    self.overlay.post("progress", value=12, indeterminate=False)
                with self._hotkey_lock:
                    if not self._hotkey_down:
                        if self.overlay_enabled:
                            self.overlay.post("hide")
                        return
                self.stream = self._open_stream()
                with self._hotkey_lock:
                    if not self._hotkey_down:
                        self.stream.stop()
                        self.stream.close()
                        self.stream = None
                        if self.overlay_enabled:
                            self.overlay.post("hide")
                        return
                self.recording = True
                self.stopping = False
                self.status = "recording"
                if self.overlay_enabled:
                    self.overlay.post(
                        "show",
                        text="Escuchando…",
                        detail=f"{self.stream_info.device_name} · {self.sample_rate} Hz",
                        state="recording",
                    )
                    self.overlay.post("progress", value=None, indeterminate=False)
                self._write_state(target_window=self.target_window)
                self.worker_thread = threading.Thread(
                    target=self._worker,
                    args=(self.session_id,),
                    name="dictation-worker",
                    daemon=True,
                )
                self.worker_thread.start()
                self.chunk_thread = threading.Thread(
                    target=self._chunk_loop,
                    args=(self.session_id,),
                    name="audio-chunker",
                    daemon=True,
                )
                self.chunk_thread.start()
                LOGGER.info(
                    "Dictado iniciado | session=%s | target_hwnd=%s | mic=%s | rate=%s",
                    self.session_id,
                    self.target_window,
                    self.stream_info.device_name,
                    self.sample_rate,
                )
            except Exception as exc:
                LOGGER.exception("No se pudo iniciar el dictado")
                self._fail(str(exc))

    def stop_recording(self) -> None:
        with self._operation_lock:
            if not self.recording or self.stopping:
                return
            self.stopping = True
            self.recording = False
            self.status = "processing"
            if self.overlay_enabled:
                self.overlay.post(
                    "status",
                    text="Finalizando audio…",
                    detail="Procesando el último fragmento",
                    state="processing",
                )
                self.overlay.post("progress", value=None, indeterminate=True)
            try:
                if self.stream:
                    self.stream.stop()
                    self.stream.close()
            except Exception:
                LOGGER.exception("Error cerrando el micrófono")
            finally:
                self.stream = None

            if self.chunk_thread and self.chunk_thread.is_alive():
                self.chunk_thread.join(timeout=1.5)
            with self.buffer_lock:
                remaining = bytes(self.buffer)
                self.buffer.clear()
            min_bytes = int(self.sample_rate * SAMPLE_WIDTH * MIN_FINAL_SECONDS)
            if len(remaining) >= min_bytes:
                self._chunk_counter += 1
                self.audio_queue.put(
                    (self._chunk_counter, self._to_wav_bytes(remaining))
                )
                LOGGER.debug(
                    "Chunk final encolado | index=%s | bytes=%s | rate=%s",
                    self._chunk_counter,
                    len(remaining),
                    self.sample_rate,
                )
            self.audio_queue.put(None)
            self._write_state()
            LOGGER.info(
                "Dictado detenido; esperando transcripción | session=%s",
                self.session_id,
            )

    def _finalize(self, session_id: str) -> None:
        if session_id != self.session_id:
            return
        text = " ".join(" ".join(self.transcript_parts).split()).strip()
        if not text:
            self.status = "idle"
            self.stopping = False
            if self.overlay_enabled:
                self.overlay.post(
                    "status",
                    text="No se detectó voz",
                    detail="Comprueba el nivel del micrófono e inténtalo otra vez",
                    state="error",
                )
                self.overlay.post("progress", value=0, indeterminate=False)
                threading.Timer(2.2, lambda: self.overlay.post("hide")).start()
            self._write_state(last_text_preview="")
            LOGGER.info("Dictado finalizado sin texto | session=%s", session_id)
            return
        try:
            should_copy = self.settings.get(
                "copy_to_clipboard", True
            ) or self.settings.get("auto_paste", True)
            if should_copy:
                set_clipboard_text(text)
            if self.settings.get("auto_paste", True):
                self._wait_hotkey_release()
                time.sleep(int(self.settings.get("paste_delay_ms", 180)) / 1000)
                if self.settings.get("restore_focus", True):
                    restore_foreground_window(self.target_window)
                    time.sleep(0.06)
                send_ctrl_v()
            self.status = "idle"
            self.stopping = False
            if self.overlay_enabled:
                self.overlay.post(
                    "status",
                    text=f"Pegado · {len(text)} caracteres",
                    detail="Dictado completado",
                    state="done",
                )
                self.overlay.post("progress", value=100, indeterminate=False)
                threading.Timer(1.25, lambda: self.overlay.post("hide")).start()
            self._write_state(last_text_chars=len(text))
            LOGGER.info(
                "Dictado completado | session=%s | chars=%s | pasted=%s",
                session_id,
                len(text),
                self.settings.get("auto_paste", True),
            )
        except Exception as exc:
            LOGGER.exception("No se pudo copiar o pegar el dictado")
            self._fail(str(exc))

    def _fail(self, message: str) -> None:
        self.last_error = message
        self.status = "error"
        self.recording = False
        self.stopping = False
        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
        except Exception:
            pass
        self.stream = None
        if self.overlay_enabled:
            self.overlay.post(
                "show",
                text=message[:92],
                detail="Consulta logs/agent.log para ver el detalle",
                state="error",
            )
            self.overlay.post("progress", value=0, indeterminate=False)
            threading.Timer(3.8, lambda: self.overlay.post("hide")).start()
        self._write_state()

    def shutdown(self) -> None:
        if self._shutdown.is_set():
            return
        LOGGER.info("Cerrando agente de dictado")
        self._shutdown.set()
        if self.recording:
            self.stop_recording()
        self._unregister_hotkey()
        try:
            self.overlay.root.after(0, self.overlay.root.destroy)
        except Exception:
            pass
        self.status = "stopped"
        self._write_state()

    def run(self) -> None:
        self._register_hotkey()
        self.status = "idle"
        self._write_state()
        threading.Thread(
            target=self._heartbeat, name="agent-heartbeat", daemon=True
        ).start()
        threading.Thread(
            target=self._warmup, name="warmup-request", daemon=True
        ).start()
        threading.Thread(
            target=self._model_monitor, name="model-monitor", daemon=True
        ).start()
        LOGGER.info("Agente listo | hotkey=%s", self.hotkey)
        self.overlay.run()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Feria Transcriber global dictation agent"
    )
    parser.add_argument("--server-url", required=True)
    parser.add_argument(
        "--state-path", default=str(ROOT / "runtime" / "agent_state.json")
    )
    parser.add_argument("--config-path", default=str(CONFIG_PATH))
    args = parser.parse_args()
    agent = DictationAgent(
        args.server_url, Path(args.state_path), Path(args.config_path)
    )

    def stop_handler(_signum, _frame):
        agent.shutdown()

    signal.signal(signal.SIGINT, stop_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop_handler)
    try:
        agent.run()
        return 0
    except Exception as exc:
        LOGGER.exception("El agente terminó por un error fatal")
        agent.last_error = str(exc)
        agent.status = "crashed"
        agent._write_state()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
