# Nitrogen Vue Module

这个文件夹现在已经是一个可以独立运行的最小 Vite 前端。

## 核心文件

- `src/views/NitrogenPlugDemo.vue`
- `src/utils/nitrogenCore.js`
- `src/utils/chartUpdate.js`
- `src/workers/nitrogenScan.worker.js`
- `src/App.vue`
- `src/main.js`
- `index.html`
- `vite.config.js`
- `package.json`

## 运行方式

```bash
cd nitrogen_vue_module
npm install
npm run dev
```

默认访问：

- [http://127.0.0.1:5176](http://127.0.0.1:5176)

## 双击启动 dist

如果你想让别人直接利用现有 `dist` 成果打开界面，可以双击：

- [一键启动_dist.bat](</D:/Code/0 自主学习/demo2opt/nitrogen_vue_module/一键启动_dist.bat:1>)

它会：

1. 使用本机 Python 在 `dist/` 目录启动一个静态服务
2. 自动打开浏览器
3. 访问 `http://127.0.0.1:4176`

注意：

- 这个方式依赖本机已安装 Python
- 需要保持弹出的服务窗口不关闭，页面才能继续访问

## 默认运行模式

默认是“纯前端静态模式”：

- 历史数据使用 `public/data/nitrogen-demo-default.csv`
- 精选病例使用 `public/mock-api/nitrogen-demo-selected/`
- 原因分析在后端不可用时会自动回退到页面本地规则分析

也就是说，不启动原后端也能打开页面、识别氮塞并走完整个演示流程。

## 可选：接原后端

如果你想让这个独立前端去请求原后端接口，可以在本目录新增 `.env`：

```bash
VITE_NITROGEN_API_BASE=http://127.0.0.1:5000
```

这样页面会优先请求：

- `/api/nitrogen-demo/meta`
- `/api/nitrogen-demo/data`
- `/api/nitrogen-agent/analyze`

请求失败时仍会回退到本地静态数据和本地规则结果。
