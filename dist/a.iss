

#define MyAppName "Bk foods Management"
#define MyAppVersion "1.5"
#define MyAppPublisher "semicolon"
#define MyAppExeName "StoreManagementSystem.exe"
#define MyAppAssocName MyAppName + " File"
#define MyAppAssocExt ".myp"
#define MyAppAssocKey StringChange(MyAppAssocName, " ", "") + MyAppAssocExt

[Setup]
AppId={{11BC76C0-BF41-4948-8919-162FDECB97BC}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=yes
DisableProgramGroupPage=yes
OutputBaseFilename=mysetup
SolidCompression=yes
WizardStyle=modern dynamic

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; \
Description: "{cm:CreateDesktopIcon}"; \
GroupDescription: "{cm:AdditionalIcons}"; \
Flags: unchecked

[Files]
Source: "C:\Users\abkil\Desktop\Bkfoods\store_app_with_license\dist\{#MyAppExeName}"; \
DestDir: "{app}"; \
Flags: ignoreversion

[Registry]
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocExt}\OpenWithProgids"; ValueType: string; ValueName: "{#MyAppAssocKey}"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocKey}"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocKey}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocKey}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[Icons]
; Start Menu shortcut
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

; Desktop shortcut (optional via checkbox)
Name: "{commondesktop}\{#MyAppName}"; \
Filename: "{app}\{#MyAppExeName}"; \
Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; \
Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; \
Flags: nowait postinstall skipifsilent
