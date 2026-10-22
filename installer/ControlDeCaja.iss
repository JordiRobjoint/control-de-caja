; Instalador de Control de Caja (Inno Setup 6).
; No se compila a mano: lo hace build.py, que pasa la versión de app_info.py.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "Control de Caja"
#define AppExe "Control de Caja.exe"

[Setup]
; El AppId identifica la aplicación para actualizar y desinstalar: no cambiarlo.
AppId={{A2F0AAD6-0946-4EDE-8C99-50F1318D32F4}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Instalación para el usuario actual, sin pedir permisos de administrador.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=ControlDeCaja-{#AppVersion}-Setup
SetupIconFile=..\assets\app.ico
; Condiciones de la beta: hay que aceptarlas para instalar.
LicenseFile=..\LICENSE
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

; Los datos del usuario (%LOCALAPPDATA%\ControlDeCaja) no se tocan al
; desinstalar: así una reinstalación o actualización los conserva.
