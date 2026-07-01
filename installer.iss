; Inno Setup script untuk bxtoyektor.
; Kompilasi: ISCC.exe installer.iss  → installer_output\bxtoyektor-Setup.exe
; Prasyarat: sudah build dulu (pyinstaller build.spec) sehingga dist\bxtoyektor\ ada.

#define AppName "bxtoyektor"
#define AppVersion "1.0.0"
#define AppExe "bxtoyektor.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=bxtoyektor
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename={#AppName}-Setup
SetupIconFile=assets\app.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Per-user install → tidak butuh hak admin, cocok untuk pasang di komputer lain.
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Buat ikon di Desktop"; GroupDescription: "Ikon tambahan:"

[Files]
Source: "dist\bxtoyektor\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Jalankan {#AppName} sekarang"; Flags: nowait postinstall skipifsilent
