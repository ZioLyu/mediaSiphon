# mediaSiphon

一个本地流媒体抓取控制台。粘贴 m3u8 / mpd 地址，选择清晰度，由后台引擎完成下载、解密与封装，
界面用 Vue 3 绘制，后端是纯 Python，两者通过本机 HTTP + WebSocket 通信。

> 本项目为独立实现，代码与架构均为自行设计，不复用任何既有项目的源码。

## 目录结构

```
mediaSiphon/
├── siphon/                 后端（Python）
│   ├── api.py              HTTP + WebSocket 接口
│   ├── desktop.py          桌面外壳：端口协商 + 单实例 + 原生窗口
│   ├── runner.py           引擎进程管理（异步子进程）
│   ├── spec.py             抓取规格 → 命令行参数
│   ├── progress.py         从终端输出解析进度
│   ├── probe.py            清单探测（分辨率 / 编码 / 帧率 / 直播判定）
│   ├── store.py            任务台账（sqlite3）
│   ├── settings.py         设置读写（JSON + 原子落盘）
│   └── paths.py            运行时目录解析
├── frontend/               前端（Vue 3 + TypeScript + Vite）
│   ├── src/
│   │   ├── views/          抓取 / 任务 / 设置 三个页面
│   │   ├── components/     通用控件
│   │   ├── api/            请求与实时通道
│   │   ├── state/          全局状态
│   │   └── styles/         设计令牌与全局样式
│   └── vite.config.ts
├── engine/                 放置外部引擎（不进版本库）
├── tools/                  开发自检脚本（静态检查 + 逻辑测试）
├── build.py                Nuitka 打包入口
├── dev.py                  后端热重启入口
├── pyproject.toml
└── README.md
```

## 环境准备

需要 Python 3.10+ 与 Node 18+。

```bash
pip install -e ".[dev]"
cd frontend && npm install
```

把两个外部程序放进 `engine/` 目录：

- `N_m3u8DL-RE`（Windows 下为 `N_m3u8DL-RE.exe`）—— 负责下载、解密、混流
- `ffmpeg`（Windows 下为 `ffmpeg.exe`）—— 负责抽封面与封装

## 开发

开两个终端：

```bash
# 终端 1：前端，带热更新
cd frontend && npm run dev

# 终端 2：后端 + 桌面窗口，指向 Vite
python -m siphon.desktop --dev
```

也可以只跑后端，用浏览器访问：

```bash
python -m siphon.desktop --no-window --port 8765
```

此时 Vite 的代理会把 `/api` 与 `/ws` 转发到 8765，改前端代码即时生效。

## 构建

```bash
cd frontend && npm run build     # 产物输出到 frontend/dist
python build.py                  # 用 Nuitka 打包成单目录应用
python -m siphon.desktop
```

打包后运行 `dist/mediaSiphon.dist/mediaSiphon.exe`，数据写在 `%APPDATA%\mediaSiphon`。

## 自检

`tools/` 目录存放一组不需要额外依赖的静态检查与逻辑测试：

```bash
python tools/selfcheck.py      # 核心逻辑断言（进度解析 / 参数拼装 / 数据层）
python tools/runtests.py       # 执行 tests/ 下的全部用例（未装 pytest 也能跑）
python tools/checkrefs.py      # 模块间引用是否都存在
python tools/checkfields.py    # 前后端设置字段是否一一对应
python tools/checkapi.py       # 前端调用的接口后端是否都有
python tools/checkui.py        # Vue 单文件组件结构与导入路径
python tools/checkicons.py     # 模板里用到的图标名是否都已定义
```

> 在 Windows 上编辑文件后，若编辑器用系统区域编码保存，可先运行
> `python tools/normalize_utf8.py` 把所有文本源文件统一转成 UTF-8。

## 运行时数据

| 位置（源码模式） | 内容 |
|---|---|
| `runtime/settings.json` | 全部设置 |
| `runtime/history.db` | 任务台账（SQLite） |
| `runtime/thumbs/` | 自动抽取的封面 |
| `runtime/logs/` | 每个任务的完整输出与应用日志 |

设置环境变量 `SIPHON_DATA_DIR` 可把上述目录整体挪到别处。

## 字段与契约

外部引擎的参数名属于第三方程序的稳定接口，本项目沿用其命令行约定；
除此之外的数据结构、接口、表结构、配置键名均为自行设计。
