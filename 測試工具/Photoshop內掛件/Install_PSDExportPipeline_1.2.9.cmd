@echo off
setlocal
set "CCX=%~dp0PSDExportPipeline_1.2.9.ccx"
if not "%~1"=="" set "CCX=%~1"
set "UPIA=C:\Program Files\Common Files\Adobe\Adobe Desktop Common\RemoteComponents\UPI\UnifiedPluginInstallerAgent\UnifiedPluginInstallerAgent.exe"
if not exist "%CCX%" (
  echo Missing CCX: "%CCX%"
  pause
  exit /b 1
)
if not exist "%UPIA%" (
  set "UPIA=%ProgramFiles%\Common Files\Adobe\Adobe Desktop Common\RemoteComponents\UPI\UnifiedPluginInstallerAgent\UnifiedPluginInstallerAgent.exe"
)
if not exist "%UPIA%" (
  set "UPIA=%ProgramFiles(x86)%\Common Files\Adobe\Adobe Desktop Common\RemoteComponents\UPI\UnifiedPluginInstallerAgent\UnifiedPluginInstallerAgent.exe"
)
if not exist "%UPIA%" (
  echo UnifiedPluginInstallerAgent.exe was not found. Install or update Adobe Creative Cloud Desktop, then run this again.
  pause
  exit /b 1
)
echo Installing "%CCX%" with:
echo   "%UPIA%"
"%UPIA%" /install "%CCX%"
if errorlevel 1 (
  echo.
  echo First install command failed. Trying --install syntax...
  "%UPIA%" --install "%CCX%"
)
echo.
echo Done. Restart Photoshop and check Plugins / UXP panel list.
pause
