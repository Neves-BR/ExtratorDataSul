#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extrator DataSul NF-e — PyWebView
Ponto de entrada: python extrator_pywebview.py
"""
import os
import sys
import time

t0 = time.time()
def log_tempo(msg):
    print(f"[{time.time()-t0:.2f}s] {msg}")

log_tempo("Inicio")

def base_dir():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS # noqa
    return os.path.dirname(os.path.abspath(__file__))

BASE = base_dir()
sys.path.insert(0, BASE)
log_tempo("base_dir OK")

import webview
log_tempo("webview importado")

from Api import Api
log_tempo("Api importado")

from core.updater import APP_VERSION
versao = APP_VERSION

def main():
    api = Api()
    log_tempo("Api instanciada")

    ui_path = os.path.join(BASE, 'ui', 'index.html')

    window = webview.create_window(
        title            = f'DataSul NF-e Extrator {versao}',
        url              = f'file:///{ui_path.replace(os.sep, "/")}',
        js_api           = api,
        width            = 850,
        height           = 720,
        min_size         = (700, 550),
        resizable        = False,
        # Cor alinhada ao tema dark (#0b0f1a = --bg do data-theme="dark")
        # Elimina o flash branco antes do WebView renderizar o primeiro frame
        background_color = '#faf8f4',
    )
    api.set_window(window)
    log_tempo("create_window OK")

    def on_loaded():
        log_tempo("on_loaded (app pronto)")

    webview.start(on_loaded, debug=False)
    log_tempo("webview.start retornou")

if __name__ == '__main__':
    main()
