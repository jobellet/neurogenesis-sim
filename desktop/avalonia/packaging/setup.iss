; Inno Setup Script for Neurogenesis Desktop Application (Windows)
; Built for per-user installation without requiring administrator privileges.

#define MyAppName "Neurogenesis"
#ifndef MyAppVersion
#define MyAppVersion "0.1.0"
#endif
#define MyAppPublisher "Neurogenesis Sim Contributors"
#define MyAppURL "https://github.com/jobellet/neurogenesis-sim"
#define MyAppExeName "Neurogenesis.exe"

[Setup]
AppId={{E68F91B4-36D8-4C2B-9871-331BCAEF1728}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=.
OutputBaseFilename=Neurogenesis-setup-win-x64
SetupIconFile=neurogenesis.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "assocngb"; Description: "Associate .ngb files with Neurogenesis"; GroupDescription: "File associations:"

[Files]
Source: "..\..\..\publish\win-x64\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "neurogenesis.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\neurogenesis.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\neurogenesis.ico"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Classes\.ngb"; ValueType: string; ValueName: ""; ValueData: "Neurogenesis.Network"; Flags: uninsdeletevalue; Tasks: assocngb
Root: HKCU; Subkey: "Software\Classes\Neurogenesis.Network"; ValueType: string; ValueName: ""; ValueData: "Neurogenesis Network File"; Flags: uninsdeletekey; Tasks: assocngb
Root: HKCU; Subkey: "Software\Classes\Neurogenesis.Network\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\neurogenesis.ico,0"; Flags: uninsdeletekey; Tasks: assocngb
Root: HKCU; Subkey: "Software\Classes\Neurogenesis.Network\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Flags: uninsdeletekey; Tasks: assocngb

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
