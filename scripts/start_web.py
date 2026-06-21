"""
启动后端服务：
1. REST API (Port 5000)
2. WebSocket Server (Port 8001)

注意：前端开发请单独运行 `npm run dev` (在 frontend 目录下)
"""

import os
import sys
import subprocess
import threading
import time


def _configure_console_encoding():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


_configure_console_encoding()

# 端口配置
REST_PORT = 5000
WS_PORT = 8001


def start_websocket_server():
    """启动 WebSocket 服务器"""
    # 调用 src/api/ws/server.py
    ws_server_script = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src', 'api', 'ws', 'server.py')
    print(f"启动 WebSocket 服务器: {ws_server_script}")
    subprocess.run([sys.executable, ws_server_script])


def start_rest_server():
    """启动 REST API 服务器"""
    # 调用 src/api/rest/server.py
    rest_server_script = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src', 'api', 'rest', 'server.py')
    print(f"启动 REST API 服务器: {rest_server_script}")
    subprocess.run([sys.executable, rest_server_script])


def main():
    """主函数"""
    print("=" * 80)
    print("工业空分装置智能优化系统 v2.0 - 后端服务启动")
    print("=" * 80)
    print()
    print(f"REST API: http://localhost:{REST_PORT}")
    print(f"WebSocket: ws://localhost:{WS_PORT}")
    print()
    print("注意：")
    print("1. 请确保前端开发服务器已启动 (cd frontend && npm run dev)")
    print("2. 访问前端显示的 Local URL (通常是 http://localhost:5173)")
    print()

    # 启动 WebSocket 服务线程
    ws_thread = threading.Thread(target=start_websocket_server, daemon=True)
    ws_thread.start()

    # 启动 REST API 服务线程
    rest_thread = threading.Thread(target=start_rest_server, daemon=True)
    rest_thread.start()

    try:
        # 保持主线程运行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n服务器已停止")
        sys.exit(0)


if __name__ == "__main__":
    main()
