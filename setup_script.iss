; Script gerado para Inno Setup - Modo Onefile
#define MyAppName "RPV Automacao"
#define MyAppVersion "1.0.1"
#define MyAppPublisher "Salles&Santos"
#define MyAppExeName "RPV_Automacao.exe" 

[Setup]
AppId={{A9F3C8A1-7B4D-4F1B-9E9E-2C4F6E9C1D21}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=dist\installer
OutputBaseFilename=Instalador_RPV_Automacao
SetupIconFile=py.ico 
Compression=lzma
SolidCompression=yes
WizardStyle=modern
LicenseFile=LICENSE.txt
WizardSizePercent=120

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; No modo Onefile, trazemos apenas os executaveis limpos
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\updater.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
function IsTesseractInstalled: Boolean;
var
  TesseractPath: String;
begin
  TesseractPath := 'C:\Program Files\Tesseract-OCR\tesseract.exe';
  Result := FileExists(TesseractPath);
end;

function InitializeSetup: Boolean;
begin
  Result := True;
  if not IsTesseractInstalled then
  begin
    if MsgBox('Tesseract OCR não foi detectado (C:\Program Files\Tesseract-OCR\tesseract.exe).' + #13#10#13#10 + 
       'Este software auxiliar é altamente recomendado para a extração de texto de alguns documentos PDF.' + #13#10#13#10 + 
       'Deseja continuar com a instalação mesmo assim?', mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    if not IsTesseractInstalled then
    begin
        if MsgBox('Deseja baixar o instalador do Tesseract OCR 5.3.3 agora?' + #13#10 +
                  '(O idioma português será incluído automaticamente na instalação)', 
                  mbConfirmation, MB_YESNO) = IDYES then
        begin
          ShellExec('open', 'https://github.com/tesseract-ocr/tesseract/releases/download/5.3.3/tesseract-ocr-w64-setup-5.3.3.20230621.exe', 
                    '', '', SW_SHOW, ewNoWait, ResultCode);
        end;
    end;
  end;
end;
