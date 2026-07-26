import importlib
import json
import logging
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from audio_pipeline import get_ffmpeg_executable
from config_manager import CONFIG_PATH,load_config
from logging_setup import LOG_DIR

LOGGER=logging.getLogger(__name__)
APP_DIR=Path(__file__).resolve().parent
RUNTIME_DIR=APP_DIR/'runtime'

DEPENDENCIES=(
    'flask','waitress','faster_whisper','ctranslate2','imageio_ffmpeg',
    'sounddevice','requests','keyboard',
)


def _check(name:str,ok:bool,detail:str,level:str='ok')->dict[str,Any]:
    return {'name':name,'ok':bool(ok),'detail':detail,'level':level if not ok else 'ok'}


def _module_check(module_name:str)->dict[str,Any]:
    try:
        module=importlib.import_module(module_name)
        version=getattr(module,'__version__','instalado')
        return _check(f'Dependencia: {module_name}',True,str(version))
    except Exception as exc:
        return _check(f'Dependencia: {module_name}',False,f'{type(exc).__name__}: {exc}','error')


def _ffmpeg_check()->dict[str,Any]:
    try:
        executable=get_ffmpeg_executable()
        result=subprocess.run([executable,'-version'],capture_output=True,text=True,timeout=15)
        first=(result.stdout or result.stderr).splitlines()[0] if (result.stdout or result.stderr) else executable
        return _check('FFmpeg',result.returncode==0,first,'error')
    except Exception as exc:
        return _check('FFmpeg',False,str(exc),'error')


def _audio_checks()->list[dict[str,Any]]:
    try:
        import sounddevice as sd
        devices=sd.query_devices()
        inputs=[(index,item.get('name','')) for index,item in enumerate(devices) if item.get('max_input_channels',0)>0]
        default=sd.default.device
        detail=f'{len(inputs)} entradas detectadas; predeterminado={default}'
        return [
            _check('Sistema de audio',bool(inputs),detail,'error'),
            {'name':'Dispositivos de entrada','ok':bool(inputs),'detail':inputs,'level':'ok' if inputs else 'error'},
        ]
    except Exception as exc:
        return [_check('Sistema de audio',False,f'{type(exc).__name__}: {exc}','error')]


def _cuda_check()->dict[str,Any]:
    try:
        import ctranslate2
        count=ctranslate2.get_cuda_device_count()
        return _check('CUDA para CTranslate2',count>0,f'{count} GPU compatible(s)' if count else 'No disponible; se usará CPU','warning')
    except Exception as exc:
        return _check('CUDA para CTranslate2',False,f'No disponible: {exc}','warning')


def _nvidia_check()->dict[str,Any]:
    executable=shutil.which('nvidia-smi')
    if not executable:
        return _check('Controlador NVIDIA',False,'nvidia-smi no está disponible','warning')
    try:
        result=subprocess.run([executable,'--query-gpu=name,driver_version,memory.total','--format=csv,noheader'],capture_output=True,text=True,timeout=15)
        detail=(result.stdout or result.stderr).strip()
        return _check('Controlador NVIDIA',result.returncode==0,detail or 'Detectado','warning')
    except Exception as exc:
        return _check('Controlador NVIDIA',False,str(exc),'warning')


def run_diagnostics(include_audio:bool=True)->dict[str,Any]:
    started=time.perf_counter()
    checks=[]
    supported=(3,10)<=sys.version_info[:2]<=(3,12)
    checks.append(_check('Python compatible',supported,f'{platform.python_version()} · recomendado 3.10-3.12','error'))
    checks.append(_check('Sistema operativo',os.name=='nt',f'{platform.system()} {platform.release()} · {platform.machine()}','warning'))
    checks.append(_check('Arquitectura de 64 bits',platform.architecture()[0]=='64bit',platform.architecture()[0],'error'))

    for folder,name in ((APP_DIR,'Carpeta de aplicación'),(LOG_DIR,'Carpeta de logs'),(RUNTIME_DIR,'Carpeta runtime')):
        try:
            folder.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=folder,delete=True) as handle:
                handle.write(b'ok');handle.flush()
            checks.append(_check(name,True,str(folder)))
        except Exception as exc:
            checks.append(_check(name,False,str(exc),'error'))

    checks.extend(_module_check(name) for name in DEPENDENCIES)
    checks.append(_ffmpeg_check())
    checks.append(_cuda_check())
    checks.append(_nvidia_check())
    if include_audio:
        checks.extend(_audio_checks())

    try:
        disk=shutil.disk_usage(APP_DIR)
        free_gb=round(disk.free/(1024**3),2)
        checks.append(_check('Espacio libre',free_gb>=8,f'{free_gb} GB libres; large-v3-turbo puede requerir varios GB','warning'))
    except Exception as exc:
        checks.append(_check('Espacio libre',False,str(exc),'warning'))

    errors=sum(1 for item in checks if not item['ok'] and item['level']=='error')
    warnings=sum(1 for item in checks if not item['ok'] and item['level']=='warning')
    report={
        'generated_at':time.strftime('%Y-%m-%d %H:%M:%S'),
        'duration_seconds':round(time.perf_counter()-started,3),
        'summary':{'ok':errors==0,'errors':errors,'warnings':warnings,'checks':len(checks)},
        'environment':{
            'python':sys.version,
            'executable':sys.executable,
            'platform':platform.platform(),
            'app_dir':str(APP_DIR),
            'hostname':socket.gethostname(),
        },
        'checks':checks,
    }
    LOGGER.info('Diagnóstico completado | errors=%s | warnings=%s | checks=%s',errors,warnings,len(checks))
    return report


def create_support_bundle(destination:Path|None=None)->Path:
    RUNTIME_DIR.mkdir(parents=True,exist_ok=True)
    if destination is None:
        destination=RUNTIME_DIR/f'Feria-Transcriber-Soporte-{time.strftime("%Y%m%d-%H%M%S")}.zip'
    report=run_diagnostics(include_audio=True)
    config=load_config()
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('diagnostico.json',json.dumps(report,ensure_ascii=False,indent=2))
        archive.writestr('config.json',json.dumps(config,ensure_ascii=False,indent=2))
        for path in sorted(LOG_DIR.glob('*.log*')):
            if path.is_file():
                archive.write(path,arcname=f'logs/{path.name}')
        state=RUNTIME_DIR/'agent_state.json'
        if state.exists():
            archive.write(state,arcname='runtime/agent_state.json')
    LOGGER.info('Paquete de soporte creado: %s',destination)
    return destination
