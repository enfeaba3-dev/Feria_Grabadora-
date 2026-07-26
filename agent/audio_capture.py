from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

LOGGER = logging.getLogger(__name__)
COMMON_SAMPLE_RATES = (48000, 44100, 32000, 16000)


@dataclass(frozen=True)
class AudioStreamInfo:
    device_index: int | None
    device_name: str
    hostapi_name: str
    sample_rate: int
    channels: int
    latency: str | None


def candidate_sample_rates(default_rate: Any) -> list[int]:
    values: list[int] = []
    try:
        rate = int(round(float(default_rate)))
        if rate > 0:
            values.append(rate)
    except (TypeError, ValueError):
        pass
    for rate in COMMON_SAMPLE_RATES:
        if rate not in values:
            values.append(rate)
    return values


def _default_input_index(sd: Any) -> int | None:
    try:
        default = sd.default.device
        if isinstance(default, (tuple, list)) and default:
            value = default[0]
        else:
            value = default
        return int(value) if value is not None and int(value) >= 0 else None
    except Exception:
        return None


def _hostapi_name(sd: Any, device: dict[str, Any]) -> str:
    try:
        index = int(device.get("hostapi", -1))
        hostapis = sd.query_hostapis()
        if 0 <= index < len(hostapis):
            return str(hostapis[index].get("name") or f"Host API {index}")
    except Exception:
        pass
    return "Desconocido"


def _device_candidates(sd: Any, requested: int | None) -> list[int | None]:
    devices = list(sd.query_devices())
    valid = [
        index
        for index, item in enumerate(devices)
        if int(item.get("max_input_channels", 0) or 0) > 0
    ]
    ordered: list[int | None] = []
    if requested is not None:
        ordered.append(requested)
    default = _default_input_index(sd)
    if default is not None and default not in ordered:
        ordered.append(default)
    for index in valid:
        if index not in ordered:
            ordered.append(index)
    if not ordered:
        ordered.append(None)
    return ordered


def open_input_stream(
    callback: Callable[..., None],
    requested_device: int | None = None,
) -> tuple[Any, AudioStreamInfo]:
    try:
        import sounddevice as sd
    except Exception as exc:
        raise RuntimeError(
            "No está disponible sounddevice. Ejecuta instalar.bat."
        ) from exc

    devices = list(sd.query_devices())
    errors: list[str] = []
    for device_index in _device_candidates(sd, requested_device):
        try:
            if device_index is None:
                device = sd.query_devices(kind="input")
            elif device_index < 0 or device_index >= len(devices):
                errors.append(f"Dispositivo {device_index}: índice inexistente")
                continue
            else:
                device = devices[device_index]
            channels = 1 if int(device.get("max_input_channels", 0) or 0) >= 1 else 0
            if channels < 1:
                errors.append(f"Dispositivo {device_index}: sin canales de entrada")
                continue
            name = str(device.get("name") or f"Micrófono {device_index}")
            hostapi = _hostapi_name(sd, device)
            for sample_rate in candidate_sample_rates(device.get("default_samplerate")):
                try:
                    sd.check_input_settings(
                        device=device_index,
                        samplerate=sample_rate,
                        channels=channels,
                        dtype="int16",
                    )
                except Exception as exc:
                    errors.append(
                        f"{name} @ {sample_rate} Hz: configuración rechazada ({exc})"
                    )
                    continue
                for latency in ("low", "high", None):
                    kwargs = {
                        "samplerate": sample_rate,
                        "blocksize": 0,
                        "device": device_index,
                        "channels": channels,
                        "dtype": "int16",
                        "callback": callback,
                    }
                    if latency is not None:
                        kwargs["latency"] = latency
                    try:
                        stream = sd.RawInputStream(**kwargs)
                        stream.start()
                        info = AudioStreamInfo(
                            device_index=device_index,
                            device_name=name,
                            hostapi_name=hostapi,
                            sample_rate=sample_rate,
                            channels=channels,
                            latency=latency,
                        )
                        LOGGER.info(
                            "Micrófono abierto | index=%s | name=%s | hostapi=%s | rate=%s | latency=%s",
                            device_index,
                            name,
                            hostapi,
                            sample_rate,
                            latency or "default",
                        )
                        return stream, info
                    except Exception as exc:
                        errors.append(
                            f"{name} @ {sample_rate} Hz / {latency or 'default'}: {exc}"
                        )
                        LOGGER.warning(
                            "Intento de micrófono falló | index=%s | name=%s | rate=%s | latency=%s | error=%r",
                            device_index,
                            name,
                            sample_rate,
                            latency,
                            exc,
                        )
        except Exception as exc:
            errors.append(f"Dispositivo {device_index}: {exc}")

    detail = " | ".join(errors[-8:])
    raise RuntimeError(
        "No se pudo abrir ningún micrófono compatible. "
        "Revisa el dispositivo seleccionado y los permisos de Windows."
        + (f" Detalle: {detail}" if detail else "")
    )
