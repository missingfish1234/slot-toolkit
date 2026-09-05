@echo off
setlocal
set "CCX=%~dp0PSDExportPipeline_1.2.19.ccx"
if not "%~1"=="" set "CCX=%~1"
if not exist "%CCX%" (
  echo Missing CCX: "%CCX%"
  pause
  exit /b 1
)
set "UPIA=%ProgramFiles%\Common Files\Adobe\Adobe Desktop Common\RemoteComponents\UPI\UnifiedPluginInstallerAgent\UnifiedPluginInstallerAgent.exe"
if not exist "%UPIA%" set "UPIA=%ProgramFiles(x86)%\Common Files\Adobe\Adobe Desktop Common\RemoteComponents\UPI\UnifiedPluginInstallerAgent\UnifiedPluginInstallerAgent.exe"
if not exist "%UPIA%" (
  echo Adobe plugin installer not found. Install or update Creative Cloud Desktop first.
  pause
  exit /b 2
)
set "INSTALL_LOG=%TEMP%\PSDExportPipeline_1.2.19_install.log"
"%UPIA%" /install "%CCX%" > "%INSTALL_LOG%" 2>&1
if not errorlevel 1 goto installed
"%UPIA%" --install "%CCX%" >> "%INSTALL_LOG%" 2>&1
if errorlevel 1 goto failed
:installed
echo Installation succeeded. Restart Photoshop and open Plugins / PSD Export Pipeline.
echo Log: "%INSTALL_LOG%"
pause
exit /b 0
:failed
echo Installation failed. Your existing plugin has not been reported as updated.
echo Log: "%INSTALL_LOG%"
type "%INSTALL_LOG%"
pause
exit /b 1
