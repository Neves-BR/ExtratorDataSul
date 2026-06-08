"""
Módulo de auto-update — verifica e baixa atualizações via GitHub Releases API.
Repositório público — sem necessidade de autenticação.
"""
import os
import requests
from core.version import APP_VERSION
from packaging.version import Version

# ── Constantes do repositório ─────────────────────────────────────────────────
GITHUB_OWNER = 'Neves-BR'
GITHUB_REPO  = 'ExtratorDataSul'
GITHUB_API   = f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest'

_HEADERS = {
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
}

# ── Verificação de versão ─────────────────────────────────────────────────────

def verificar_atualizacao():
    """
    Consulta o GitHub Releases API e compara com APP_VERSION.
    Repositório público — sem autenticação necessária.

    Retorna dict:
      { 'disponivel': bool, 'versao': str, 'url_download': str,
        'tamanho': int, 'notas': str, 'erro': str|None }
    """
    _vazio = {
        'disponivel': False, 'versao': None,
        'url_download': None, 'tamanho': None, 'notas': None,
    }

    try:
        resp = requests.get(GITHUB_API, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        tag   = data.get('tag_name', '').lstrip('v').strip()
        notas = data.get('body', '')
        asset = next(
            (a for a in data.get('assets', []) if a['name'].endswith('.exe')),
            None
        )

        if not tag or not asset:
            return {**_vazio, 'erro': 'Release sem asset .exe encontrado.'}

        try:
            disponivel = Version(tag) > Version(APP_VERSION)
        except Exception:
            return {**_vazio, 'erro': f'Tag de versão inválida no GitHub: "{tag}"'}

        return {
            'disponivel':   disponivel,
            'versao':       tag,
            'url_download': asset['browser_download_url'],
            'tamanho':      asset['size'],
            'notas':        notas,
            'erro':         None,
        }

    except requests.exceptions.ConnectionError:
        return {**_vazio, 'erro': 'Sem conexão com o GitHub.'}
    except requests.exceptions.Timeout:
        return {**_vazio, 'erro': 'Timeout ao verificar atualizações.'}
    except Exception as e:
        return {**_vazio, 'erro': str(e)}


# ── Download do instalador ────────────────────────────────────────────────────

def baixar_instalador(url_download, destino, progresso_cb=None):
    """
    Baixa o instalador diretamente da URL pública do release.

    progresso_cb(pct: float) é chamado a cada chunk com progresso 0.0–1.0.
    Retorna (True, None) em sucesso ou (False, mensagem_erro).
    """
    try:
        with requests.get(url_download, stream=True,
                          timeout=120, allow_redirects=True) as r:
            r.raise_for_status()
            total   = int(r.headers.get('content-length', 0))
            baixado = 0
            with open(destino, 'wb') as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        baixado += len(chunk)
                        if progresso_cb and total:
                            progresso_cb(baixado / total)
        return True, None
    except Exception as e:
        try:
            if os.path.exists(destino):
                os.remove(destino)
        except Exception:
            pass
        return False, str(e)


def caminho_instalador_temp(versao):
    """Retorna o caminho padrão para o instalador em %TEMP%."""
    import tempfile
    return os.path.join(tempfile.gettempdir(), f'ExtratorDataSul_Setup_v{versao}.exe')