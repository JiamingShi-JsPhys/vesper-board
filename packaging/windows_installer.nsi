; NSIS 安装脚本：dist\VesperBoard -> VesperBoard-1.0.0-setup.exe
; 用免安装的 NSIS 编译：
;   & "$env:TEMP\nsis\nsis-3.11\makensis.exe" packaging\windows_installer.nsi
; 全程装到 %LOCALAPPDATA%\Programs\VesperBoard，不需要管理员权限。

Unicode True
!include "MUI2.nsh"

!define APP_NAME "晚星看板"
!define APP_EXE "VesperBoard.exe"
!define APP_VER "1.0.0"
!define APP_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\VesperBoard"
!define RUN_KEY "Software\Microsoft\Windows\CurrentVersion\Run"

; 当前数据目录与改名前的旧目录，卸载时要一起处理。
!define DATA_DIR "$LOCALAPPDATA\VesperBoard"
!define LEGACY_DATA_DIR "$LOCALAPPDATA\WestlakeDock"

Name "${APP_NAME}"
OutFile "..\dist\installer\VesperBoard-${APP_VER}-setup.exe"
InstallDir "$LOCALAPPDATA\Programs\VesperBoard"
InstallDirRegKey HKCU "${APP_KEY}" "InstallLocation"
RequestExecutionLevel user
SetCompressor /SOLID lzma

!define MUI_ICON "..\build\icon.ico"
!define MUI_UNICON "..\build\icon.ico"
!define MUI_ABORTWARNING

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

Section "!程序文件" SEC_APP
  SectionIn RO
  ; 升级时先结束正在运行的实例：否则文件被占用，新进程也会被单实例锁挡掉，
  ; 用户看到的还是旧界面。
  nsExec::Exec 'taskkill /IM ${APP_EXE} /F'
  Pop $0
  Sleep 600
  SetOutPath "$INSTDIR"
  File /r "..\dist\VesperBoard\*.*"

  CreateShortcut "$SMPROGRAMS\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
  WriteUninstaller "$INSTDIR\uninstall.exe"

  WriteRegStr HKCU "${APP_KEY}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKCU "${APP_KEY}" "DisplayVersion" "${APP_VER}"
  WriteRegStr HKCU "${APP_KEY}" "Publisher" "Vesper Board"
  WriteRegStr HKCU "${APP_KEY}" "DisplayIcon" "$INSTDIR\${APP_EXE}"
  WriteRegStr HKCU "${APP_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${APP_KEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegDWORD HKCU "${APP_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${APP_KEY}" "NoRepair" 1
SectionEnd

Section "开机自动启动" SEC_AUTO
  WriteRegStr HKCU "${RUN_KEY}" "VesperBoard" '"$INSTDIR\${APP_EXE}"'
SectionEnd

; 卸载时问一句要不要连用户数据一起删。静默卸载默认保留。
; 数据在 %LOCALAPPDATA%\VesperBoard：设置、登录会话、归档、日志。
; 从旧版本升级上来的机器上还可能有 %LOCALAPPDATA%\WestlakeDock，一并清掉。
Section "Uninstall"
  ; 卸载前先结束常驻实例：文件被占用会删不干净，而且程序退出时还会把
  ; settings.json 写回数据目录，等于「删除数据」之后又把目录复活。
  nsExec::Exec 'taskkill /IM ${APP_EXE} /F'
  Pop $0
  Sleep 600

  Delete "$SMPROGRAMS\${APP_NAME}.lnk"
  Delete "$DESKTOP\${APP_NAME}.lnk"
  DeleteRegValue HKCU "${RUN_KEY}" "VesperBoard"
  DeleteRegValue HKCU "${RUN_KEY}" "WestlakeDock"
  DeleteRegKey HKCU "${APP_KEY}"
  RMDir /r "$INSTDIR"

  IfSilent keep_data
  MessageBox MB_YESNO|MB_ICONQUESTION "是否同时删除本机数据？$\r$\n$\r$\n包括登录令牌、会话、设置、归档记录和日志（%LOCALAPPDATA%\VesperBoard）。$\r$\n选择「否」会保留，重装后无需重新登录。" IDNO keep_data
  RMDir /r "${DATA_DIR}"
  RMDir /r "${LEGACY_DATA_DIR}"
  keep_data:
SectionEnd

LangString DESC_SEC_APP ${LANG_SIMPCHINESE} "程序本体、图标与快捷方式。"
LangString DESC_SEC_APP ${LANG_ENGLISH} "Application files and shortcuts."
LangString DESC_SEC_AUTO ${LANG_SIMPCHINESE} "登录 Windows 后自动启动悬浮球。"
LangString DESC_SEC_AUTO ${LANG_ENGLISH} "Start the floating ball with Windows."

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_APP} $(DESC_SEC_APP)
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_AUTO} $(DESC_SEC_AUTO)
!insertmacro MUI_FUNCTION_DESCRIPTION_END
