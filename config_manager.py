import json
import logging
import os
import re
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)
APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"

MODEL_IDS = (
    "tiny",
    "base",
    "small",
    "medium",
    "large-v2",
    "large-v3",
    "large-v3-turbo",
)
LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}$")
SAFE_HOTKEY_KEY_PATTERN = re.compile(
    r"^(f([1-9]|1[0-2])|pause|scroll lock|insert|home|end|page up|page down|right ctrl|right alt)$"
)
MODIFIERS = {"ctrl", "alt", "shift", "windows"}

DEFAULT_CONFIG = {
    "model": "large-v3-turbo",
    "language": "es",
    "device": "cuda",
    "dictation": {
        "enabled": True,
        "hotkey": "f8",
        "chunk_seconds": 3.0,
        "input_device": None,
        "copy_to_clipboard": True,
        "auto_paste": True,
        "paste_delay_ms": 180,
        "show_overlay": True,
        "overlay_position": "bottom-center",
        "restore_focus": True,
    },
    "web": {
        "live_chunk_seconds": 6.0,
        "open_browser": True,
    },
}


def _merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in incoming.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def normalize_hotkey(value: Any) -> str:
    raw = (
        str(value or "")
        .strip()
        .lower()
        .replace("control", "ctrl")
        .replace("win+", "windows+")
    )
    raw = re.sub(r"\s*\+\s*", "+", raw)
    aliases = {
        "pgup": "page up",
        "pgdn": "page down",
        "ins": "insert",
        "del": "delete",
        "esc": "escape",
    }
    parts = [aliases.get(part, part) for part in raw.split("+") if part]
    if not parts:
        return "f8"
    seen = []
    for part in parts:
        if part not in seen:
            seen.append(part)
    return "+".join(seen)


def validate_hotkey(value: Any) -> tuple[bool, str, str]:
    hotkey = normalize_hotkey(value)
    parts = hotkey.split("+")
    trigger = parts[-1]
    prefix = parts[:-1]
    if len(parts) > 4:
        return False, hotkey, "La combinación tiene demasiadas teclas."
    if any(item not in MODIFIERS for item in prefix):
        return (
            False,
            hotkey,
            "Usa modificadores Ctrl, Alt, Shift o Windows antes de la tecla final.",
        )
    if trigger in MODIFIERS:
        return False, hotkey, "La tecla final debe ser F8, F9 u otra tecla especial."
    if not SAFE_HOTKEY_KEY_PATTERN.fullmatch(trigger):
        return (
            False,
            hotkey,
            "Por seguridad, usa F1-F12 o una tecla especial que no escriba caracteres.",
        )
    return True, hotkey, ""


def validate_config(candidate: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    cfg = _merge(DEFAULT_CONFIG, candidate if isinstance(candidate, dict) else {})
    warnings = []

    if cfg.get("model") not in MODEL_IDS:
        warnings.append("Modelo inválido; se restauró large-v3-turbo.")
        cfg["model"] = DEFAULT_CONFIG["model"]
    language = str(cfg.get("language") or "").strip().lower()
    if language and not LANGUAGE_PATTERN.fullmatch(language):
        warnings.append("Idioma inválido; se restauró detección automática.")
        language = ""
    cfg["language"] = language
    if cfg.get("device") not in {"auto", "cpu", "cuda"}:
        warnings.append("Dispositivo inválido; se restauró automático.")
        cfg["device"] = "auto"

    d = cfg["dictation"]
    d["enabled"] = bool(d.get("enabled", True))
    valid, hotkey, message = validate_hotkey(d.get("hotkey"))
    d["hotkey"] = hotkey if valid else "f8"
    if not valid:
        warnings.append(f"{message} Se restauró F8.")
    try:
        d["chunk_seconds"] = max(1.5, min(float(d.get("chunk_seconds", 3.0)), 10.0))
    except (TypeError, ValueError):
        d["chunk_seconds"] = 3.0
    device = d.get("input_device")
    if device in ("", None, "null"):
        d["input_device"] = None
    else:
        try:
            d["input_device"] = int(device)
        except (TypeError, ValueError):
            d["input_device"] = None
    d["copy_to_clipboard"] = bool(d.get("copy_to_clipboard", True))
    d["auto_paste"] = bool(d.get("auto_paste", True))
    d["show_overlay"] = bool(d.get("show_overlay", True))
    d["restore_focus"] = bool(d.get("restore_focus", True))

    try:
        d["paste_delay_ms"] = max(50, min(int(d.get("paste_delay_ms", 180)), 2000))
    except (TypeError, ValueError):
        d["paste_delay_ms"] = 180
    if d.get("overlay_position") not in {"bottom-center", "top-center", "bottom-right"}:
        d["overlay_position"] = "bottom-center"

    web = cfg["web"]
    try:
        web["live_chunk_seconds"] = max(
            3.0, min(float(web.get("live_chunk_seconds", 6.0)), 15.0)
        )
    except (TypeError, ValueError):
        web["live_chunk_seconds"] = 6.0
    web["open_browser"] = bool(web.get("open_browser", True))
    return cfg, warnings


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        cfg = deepcopy(DEFAULT_CONFIG)
        save_config(cfg, path)
        return cfg
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        cfg, warnings = validate_config(raw)
        for warning in warnings:
            LOGGER.warning("Configuración: %s", warning)
        if cfg != raw:
            save_config(cfg, path)
        return cfg
    except Exception:
        LOGGER.exception(
            "No se pudo leer config.json; se restauran valores predeterminados"
        )
        broken = path.with_name(f"config.corrupta.{os.getpid()}.json")
        try:
            path.replace(broken)
        except OSError:
            pass
        cfg = deepcopy(DEFAULT_CONFIG)
        save_config(cfg, path)
        return cfg


def save_config(
    candidate: dict[str, Any], path: Path = CONFIG_PATH
) -> tuple[dict[str, Any], list[str]]:
    cfg, warnings = validate_config(candidate)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix="config_", suffix=".json", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(cfg, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    LOGGER.info(
        "Configuración guardada | model=%s | language=%s | device=%s | hotkey=%s",
        cfg["model"],
        cfg["language"] or "auto",
        cfg["device"],
        cfg["dictation"]["hotkey"],
    )
    return cfg, warnings
