import argparse
import json
import logging
import sys
import tempfile
import time
import wave
from pathlib import Path

from audio_pipeline import pcm16_to_wav_bytes,prepare_audio
from config_manager import CONFIG_PATH,load_config,validate_config,validate_hotkey
from diagnostics import run_diagnostics
from logging_setup import LOG_DIR,configure_logging,get_file_logger

LOGGER=configure_logging('tests')
APP_DIR=Path(__file__).resolve().parent


def test_core()->list[dict]:
    results=[]
    def add(name,fn):
        started=time.perf_counter()
        try:
            detail=fn()
            results.append({'name':name,'ok':True,'detail':detail or 'OK','seconds':round(time.perf_counter()-started,3)})
        except Exception as exc:
            LOGGER.exception('Autoprueba falló: %s',name)
            results.append({'name':name,'ok':False,'detail':f'{type(exc).__name__}: {exc}','seconds':round(time.perf_counter()-started,3)})

    def config_test():
        cfg,warnings=validate_config({'model':'large-v3-turbo','dictation':{'hotkey':'ctrl+alt+f8'}})
        assert cfg['model']=='large-v3-turbo'
        assert cfg['dictation']['hotkey']=='ctrl+alt+f8'
        return f'config validada; warnings={len(warnings)}'

    def hotkey_test():
        assert validate_hotkey('f8')[0]
        assert validate_hotkey('ctrl+alt+f10')[0]
        assert not validate_hotkey('h')[0]
        return 'F8 y combinaciones seguras validadas'

    def wav_test():
        wav=pcm16_to_wav_bytes(b'\x00\x00'*1600)
        assert wav[:4]==b'RIFF' and len(wav)>3200
        with wave.open(__import__('io').BytesIO(wav),'rb') as handle:
            assert handle.getframerate()==16000 and handle.getnchannels()==1
        return f'WAV válido de {len(wav)} bytes'

    def config_io_test():
        cfg=load_config(CONFIG_PATH)
        assert cfg['model']
        return str(CONFIG_PATH)

    add('Validación de configuración',config_test)
    add('Validación de hotkeys',hotkey_test)
    add('Generación WAV PCM',wav_test)
    add('Lectura de config.json',config_io_test)
    return results


def deep_audio_test()->dict:
    import math,struct
    sample_rate=16000
    frames=bytearray()
    for index in range(sample_rate):
        value=int(3500*math.sin(2*math.pi*440*index/sample_rate))
        frames.extend(struct.pack('<h',value))
    with tempfile.TemporaryDirectory(prefix='feria_test_') as temp:
        folder=Path(temp)
        source=folder/'tone.wav'
        source.write_bytes(pcm16_to_wav_bytes(bytes(frames)))
        output=prepare_audio(source,folder)
        with wave.open(str(output),'rb') as handle:
            return {'path':str(output),'channels':handle.getnchannels(),'rate':handle.getframerate(),'frames':handle.getnframes()}


def main()->int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--quick',action='store_true',help='Pruebas rápidas sin cargar modelos')
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    report={'generated_at':time.strftime('%Y-%m-%d %H:%M:%S'),'core':test_core(),'diagnostics':run_diagnostics(include_audio=True)}
    try:report['audio_pipeline']={'ok':True,'detail':deep_audio_test()}
    except Exception as exc:
        LOGGER.exception('Prueba real de audio falló')
        report['audio_pipeline']={'ok':False,'detail':f'{type(exc).__name__}: {exc}'}
    failures=sum(1 for item in report['core'] if not item['ok'])
    failures+=0 if report['audio_pipeline']['ok'] else 1
    failures+=report['diagnostics']['summary']['errors']
    report['ok']=failures==0;report['failures']=failures
    LOG_DIR.mkdir(parents=True,exist_ok=True)
    (LOG_DIR/'self_test_latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if args.json:print(json.dumps(report,ensure_ascii=False,indent=2))
    else:
        print('\nFERIA TRANSCRIBER · AUTOPRUEBA')
        print('='*60)
        for item in report['core']:
            print(f"[{'OK' if item['ok'] else 'ERROR'}] {item['name']}: {item['detail']}")
        print(f"[{'OK' if report['audio_pipeline']['ok'] else 'ERROR'}] Pipeline de audio: {report['audio_pipeline']['detail']}")
        summary=report['diagnostics']['summary']
        print(f"Diagnóstico: {summary['checks']} comprobaciones · {summary['errors']} errores · {summary['warnings']} avisos")
        print(f"Informe: {LOG_DIR/'self_test_latest.json'}")
        print('='*60)
    return 0 if report['ok'] else 1


if __name__=='__main__':
    raise SystemExit(main())
