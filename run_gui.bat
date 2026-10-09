@echo off
rem 双击这个 = 打开「源码版」图形界面（和 exe 版功能一样，新版功能先在这里有）
rem 走代理：Clash 请用「规则模式」（YouTube 走代理、B站直连）。端口不一样就改下面两行。
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set HTTPS_PROXY=http://127.0.0.1:7890
set HTTP_PROXY=http://127.0.0.1:7890
cd /d "%~dp0"
".venv\Scripts\python.exe" live_gui.py
if errorlevel 1 pause
