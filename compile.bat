@echo off
title Compilando GMOD Editor...

echo ==========================================
echo 🔨 COMPILANDO GMOD EDITOR...
echo ==========================================

set PYTHON_PATH=C:\Users\AdministradorUser\AppData\Local\Python\pythoncore-3.14-64\python.exe

"%PYTHON_PATH%" -m PyInstaller --onefile --windowed --hidden-import=tkinter --hidden-import=tkinter.ttk --name="GMOD_Editor" main.py

echo.
echo ==========================================
echo ✅ CONCLUIDO! Arquivo em: dist\GMOD_Editor.exe
echo ==========================================
pause