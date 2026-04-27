"""
Módulo de auto-update — verifica e baixa atualizações via GitHub Releases API.
Repositório privado: requer PAT armazenado com segurança (DPAPI/Keyring).

Mudanças v1.3:
- APP_VERSION agora carregado dinamicamente de version.txt
- Detecção de erro 401 (retorna requer_pat: True)
- Suporte a criptografia com keyring (macOS/Linux)
- Mantém compatibilidade com DPAPI (Windows)
"""
import os
import sys
import base64
import requests
from packaging.version import Version

# ── Constantes do repositório ─────────────────────────────────────────────────
GITHUB_OWNER = 'Neves-BR'
GITHUB_REPO  = 'ExtratorDataSul'
GITHUB_API   = f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest'
GITHUB_ASSET_API = f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/assets'

# ── Carregamento dinâmico de versão do version.txt ─────────────────────────────

def _carregar_app_version():
    """
    Lê a versão do arquivo version.txt na pasta raiz do app.
    Fallback para '0.0.0' se não encontrar (apenas em desenvolvimento).

    Busca em:
    1. Diretório do executável (PyInstaller --onedir)
    2. Diretório do script (desenvolvimento)
    """
    try:
        # PyInstaller --onedir: o script fica em ExtratorDataSul/ExtratorDataSul.exe
        # version.txt está no mesmo nível
        script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        version_file = os.path.join(script_dir, 'version.txt')

        if os.path.exists(version_file):
            with open(version_file, 'r', encoding='utf-8') as f:
                versao = f.read().strip()
                if versao:
                    return versao

        # Fallback: procura em diretórios superiores (desenvolvimento)
        for _ in range(3):
            script_dir = os.path.dirname(script_dir)
            version_file = os.path.join(script_dir, 'version.txt')
            if os.path.exists(version_file):
                with open(version_file, 'r', encoding='utf-8') as f:
                    versao = f.read().strip()
                    if versao:
                        return versao
    except Exception:
        pass

    return '0.0.0'  # Fallback para desenvolvimento

APP_VERSION = _carregar_app_version()


# ── Criptografia do PAT: DPAPI (Windows) + Keyring (macOS/Linux) ───────────────

def _plataforma():
    """Detecta a plataforma do sistema."""
    if sys.platform == 'win32':
        return 'windows'
    elif sys.platform == 'darwin':
        return 'macos'
    else:
        return 'linux'


def _pat_criptografar_windows(texto):
    """Criptografa usando DPAPI (Windows only)."""
    try:
        import win32crypt
        dados = win32crypt.CryptProtectData(
            texto.encode('utf-8'), None, None, None, None, 0
        )
        return 'dpapi:' + base64.b64encode(dados).decode('utf-8')
    except Exception:
        return 'b64:' + base64.b64encode(texto.encode('utf-8')).decode('utf-8')


def _pat_criptografar_keyring(texto):
    """Criptografa usando keyring (macOS/Linux)."""
    try:
        import keyring
        # Usar um nome de serviço fixo e nome de usuário fixo
        servico = 'ExtratorDataSul'
        usuario = 'github_pat'
        keyring.set_password(servico, usuario, texto)
        return 'keyring:stored'  # Marcador que está em keyring
    except Exception:
        # Fallback para base64 se keyring falhar
        return 'b64:' + base64.b64encode(texto.encode('utf-8')).decode('utf-8')


def _pat_criptografar(texto):
    """
    Criptografa o PAT usando o método apropriado para a plataforma.

    Windows: DPAPI (prefixo 'dpapi:')
    macOS/Linux: Keyring (prefixo 'keyring:') com fallback para base64 (prefixo 'b64:')
    """
    plat = _plataforma()

    if plat == 'windows':
        return _pat_criptografar_windows(texto)
    else:
        return _pat_criptografar_keyring(texto)


def _pat_descriptografar_windows(valor):
    """Descriptografa DPAPI."""
    try:
        import win32crypt
        dados = base64.b64decode(valor.encode('utf-8'))
        _, resultado = win32crypt.CryptUnprotectData(
            dados, None, None, None, 0
        )
        return resultado.decode('utf-8')
    except Exception:
        return None


def _pat_descriptografar_keyring(valor):
    """Descriptografa usando keyring."""
    try:
        import keyring
        servico = 'ExtratorDataSul'
        usuario = 'github_pat'
        pat = keyring.get_password(servico, usuario)
        return pat
    except Exception:
        return None


def _pat_descriptografar(valor):
    """
    Descriptografa o PAT salvo.

    Suporta formatos:
      - 'dpapi:<base64>'  → DPAPI (Windows)
      - 'keyring:stored'  → Keyring (macOS/Linux)
      - 'b64:<base64>'    → base64 simples (fallback)
      - Texto claro       → Fallback legado
    """
    if valor.startswith('dpapi:'):
        return _pat_descriptografar_windows(valor[6:])
    elif valor.startswith('keyring:'):
        return _pat_descriptografar_keyring('')
    elif valor.startswith('b64:'):
        try:
            return base64.b64decode(valor[4:].encode('utf-8')).decode('utf-8')
        except Exception:
            return None
    else:
        # Fallback: assume texto claro (desenvolvimento)
        return valor if valor else None


# ── Gerenciamento do PAT ──────────────────────────────────────────────────────

def _appdata_dir():
    """Retorna diretório AppData para armazenar dados do usuário."""
    appdata = os.getenv('APPDATA') or os.path.expanduser('~')
    path = os.path.join(appdata, 'ExtratorDataSul')
    os.makedirs(path, exist_ok=True)
    return path


def _update_env_path():
    """Retorna caminho do arquivo update.env."""
    return os.path.join(_appdata_dir(), 'update.env')


def _aplicar_permissoes(caminho):
    """Restringe o arquivo ao usuário atual via icacls (Windows)."""
    if sys.platform == 'win32':
        import subprocess
        try:
            subprocess.run(
                ['icacls', caminho, '/inheritance:r', '/grant:r',
                 f'{os.getenv("USERNAME")}:F'],
                capture_output=True, timeout=5
            )
        except Exception:
            pass


def carregar_pat():
    """
    Lê e descriptografa o GitHub PAT armazenado.

    Busca em:
    1. Arquivo update.env (AppData) — DPAPI/Keyring/Base64
    2. Keyring do SO (macOS/Linux) — sem arquivo

    Retorna string do PAT ou None se não estiver configurado.
    """
    # Tentar ler do arquivo update.env primeiro
    p = _update_env_path()
    if os.path.exists(p):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                for linha in f:
                    linha = linha.strip()
                    if linha.startswith('GH_PAT='):
                        valor_bruto = linha.split('=', 1)[1].strip()
                        pat = _pat_descriptografar(valor_bruto)
                        if pat:
                            return pat
        except Exception:
            pass

    # Fallback: tentar carregar do keyring (se não estiver em arquivo)
    if _plataforma() != 'windows':
        try:
            import keyring
            pat = keyring.get_password('ExtratorDataSul', 'github_pat')
            if pat:
                return pat
        except Exception:
            pass

    return None


def _escrever_pat_no_arquivo(caminho, pat_plaintext):
    """Criptografa e persiste o PAT no arquivo, aplicando permissões."""
    valor_enc = _pat_criptografar(pat_plaintext)
    with open(caminho, 'w', encoding='utf-8') as f:
        f.write(f'GH_PAT={valor_enc}\n')
    _aplicar_permissoes(caminho)


def salvar_pat(pat):
    """
    Criptografa e salva o GitHub PAT com o método apropriado para a plataforma.

    Windows: DPAPI em update.env
    macOS/Linux: Keyring + fallback para update.env
    """
    if not pat or not pat.strip():
        return

    pat = pat.strip()

    # Em todos os casos, tentar salvar também no arquivo update.env
    p = _update_env_path()
    try:
        _escrever_pat_no_arquivo(p, pat)
    except Exception:
        pass

    # Se não for Windows, também salvar em keyring
    if _plataforma() != 'windows':
        try:
            import keyring
            keyring.set_password('ExtratorDataSul', 'github_pat', pat)
        except Exception:
            pass


def pat_configurado():
    """Retorna True se o PAT está configurado e não está vazio."""
    pat = carregar_pat()
    return bool(pat and pat.strip())


# ── Verificação de versão com detecção de erro 401 ────────────────────────────

def verificar_atualizacao():
    """
    Consulta o GitHub Releases API e compara com APP_VERSION.

    ✅ NOVO: Detecta erro 401 (não autorizado) e retorna `requer_pat: True`
    para sinalizar ao frontend que PAT é necessário.

    Retorna dict:
      { 'disponivel': bool, 'versao': str, 'asset_id': int,
        'tamanho': int, 'notas': str, 'erro': str|None, 'requer_pat': bool }

    Nota: usa asset_id (não browser_download_url) para suportar
    download autenticado de repositórios privados.
    """
    pat = carregar_pat()
    headers = {
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    if pat:
        headers['Authorization'] = f'Bearer {pat}'

    try:
        resp = requests.get(GITHUB_API, headers=headers, timeout=10)

        # ✅ NOVO: Detectar 401 especificamente
        if resp.status_code == 401:
            return {
                'disponivel': False,
                'erro': 'Acesso negado ao repositório privado',
                'requer_pat': True,  # Sinaliza que precisa de PAT
                'versao': None,
                'asset_id': None,
                'tamanho': None,
                'notas': None,
            }

        resp.raise_for_status()
        data = resp.json()

        tag = data.get('tag_name', '').lstrip('v').strip()
        notas = data.get('body', '')

        # Procura o asset .exe (instalador Inno Setup)
        asset = next(
            (a for a in data.get('assets', []) if a['name'].endswith('.exe')),
            None
        )

        if not tag or not asset:
            return {
                'disponivel': False,
                'erro': 'Release sem asset .exe encontrado.',
                'requer_pat': False,
                'versao': None,
                'asset_id': None,
                'tamanho': None,
                'notas': None,
            }

        # Comparação defensiva — ignora se a tag não for um semver válido
        try:
            disponivel = Version(tag) > Version(APP_VERSION)
        except Exception:
            return {
                'disponivel': False,
                'erro': f'Tag de versão inválida no GitHub: "{tag}"',
                'requer_pat': False,
                'versao': None,
                'asset_id': None,
                'tamanho': None,
                'notas': None,
            }

        return {
            'disponivel': disponivel,
            'versao':     tag,
            'asset_id':   asset['id'],           # usado para download autenticado
            'tamanho':    asset['size'],
            'notas':      notas,
            'erro':       None,
            'requer_pat': False,  # Sucesso — não precisa de PAT novo
        }

    except requests.exceptions.ConnectionError:
        return {
            'disponivel': False,
            'erro': 'Sem conexão com o GitHub.',
            'requer_pat': False,
            'versao': None,
            'asset_id': None,
            'tamanho': None,
            'notas': None,
        }
    except requests.exceptions.Timeout:
        return {
            'disponivel': False,
            'erro': 'Timeout ao verificar atualizações.',
            'requer_pat': False,
            'versao': None,
            'asset_id': None,
            'tamanho': None,
            'notas': None,
        }
    except Exception as e:
        return {
            'disponivel': False,
            'erro': str(e),
            'requer_pat': False,
            'versao': None,
            'asset_id': None,
            'tamanho': None,
            'notas': None,
        }


# ── Download do instalador ────────────────────────────────────────────────────

def baixar_instalador(asset_id, destino, progresso_cb=None):
    """
    Baixa o asset do release via API endpoint autenticado.
    Funciona corretamente com repositórios privados.

    Usa GET /repos/{owner}/{repo}/releases/assets/{asset_id}
    com Accept: application/octet-stream — o GitHub retorna
    o binário diretamente (sem redirect para CDN não-autenticado).

    progresso_cb(pct: float) é chamado a cada chunk com progresso 0.0–1.0.
    Retorna (True, None) em sucesso ou (False, mensagem_erro).
    """
    pat = carregar_pat()
    headers = {
        'Accept': 'application/octet-stream',  # força download direto do binário
        'X-GitHub-Api-Version': '2022-11-28',
    }
    if pat:
        headers['Authorization'] = f'Bearer {pat}'

    url = f'{GITHUB_ASSET_API}/{asset_id}'

    try:
        with requests.get(url, headers=headers, stream=True,
                          timeout=120, allow_redirects=True) as r:
            r.raise_for_status()
            total = int(r.headers.get('content-length', 0))
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
        # Remove arquivo parcial se existir
        try:
            if os.path.exists(destino):
                os.remove(destino)
        except Exception:
            pass
        return False, str(e)


def caminho_instalador_temp(versao):
    """Retorna o caminho padrão para o instalador baixado em %TEMP%."""
    import tempfile
    nome = f'ExtratorDataSul_Setup_v{versao}.exe'
    return os.path.join(tempfile.gettempdir(), nome)