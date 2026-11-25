; Inno Setup 脚本：把 dist\VesperBoard 打成一个安装包
; 编译： "C:\Program Files\Inno Setup 7\ISCC.exe" packaging\windows_installer.iss

#define MyAppName "晚星看板"
#define MyAppVersion "1.0.2"
#define MyAppExeName "VesperBoard.exe"

[Setup]
AppId={{7E2C4A61-3B7F-4C55-9A1E-5D0F2B8C7A31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
DefaultDirName={autopf}\VesperBoard
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=VesperBoard-{#MyAppVersion}-setup
SetupIconFile=..\build\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"
Name: "autostart"; Description: "Start with Windows"; GroupDescription: "Startup:"

[Files]
Source: "..\dist\VesperBoard\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "VesperBoard"; \
    ValueData: """{app}\{#MyAppExeName}"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
{ 卸载时问一句要不要连用户数据一起删（静默卸载默认保留）。
  当前目录 %LOCALAPPDATA%\VesperBoard；从旧版本升上来的机器上还可能有
  %LOCALAPPDATA%\WestlakeDock，选择删除时一并清掉。 }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    { 必须在删文件之前结束常驻实例：usPostUninstall 太晚，那时程序锁着
      自己的 exe，删除会被排到重启后；而且程序退出时还会把 settings.json
      写回数据目录，等于把刚删掉的目录又建回来。 }
    Exec('taskkill.exe', '/IM VesperBoard.exe /F', '', SW_HIDE,
         ewWaitUntilTerminated, ResultCode);
    Sleep(600);
  end;

  if CurUninstallStep = usPostUninstall then
  begin
    if MsgBox('是否同时删除本机数据？' + #13#10 + #13#10 +
              '包括登录令牌、会话、设置、归档记录和日志。' + #13#10 +
              '选择「否」会保留，重装后无需重新登录。',
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      DataDir := ExpandConstant('{localappdata}\VesperBoard');
      DelTree(DataDir, True, True, True);
      DataDir := ExpandConstant('{localappdata}\WestlakeDock');
      DelTree(DataDir, True, True, True);
    end;
  end;
end;
