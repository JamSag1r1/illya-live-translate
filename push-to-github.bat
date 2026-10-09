@echo off
rem Push this repo to GitHub. Requires: git + GitHub CLI (gh) installed, and
rem github.com reachable (in mainland China you usually need a VPN for this).
rem   install gh:  winget install --id GitHub.cli -e      (then reopen terminal)
rem ASCII only on purpose: cmd.exe mangles non-ASCII batch files.
setlocal
cd /d "%~dp0"
echo ============================================
echo   Push "Illya's live-translate tools" to GitHub
echo ============================================
echo.

where git >nul 2>nul
if errorlevel 1 (
  echo [!] git not found. Install Git for Windows first.
  pause & exit /b 1
)
where gh >nul 2>nul
if errorlevel 1 (
  echo [!] GitHub CLI ^(gh^) not found. Run:  winget install --id GitHub.cli -e
  echo     then reopen the terminal and run this file again.
  pause & exit /b 1
)

set GHUSER=
set /p GHUSER=Your GitHub username: 
if "%GHUSER%"=="" (
  echo [!] No username given. Aborted.
  pause & exit /b 1
)
set REPO=
set /p REPO=Repo name [Enter = illya-live-translate]: 
if "%REPO%"=="" set REPO=illya-live-translate
set VIS=
set /p VIS=Public or private? [Enter = public, type "private" for private]: 
set VISFLAG=--public
if /i "%VIS%"=="private" set VISFLAG=--private

rem 1) commit as you (this repo has never been pushed, so rewriting the author is safe)
git config user.name "%GHUSER%"
git config user.email "%GHUSER%@users.noreply.github.com"
git commit --amend --no-edit --reset-author

rem 2) log in to GitHub if not already (opens a device-code flow in the browser)
gh auth status >nul 2>nul
if errorlevel 1 gh auth login

rem 3) create the remote repo and push
gh repo create "%REPO%" %VISFLAG% --source=. --remote=origin --push
if errorlevel 1 (
  echo.
  echo [!] Push failed. Usual causes:
  echo     - github.com unreachable ^(needs a VPN here^)
  echo     - repo name already taken by someone
  echo     - you are not logged in
  pause & exit /b 1
)
echo.
echo [OK] Pushed: https://github.com/%GHUSER%/%REPO%
pause
