@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=C:\Users\lq\AppData\Local\Programs\Python\Python313\python.exe
if not exist "%PY%" set PY=python
echo ====================================================================
echo   Starting Weekly Short Put Recommender at http://127.0.0.1:5058
echo   每周动态卖Put推荐系统 · 美股/ETF · 美国期货 · 中国期货
echo ====================================================================
start "" "http://127.0.0.1:5058"
"%PY%" app.py
pause
