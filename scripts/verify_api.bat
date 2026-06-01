@echo off
REM 物联网技术支持Agent - API验证脚本
REM 用法: verify_api.bat [port]
REM 示例: verify_api.bat 5000

set PORT=%1
if "%PORT%"=="" set PORT=5000

echo ============================================
echo 物联网技术支持Agent - API验证
echo ============================================
echo.

REM 检查服务是否运行
echo [1/5] 检查服务状态...
curl -s "http://localhost:%PORT%/api/health" > nul
if errorlevel 1 (
    echo [FAIL] 服务未运行，请先启动: python main.py --mode api --port %PORT%
    exit /b 1
)
echo [PASS] 服务正常运行

REM 检查知识库文档列表
echo [2/5] 检查知识库文档列表...
curl -s "http://localhost:%PORT%/api/labs/kbs/vehiclink-hardware/docs" > "%TEMP%\kb_docs.json"
findstr /C:"protocol_docs" "%TEMP%\kb_docs.json" > nul
if errorlevel 1 (
    echo [FAIL] 文档列表为空或返回错误
    echo Response:
    type "%TEMP%\kb_docs.json"
    exit /b 1
)
echo [PASS] 文档列表正常

REM 统计文档数量
for /f "delims=" %%i in ('curl -s "http://localhost:%PORT%/api/labs/kbs/vehiclink-hardware/docs" ^| findstr /C:"name"') do set /a DOC_COUNT+=1
echo       文档数量: %DOC_COUNT%

REM 检查资产上传端点
echo [3/5] 检查资产上传端点...
curl -s -X GET "http://localhost:%PORT%/api/labs/assets" > nul
if errorlevel 1 (
    echo [WARN] 资产端点异常
) else (
    echo [PASS] 资产端点正常
)

REM 检查分块预览端点
echo [4/5] 检查分块预览端点...
curl -s -X POST "http://localhost:%PORT%/api/labs/assets/chunks/preview" -H "Content-Type: application/json" -d "{\"text\":\"test\",\"chunk_size\":800,\"overlap\":120,\"mode\":\"fixed\"}" > nul
if errorlevel 1 (
    echo [WARN] 分块预览端点异常
) else (
    echo [PASS] 分块预览端点正常
)

REM 检查实验配置端点
echo [5/5] 检查实验配置端点...
curl -s -X GET "http://localhost:%PORT%/api/labs/experiments" > nul
if errorlevel 1 (
    echo [WARN] 实验配置端点异常
) else (
    echo [PASS] 实验配置端点正常
)

echo.
echo ============================================
echo 验证完成
echo ============================================
exit /b 0