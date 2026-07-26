import ctypes
import logging
import time
from ctypes import wintypes

LOGGER=logging.getLogger(__name__)

CF_UNICODETEXT=13
GMEM_MOVEABLE=0x0002
SW_SHOW=5
VK_CONTROL=0x11
VK_V=0x56
KEYEVENTF_KEYUP=0x0002


def _apis():
    if not hasattr(ctypes,'windll'):
        raise RuntimeError('Esta función solo está disponible en Windows.')
    user32=ctypes.windll.user32
    kernel32=ctypes.windll.kernel32

    user32.GetForegroundWindow.restype=wintypes.HWND
    user32.SetForegroundWindow.argtypes=[wintypes.HWND]
    user32.SetForegroundWindow.restype=wintypes.BOOL
    user32.ShowWindow.argtypes=[wintypes.HWND,ctypes.c_int]
    user32.ShowWindow.restype=wintypes.BOOL
    user32.BringWindowToTop.argtypes=[wintypes.HWND]
    user32.BringWindowToTop.restype=wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype=wintypes.DWORD
    user32.AttachThreadInput.argtypes=[wintypes.DWORD,wintypes.DWORD,wintypes.BOOL]
    user32.AttachThreadInput.restype=wintypes.BOOL

    user32.OpenClipboard.argtypes=[wintypes.HWND]
    user32.OpenClipboard.restype=wintypes.BOOL
    user32.EmptyClipboard.restype=wintypes.BOOL
    user32.SetClipboardData.argtypes=[wintypes.UINT,ctypes.c_void_p]
    user32.SetClipboardData.restype=ctypes.c_void_p
    user32.CloseClipboard.restype=wintypes.BOOL

    kernel32.GlobalAlloc.argtypes=[wintypes.UINT,ctypes.c_size_t]
    kernel32.GlobalAlloc.restype=ctypes.c_void_p
    kernel32.GlobalLock.argtypes=[ctypes.c_void_p]
    kernel32.GlobalLock.restype=ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes=[ctypes.c_void_p]
    kernel32.GlobalUnlock.restype=wintypes.BOOL
    kernel32.GlobalFree.argtypes=[ctypes.c_void_p]
    kernel32.GlobalFree.restype=ctypes.c_void_p
    kernel32.GetCurrentThreadId.restype=wintypes.DWORD
    return user32,kernel32


def get_foreground_window()->int|None:
    try:
        user32,_=_apis()
        hwnd=user32.GetForegroundWindow()
        return int(hwnd) if hwnd else None
    except Exception:
        LOGGER.exception('No se pudo obtener la ventana activa')
        return None


def restore_foreground_window(hwnd:int|None)->bool:
    if not hwnd:
        return False
    try:
        user32,kernel32=_apis()
        target=hwnd
        foreground_raw=user32.GetForegroundWindow()
        foreground=int(foreground_raw) if foreground_raw else 0
        if foreground==target:
            return True
        process_id=wintypes.DWORD()
        target_thread=user32.GetWindowThreadProcessId(target,ctypes.byref(process_id))
        foreground_thread=user32.GetWindowThreadProcessId(foreground,None) if foreground else 0
        current_thread=kernel32.GetCurrentThreadId()
        attached=[]
        try:
            for thread_id in {target_thread,foreground_thread}:
                if thread_id and thread_id!=current_thread and user32.AttachThreadInput(current_thread,thread_id,True):
                    attached.append(thread_id)
            user32.ShowWindow(target,SW_SHOW)
            user32.BringWindowToTop(target)
            success=bool(user32.SetForegroundWindow(target))
            LOGGER.info('Restauración de foco | hwnd=%s | success=%s',hwnd,success)
            return success
        finally:
            for thread_id in attached:
                user32.AttachThreadInput(current_thread,thread_id,False)
    except Exception:
        LOGGER.exception('No se pudo restaurar la ventana activa')
        return False


def set_clipboard_text(text:str)->None:
    user32,kernel32=_apis()
    encoded=(text+'\0').encode('utf-16-le')
    for attempt in range(10):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.035*(attempt+1))
    else:
        raise RuntimeError('No se pudo abrir el portapapeles; otra aplicación lo está bloqueando.')
    handle=None
    try:
        if not user32.EmptyClipboard():
            LOGGER.warning('EmptyClipboard devolvió false')
        handle=kernel32.GlobalAlloc(GMEM_MOVEABLE,len(encoded))
        if not handle:
            raise MemoryError('No se pudo reservar memoria para el portapapeles.')
        pointer=kernel32.GlobalLock(handle)
        if not pointer:
            raise MemoryError('No se pudo bloquear la memoria del portapapeles.')
        ctypes.memmove(pointer,encoded,len(encoded))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT,handle):
            raise RuntimeError('Windows rechazó el contenido del portapapeles.')
        handle=None
    finally:
        user32.CloseClipboard()
        if handle:
            kernel32.GlobalFree(handle)
    LOGGER.info('Texto copiado al portapapeles | chars=%s',len(text))


def send_ctrl_v()->None:
    user32,_=_apis()
    user32.keybd_event(VK_CONTROL,0,0,0)
    user32.keybd_event(VK_V,0,0,0)
    user32.keybd_event(VK_V,0,KEYEVENTF_KEYUP,0)
    user32.keybd_event(VK_CONTROL,0,KEYEVENTF_KEYUP,0)
    LOGGER.info('Combinación Ctrl+V enviada')
