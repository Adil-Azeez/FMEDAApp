; Build FMEDA.spec first. Version is read from the executable, whose version
; resource comes directly from fmeda_tool/version.py. Keep AppId stable forever.
#define AppExecutable "dist\FMEDA Tool\FMEDA Tool.exe"
#if !FileExists(AddBackslash(SourcePath) + AppExecutable)
  #error Run build.bat before compiling the installer.
#endif
#define AppVersion GetStringFileInfo(AddBackslash(SourcePath) + AppExecutable, "ProductVersion")
#if AppVersion == ""
  #error The application executable has no ProductVersion resource.
#endif

[Setup]
AppId={{5C720143-C1BC-4737-9814-945017D98EF2}
AppName=FMEDA Tool
AppVersion={#AppVersion}
AppVerName=FMEDA Tool v{#AppVersion}
DefaultDirName={localappdata}\Programs\FMEDA Tool
DefaultGroupName=FMEDA Tool
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=installer
OutputBaseFilename=FMEDA_Setup_v{#AppVersion}
SetupIconFile=assets\FMEDA.ico
UninstallDisplayIcon={app}\FMEDA Tool.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
CloseApplicationsFilter=FMEDA Tool.exe
RestartApplications=no
UsePreviousAppDir=yes
VersionInfoVersion={#AppVersion}

[Files]
Source: "dist\FMEDA Tool\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\FMEDA Tool"; Filename: "{app}\FMEDA Tool.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\FMEDA Tool"; Filename: "{app}\FMEDA Tool.exe"; WorkingDir: "{app}"
Name: "{group}\Uninstall FMEDA Tool"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\FMEDA Tool.exe"; Description: "Launch FMEDA Tool"; Flags: nowait postinstall skipifsilent

; User databases, projects and logs live outside {app}; upgrades and uninstall
; intentionally leave them intact. Never add a user-data [UninstallDelete] rule.
