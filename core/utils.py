"""Utilitários puros — sem dependência de UI."""
import os
import sys
import subprocess
import base64
from datetime import datetime

DOMAIN         = 'novacampina'
BASE_URL       = 'http://datasul.novacampina.net'
ARQUIVO_PADRAO = 'relatorio_nfe_acumulativo.xlsx'
CHAVE_MERGE    = ['Estab', 'Série', 'Nota Fiscal']
XML_NUM_COLUNAS = 87

# Habilita verificação SSL apenas quando BASE_URL usar HTTPS.
VERIFY_SSL = BASE_URL.startswith('https://')

# ── Keyring — constantes de serviço ──────────────────────────────────────────

_KEYRING_SERVICE  = 'ExtratorDataSul'
_KEYRING_USER_KEY = 'datasul_username'


# ── Criptografia via DPAPI (Windows) ─────────────────────────────────────────

def _dpapi_disponivel():
    return sys.platform == 'win32'

def _criptografar(texto):
    """
    Criptografa usando DPAPI — só o mesmo usuário na mesma máquina
    consegue descriptografar. Uso exclusivo no fluxo Windows (arquivo .env).
    """
    if _dpapi_disponivel():
        try:
            import win32crypt
            dados = win32crypt.CryptProtectData(
                texto.encode('utf-8'), None, None, None, None, 0
            )
            return 'dpapi:' + base64.b64encode(dados).decode('utf-8')
        except Exception:
            pass
    # Fallback interno — nunca deve ser atingido em produção Windows
    return 'b64:' + base64.b64encode(texto.encode('utf-8')).decode('utf-8')

def _descriptografar(valor):
    """
    Descriptografa valor salvo no arquivo .env (DPAPI ou fallback base64).
    Uso exclusivo no fluxo Windows.
    """
    if valor.startswith('dpapi:'):
        if _dpapi_disponivel():
            try:
                import win32crypt
                dados = base64.b64decode(valor[6:].encode('utf-8'))
                _, resultado = win32crypt.CryptUnprotectData(
                    dados, None, None, None, 0
                )
                return resultado.decode('utf-8')
            except Exception:
                return None
        return None
    elif valor.startswith('b64:'):
        try:
            return base64.b64decode(valor[4:].encode('utf-8')).decode('utf-8')
        except Exception:
            return None
    else:
        # Texto claro — retrocompatibilidade com .env antigos
        return valor

# ── AppData ───────────────────────────────────────────────────────────────────

def _appdata_dir():
    appdata = os.getenv('APPDATA') or os.path.expanduser('~')
    path = os.path.join(appdata, 'ExtratorDataSul')
    os.makedirs(path, exist_ok=True)
    return path

def get_env_path():
    return os.path.join(_appdata_dir(), '.env')

def get_prefs_path():
    return os.path.join(_appdata_dir(), 'prefs.txt')

# ── Preferências ──────────────────────────────────────────────────────────────

def carregar_arquivo_preferido():
    try:
        p = get_prefs_path()
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                v = f.read().strip()
                if v.endswith('.xlsx'):
                    return v
    except Exception as e:
        print(f"Erro ao carregar arquivo preferido: {e}")
    return None

def salvar_arquivo_preferido(caminho):
    try:
        with open(get_prefs_path(), 'w', encoding='utf-8') as f:
            f.write(caminho)
    except Exception as e:
        print(f"Erro ao salvar arquivo preferido: {e}")

def get_filtros_path():
    return os.path.join(_appdata_dir(), 'filtros.json')

def get_prefs_ui_path():
    return os.path.join(_appdata_dir(), 'prefs_ui.json')

# ── Preferências de UI ────────────────────────────────────────────────────────

def carregar_tema():
    """Retorna 'dark' ou 'light'. Padrão: 'dark'."""
    try:
        import json
        p = get_prefs_ui_path()
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                dados = json.load(f)
                return dados.get('tema', 'dark')
    except Exception as e:
        print(f"Erro ao carregar tema: {e}")
    return 'dark'

def salvar_tema(tema):
    """Persiste o tema ('dark' ou 'light') em prefs_ui.json."""
    try:
        import json
        p = get_prefs_ui_path()
        dados = {}
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    dados = json.load(f)
            except Exception:
                pass
        dados['tema'] = tema if tema in ('dark', 'light', 'pink', 'purple') else 'dark'
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erro ao salvar tema: {e}")

def carregar_acento():
    """Retorna o acento de cor salvo: 'indigo', 'teal', ou 'amber'. Padrão: 'indigo'."""
    try:
        import json
        p = get_prefs_ui_path()
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                dados = json.load(f)
                return dados.get('acento', 'indigo')
    except Exception as e:
        print(f"Erro ao carregar acento: {e}")
    return 'indigo'

def salvar_acento(acento):
    """Persiste o acento de cor em prefs_ui.json."""
    try:
        import json
        p = get_prefs_ui_path()
        dados = {}
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    dados = json.load(f)
            except Exception:
                pass
        dados['acento'] = acento if acento in ('indigo', 'teal', 'amber') else 'indigo'
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erro ao salvar acento: {e}")

def carregar_filtros():
    """Lê os filtros salvos. Retorna dict com os valores ou None se não existir."""
    try:
        import json
        p = get_filtros_path()
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Erro ao carregar filtros: {e}")
    return None

def salvar_filtros(filtros):
    """Persiste os filtros em JSON."""
    try:
        import json
        with open(get_filtros_path(), 'w', encoding='utf-8') as f:
            json.dump(filtros, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erro ao salvar filtros: {e}")

# ── Credenciais ───────────────────────────────────────────────────────────────

def carregar_credenciais():
    """Lê e retorna (username, password) desprotegidos."""
    if _dpapi_disponivel():
        return _carregar_credenciais_dpapi()
    return _carregar_credenciais_keyring()

def salvar_credenciais(username, password):
    """Criptografa e persiste as credenciais de forma segura."""
    if _dpapi_disponivel():
        _salvar_credenciais_dpapi(username, password)
    else:
        _salvar_credenciais_keyring(username, password)

def remover_credenciais():
    """Remove as credenciais salvas."""
    if _dpapi_disponivel():
        _remover_credenciais_dpapi()
    else:
        _remover_credenciais_keyring()

# ── Implementações por plataforma ─────────────────────────────────────────────

def _carregar_credenciais_dpapi():
    p = get_env_path()
    if not os.path.exists(p):
        return None, None
    try:
        dados = {}
        for linha in open(p, 'r', encoding='utf-8'):
            linha = linha.strip()
            if '=' in linha and not linha.startswith('#'):
                k, _, v = linha.partition('=')
                dados[k.strip()] = v.strip()
        u = _descriptografar(dados.get('DATASUL_USER', ''))
        s = _descriptografar(dados.get('DATASUL_PASS', ''))
        return u, s
    except Exception:
        return None, None

def _salvar_credenciais_dpapi(username, password):
    p = get_env_path()
    u_enc = _criptografar(username)
    s_enc = _criptografar(password)
    open(p, 'w', encoding='utf-8').write(
        f'DATASUL_USER={u_enc}\nDATASUL_PASS={s_enc}\n'
    )
    # Restringir permissões via icacls no Windows
    try:
        subprocess.run(
            ['icacls', p, '/inheritance:r', '/grant:r',
             f'{os.getenv("USERNAME")}:F'],
            capture_output=True, timeout=5
        )
    except Exception:
        pass

def _remover_credenciais_dpapi():
    try:
        p = get_env_path()
        if os.path.exists(p):
            os.remove(p)
    except Exception:
        pass

def _carregar_credenciais_keyring():
    try:
        import keyring
        username = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER_KEY)
        if not username:
            return None, None
        password = keyring.get_password(_KEYRING_SERVICE, username)
        return username, password
    except Exception:
        return None, None

def _salvar_credenciais_keyring(username, password):
    try:
        import keyring
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER_KEY, username)
        keyring.set_password(_KEYRING_SERVICE, username, password)
    except Exception:
        pass

def _remover_credenciais_keyring():
    try:
        import keyring
        username = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER_KEY)
        if username:
            try:
                keyring.delete_password(_KEYRING_SERVICE, username)
            except Exception:
                pass
        try:
            keyring.delete_password(_KEYRING_SERVICE, _KEYRING_USER_KEY)
        except Exception:
            pass
    except Exception:
        pass

# ── Utilitários ───────────────────────────────────────────────────────────────

def range_to_semicolon(de, ate):
    """
    Converte range de números em formato 'De;Ate' para API DataSul.
    ✅ SEGURANÇA: Converte para int, impede injeção de strings.
    """
    de, ate = str(de).strip(), str(ate).strip()
    if not de or not ate:
        return None
    try:
        return f"{int(de)};{int(ate)}"
    except Exception:
        return None

def ts():
    return datetime.now().strftime('%d/%m %H:%M')