# 工业空分装置智能优化系统 v2.0 - Web 界面

## 启动指南

### 1. 启动后端服务

后端服务包括 REST API (Port 5000) 和 WebSocket 服务器 (Port 8001)。

```bash
# 在项目根目录下运行
python scripts/start_web.py
```

### 2. 启动前端界面

前端使用 Vue 3 + Vite 开发。

```bash
# 进入 frontend 目录
cd frontend

# 安装依赖 (首次运行)
npm install

# 启动开发服务器
npm run dev
```

### 3. 访问系统

启动前端后，控制台会显示访问地址，通常为：

```
http://localhost:5173
```

## 功能特性

- **实时监控**：通过 WebSocket 实时显示程序运行过程
- **可视化界面**：左右布局，左侧显示步骤进度，右侧显示终端输出
- **自动折叠**：大步骤完成后自动折叠，保持界面整洁
- **终端控制**：支持折叠/展开、清空、日志过滤
- **连接状态**：显示 WebSocket 连接状态
- **进度追踪**：实时显示整体进度和步骤状态
- **配置管理**：支持 LLM 配置和 Dify 配置
- **报告生成**：支持 Markdown 和 PDF 报告下载

## 技术架构

- **前端**：Vue 3 + Vite + Bootstrap 5
- **通信协议**：WebSocket + REST API
- **后端**：Python (Flask + websockets)

## 故障排除

### 无法连接到后端
- 检查 `scripts/start_web.py` 是否正在运行
- 检查端口 5000 (REST) 和 8001 (WS) 是否被占用

### 页面无法加载
- 检查 `npm run dev` 是否成功启动
- 确认访问地址是否正确

### API 调用失败
- 检查 REST API 服务是否正常运行 (访问 http://localhost:5000/api/health)
