import os
import sys
import time

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5001"
AUDIO = sys.argv[2] if len(sys.argv) > 2 else None
EXPECT_TEXT = os.environ.get("FERIA_E2E_EXPECT_TEXT", "1") != "0"

passed = 0
failed = 0


def check(name: str, cond: bool, detail: str = ""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [OK] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name} {detail}")


def session_ready() -> requests.Session:
    s = requests.Session()
    r = s.get(f"{BASE}/")
    assert r.status_code == 200, f"GET / -> {r.status_code}"
    assert "feria_sid" in s.cookies, "cookie feria_sid no emitida"
    assert "feria_csrf" in s.cookies, "cookie feria_csrf no emitida"
    return s


def csrf(s: requests.Session) -> str:
    return s.cookies.get("feria_csrf", "")


print(f"== E2E Feria Transcriber @ {BASE} ==")

# --- 1. Pagina principal y cabeceras de seguridad
s = session_ready()
r = s.get(f"{BASE}/")
check("GET / 200 + HTML", r.status_code == 200 and "Feria" in r.text)
for header, expect in [
    ("X-Frame-Options", "DENY"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("Content-Security-Policy", "default-src 'self'"),
]:
    check(f"header {header}", r.headers.get(header, "").startswith(expect))
check("Cache-Control no-store", r.headers.get("Cache-Control") == "no-store")
check("X-Request-ID presente", bool(r.headers.get("X-Request-ID")))

# --- 2. API basica
r = s.get(f"{BASE}/api/status")
status = r.json()
check("GET /api/status 200", r.status_code == 200)
check("status.ready", status.get("ready") is True)
check("status.version 3.0.0", status.get("version") == "3.0.0")
check("status.model.current", status.get("model", {}).get("current") is not None)

r = s.get(f"{BASE}/api/config")
check(
    "GET /api/config 200 + model",
    r.status_code == 200 and r.json().get("config", {}).get("model"),
)

r = s.get(f"{BASE}/api/languages")
check(
    "GET /api/languages",
    r.status_code == 200 and len(r.json().get("languages", [])) >= 30,
)

r = s.get(f"{BASE}/api/audio-devices")
check("GET /api/audio-devices", r.status_code == 200)

# --- 3. CSRF: POST sin token -> 403
r = s.post(f"{BASE}/api/transcribe")
check(
    "POST /api/transcribe sin CSRF -> 403",
    r.status_code == 403 and r.json().get("error", {}).get("code") == "CSRF_FAILED",
    f"got {r.status_code} {r.text[:120]}",
)

# POST con CSRF pero sin audio -> 400
r = s.post(f"{BASE}/api/transcribe", headers={"X-CSRF-Token": csrf(s)})
check(
    "POST con CSRF sin audio -> 400 AUDIO_MISSING",
    r.status_code == 400 and r.json().get("error", {}).get("code") == "AUDIO_MISSING",
    f"got {r.status_code} {r.text[:120]}",
)

# extension no permitida -> 415
r = s.post(
    f"{BASE}/api/transcribe",
    headers={"X-CSRF-Token": csrf(s)},
    files={"audio": ("malware.exe", b"fake", "application/octet-stream")},
)
check(
    "extension .exe -> 415",
    r.status_code == 415
    and r.json().get("error", {}).get("code") == "AUDIO_TYPE_DENIED",
    f"got {r.status_code} {r.text[:120]}",
)

# modelo invalido -> 400
r = s.post(
    f"{BASE}/api/transcribe",
    headers={"X-CSRF-Token": csrf(s)},
    data={"model": "no-existe"},
    files={"audio": ("a.wav", b"\x00" * 100, "audio/wav")},
)
check(
    "modelo invalido -> 400 MODEL_INVALID",
    r.status_code == 400 and r.json().get("error", {}).get("code") == "MODEL_INVALID",
    f"got {r.status_code} {r.text[:120]}",
)

# --- 4. Transcribir audio real
if AUDIO:
    with open(AUDIO, "rb") as fh:
        audio_bytes = fh.read()
    check(
        "audio de prueba no vacio", len(audio_bytes) > 1000, f"{len(audio_bytes)} bytes"
    )
    started = time.perf_counter()
    r = s.post(
        f"{BASE}/api/transcribe",
        headers={"X-CSRF-Token": csrf(s)},
        data={
            "model": os.environ.get("FERIA_E2E_MODEL", "large-v3-turbo"),
            "language": "es",
        },
        files={"audio": ("prueba.wav", audio_bytes, "audio/wav")},
    )
    elapsed = round(time.perf_counter() - started, 1)
    if r.status_code == 200:
        payload = r.json()
        text = payload.get("text", "")
        print(f"  TRANSCRIPCION ({elapsed}s): {text!r}")
        if EXPECT_TEXT:
            check("transcripcion no vacia", len(text) > 5)
            check(
                "texto contiene 'hola'",
                any(w in text.lower() for w in ["hola", "prueba", "transcripci"]),
                repr(text),
            )
        else:
            print("  (checks de texto omitidos: FERIA_E2E_EXPECT_TEXT=0)")
        check("idioma es", payload.get("language", "").startswith("es"))
        check("total_seconds presente", payload.get("total_seconds") is not None)
        check("request_id presente", bool(payload.get("request_id")))
        check("device cuda o cpu", payload.get("device") in {"cuda", "cpu"})
        check("compute_type presente", bool(payload.get("compute_type")))
        transcribed_text = text
    else:
        transcribed_text = ""
        check(f"transcripcion 200 (got {r.status_code})", False, r.text[:300])

# --- 5. Historial
r = s.get(f"{BASE}/api/history")
check("GET /api/history", r.status_code == 200)
history = r.json().get("items", [])
if AUDIO and transcribed_text:
    check(
        "historial contiene la transcripcion",
        any(i.get("text") == transcribed_text for i in history),
    )

r = s.post(
    f"{BASE}/api/history", headers={"X-CSRF-Token": csrf(s)}, json={"text": "test e2e"}
)
check(
    "POST /api/history con CSRF",
    r.status_code == 200,
    f"got {r.status_code} {r.text[:150]}",
)
if r.status_code == 200:
    item_id = r.json().get("item", {}).get("id")
    r = s.delete(f"{BASE}/api/history/{item_id}", headers={"X-CSRF-Token": csrf(s)})
    check("DELETE /api/history/<id>", r.status_code == 200, f"got {r.status_code}")

# --- 6. Exportacion
if AUDIO and transcribed_text:
    r = s.post(
        f"{BASE}/api/export/pdf",
        headers={"X-CSRF-Token": csrf(s)},
        json={"text": transcribed_text},
    )
    check(
        "export PDF",
        r.status_code == 200
        and r.headers.get("Content-Type", "").startswith("application/pdf"),
        f"got {r.status_code} {r.headers.get('Content-Type')}",
    )
    r = s.post(
        f"{BASE}/api/export/docx",
        headers={"X-CSRF-Token": csrf(s)},
        json={"text": transcribed_text},
    )
    check(
        "export DOCX",
        r.status_code == 200
        and "wordprocessingml" in r.headers.get("Content-Type", ""),
        f"got {r.status_code} {r.headers.get('Content-Type')}",
    )

# --- 7. Config: PUT con CSRF; modelo invalido -> sanado con warning (no 400)
r = s.put(
    f"{BASE}/api/config", headers={"X-CSRF-Token": csrf(s)}, json={"model": "no-existe"}
)
body = (
    r.json() if r.headers.get("Content-Type", "").startswith("application/json") else {}
)
warnings = body.get("warnings", [])
check(
    "PUT /api/config modelo invalido -> sanado con warning",
    r.status_code == 200
    and any("Modelo inv" in w for w in warnings)
    and body.get("config", {}).get("model") == "large-v3-turbo",
    f"got {r.status_code} {r.text[:200]}",
)

# --- 8. Rate limit: 20/min por IP+ruta -> los 400 ocurren antes que los 429
r = s.put(
    f"{BASE}/api/config",
    headers={"X-CSRF-Token": csrf(s)},
    json={"web": {"open_browser": False}},
)
if r.status_code == 200:
    print("  (config restaurada para rate-limit test)")
r = s.post(
    f"{BASE}/api/model/warmup",
    headers={"X-CSRF-Token": csrf(s)},
    json={"model": "tiny", "device": "cpu"},
)
print(f"  warmup tiny (carga modelo): {r.status_code}")
statuses = []
for i in range(22):
    r = s.post(f"{BASE}/api/transcribe", headers={"X-CSRF-Token": csrf(s)})
    statuses.append(r.status_code)
check("rate limit: al menos un 429", 429 in statuses, str(statuses))
first_429 = statuses.index(429) if 429 in statuses else len(statuses)
check(
    "rate limit: 400s todos antes del primer 429",
    all(code == 400 for code in statuses[:first_429])
    and all(code == 429 for code in statuses[first_429:]),
    str(statuses),
)

# --- 9. Token interno (agente de dictado)
try:
    from pathlib import Path as _Path

    token_path = _Path(__file__).resolve().parent.parent / "runtime" / "internal_token"
    token = token_path.read_text(encoding="utf-8").strip()
    r = requests.post(
        f"{BASE}/api/transcribe",
        headers={"X-Internal-Token": token},
        files={"audio": ("a.wav", b"\x00" * 100, "audio/wav")},
    )
    check(
        "token interno sin cookie -> NO 403",
        r.status_code != 403,
        f"got {r.status_code}",
    )
    r2 = requests.post(
        f"{BASE}/api/transcribe",
        headers={"X-Internal-Token": "token-falso"},
        files={"audio": ("a.wav", b"\x00" * 100, "audio/wav")},
    )
    check("token interno falso -> 403", r2.status_code == 403, f"got {r2.status_code}")
except Exception as exc:
    check("token interno leido", False, str(exc))

print(f"\n== RESULTADO: {passed} OK, {failed} FAIL ==")
sys.exit(1 if failed else 0)
