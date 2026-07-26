import logging
import subprocess
import wave
from io import BytesIO
from pathlib import Path

LOGGER=logging.getLogger(__name__)
AUDIO_FILTER=','.join([
    'highpass=f=70',
    'lowpass=f=7900',
    'afftdn=nf=-25',
    'dynaudnorm=f=150:g=15:p=0.95',
])
FFMPEG_TIMEOUT=3600


def get_ffmpeg_executable()->str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        LOGGER.exception('No se pudo localizar FFmpeg')
        raise RuntimeError('FFmpeg no está disponible. Ejecuta instalar.bat o diagnostico.bat.') from exc


def prepare_audio(source:Path,work_dir:Path)->Path:
    work_dir.mkdir(parents=True,exist_ok=True)
    output=work_dir/f'{source.stem}_clean.wav'
    ffmpeg=get_ffmpeg_executable()
    command=[
        ffmpeg,'-y','-hide_banner','-loglevel','error','-i',str(source),'-vn',
        '-ac','1','-ar','16000','-af',AUDIO_FILTER,str(output),
    ]
    LOGGER.debug('FFmpeg start | source=%s | bytes=%s | output=%s',source,source.stat().st_size,output)
    try:
        completed=subprocess.run(command,check=True,timeout=FFMPEG_TIMEOUT,capture_output=True,text=True)
        if completed.stderr:
            LOGGER.debug('FFmpeg stderr: %s',completed.stderr.strip())
    except subprocess.CalledProcessError as exc:
        detail=(exc.stderr or exc.stdout or str(exc)).strip()
        LOGGER.error('FFmpeg falló | code=%s | detail=%s',exc.returncode,detail)
        raise RuntimeError(f'FFmpeg no pudo convertir el audio: {detail[-800:]}') from exc
    except subprocess.TimeoutExpired as exc:
        LOGGER.error('FFmpeg superó el tiempo límite | source=%s',source)
        raise RuntimeError('La conversión del audio superó el tiempo máximo permitido.') from exc
    if not output.exists() or output.stat().st_size<44:
        raise RuntimeError('FFmpeg terminó sin generar un WAV válido.')
    LOGGER.debug('FFmpeg done | output_bytes=%s',output.stat().st_size)
    return output


def pcm16_to_wav_bytes(pcm:bytes,sample_rate:int=16000,channels:int=1)->bytes:
    buffer=BytesIO()
    with wave.open(buffer,'wb') as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()
