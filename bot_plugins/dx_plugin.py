# -*- coding: utf-8 -*-
"""
中国电信话费自动化 - QQ机器人插件
==================================
QL-Bot 业务项目插件，提供完整的 QQ 交互逻辑。
支持多轮会话引导配置、一键提交青龙面板、手动触发任务。

命令列表:
  /dx              - 帮助菜单
  /dx login        - 设置账号密码（多轮引导）
  /dx status       - 查看配置状态
  /dx setup        - 提交环境变量到青龙面板
  /dx signin       - 手动触发签到
  /dx exchange     - 手动触发金豆兑换
  /dx run          - 执行全部任务
  /dx enable XX    - 开启功能 (signin/exchange/activity/flash)
  /dx disable XX   - 关闭功能
  /dx config       - 查看当前所有配置
  /dx set KEY VAL  - 设置单个配置项
"""

import os
import re
import json
import subprocess
import sys
from pathlib import Path

from bot.plugins.base import Plugin
from bot.utils import send_qq_message, Log, normalize_text
from bot.ql_api import ql
from bot.session import SessionManager

# ==================== 环境变量定义 ====================
DX_ENV_VARS = [
    ("DX_PHONE",              "电信手机号"),
    ("DX_PASSWORD",           "登录密码"),
    ("DX_ENABLE_SIGNIN",      "启用签到 (true/false)"),
    ("DX_ENABLE_EXCHANGE",    "启用兑换 (true/false)"),
    ("DX_ENABLE_ACTIVITY",    "启用活动扫描 (true/false)"),
    ("DX_ENABLE_FLASH_SALE",  "启用秒杀 (true/false)"),
    ("DX_MIN_BEANS_TO_EXCHANGE", "兑换阈值金豆数"),
    ("DX_FLASH_SALE_TIME",    "秒杀时间 (HH:MM:SS)"),
    ("DX_HEADLESS",           "无头模式 (true/false)"),
    ("DX_TIMEOUT",            "超时秒数"),
]

# ==================== 帮助文本 ====================
HELP_TEXT = """📱 中国电信话费自动化

可用命令:
━━━━━━━━━━━━━━━━━━━━
🔑 /dx login       - 设置账号密码
📊 /dx status      - 查看运行状态
⚙️  /dx setup       - 提交配置到青龙面板
🎯 /dx signin      - 手动触发签到
💎 /dx exchange    - 手动触发兑换
🚀 /dx run         - 执行全部任务
🔧 /dx config      - 查看当前所有配置
📝 /dx set KEY VAL - 设置单个配置项
✅ /dx enable XX   - 开启功能
❌ /dx disable XX  - 关闭功能
━━━━━━━━━━━━━━━━━━━━
功能项: signin | exchange | activity | flash

项目地址: github.com/Hayfan-wu/QL-DX"""


# ==================== 插件类 ====================
class DXPlugin(Plugin):
    name = "DX-Telecom"
    commands = [
        r"^/dx\b",
        r"^dx\s",
        r"^话费",
        r"^签到",
        r"^金豆",
        r"^电信",
    ]

    def __init__(self):
        super().__init__()
        self.project_dir = None  # 由 project_loader 注入
        self._env_path = None

    # ---------- 命令匹配 ----------
    def match(self, text):
        text = text.strip()
        for cmd in self.commands:
            if isinstance(cmd, str) and not cmd.startswith("^"):
                if text.lower().startswith(cmd.lower()):
                    return True
            else:
                if re.search(cmd, text, re.IGNORECASE):
                    return True
        return False

    # ---------- 消息处理 ----------
    def handle(self, text, sender_id, group_id=None):
        text = text.strip()

        # 非 /dx 开头的简化命令
        if text.startswith("签到"):
            return self._cmd_signin(sender_id, group_id)
        if text.startswith("话费"):
            return self._cmd_status(sender_id, group_id)
        if text.startswith("金豆"):
            return self._cmd_status(sender_id, group_id)

        # 解析 /dx 子命令
        parts = text.split(maxsplit=2)
        if len(parts) < 2:
            return HELP_TEXT

        sub_cmd = parts[1].lower() if len(parts) > 1 else ""
        arg = parts[2] if len(parts) > 2 else ""

        handlers = {
            "login":    lambda: self._cmd_login(sender_id, group_id),
            "status":   lambda: self._cmd_status(sender_id, group_id),
            "setup":    lambda: self._cmd_setup(sender_id, group_id),
            "signin":   lambda: self._cmd_signin(sender_id, group_id),
            "exchange": lambda: self._cmd_exchange(sender_id, group_id),
            "run":      lambda: self._cmd_run(sender_id, group_id),
            "config":   lambda: self._cmd_config(sender_id, group_id),
            "set":      lambda: self._cmd_set(arg, sender_id, group_id),
            "enable":   lambda: self._cmd_toggle(arg, True, sender_id, group_id),
            "disable":  lambda: self._cmd_toggle(arg, False, sender_id, group_id),
        }

        handler = handlers.get(sub_cmd)
        if handler:
            return handler()
        return HELP_TEXT

    # ---------- 环境文件路径 ----------
    def _get_env_path(self):
        if self._env_path:
            return self._env_path
        if self.project_dir:
            self._env_path = os.path.join(self.project_dir, ".env")
        else:
            self._env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
        return self._env_path

    def _read_env(self) -> dict:
        """读取 .env 文件为字典"""
        env = {}
        p = self._get_env_path()
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        env[k.strip()] = v.strip().strip("\"'")
        return env

    def _write_env(self, env: dict):
        """写入 .env 文件"""
        p = self._get_env_path()
        lines = []
        # 保留注释头
        lines.append("# 中国电信话费自动化 - 环境变量")
        lines.append("# 由 QQ 机器人自动生成")
        lines.append("")
        for key, desc in DX_ENV_VARS:
            val = env.get(key, "")
            lines.append(f"# {desc}")
            lines.append(f"{key}={val}")
            lines.append("")
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        Log.ok(f".env 已更新: {p}")

    # ---------- 命令实现 ----------

    def _cmd_login(self, sender_id, group_id=None):
        """引导设置账号密码 - 多轮会话"""
        # 注册会话处理器
        SessionManager.register(sender_id, "dx_login", self._login_session)
        return "🔑 请输入你的中国电信手机号（11位数字）："

    def _login_session(self, sender_id, group_id, text):
        """登录会话处理"""
        text = text.strip()

        # 第1步：输入手机号
        if re.match(r"^1[3-9]\d{9}$", text):
            SessionManager.set_data(sender_id, "dx_phone", text)
            return "📱 手机号已记录，请输入登录密码："

        # 第2步：输入密码
        if SessionManager.get_data(sender_id, "dx_phone"):
            phone = SessionManager.get_data(sender_id, "dx_phone")
            pwd = text
            # 保存到 .env
            env = self._read_env()
            env["DX_PHONE"] = phone
            env["DX_PASSWORD"] = pwd
            self._write_env(env)

            SessionManager.clear(sender_id)
            return (
                f"✅ 账号密码已保存！\n"
                f"📱 手机号: {phone[:3]}****{phone[-4:]}\n"
                f"🔐 密码: {'*' * len(pwd)}\n\n"
                f"下一步请发送 /dx setup 提交到青龙面板"
            )

        return "⚠️ 请先输入正确的手机号（11位数字）"

    def _cmd_status(self, sender_id, group_id=None):
        """查看运行状态"""
        env = self._read_env()
        phone = env.get("DX_PHONE", "未设置")
        if phone and len(phone) >= 11:
            phone_display = f"{phone[:3]}****{phone[-4:]}"
        else:
            phone_display = "未设置"

        pwd_set = "已设置" if env.get("DX_PASSWORD") else "未设置"

        def _on_off(key):
            v = env.get(key, "true").lower()
            return "✅ 开启" if v in ("true", "1", "yes", "on") else "❌ 关闭"

        return (
            f"📊 中国电信话费自动化 - 状态\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 手机号: {phone_display}\n"
            f"🔐 密码:   {pwd_set}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"签到: {_on_off('DX_ENABLE_SIGNIN')}\n"
            f"兑换: {_on_off('DX_ENABLE_EXCHANGE')}\n"
            f"活动: {_on_off('DX_ENABLE_ACTIVITY')}\n"
            f"秒杀: {_on_off('DX_ENABLE_FLASH_SALE')}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💎 兑换阈值: {env.get('DX_MIN_BEANS_TO_EXCHANGE', '100')} 金豆\n"
            f"⏰ 秒杀时间: {env.get('DX_FLASH_SALE_TIME', '10:00:00')}\n"
            f"🖥️  无头模式: {_on_off('DX_HEADLESS')}\n"
        )

    def _cmd_setup(self, sender_id, group_id=None):
        """提交环境变量到青龙面板"""
        env = self._read_env()
        if not env.get("DX_PHONE") or not env.get("DX_PASSWORD"):
            return "⚠️ 请先执行 /dx login 设置账号密码"

        # 获取青龙配置
        ql_url = env.get("QL_URL", "")
        ql_cid = env.get("QL_CLIENT_ID", "")
        ql_cs = env.get("QL_CLIENT_SECRET", "")

        if not ql_url or not ql_cid or not ql_cs:
            return (
                "⚠️ 青龙面板未配置，请先设置:\n"
                "QL_URL=http://你的青龙IP:5700\n"
                "QL_CLIENT_ID=你的ClientID\n"
                "QL_CLIENT_SECRET=你的ClientSecret\n\n"
                "可使用 /dx set QL_URL http://xxx:5700 设置"
            )

        try:
            # 初始化青龙 API
            ql.base_url = ql_url.rstrip("/")
            ql.client_id = ql_cid
            ql.client_secret = ql_cs
            ql.token = None

            success = 0
            fail = 0
            msgs = []

            for key, desc in DX_ENV_VARS:
                val = env.get(key, "")
                if not val:
                    continue
                try:
                    # 检查是否已存在
                    existing = ql.list_envs(search_value=key)
                    found = [e for e in existing if e.get("name") == key]
                    if found:
                        eid = found[0].get("id") or found[0].get("_id")
                        ql.update_env(eid, key, val, f"DX-Telecom: {desc}")
                    else:
                        ql.create_env(key, val, f"DX-Telecom: {desc}")
                    success += 1
                except Exception as e:
                    fail += 1
                    msgs.append(f"  ❌ {key}: {e}")

            result = f"📤 青龙面板配置提交\n━━━━━━━━━━━━━━━━━━━━\n✅ 成功: {success} 个\n"
            if fail:
                result += f"❌ 失败: {fail} 个\n"
                result += "\n".join(msgs)
            result += "\n━━━━━━━━━━━━━━━━━━━━\n请在青龙面板中创建定时任务:\n任务名: DX-Telecom\n命令: task QL-DX/main.py\n定时: 0 8,12,18 * * *"

            return result

        except Exception as e:
            return f"❌ 提交青龙面板失败: {e}"

    def _cmd_signin(self, sender_id, group_id=None):
        """手动触发签到"""
        return self._run_script("签到", ["--signin-only"])

    def _cmd_exchange(self, sender_id, group_id=None):
        """手动触发兑换"""
        return self._run_script("金豆兑换", ["--exchange-only"])

    def _cmd_run(self, sender_id, group_id=None):
        """执行全部任务"""
        return self._run_script("全部任务", [])

    def _cmd_config(self, sender_id, group_id=None):
        """查看所有配置"""
        env = self._read_env()
        lines = ["📋 当前完整配置", "━━━━━━━━━━━━━━━━━━━━"]
        for key, desc in DX_ENV_VARS:
            val = env.get(key, "")
            if key in ("DX_PASSWORD",):
                val = "***" if val else "未设置"
            elif not val:
                val = "(未设置)"
            lines.append(f"{key} = {val}")
        return "\n".join(lines)

    def _cmd_set(self, arg, sender_id, group_id=None):
        """设置单个配置项"""
        parts = arg.split(maxsplit=1)
        if len(parts) < 2:
            return "用法: /dx set KEY VALUE\n例如: /dx set DX_FLASH_SALE_TIME 14:00:00"

        key, val = parts[0].strip().upper(), parts[1].strip()

        # 验证 key 是否合法
        valid_keys = {k for k, _ in DX_ENV_VARS}
        valid_keys.update({"QL_URL", "QL_CLIENT_ID", "QL_CLIENT_SECRET"})
        if key not in valid_keys:
            return f"❌ 未知配置项: {key}\n可用: {', '.join(sorted(valid_keys))}"

        env = self._read_env()
        env[key] = val
        self._write_env(env)

        display_val = "***" if "PASSWORD" in key else val
        return f"✅ {key} = {display_val}"

    def _cmd_toggle(self, arg, enable: bool, sender_id, group_id=None):
        """开关功能"""
        toggle_map = {
            "signin":   "DX_ENABLE_SIGNIN",
            "exchange": "DX_ENABLE_EXCHANGE",
            "activity": "DX_ENABLE_ACTIVITY",
            "flash":    "DX_ENABLE_FLASH_SALE",
        }
        key = toggle_map.get(arg.lower().strip())
        if not key:
            return f"❌ 未知功能: {arg}\n可用: {', '.join(toggle_map.keys())}"

        env = self._read_env()
        env[key] = "true" if enable else "false"
        self._write_env(env)

        status = "开启 ✅" if enable else "关闭 ❌"
        return f"{status} {arg}"

    # ---------- 脚本执行 ----------
    def _run_script(self, task_name: str, extra_args: list) -> str:
        """调用 telecom_api.py 执行任务（异步）"""
        env = self._read_env()
        if not env.get("DX_PHONE") or not env.get("DX_PASSWORD"):
            return "⚠️ 请先执行 /dx login 设置账号密码"

        script_dir = self.project_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script_path = os.path.join(script_dir, "main.py")

        if not os.path.exists(script_path):
            return f"❌ 脚本未找到: {script_path}"

        try:
            # 使用 subprocess 异步执行
            env_copy = os.environ.copy()
            env_copy.update(env)

            cmd = [sys.executable, script_path] + extra_args
            proc = subprocess.Popen(
                cmd,
                cwd=script_dir,
                env=env_copy,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # 非阻塞，返回提示
            return (
                f"🚀 {task_name}任务已提交执行\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"进程 PID: {proc.pid}\n"
                f"请稍后查看青龙面板日志获取结果\n"
                f"或发送 /dx status 查看配置"
            )

        except Exception as e:
            return f"❌ 执行失败: {e}"


# ==================== 会话处理器注册 ====================
def register_session_handlers(handlers: dict):
    """
    由 QL-Bot 的 project_loader 自动调用，
    注册 DX 插件的多轮会话处理器。
    """
    plugin = DXPlugin()

    def dx_login_handler(sender_id, group_id, text):
        return plugin._login_session(sender_id, group_id, text)

    handlers["dx_login"] = dx_login_handler
    Log.ok("DX-Telecom 会话处理器已注册")