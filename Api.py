"""
Classe Api — exposta ao JavaScript via window.pywebview.api
Todos os métodos públicos são chamáveis do frontend.
"""
import os
import sys
# Garante que core/ é encontrado independente de onde o script é chamado
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json
import time
import threading
import subprocess
import base64
from datetime import datetime
import requests

from core.utils import (
    DOMAIN, BASE_URL, CHAVE_MERGE, VERIFY_SSL,
    carregar_credenciais, salvar_credenciais, remover_credenciais,
    carregar_arquivo_preferido, salvar_arquivo_preferido,
    carregar_filtros, salvar_filtros,
    carregar_tema, salvar_tema,
    carregar_acento, salvar_acento,
    range_to_semicolon, ts,
)
from core.extrator import processar_dados, filtrar_dataframe, salvar_com_append_apenas

import pandas as pd


class Api:
    def __init__(self):
        self._window          = None   # injetado pelo main após criação da janela
        self._username        = None
        self._password        = None
        self._em_execucao     = False
        self._session         = None   # referência para cancelamento externo
        self._cancelado       = False  # flag de cancelamento explícito pelo usuário
        self._instalador_path = None
        _docs   = os.path.join(os.path.expanduser('~'), 'Documents')
        _padrao = os.path.join(_docs, 'relatorio_nfe_acumulativo.xlsx')
        self._arquivo = carregar_arquivo_preferido() or _padrao

    # ── Janela ────────────────────────────────────────────────────────────────

    def set_window(self, window):
        self._window = window

    # ── Log / Status / Progress (push para o JS) ──────────────────────────────

    def _log(self, msg, tipo='info'):
        """tipo: info | ok | warn | err"""
        texto = f"[{ts()}] {msg}"
        if self._window:
            self._window.evaluate_js(
                f"appendLog({json.dumps(texto)}, {json.dumps(tipo)})"
            )

    def _status(self, msg, tipo='processando'):
        if self._window:
            self._window.evaluate_js(
                f"setStatus({json.dumps(msg)}, {json.dumps(tipo)})"
            )

    def _progress(self, valor):
        if self._window:
            self._window.evaluate_js(f'setProgress({valor})')

    # ── Credenciais ───────────────────────────────────────────────────────────

    def get_estado_inicial(self):
        """Retorna estado inicial para o frontend: credenciais, arquivo, tema e acento."""
        u, s = carregar_credenciais()
        if u and s:
            self._username = u
            self._password = s
        filtros = carregar_filtros() or {}
        return {
            'usuario':          u or '',
            'usuario_windows':  os.getenv('USERNAME', ''),
            'autenticado':      bool(u and s),
            'arquivo':          self._arquivo,
            'filtros':          filtros,
            'tema':             carregar_tema(),
            'accent':           carregar_acento(),
        }

    def get_tema(self):
        """Retorna o tema salvo."""
        return {'tema': carregar_tema()}

    def set_tema(self, tema):
        """Salva o tema escolhido pelo usuário."""
        salvar_tema(tema)
        return {'ok': True}

    def set_accent(self, accent):
        """Salva o acento de cor escolhido pelo usuário."""
        salvar_acento(accent)
        return {'ok': True}

    def fazer_login(self, username, password, salvar):
        username = username.strip()
        password = password.strip()
        if not username or not password:
            return {'ok': False, 'erro': 'Preencha usuário e senha.'}
        if salvar:
            salvar_credenciais(username, password)
        self._username = username
        self._password = password
        return {'ok': True, 'usuario': username}

    def fazer_logout(self):
        remover_credenciais()
        self._username = None
        self._password = None
        return {'ok': True}

    # ── Arquivo ───────────────────────────────────────────────────────────────

    def escolher_arquivo(self):
        import webview
        resultado = self._window.create_file_dialog(
            webview.FileDialog.SAVE,
            directory=os.path.dirname(self._arquivo),
            save_filename=os.path.basename(self._arquivo),
            file_types=('Excel (*.xlsx)',)
        )
        if resultado:
            caminho = resultado[0] if isinstance(resultado, (list, tuple)) else resultado
            if not caminho.endswith('.xlsx'):
                caminho += '.xlsx'
            self._arquivo = caminho
            salvar_arquivo_preferido(caminho)
            return {'ok': True, 'arquivo': caminho}
        return {'ok': False}

    def limpar_arquivo(self):
        try:
            if os.path.exists(self._arquivo):
                os.remove(self._arquivo)
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'erro': str(e)}

    def abrir_arquivo(self):
        """Abre o arquivo Excel no aplicativo padrão do SO."""
        # Validação de extensão e existência antes de abrir
        if not self._arquivo.endswith('.xlsx'):
            return {'ok': False, 'erro': 'Caminho de arquivo inválido (deve ser .xlsx).'}
        if not os.path.exists(self._arquivo):
            return {'ok': False, 'erro': 'Arquivo não encontrado.'}
        try:
            if sys.platform == 'win32':
                os.startfile(self._arquivo)  # noqa — seguro: sem shell, sem expansão
            else:
                subprocess.run(['open', self._arquivo], check=False)
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'erro': str(e)}

    # ── Auto-update ───────────────────────────────────────────────────────────

    def verificar_atualizacao(self):
        """
        Chamado no startup (via pywebviewready no JS).
        Roda em thread separada para não bloquear a UI.
        """
        threading.Thread(target=self._verificar_thread, daemon=True).start()
        return {'ok': True}

    def _verificar_thread(self):
        from core.updater import verificar_atualizacao
        resultado = verificar_atualizacao()
        if not self._window:
            return
        if resultado.get('disponivel'):
            v            = resultado['versao']
            url_download = resultado['url_download']
            tam          = resultado['tamanho']
            notas        = resultado.get('notas', '')
            self._window.evaluate_js(
                f"onAtualizacaoDisponivel("
                f"{json.dumps(v)}, {json.dumps(url_download)}, {tam}, {json.dumps(notas)})"
            )
        elif resultado.get('erro'):
            self._log(f"Verificação de update: {resultado['erro']}", 'warn')

    def baixar_atualizacao(self, url_download, versao):
        """
        Inicia o download do instalador em background.
        Progresso é enviado via onDownloadProgresso(pct).
        """
        threading.Thread(
            target=self._baixar_thread, args=(url_download, versao), daemon=True
        ).start()
        return {'ok': True}

    def _baixar_thread(self, url_download, versao):
        from core.updater import baixar_instalador, caminho_instalador_temp
        destino = caminho_instalador_temp(versao)
        self._instalador_path = None

        def progresso(pct):
            if self._window:
                self._window.evaluate_js(f'onDownloadProgresso({pct:.3f})')

        ok, erro = baixar_instalador(url_download, destino, progresso_cb=progresso)

        if ok:
            self._instalador_path = destino
            if self._window:
                self._window.evaluate_js('onDownloadConcluido()')
        else:
            if self._window:
                self._window.evaluate_js(
                    f'onDownloadErro({json.dumps(str(erro))})'
                )

    def fechar_e_instalar(self):
        """
        Executa o instalador e fecha o app.
        /SILENT       — janela mínima
        /NORESTART    — não reinicia o Windows
        """
        if not self._instalador_path:
            return {'ok': False, 'erro': 'Instalador não encontrado.'}
        try:
            subprocess.Popen(
                [self._instalador_path, '/SILENT', '/NORESTART'],
                creationflags=0x00000008  # DETACHED_PROCESS
            )
            if self._window:
                self._window.destroy()
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'erro': str(e)}

    # ── Execução principal ────────────────────────────────────────────────────

    def executar(self, params):
        """
        Inicia extração em thread separada.
        params: dict com data_ini, data_fim, estab_de/ate, serie_de/ate,
                nf_de/ate, sit_confirmadas, sit_canceladas, abrir_arquivo
        """
        if self._em_execucao:
            return {'ok': False, 'erro': 'Extração já em andamento.'}
        if not self._username or not self._password:
            return {'ok': False, 'erro': 'Faça login antes de executar.'}

        t = threading.Thread(target=self._executar_thread, args=(params,), daemon=True)
        t.start()
        return {'ok': True}

    def cancelar_extracao(self):
        """
        Cancela a extração em andamento fechando a sessão HTTP.
        A thread detecta o fechamento (ConnectionError) e notifica o frontend
        via onExtracaoCancelada() — distinguindo cancelamento de erro real.
        """
        if not self._em_execucao:
            return {'ok': False, 'erro': 'Nenhuma extração em andamento.'}
        self._cancelado = True
        if self._session:
            try:
                self._session.close()
            except Exception:
                pass
        return {'ok': True}

    def _keepalive(self, session):
        while self._em_execucao:
            try:
                time.sleep(120)
                if self._em_execucao:
                    session.get(
                        f"{BASE_URL}/totvs-login/keepalive",
                        timeout=10,
                        verify=VERIFY_SSL,
                    )
            except Exception:
                pass

    def _executar_thread(self, p):
        self._em_execucao = True
        self._cancelado   = False
        self._progress(0.1)
        tempo_inicio = datetime.now()
        session = None

        try:
            # Validar datas
            try:
                data_ini = datetime.strptime(p['data_ini'], '%d/%m/%Y')
                data_fim = datetime.strptime(p['data_fim'], '%d/%m/%Y')
            except Exception:
                self._status('Formato de data inválido (use DD/MM/AAAA)', 'erro')
                return

            if data_ini > data_fim:
                self._status('Data inicial maior que data final', 'erro')
                return

            self._log(f"Período: {p['data_ini']} a {p['data_fim']}")
            self._status('Conectando ao DataSul...', 'processando')
            self._progress(0.2)

            # Autenticação
            self._log('Conectando ao DataSul...')
            session = requests.Session()
            self._session = session  # expõe para cancelar_extracao()

            try:
                session.post(
                    f"{BASE_URL}/totvs-login/ACS?login",
                    data={
                        'j_username':   self._username,
                        'j_password':   self._password,
                        'j_domain':     DOMAIN,
                        'j_use_domain': 'on',
                        'chosenLang':   'pt',
                    },
                    timeout=30,
                    allow_redirects=True,
                    headers={
                        'User-Agent':   'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Content-Type': 'application/x-www-form-urlencoded',
                    },
                    verify=VERIFY_SSL,
                )
            except Exception as e:
                raise Exception(f"Falha na autenticação: {e}")

            if not session.cookies.get('JSESSIONID'):
                raise Exception('Falha na autenticação: JSESSIONID não recebido')

            self._log('Conexão estabelecida', 'ok')
            threading.Thread(target=self._keepalive, args=(session,), daemon=True).start()

            # Checkpoint: usuário pode ter cancelado durante o login
            if self._cancelado:
                raise Exception('__cancelled__')

            # Requisição
            self._status('Buscando dados...', 'processando')
            self._progress(0.4)
            self._log('Buscando dados...')

            cod_estab = range_to_semicolon(p.get('estab_de', ''), p.get('estab_ate', ''))
            cod_serie = range_to_semicolon(p.get('serie_de', ''), p.get('serie_ate', ''))
            cod_nf    = range_to_semicolon(p.get('nf_de', ''),    p.get('nf_ate', ''))

            sit_opcoes = []
            if p.get('sit_confirmadas'): sit_opcoes.append('5')
            if p.get('sit_canceladas'):  sit_opcoes.append('6')
            ind_sit = ';'.join(sit_opcoes) if sit_opcoes else '5;6'

            filtros_log = ' | '.join(
                ([f"Estab={cod_estab}"] if cod_estab else []) +
                ([f"Série={cod_serie}"] if cod_serie else []) +
                ([f"NF={cod_nf}"]       if cod_nf    else [])
            ) or 'Nenhum (puxar tudo)'
            self._log(f"Filtros: {filtros_log}")

            params_req = {
                'datHoraEmissao': f"{data_ini.strftime('%Y-%m-%d')};{data_fim.strftime('%Y-%m-%d')}"
            }
            body = {
                'wayOfGeneration':    'Online',
                'detailsHeader':       True,
                'accountingGrid':      False,
                'duplicates':          True,
                'noteRemark':          True,
                'invoiceItemNarrative': True,
                'itemTax':             False,
                'trackingInformation': False,
            }
            if cod_estab:  body['codEstab']   = cod_estab
            if cod_serie:  body['codSerie']   = cod_serie
            if cod_nf:     body['codNotaFis'] = cod_nf
            if sit_opcoes: body['indSitNota'] = ind_sit

            response = session.post(
                f"{BASE_URL}/dts/datasul-rest/resources/prg/ftp/v1/relatInvoices/excel",
                params=params_req,
                json=body,
                timeout=300,
                headers={
                    'Origin':  BASE_URL,
                    'Referer': f"{BASE_URL}/totvs-fat-relat/",
                    'Accept':  'application/json, text/plain, */*',
                },
                verify=VERIFY_SSL,
            )

            # Checkpoint: verifica cancelamento logo após o request retornar
            if self._cancelado:
                raise Exception('__cancelled__')

            if response.status_code != 200:
                raise Exception(f"Status {response.status_code}: {response.text[:200]}")

            self._status('Processando dados...', 'processando')
            self._progress(0.65)

            content_type = response.headers.get('content-type', '')
            if content_type.startswith('application/json'):
                json_data = response.json()
                if 'content' not in json_data:
                    raise Exception(f"JSON sem 'content': {str(json_data)[:200]}")
                xml_content = base64.b64decode(json_data['content'])
            else:
                xml_content = response.content

            df_novo = processar_dados(xml_content)

            if df_novo is None or len(df_novo) == 0:
                self._log('Nenhum dado encontrado para o período informado', 'warn')
                self._status('Nenhum dado encontrado', 'atencao')
                return

            df_novo, descartados = filtrar_dataframe(
                df_novo,
                p.get('estab_de', ''), p.get('estab_ate', ''),
                p.get('serie_de', ''), p.get('serie_ate', ''),
                p.get('nf_de', ''),    p.get('nf_ate', ''),
                sit_confirmadas=bool(p.get('sit_confirmadas', True)),
                sit_canceladas= bool(p.get('sit_canceladas',  False)),
            )
            for msg in descartados:
                self._log(f"  {msg}")
            self._log(f"{len(df_novo)} registros encontrados", 'ok')

            # Salvar
            self._status('Salvando arquivo...', 'processando')
            self._progress(0.85)
            self._log('Salvando arquivo...')

            registros_antes = 0
            if os.path.exists(self._arquivo):
                df_existente = pd.read_excel(self._arquivo)
                registros_antes = len(df_existente)
                if all(c in df_novo.columns for c in CHAVE_MERGE):
                    df_novo['_KEY']      = (df_novo['Estab'].astype(str) + '|' +
                                            df_novo['Série'].astype(str) + '|' +
                                            df_novo['Nota Fiscal'].astype(str))
                    df_existente['_KEY'] = (df_existente['Estab'].astype(str) + '|' +
                                            df_existente['Série'].astype(str) + '|' +
                                            df_existente['Nota Fiscal'].astype(str))
                    dups = len(df_novo[df_novo['_KEY'].isin(df_existente['_KEY'])])
                    df_novo = df_novo[~df_novo['_KEY'].isin(df_existente['_KEY'])].drop(columns=['_KEY'])
                    if dups > 0:
                        self._log(f"  {dups} duplicatas ignoradas", 'warn')

            salvar_com_append_apenas(self._arquivo, df_novo)
            total = registros_antes + len(df_novo)
            self._log(f"Total no arquivo: {total} registros", 'ok')

            self._progress(1.0)
            segundos = int((datetime.now() - tempo_inicio).total_seconds())
            self._status(f"Concluído em {segundos}s — {len(df_novo)} registros adicionados", 'sucesso')

            # Persistir filtros usados
            salvar_filtros({
                'data_ini':        p.get('data_ini', ''),
                'data_fim':        p.get('data_fim', ''),
                'estab_de':        p.get('estab_de', ''),
                'estab_ate':       p.get('estab_ate', ''),
                'serie_de':        p.get('serie_de', ''),
                'serie_ate':       p.get('serie_ate', ''),
                'nf_de':           p.get('nf_de', ''),
                'nf_ate':          p.get('nf_ate', ''),
                'sit_confirmadas': p.get('sit_confirmadas', True),
                'sit_canceladas':  p.get('sit_canceladas', False),
            })

            # Notificar frontend do sucesso
            if self._window:
                n     = len(df_novo)
                abrir = bool(p.get('abrir_arquivo', True))
                self._window.evaluate_js(
                    f"onExtracao({{ok:true, n:{n}, segundos:{segundos},"
                    f" arquivo:{json.dumps(self._arquivo)}, abrir:{str(abrir).lower()}}})"
                )

        except Exception as e:
            # Distingue cancelamento intencional de erro real
            if self._cancelado or str(e) == '__cancelled__':
                self._log('Extração cancelada pelo usuário', 'warn')
                self._status('Extração cancelada', 'atencao')
                if self._window:
                    self._window.evaluate_js('onExtracaoCancelada()')
            else:
                self._status(f"Erro: {str(e)}", 'erro')
                self._log(f"Erro: {str(e)}", 'err')
                if self._window:
                    self._window.evaluate_js(
                        f"onExtracao({{ok:false, erro:{json.dumps(str(e))}}})"
                    )

        finally:
            if session:
                try:
                    session.close()
                except Exception:
                    pass
            self._session     = None
            self._em_execucao = False
            self._cancelado   = False
            self._progress(0)
            if self._window:
                self._window.evaluate_js('setExecutando(false)')
