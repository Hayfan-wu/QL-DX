# QL-DX - 中国电信话费自动化

基于 API 直调的中国电信网上营业厅自动化脚本，支持**青龙面板定时运行** + **QQ 机器人交互控制** + **产物自动记录查询**。

> **v3.0 重大更新**：从 Playwright 浏览器模式迁移到 API 直调，无需 Chromium，部署更简单。

## 功能

| 功能 | 说明 |
|------|------|
| 服务密码登录 | Token 缓存，24 小时内免重复登录 |
| 每日签到 | 签到翻牌领金豆 |
| 连签兑换 | 7天/15天/28天连签奖励自动兑换 |
| 首页任务 | 领取奖励/看视频/聚合任务自动完成 |
| 宠物乐园 | 喂食/升级/兑换话费 |
| 金豆查询 | 余额及过期提醒 |
| 产物记录 | 每次执行自动记录产物，可随时查询 |
| 瑞数绕过 | 内置 execjs 反爬处理 |

## 活动产物一览

| 编号 | 活动名称 | 产物 |
|------|----------|------|
| ① | 每日签到翻牌 | 金豆(20~1500)、通话时长、流量包 |
| ② | 连签奖励兑换 | 金豆、话费券 |
| ③ | 首页任务 | 金豆、流量包 |
| ④ | 宠物乐园 | 话费券、金豆 |

---

## 快速开始

### 青龙面板部署

```bash
# 1. 拉取仓库
cd /ql/data/scripts && git clone https://github.com/Hayfan-wu/QL-DX.git

# 2. 安装依赖（青龙面板依赖管理 → 新增依赖，或终端执行）
pip install httpx execjs pycryptodome requests --break-system-packages

# 3. 创建定时任务
# 任务名: DX-Telecom
# 命令: task QL-DX/main.py
# 定时: 0 8,12,18 * * *
```

> **注意**：青龙面板需要 Node.js 运行时（execjs 依赖）。青龙面板通常已内置 Node.js。

### 宿主机部署

```bash
cd /opt && git clone https://github.com/Hayfan-wu/QL-DX.git
cd QL-DX
pip install httpx execjs pycryptodome requests --break-system-packages
```

### 更新

```bash
cd /opt/QL-DX && git pull
```

### 配置环境变量

在青龙面板中创建以下环境变量，或通过 QQ 机器人 `电信登录` 设置：

| 变量 | 说明 | 必填 |
|------|------|------|
| `DX_ACCOUNT` | 电信账号（格式: 手机号#密码） | ✅ |
| `DX_ENABLE_SIGNIN` | 启用签到 | 否 |
| `DX_ENABLE_ACTIVITY` | 启用活动扫描 | 否 |
| `DX_ENABLE_FLASH_SALE` | 启用秒杀 | 否 |
| `DX_FLASH_SALE_TIME` | 秒杀时间 HH:MM:SS | 否 |
| `DX_HEADLESS` | 无头模式（本版已废弃） | 否 |

### 创建定时任务（重要）

青龙面板通过宿主机 `/opt/` 目录读取脚本，任务命令使用绝对路径：

```
任务名称: DX-Telecom
命令: task /opt/QL-DX/main.py
定时规则: 0 8,12,18 * * *
```

---

## QQ 机器人交互

本仓库自带 `bot_plugins/` 插件，配合 [QL-Bot](https://github.com/Hayfan-wu/QL-Bot) 框架使用，零侵入接入。

### 部署方式

```bash
# 首次
cd /opt && git clone https://github.com/Hayfan-wu/QL-DX.git

# 更新
cd /opt/QL-DX && git pull
```

QL-Bot 启动时自动扫描 `/opt/QL-DX/bot_plugins/` 并加载插件。

### 机器人命令（全部中文）

| 命令 | 功能 |
|------|------|
| `电信菜单` | 显示活动清单（含产物）和全部命令功能 |
| `电信登录` | 多轮引导：输入手机号 → 输入密码 → 自动保存并提交青龙面板 |
| `电信状态` | 查看当前账号、密码状态、各功能开关 |
| `电信查询` | 查询所有历史任务获得的产物（累计+详情） |
| `电信签到` | 手动触发签到翻牌任务（后台线程，不阻塞） |
| `电信执行` | 执行全部自动化任务 |
| `电信配置` | 查看所有环境变量当前值（账号脱敏显示） |
| `电信开启 签到` | 开启签到功能（可选: 签到/活动/秒杀） |
| `电信关闭 秒杀` | 关闭秒杀功能（可选: 签到/活动/秒杀） |
| `签到` | 快捷命令，等于 `电信签到` |
| `话费` / `金豆` | 快捷命令，等于 `电信状态` |

---

## 项目结构

```
QL-DX/
├── main.py              # 唯一入口（青龙只需这一个任务）
├── telecom_api.py       # 核心 API 自动化逻辑
├── rs_core.js           # 瑞数反爬绕过 JS 环境
├── config.py            # 配置管理
├── .env                 # 环境变量（git不追踪）
├── .env.example         # 环境变量模板
├── result.json          # 产物记录（自动生成）
├── requirements.txt     # Python 依赖
├── README.md            # 本文件
└── bot_plugins/         # QQ机器人插件
    ├── __init__.py
    └── dx_plugin.py     # 交互逻辑
```

## 依赖

| 依赖 | 用途 |
|------|------|
| `httpx` | HTTP 请求 |
| `execjs` | 执行 JS 瑞数反爬 |
| `pycryptodome` | RSA/AES/3DES 加密 |
| `requests` | 青龙 API 调用 |

无需 Chromium / Playwright，部署简单。

## 注意事项

- 需要 Node.js 运行时（execjs 依赖），青龙面板通常已内置
- 首次运行建议查看日志文件 `dx_telecom.log` 确认流程正常
- `DX_ACCOUNT` 格式为 `手机号#密码`，用 `#` 分隔
- 青龙面板拉取后**务必删除多余任务**，只保留 main.py
- 产物记录保存在 `result.json`，通过 `电信查询` 命令查看