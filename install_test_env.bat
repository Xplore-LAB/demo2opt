@echo off
REM 工业空分装置智能优化系统 - E2E 测试环境安装脚本

echo ========================================
echo   Playwright E2E 测试环境安装
echo ========================================
echo.

echo [1/4] 升级 pip...
python -m pip install --upgrade pip

echo.
echo [2/4] 安装测试依赖...
pip install playwright pytest pytest-playwright

echo.
echo [3/4] 安装浏览器驱动...
python -m playwright install chromium

echo.
echo [4/4] 验证安装...
python -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"

echo.
echo ========================================
echo   安装完成！
echo ========================================
echo.
echo 运行测试:
echo   1. 启动服务器: python start_web.py
echo   2. 运行测试: python -m pytest tests/e2e/test_chat_flow.py -v -s
echo.
echo 或使用自动服务器启动:
echo   python tests/e2e/playwright_config.py --server
echo.
pause
