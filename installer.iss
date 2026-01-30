; Inno Setup Script for Store Management System
; Compile this script using Inno Setup Compiler (https://jrsoftware.org/isinfo.php)

#define AppName "Store Management System"
#define AppVersion "1.0.0"
#define AppPublisher "Semicolon"
#define AppPublisherURL "https://semicolon.com"
#define AppExeName "StoreManagementSystem.exe"
#define SourceDir "dist"
#define IconFile "Icons\appico.ico"

[Setup]
; Application info
AppId={{F8A3B5C2-9D4E-4F1A-8B6C-7E9D0A1B2C3D}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppPublisherURL}
AppSupportURL={#AppPublisherURL}
AppUpdatesURL={#AppPublisherURL}

; Installer settings
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
LicenseFile=
OutputDir=installer
OutputBaseFilename=StoreManagementSystem_Setup
SetupIconFile={#IconFile}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

; UI Settings
WizardImageFile=
WizardSmallImageFile=
WizardImageStretch=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1

[Files]
; Main executable
Source: "{#SourceDir}\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Include database file if it exists (optional - usually created at runtime)
; Source: "store.db"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist

; Include config file
Source: "utils\config.json"; DestDir: "{app}\utils"; Flags: ignoreversion

; Include themes
Source: "themes\*"; DestDir: "{app}\themes"; Flags: ignoreversion recursesubdirs createallsubdirs

; Include icons
Source: "Icons\*"; DestDir: "{app}\Icons"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\Icons\appico.ico"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon; IconFilename: "{app}\Icons\appico.ico"
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: quicklaunchicon; IconFilename: "{app}\Icons\appico.ico"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\invoices"
Type: files; Name: "{app}\store.db"
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

