@echo off
REM One-command launcher for Windows.
REM
REM Usage:
REM   run.bat 2d   - launch the original bgfx import-graph explorer
REM   run.bat 3d   - launch the 3D "mathematical kingdom" map

setlocal
set DIR=%~dp0
set MODE=%1

if /i "%MODE%"=="2d" goto :run2d
if /i "%MODE%"=="3d" goto :run3d

echo Usage: run.bat [2d^|3d]
echo   2d - launch the original bgfx import-graph explorer
echo   3d - launch the 3D "mathematical kingdom" map
exit /b 1

:run2d
set EXE=%DIR%release\bin_win64\MathlibExplorer.exe
if not exist "%EXE%" (
  echo No prebuilt MathlibExplorer.exe found at "%EXE%"
  exit /b 1
)
cd /d "%DIR%release\bin_win64"
start "" "MathlibExplorer.exe"
goto :eof

:run3d
set HTML=%DIR%kingdom\viewer\index.html
if not exist "%HTML%" (
  echo No 3D viewer found at "%HTML%"
  exit /b 1
)
set FILEURL=file:///%HTML:\=/%

REM Prefer an "app mode" window (no tabs/address bar) for a closer-to-native
REM feel matching the bgfx MathlibExplorer window; fall back to whatever the
REM system's default browser association is.
set EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe
set CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe

if exist "%EDGE%" (
  start "" "%EDGE%" --app="%FILEURL%"
  goto :eof
)
if exist "%CHROME%" (
  start "" "%CHROME%" --app="%FILEURL%"
  goto :eof
)

start "" "%HTML%"
