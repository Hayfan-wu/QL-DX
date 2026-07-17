# QL-DX - 中国电信话费自动化

基于 Playwright 的中国电信网上营业厅自动化脚本，支持**青龙面板定时运行** + **QQ 机器人交互控制**。

## 功能

| 功能 | 说明 |
|------|------|
| 账号密码登录 | Cookie 持久化，一次登录持续有效 |
| 每日签到 | 自动签到翻牌领金豆/话费 |
| 金豆抽奖 | 金豆商城转盘抽奖 |
| 金豆兑换 | 金豆达到阈值自动兑换话费 |
| 活动扫描 | 遍历核心活动页面自动参与 |
| 限时秒杀 | 指定时间精准抢购 |

---

## 全部 17 个活动入口一览

### ✅ 核心活动（保留，全国通用，网页可自动化）

| 编号 | 活动名称 | URL | 说明 |
|------|----------|-----|------|
| ① | 签到翻牌抽奖 | `wapact.189.cn:9001/mas-pub-ui/spm/Spring2024` | 翻牌抽话费/金豆 |
| ② | 金豆商城转盘抽奖 | `wapact.189.cn:9001/JinDouMall/JinDouMall_luckDraw.html` | 消耗金豆抽奖 |
| ③ | 见面礼-暖心福利包 | `wappark.189.cn/.../rearendMoneyWap.html` | 登录领200金豆，至2026.7.31 |
| ④ | 见面礼短链接 | `a.189.cn/NeYzRQ` | 重定向到③ |
| ⑤ | 积分商城 | `jf.189.cn` | 积分兑话费/流量 |
| ⑥ | 积分商城备用 | `jf.ct10000.com/` | 备用域名 |
| ⑦ | 口令兑换 | `wapact.189.cn:9001/flcj/index.html` | 输入省份口令抽0.66~100元话费 |

### ⚠️ 过滤活动（地区限制 / 需兑换码 / 已过期，默认不启用）

| 编号 | 活动名称 | URL | 过滤原因 |
|------|----------|-----|----------|
| ⑧ | 兑换码兑奖入口 | `wapact.189.cn:9001/InvitationCode/inviteesNew4.html` | 需提前获取兑换码 |
| ⑨ | 天津-充值抽奖 | `waptj.189.cn/tj/wap/rechargeDraw.html` | 地区限制 + 需充值 |
| ⑩ | 安徽-权益会员日 | `qy.ah.189.cn/member/qyMemberDay/index.html` | 地区限制 |
| ⑪ | 河北-周三宠粉日 | `hyzx.he.189.cn/.../Wednesday/wednesday.html` | 地区限制 |
| ⑫ | 湖南-聚合权益流量包 | `qy.hn.189.cn/h5app/equity/` | 地区限制 + 需订购 |
| ⑬ | 江苏-人人有礼 | `wapjs.189.cn/mall/pages/jhAll/index.html` | 地区限制 |
| ⑭ | 江苏-签到领流量 | `wapjs.189.cn/mall/pages/signinActivity/index.html` | 已迁移至APP |

### ⚠️ APP 专属（网页无法自动化，仅供参考）

| 编号 | 活动名称 | 入口路径 | 说明 |
|------|----------|----------|------|
| ⑮ | 每日签到领金豆 | APP首页 → 签到 | 20-35金豆/天 |
| ⑯ | 金豆秒杀0.5元 | APP金豆商城 → 兑换区 | 100金豆，每日10:00 |
| ⑰ | 金豆秒杀1元 | APP金豆商城 → 兑换区 | 200金豆，每日14:00 |

> 脚本实际执行的是 ①~⑦ 中的 5 个核心活动（①签到 ②抽奖 ③见面礼 ⑤积分商城 ⑦口令兑换）。

---

## 快速开始

### 1. 部署到青龙面板

```bash
cd /ql/data/scripts   # 或 /ql/scripts
git clone https://github.com/Hayfan-wu/QL-DX.git
cd QL-DX
pip install -r requirements.txt --break-system-packages
playwright install chromium
```

### 2. 配置环境变量

在青龙面板中创建以下环境变量，或通过 QQ 机器人 `电信登录` 设置：

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
| `DX_HEADLESS` | 无头模式 true/false | 否 |

### 3. 创建定时任务

```
任务名称: DX-Telecom
命令: task QL-DX/main.py
定时规则: 0 8,12,18 * * *
```

---

## QQ 机器人交互

本仓库自带 `bot_plugins/` 插件，配合 [QL-Bot](https://github.com/Hayfan-wu/QL-Bot) 框架使用，零侵入接入。

### 部署方式

```bash
cd /opt
git clone https://github.com/Hayfan-wu/QL-DX.git
```

QL-Bot 启动时自动扫描 `/opt/QL-DX/bot_plugins/` 并加载插件。

### 机器人命令（全部中文）

| 命令 | 说明 |
|------|------|
| `电信` / `电信帮助` | 帮助菜单 |
| `电信登录` | 多轮引导设置账号密码 |
| `电信状态` | 查看运行状态 |
| `电信提交` | 一键提交环境变量到青龙面板 |
| `电信签到` | 手动触发签到 |
| `电信兑换` | 手动触发金豆兑换 |
| `电信执行` | 执行全部任务 |
| `电信配置` | 查看所有配置项 |
| `电信设置 K V` | 设置单个配置项 |
| `电信开启 签到` | 开启签到功能 |
| `电信关闭 秒杀` | 关闭秒杀功能 |
| `签到` / `话费` / `金豆` | 快捷命令 |

可开关功能: `签到` `兑换` `活动` `秒杀`

### 交互流程示例

```
用户: 电信登录
Bot:  🔑 请输入你的中国电信手机号（11位数字）：

用户: 13800138000
Bot:  📱 手机号已记录，请输入登录密码：

用户: mypassword
Bot:  ✅ 账号密码已保存！
      📱 手机号: 138****8000
      🔐 密码: **********
      
      下一步请发送 电信提交 提交到青龙面板

用户: 电信提交
Bot:  📤 青龙面板配置提交
      ✅ 成功: 9 个
      请在青龙面板中创建定时任务...

用户: 电信状态
Bot:  📊 中国电信话费自动化 - 状态
      📱 手机号: 138****8000
      🔐 密码:   已设置
      签到: ✅ 开启
      兑换: ✅ 开启
      活动: ✅ 开启
      秒杀: ✅ 开启
```

## 项目结构

```
QL-DX/
├── main.py              # 青龙面板入口
├── telecom_api.py       # 核心自动化逻辑
├── config.py            # 配置管理（17个活动URL）
├── .env                 # 环境变量
├── .env.example         # 环境变量模板
├── requirements.txt     # Python 依赖
├── README.md            # 本文件
└── bot_plugins/         # QQ机器人插件
    ├── __init__.py
    └── dx_plugin.py     # 交互逻辑（全中文命令）
```

## 注意事项

- 首次运行建议关闭无头模式（`DX_HEADLESS=false`），确认流程正常后再开启
- 如遇验证码，无头模式下会失败，请先手动登录一次保存 Cookie
- 活动页面 URL 可能变动，可在 `config.py` 中更新
- 秒杀功能仅在脚本运行时间接近目标时间时自动触发，建议定时任务设置在秒杀前几分钟
- 如需启用地区活动，修改 `config.py` 中 `ACTIVITY_URLS` 列表即可