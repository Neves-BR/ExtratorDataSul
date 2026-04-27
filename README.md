# ExtratorDataSul NF-e

Aplicação desktop para extração de dados de notas fiscais (NF-e) do sistema DataSul, com interface web via PyWebView.

---

## Requisitos

- Python 3.13+
- VPN ativa (necessária para acessar o DataSul)
- [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) (instalado automaticamente pelo Setup)

---

## Instalação do ambiente de desenvolvimento

```bash
# 1. Clone o repositório
git clone https://github.com/Neves-BR/ExtratorDataSul.git
cd ExtratorDataSul

# 2. Crie e ative o ambiente virtual
python -m venv .venv
.venv\Scripts\activate

# 3. Instale as dependências
pip install -r requirements.txt
```

---

## Variáveis de ambiente

Crie um arquivo `.env` na raiz do projeto com as seguintes variáveis:

```env
DATASUL_URL=https://seu-servidor-datasul
DATASUL_USER=seu_usuario
DATASUL_PASS=sua_senha
DATASUL_DOMAIN=seu_dominio
```

> ⚠️ O arquivo `.env` está protegido pelo `.gitignore` e nunca deve ser commitado.

---

## Executar em modo desenvolvimento

```bash
.venv\Scripts\activate
python extrator_pywebview.py
```

---

## Gerar o executável

### 1. Build com PyInstaller

```bash
.venv\Scripts\activate
pyinstaller ExtratorDataSul.spec --clean
```

O executável será gerado em `dist\ExtratorDataSul\`.

> Teste o app antes de empacotar:
> ```bash
> dist\ExtratorDataSul\ExtratorDataSul.exe
> ```

### 2. Gerar o instalador com Inno Setup

1. Abra o **Inno Setup Compiler**
2. `File → Open` → selecione `ExtratorDataSul_Setup.iss`
3. `Compile` (`Ctrl+F9`)
4. O instalador será gerado em `Output\ExtratorDataSul_Setup.exe`

---

## Estrutura do projeto

```
ExtratorDataSul/
├── core/
│   ├── extrator.py       # Lógica de extração e processamento de dados
│   └── utils.py          # Utilitários, credenciais, configurações
├── ui/
│   ├── index.html        # Interface principal
│   ├── style.css         # Estilos (dark sci-fi)
│   └── app.js            # Lógica do frontend
├── Api.py                # Classe exposta ao JavaScript via pywebview.api
├── extrator_pywebview.py # Entrada da aplicação
├── ExtratorDataSul.spec  # Configuração do PyInstaller
├── ExtratorDataSul_Setup.iss  # Script do Inno Setup
├── requirements.txt
├── icon.ico
└── .gitignore
```

---

---

## Distribuição

Os instaladores versionados estão disponíveis em [Releases](../../releases).
