@echo off
rem Live audio -> Chinese subtitles.  Best config for this machine (RTX 5070):
rem Japanese audio, large-v3 on GPU, short fragments merged for more context.
rem Keep this file ASCII-only: cmd.exe reads it in the OEM codepage and mangles
rem non-ASCII arguments (that broke the launcher once already).
rem Language:  --src ja / en / ko / auto       CPU fallback:  --device cpu --model-size small
rem Domain terms:  --preset chem-ja / chem-en
rem Only this stream (listen to music meanwhile):  --url https://live.bilibili.com/22105860
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" live_translate.py --src ja --device cuda --model-size large-v3 --merge-below 1.6 %*
pause
