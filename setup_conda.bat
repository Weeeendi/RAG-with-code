@echo off
chcp 65001 >nul
set CONDA=C:\Users\w1078\miniconda3\Scripts\conda.exe

echo Configuring conda mirror...
%CONDA% config --set custom_channels.conda-forge https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge
%CONDA% config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main
%CONDA% config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free

echo.
echo Current channels:
%CONDA% config --show channels

echo.
echo Creating environment...
%CONDA% create -n agent python=3.11 -y
if errorlevel 1 (
    echo Failed to create environment
    exit /b 1
)

echo.
echo Installing packages...
%CONDA% install -n agent -c pytorch -c nvidia -y numpy faiss-cpu sentence-transformers scikit-learn pdfplumber openpyxl python-docx chardet jieba requests pymupdf transformers torch

echo.
echo Installation complete!
pause