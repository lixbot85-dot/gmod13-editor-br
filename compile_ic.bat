@echo off
title Compilando GMOD Editor...

echo ==========================================
echo COMPILANDO GMOD EDITOR...
echo ==========================================

set PYTHON_PATH=C:\Users\AdministradorUser\AppData\Local\Python\pythoncore-3.14-64\python.exe
set ICON_FLAG=

:: Verifica se o arquivo main.ico existe (para não dar failback nesse script que estou escrevendo)
if exist "main.ico" (
    echo Ícone encontrado: main.ico
    set ICON_FLAG=--icon=main.ico
) else (
    echo Nenhum ícone encontrado. Compilando sem ícone.
)

echo.
echo Executando PyInstaller...
"%PYTHON_PATH%" -m PyInstaller --onefile --windowed --hidden-import=tkinter --hidden-import=tkinter.ttk %ICON_FLAG% --name="GMOD_Editor" main.py

echo.
echo ==========================================
echo CONCLUIDO! Arquivo em: dist\GMOD_Editor.exe
echo ==========================================
pause
