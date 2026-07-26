import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_DIR=Path(__file__).resolve().parent
LOG_DIR=APP_DIR/'logs'
LOG_DIR.mkdir(parents=True,exist_ok=True)

_FORMAT='%(asctime)s | %(levelname)-8s | %(processName)s:%(threadName)s | %(name)s | %(message)s'
_DATE_FORMAT='%Y-%m-%d %H:%M:%S'


def configure_logging(name:str='app',console:bool=True)->logging.Logger:
    logger=logging.getLogger()
    if getattr(logger,'_feria_configured',False):
        return logging.getLogger(name)

    logger.setLevel(logging.DEBUG)
    formatter=logging.Formatter(_FORMAT,datefmt=_DATE_FORMAT)

    file_handler=RotatingFileHandler(
        LOG_DIR/f'{name}.log',
        maxBytes=5*1024*1024,
        backupCount=5,
        encoding='utf-8',
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if console:
        console_handler=logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    logging.captureWarnings(True)
    logger._feria_configured=True
    logging.getLogger(name).info(
        'Logging iniciado | pid=%s | python=%s | cwd=%s',
        os.getpid(),sys.version.split()[0],Path.cwd(),
    )
    return logging.getLogger(name)


def get_file_logger(name:str)->logging.Logger:
    logger=logging.getLogger(name)
    marker=f'_feria_handler_{name}'
    if getattr(logger,marker,False):
        return logger
    formatter=logging.Formatter(_FORMAT,datefmt=_DATE_FORMAT)
    handler=RotatingFileHandler(
        LOG_DIR/f'{name}.log',maxBytes=5*1024*1024,backupCount=5,encoding='utf-8',
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    setattr(logger,marker,True)
    return logger


def tail_log(path:Path,max_lines:int=300)->list[str]:
    if not path.exists():
        return []
    max_lines=max(1,min(int(max_lines),2000))
    with path.open('r',encoding='utf-8',errors='replace') as handle:
        lines=handle.readlines()
    return [line.rstrip('\n') for line in lines[-max_lines:]]
