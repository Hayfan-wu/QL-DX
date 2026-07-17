# QL-DX - 中国电信话费自动化

基于 Playwright 的中国电信网上营业厅自动化脚本，支持**青龙面板定时运行** + **QQ 机器人交互控制**。

## 功能

| 功能 | 说明 |
|------|------|
| 账号密码登录 | Cookie 持久化，一次登录持续有效 |
| 每日签到 | 自动签到领金豆 |
| 金豆抽奖 | 金豆商城转盘抽奖 |
| 金豆兑换 | 金豆达到阈值自动兑换话费 |
| 活动扫描 | 遍历活动页面自动参与 |
| 限时秒杀 | 指定时间精准抢购 |

## 活动入口

| 活动 | URL |
|------|-----|
| 金豆抽奖 | `wapact.189.cn:9001/JinDouMall/JinDouMall_luckDraw.html` |
| 见面礼（领200金豆） | `wappark.189.cn/resources/shortMessage/rearendMoneyWap.html` |
| 见面礼短链接 | `a.189.cn/NeYzRQ` |
| 积分商城 | `jf.189.cn` |
| 口令兑换 | `wapact.189.cn:9001/flcj/index.html` |
| 兑换码入口 | `wapact.189.cn:9001/InvitationCode/inviteesNew4.html` |
| APP签到 | 中国电信APP → 首页签到 |
| 金豆秒杀（10点/14点） | APP内金豆商城 |

## 快速开始

### 1. 部署到青龙面板

```bash
# 将本仓库克隆到青龙面板的 scripts 目录
cd /ql/data/scripts  # 或 /ql/scripts
git clone https://github.com/Hayfan-wu/QL-DX.git
cd QL-DX
pip install -r requirements.txt --break-system-packages
playwright install chromium
```

### 2. 配置环境变量

在青龙面板中创建以下环境变量，或通过 QQ 机器人 `/dx login` 设置：

| 变量 | 说明 | 必填 |
|------|------|------|
| `DX_PHONE` | 电信手机号 | ✅ |
| `DX_PASSWORD` | 登录密码 | ✅ |
| `DX_ENABLE_SIGNIN` | 启用签到 | 否 |
| `DX_ENABLE_EXCHANGE` | 启用兑换 | 否 |
| `DX_ENABLE_ACTIVITY` | 启用活动扫描 | 否 |
| `DX_ENABLE_FLASH_SALE` | 启用秒杀 | 否 |
| `DX_MIN_BEANS_TO_EXCHANGE` | 兑换阈值金豆数 | 否 |
| `DX_FLASH_SALE_TIME` | 秒杀时间 HH:MM:SS | 否 |
| `DX_HEADLESS` | 无头模式 | 否 |

### 3. 创建定时任务

```
任务名称: DX-Telecom
命令: task QL-DX/main.py
定时规则: 0 8,12,18 * * *
```

## QQ 机器人交互

本仓库自带 `bot_plugins/` 插件，配合 [QL-Bot](https://github.com/Hayfan-wu/QL-Bot) 框架使用，实现零侵入接入。

### 部署方式

```bash
# 将 QL-DX 放到 /opt 目录下
cd /opt
git clone https://github.com/Hayfan-wu/QL-DX.git
```

QL-Bot 启动时会自动扫描 `/opt/QL-DX/bot_plugins/` 并加载插件。

### 机器人命令

| 命令 | 说明 |
|------|------|
| `/dx` | 帮助菜单 |
| `/dx login` | 多轮引导设置账号密码 |
| `/dx status` | 查看运行状态 |
| `/dx setup` | 提交环境变量到青龙面板 |
| `/dx signin` | 手动触发签到 |
| `/dx exchange` | 手动触发金豆兑换 |
| `/dx run` | 执行全部任务 |
| `/dx config` | 查看所有配置 |
| `/dx set KEY VAL` | 设置单个配置项 |
| `/dx enable XX` | 开启功能 |
| `/dx disable XX` | 关闭功能 |
| `话费` / `签到` / `金豆` | 快捷命令 |

### 交互流程示例

```
用户: /dx login
Bot:  🔑 请输入你的中国电信手机号（11位数字）：

用户: 13800138000
Bot:  📱 手机号已记录，请输入登录密码：

用户: mypassword
Bot:  ✅ 账号密码已保存！
      📱 手机号: 138****8000
      🔐 密码: **********
      
      下一步请发送 /dx setup 提交到青龙面板

用户: /dx setup
Bot:  📤 青龙面板配置提交
      ✅ 成功: 9 个
      请在青龙面板中创建定时任务...
```

## 项目结构

```
QL-DX/
├── main.py              # 青龙面板入口
├── telecom_api.py       # 核心自动化逻辑
├── config.py            # 配置管理
├── .env.example         # 环境变量模板
├── requirements.txt     # Python 依赖
├── README.md            # 本文件
└── bot_plugins/         # QQ机器人插件
    ├── __init__.py
    └── dx_plugin.py     # 交互逻辑
```

## 注意事项

- 首次运行建议关闭无头模式（`DX_HEADLESS=false`），确认流程正常后再开启
- 如遇验证码，无头模式下会失败，请先手动登录一次保存 Cookie
- 活动页面 URL 可能变动，可在 `config.py` 中更新
- 秒杀功能仅在脚本运行时间接近目标时间时自动触发，建议定时任务设置在秒杀前几分钟