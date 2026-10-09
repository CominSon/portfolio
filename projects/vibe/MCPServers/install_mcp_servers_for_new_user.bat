@echo off
setlocal EnableExtensions

REM ASCII-only bat (cmd.exe). Do not save as UTF-8 with BOM.

set "REPO_URL=https://df-bitbucket.ca.sbrf.ru/scm/wealthhub/python.git"
set "BRANCH=master"
set "SRC_SUBDIR=MCP Servers"
set "DEST=U:\MCP Servers"
set "TMP_CLONE=%TEMP%\wealthhub_python_mcp_install"

echo.
echo === MCP Servers install ===
echo Repo: %REPO_URL%  branch %BRANCH%
echo Dest: %DEST%
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo ERROR: git not found in PATH.
  goto :fail
)

if not exist "U:\" (
  echo ERROR: drive U: is not available.
  goto :fail
)

if exist "%TMP_CLONE%" rmdir /s /q "%TMP_CLONE%" 2>nul

echo Cloning repository (Bitbucket login may be required)...
git -c http.sslVerify=false clone --depth 1 --branch %BRANCH% --single-branch "%REPO_URL%" "%TMP_CLONE%"
if errorlevel 1 (
  echo ERROR: git clone failed.
  goto :fail
)

if not exist "%TMP_CLONE%\%SRC_SUBDIR%\" (
  echo ERROR: folder "%SRC_SUBDIR%" not found in clone.
  if exist "%TMP_CLONE%" rmdir /s /q "%TMP_CLONE%" 2>nul
  goto :fail
)

if not exist "%DEST%\" mkdir "%DEST%"
if not exist "%DEST%\" (
  echo ERROR: cannot create "%DEST%".
  if exist "%TMP_CLONE%" rmdir /s /q "%TMP_CLONE%" 2>nul
  goto :fail
)

echo Copying files to "%DEST%" ...
robocopy "%TMP_CLONE%\%SRC_SUBDIR%" "%DEST%" /E /NFL /NDL /NJH /NJS /nc /ns /np
set "RC=%ERRORLEVEL%"
if %RC% GEQ 8 (
  echo ERROR: robocopy failed, code %RC%.
  if exist "%TMP_CLONE%" rmdir /s /q "%TMP_CLONE%" 2>nul
  goto :fail
)

if exist "%TMP_CLONE%" rmdir /s /q "%TMP_CLONE%" 2>nul

set "RULES_SRC=%DEST%\GIGACODE_MCP_RULES.txt"
set "RULES_DST=%USERPROFILE%\.gigacode\rules\mcp.md"
set "SETTINGS=%DEST%\GIGAIDE_MCP_SETTINGS.txt"

if exist "%RULES_SRC%" (
  if not exist "%USERPROFILE%\.gigacode\rules\" mkdir "%USERPROFILE%\.gigacode\rules"
  copy /Y "%RULES_SRC%" "%RULES_DST%" >nul
  echo Rules copied to "%RULES_DST%"
) else (
  echo WARN: GIGACODE_MCP_RULES.txt not found in "%DEST%"
)

echo.
echo DONE.
echo 1^) Check "%DEST%"
echo 2^) Open "%SETTINGS%" and add MCP servers in GigaIDE
echo 3^) Restart MCP Server and start a new chat
echo.
pause
endlocal
exit /b 0

:fail
echo.
echo Install failed.
pause
endlocal
exit /b 1
