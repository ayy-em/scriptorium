; Inno Setup script for the Scriptorium Windows installer.
;
; Prerequisites:
;   1. Run  packaging\build_installer.bat  (it calls PyInstaller automatically)
;   2. Install Inno Setup 6+  (https://jrsoftware.org/issetup.php)
;
; Build:
;   iscc packaging\installer.iss
;
; Output:
;   dist\ScriptoriumSetup.exe

#define MyAppName      "Scriptorium"
#define MyAppVersion   "0.4.0"
#define MyAppPublisher "ayy-em"
#define MyAppExeName   "scriptorium.exe"
#define MyAppURL       "https://github.com/ayy-em/scriptorium"

[Setup]
AppId={{B3F7A1E2-9C4D-4E8A-B6D1-2F5A8C3E7D90}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
OutputDir=..\dist
OutputBaseFilename=ScriptoriumSetup
SetupIconFile=logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "addtopath";   Description: "Add to PATH (for CLI usage)"; GroupDescription: "System integration:"; Flags: unchecked

[Files]
Source: "..\dist\scriptorium\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}\{#MyAppName}";         Filename: "{app}\{#MyAppExeName}"
Name: "{autoprograms}\{#MyAppName}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";    Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}'))

[UninstallDelete]
Type: dirifempty; Name: "{app}"

[Code]
function NeedsAddPath(Param: string): Boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Param) + ';', ';' + Uppercase(OrigPath) + ';') = 0;
end;

procedure RemovePath();
var
  OrigPath: string;
  AppDir: string;
  P: Integer;
begin
  AppDir := ExpandConstant('{app}');
  if RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
  begin
    P := Pos(';' + Uppercase(AppDir), Uppercase(';' + OrigPath));
    if P > 0 then
    begin
      Delete(OrigPath, P, Length(AppDir) + 1);
      RegWriteStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemovePath();
end;

function IsFfmpegInstalled(): Boolean;
begin
  Result := FileExists(ExpandConstant('{sys}\ffmpeg.exe'));
  if not Result then
    Result := (Pos('FFMPEG', Uppercase(GetEnv('PATH'))) > 0);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpReady then
  begin
    if not IsFfmpegInstalled() then
      MsgBox(
        'ffmpeg was not detected on your system.' + #13#10 + #13#10 +
        'Some Scriptorium features (audio/video processing) require ffmpeg.' + #13#10 +
        'You can install it later from:' + #13#10 +
        'https://www.gyan.dev/ffmpeg/builds/' + #13#10 + #13#10 +
        'The installer will continue — ffmpeg is optional.',
        mbInformation, MB_OK
      );
  end;
end;
