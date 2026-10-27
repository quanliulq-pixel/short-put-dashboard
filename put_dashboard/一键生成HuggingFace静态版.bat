@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在拉取最新行情并生成 Hugging Face Static 免费空间专用 index.html ...
"C:\Users\lq\AppData\Local\Programs\Python\Python313\python.exe" build_hf_static.py
echo.
echo ======================================================================
echo 已生成完毕！请直接将以下文件上传并替换到 Hugging Face Static Space：
echo   %~dp0huggingface_static\index.html
echo ======================================================================
explorer "%~dp0huggingface_static"
pause
