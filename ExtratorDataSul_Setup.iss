#define AppName      "ExtratorDataSul NF-e"
#define AppVersion   "1.0.1"
#define AppPublisher "Tucano Florestal"
#define AppExeName   "ExtratorDataSul.exe"
#define AppIcon      "icon.ico"

[Setup]
AppId={{B4F2A1C3-9E47-4D2A-8F61-3C5D7E2A9B04}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\ExtratorDataSul
DefaultGroupName={#AppName}
OutputDir=Output
OutputBaseFilename=ExtratorDataSul_Setup
InfoAfterFile=README_usuario.txt

SetupIconFile={#AppIcon}

Compression=lzma2/ultra64
LZMANumFastBytes=273
SolidCompression=yes

WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

DisableDirPage=no
DisableProgramGroupPage=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "dist\ExtratorDataSul\*"; \
  DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

Source: "{#AppIcon}";           DestDir: "{app}"; Flags: ignoreversion
Source: "README_usuario.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";             Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppIcon}"
Name: "{autodesktop}\{#AppName}";       Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppIcon}"; Tasks: desktopicon
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"

[Run]
; Instalar WebView2 se necessário
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; \
  StatusMsg: "Instalando WebView2 Runtime..."; \
  Check: WebView2NotInstalled; Flags: waituntilterminated

; Reabrir o app após instalação — sem skipifsilent para funcionar também
; quando chamado via /SILENT /NORESTART pelo auto-update
Filename: "{app}\{#AppExeName}"; Description: "Iniciar {#AppName}"; Flags: nowait postinstall


[Code]

// ── Verificação do WebView2 Runtime ──────────────────────────────────────────

function WebView2NotInstalled: Boolean;
var
  Version: String;
begin
  Result := not (
    RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
    RegQueryStringValue(HKLM, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
    RegQueryStringValue(HKLM, 'Software\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version)
  );
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  ResultCode: Integer;
  Installer: String;
begin
  Result := True;
  if (CurPageID = wpReady) and WebView2NotInstalled then begin
    Installer := ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe');
    Exec('powershell.exe',
      '-Command "Invoke-WebRequest -Uri ' + #39 +
      'https://go.microsoft.com/fwlink/p/?LinkId=2124703' + #39 +
      ' -OutFile ' + #39 + Installer + #39 + '"',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if FileExists(Installer) then
      Exec(Installer, '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
    else
      MsgBox(
        'Nao foi possivel baixar o WebView2 Runtime automaticamente.' + #13#10 +
        'Instale manualmente em:' + #13#10 +
        'https://developer.microsoft.com/microsoft-edge/webview2/',
        mbInformation, MB_OK);
  end;
end;

