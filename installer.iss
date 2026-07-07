; Inno Setup script untuk bxtoyektor.
; Kompilasi: ISCC.exe installer.iss  → installer_output\bxtoyektor-Setup.exe
; Prasyarat: sudah build dulu (pyinstaller build.spec) sehingga dist\bxtoyektor\ ada.

#define AppName "bxtoyektor"
#define AppVersion "1.0.6"
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

[Code]
{ Deteksi LibreOffice (untuk preview PPTX/DOCX). Opsional — instalasi tetap lanjut. }
function LibreOfficeTerpasang(): Boolean;
begin
  Result := FileExists(ExpandConstant('{commonpf}\LibreOffice\program\soffice.exe'))
         or FileExists(ExpandConstant('{commonpf32}\LibreOffice\program\soffice.exe'))
         or FileExists(ExpandConstant('{localappdata}\Programs\LibreOffice\program\soffice.exe'));
end;

function InitializeSetup(): Boolean;
var
  Jawab: Integer;
  ErrCode: Integer;
begin
  Result := True;  { selalu lanjut — LibreOffice tidak wajib }
  if not LibreOfficeTerpasang() then
  begin
    Jawab := MsgBox(
      'LibreOffice tidak terdeteksi di komputer ini.' + #13#10#13#10 +
      'bxtoyektor memakai LibreOffice (gratis) HANYA untuk preview file PowerPoint (PPTX/PPT) ' +
      'dan Word (DOCX/DOC). Preview PDF, gambar, dan video tetap berfungsi tanpa LibreOffice.' + #13#10#13#10 +
      'Disarankan pasang LibreOffice lebih dulu. Buka halaman unduhannya sekarang?' + #13#10 +
      '(Pilih "No" untuk lanjut memasang bxtoyektor tanpa LibreOffice.)',
      mbConfirmation, MB_YESNO) ;
    if Jawab = IDYES then
      ShellExec('open', 'https://www.libreoffice.org/download/download/',
                '', '', SW_SHOW, ewNoWait, ErrCode);
  end;
end;
