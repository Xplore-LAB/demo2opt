"""
工业空分装置智能优化系统 - 完整E2E测试运行器

功能:
1. 检查并安装依赖
2. 启动测试服务器
3. 运行Playwright测试
4. 输出测试结果

运行: python run_e2e_test.py
"""
import os
import sys
import time
import socket
import subprocess
import threading
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent
SERVER_PORT = 8000
WEBSOCKET_PORT = 8000


def print_header(title: str):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def is_port_in_use(port: int) -> bool:
    """检查端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def check_dependencies():
    """检查并安装依赖"""
    print_header("步骤1: 检查依赖")

    deps_ok = True

    try:
        import playwright
        try:
            ver = playwright.__version__
        except AttributeError:
            ver = "unknown"
        print(f"  ✓ playwright {ver}")
    except ImportError:
        print("  ✗ playwright 未安装")
        deps_ok = False

    try:
        import pytest
        print(f"  ✓ pytest {pytest.__version__}")
    except ImportError:
        print("  ✗ pytest 未安装")
        deps_ok = False

    if not deps_ok:
        print("\n  正在安装依赖...")
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright", "pytest", "pytest-playwright"], check=True)
        print("  依赖安装完成")

        print("\n  安装浏览器驱动...")
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        print("  浏览器驱动安装完成")

    print("  ✓ 依赖检查通过")


def check_browser():
    """检查浏览器是否可用"""
    print_header("步骤2: 检查浏览器")

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        print("  ✓ Chromium 浏览器可用")
        return True
    except Exception as e:
        print(f"  ✗ 浏览器不可用: {e}")
        print("\n  尝试安装浏览器...")
        try:
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
            print("  ✓ 浏览器安装完成")
            return True
        except Exception as e2:
            print(f"  ✗ 浏览器安装失败: {e2}")
            return False


def start_http_server(port: int) -> subprocess.Popen:
    """启动HTTP服务器"""
    print(f"\n  尝试启动HTTP服务器 (端口 {port})...")

    if is_port_in_use(port):
        print(f"  ✓ 端口 {port} 已被占用，使用已有服务器")
        return None

    os.chdir(PROJECT_ROOT)

    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
        )

        for i in range(10):
            time.sleep(1)
            if is_port_in_use(port):
                print(f"  ✓ HTTP服务器已启动: http://localhost:{port}")
                return process

        process.terminate()
        print(f"  ⚠ 服务器启动超时，使用已有服务器")
        return None

    except Exception as e:
        print(f"  ⚠ 服务器启动异常: {e}，使用已有服务器")
        return None


def start_websocket_server() -> subprocess.Popen:
    """启动WebSocket服务器"""
    print("  启动WebSocket服务器...")

    ws_script = PROJECT_ROOT / "web_server.py"

    if not ws_script.exists():
        print("  ⚠ web_server.py 不存在，跳过WebSocket服务器")
        return None

    process = subprocess.Popen(
        [sys.executable, str(ws_script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(PROJECT_ROOT)
    )

    time.sleep(2)
    print(f"  ✓ WebSocket服务器已启动")
    return process


def stop_servers(http_process, ws_process):
    """停止服务器"""
    print("\n  停止服务器...")

    if http_process:
        http_process.terminate()
        try:
            http_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            http_process.kill()

    if ws_process:
        ws_process.terminate()
        try:
            ws_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            ws_process.kill()

    print("  ✓ 服务器已停止")


def run_tests():
    """运行测试"""
    print_header("步骤4: 运行测试")

    test_file = PROJECT_ROOT / "tests" / "e2e" / "test_chat_flow.py"

    if not test_file.exists():
        print(f"  ✗ 测试文件不存在: {test_file}")
        return False

    print(f"  测试文件: {test_file}")
    print(f"  目标URL: http://localhost:{SERVER_PORT}/index.html\n")

    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            str(test_file),
            "-v", "-s",
            "--tb=short",
            "--browser=chromium"
        ],
        cwd=str(PROJECT_ROOT),
        env={**os.environ, "HEADLESS": "true"}
    )

    return result.returncode == 0


def main():
    """主函数"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║     工业空分装置智能优化系统 - E2E自动化测试                   ║
╚══════════════════════════════════════════════════════════════╝
    """)

    http_process = None
    ws_process = None

    try:
        check_dependencies()

        if not check_browser():
            print("\n✗ 浏览器检查失败，请手动安装:")
            print("  python -m playwright install chromium")
            sys.exit(1)

        print_header("步骤3: 启动服务器")

        if is_port_in_use(SERVER_PORT):
            print(f"  ✓ 端口 {SERVER_PORT} 已被占用，使用已有服务器")
        else:
            http_process = start_http_server(SERVER_PORT)

        if is_port_in_use(WEBSOCKET_PORT):
            print(f"  ✓ 端口 {WEBSOCKET_PORT} 已被占用")
        else:
            try:
                ws_process = start_websocket_server()
            except Exception as e:
                print(f"  ⚠ WebSocket服务器启动失败: {e}")

        time.sleep(1)

        success = run_tests()

        if success:
            print_header("测试完成 - 全部通过 ✓")
        else:
            print_header("测试完成 - 存在失败 ✗")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")

    except Exception as e:
        print(f"\n✗ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        stop_servers(http_process, ws_process)


if __name__ == "__main__":
    main()
