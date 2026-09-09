#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif

[Setup]
AppId={{E53E1126-8749-45C4-87A5-2E897018D46D}
AppName=PyDeskTools
AppVersion={#MyAppVersion}
AppPublisher=openHacking
AppPublisherURL=https://github.com/openHacking/PyDeskTools
AppSupportURL=https://github.com/openHacking/PyDeskTools/issues
DefaultDirName={localappdata}\Programs\PyDeskTools
DefaultGroupName=PyDeskTools
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist
OutputBaseFilename=PyDeskTools-{#MyAppVersion}-windows-x64-unsigned
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\..\src\pydesktools\assets\logo.ico
UninstallDisplayIcon={app}\PyDeskTools.exe
VersionInfoVersion={#MyAppVersion}.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\..\dist\PyDeskTools\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\PyDeskTools"; Filename: "{app}\PyDeskTools.exe"
Name: "{autodesktop}\PyDeskTools"; Filename: "{app}\PyDeskTools.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PyDeskTools.exe"; Description: "Launch PyDeskTools"; Flags: nowait postinstall skipifsilent
