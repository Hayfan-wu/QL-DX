# -*- coding: utf-8 -*-
"""
中国电信话费自动化 - QQ机器人插件
==================================
QL-Bot 业务项目插件，提供完整的 QQ 交互逻辑。
支持多轮会话引导配置、一键提交青龙面板、手动触发任务、产物查询。

命令列表:
  电信菜单                    - 帮助菜单（含活动产物+命令功能）
  电信登录                    - 多轮引导设置账号密码，完成后自动提交青龙
  电信状态                    - 查看配置状态
  电信查询                    - 查询所有历史任务产物
  电信签到                    - 手动触发签到
  电信执行                    - 执行全部任务
  电信配置                    - 查看当前所有配置
  电信开启 签到/活动/秒杀      - 开启功能
  电信关闭 签到/活动/秒杀      - 关闭功能
  签到 / 话费 / 金豆          - 快捷命令
"""

import os
import re
import subprocess
import sys

from bot.plugins.base import Plugin
from bot.utils import Log
from bot.ql_api import ql
from bot.session import sessions
from telecom_api import query_results

# ==================== 环境变量定义 ====================
DX_ENV_VARS = [
    ("DX_ACCOUNT",                 "电信账号（格式: 手机号#密码）"),
    ("DX_ENABLE_SIGNIN",           "启用签到 (true/false)"),
    ("DX_ENABLE_ACTIVITY",         "启用活动扫描 (true/false)"),
    ("DX_ENABLE_FLASH_SALE",       "启用秒杀 (true/false)"),
    ("DX_FLASH_SALE_TIME",         "秒杀时间 (HH:MM:SS)"),
    ("DX_HEADLESS",                "无头模式 (true/false)"),
    ("DX_TIMEOUT",                 "超时秒数"),
]

# ==================== 菜单文本 ====================
MENU_TEXT = """📱 中国电信话费自动化

━━━━━━━━━━━━━━━━━━━━
📋 活动清单（产物）
━━━━━━━━━━━━━━━━━━━━
① 签到翻牌 → 话费(0.1~100元)、金豆(20~1500)、流量包
② 口令兑换 → 话费(0.66~100元)
③ APP签到  → 金豆(20~35个/天)
④ 金豆秒杀 → 0.5元(10点)/1元(14点)话费
━━━━━━━━━━━━━━━━━━━━
🔧 命令功能
━━━━━━━━━━━━━━━━━━━━
🔑 电信登录    - 多轮引导设置账号密码，完成后自动提交青龙
📊 电信状态    - 查看当前配置和开关状态
📋 电信查询    - 查询所有历史任务获得的产物
🎯 电信签到    - 手动触发签到翻牌任务
🚀 电信执行    - 执行全部自动化任务
🔧 电信配置    - 查看所有环境变量详情
✅ 电信开启 XX - 开启指定功能
❌ 电信关闭 XX - 关闭指定功能
━━━━━━━━━━━━━━━━━━━━
可开关: 签到 | 活动 | 秒杀
快捷: 签到 / 话费 / 金豆

项目: github.com/Hayfan-wu/QL-DX"""


# ==================== 插件类 ====================
class DXPlugin(Plugin):
    name = "DX-Telecom"
    commands = [
        "电信",
        "话费",
        "金豆",
        "签到",
    ]

    def __init__(self):
        super().__init__()
        self.project_dir = None
        self._env_path = None

    # ---------- 命令匹配 ----------
    def match(self, text):
        text = text.strip()
        return any(text.startswith(cmd) for cmd in self.commands)

    # ---------- 消息处理 ----------
    def handle(self, text, sender_id, group_id=None):
        text = text.strip()

        if text == "签到":
            return self._cmd_signin(sender_id, group_id)
        if text in ("话费", "金豆"):
            return self._cmd_status(sender_id, group_id)

        if not text.startswith("电信"):
            return MENU_TEXT

        rest = text[2:].strip()
        if not rest:
            return MENU_TEXT

        parts = rest.split(maxsplit=1)
        sub_cmd = parts[0] if parts else ""
        arg = parts[1] if len(parts) > 1 else ""

        if sub_cmd in ("菜单", "帮助", "help"):
            return MENU_TEXT

        if sub_cmd == "登录":
            return self._cmd_login(sender_id, group_id)

        if sub_cmd == "状态":
            return self._cmd_status(sender_id, group_id)

        if sub_cmd == "查询":
            return self._cmd_query(sender_id, group_id)

        if sub_cmd == "签到":
            return self._cmd_signin(sender_id, group_id)

        if sub_cmd == "执行":
            return self._cmd_run(sender_id, group_id)

        if sub_cmd == "配置":
            return self._cmd_config(sender_id, group_id)

        if sub_cmd == "开启":
            return self._cmd_toggle(arg, True, sender_id, group_id)

        if sub_cmd == "关闭":
            return self._cmd_toggle(arg, False, sender_id, group_id)

        return MENU_TEXT

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
        env = {}
        p = self._get_env_path()
        if not os.path.exists(p):
            self._init_env(p)
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        env[k.strip()] = v.strip().strip("\"'")
        return env

    def _init_env(self, path: str):
        """首次使用：从 .env.example 复制默认配置"""
        example_path = os.path.join(os.path.dirname(path), ".env.example")
        if os.path.exists(example_path):
            import shutil
            shutil.copy(example_path, path)
            Log.ok(f"已从 .env.example 初始化配置文件: {path}")
        else:
            self._write_env({})
            Log.ok(f"已创建默认配置文件: {path}")

    def _write_env(self, env: dict):
        p = self._get_env_path()
        lines = [
            "# 中国电信话费自动化 - 环境变量",
            "# 由 QQ 机器人自动生成",
            "",
        ]
        for key, desc in DX_ENV_VARS:
            val = env.get(key, "")
            lines.append(f"# {desc}")
            lines.append(f"{key}={val}")
            lines.append("")
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        Log.ok(f".env 已更新: {p}")

    def _parse_account(self, env: dict):
        """解析 DX_ACCOUNT 为 (phone, password)"""
        raw = env.get("DX_ACCOUNT", "")
        if raw and "#" in raw:
            return raw.split("#", 1)
        return ("", "")

    # ---------- 命令实现 ----------

    def _cmd_login(self, sender_id, group_id=None):
        """引导设置账号密码 - 多轮会话"""
        sessions.set(sender_id, group_id, "dx_login", {})
        return "🔑 请输入你的中国电信手机号（11位数字）："

    def _login_session(self, sender_id, group_id, text, session):
        """登录会话处理 - 完成后自动提交青龙"""
        text = text.strip()

        # 第1步：输入手机号
        if re.match(r"^1[3-9]\d{9}$", text):
            session["data"]["phone"] = text
            return "📱 手机号已记录，请输入登录密码："

        # 第2步：输入密码 → 保存并自动提交青龙
        phone = session.get("data", {}).get("phone")
        if phone:
            pwd = text
            account = f"{phone}#{pwd}"

            env = self._read_env()
            env["DX_ACCOUNT"] = account
            self._write_env(env)

            sessions.clear(sender_id, group_id)

            # 自动提交到青龙面板
            submit_result = self._auto_submit(env)

            return (
                f"✅ 账号密码已保存！\n"
                f"📱 手机号: {phone[:3]}****{phone[-4:]}\n"
                f"🔐 密码: {'*' * len(pwd)}\n\n"
                f"{submit_result}"
            )

        return "⚠️ 请先输入正确的手机号（11位数字）"

    def _auto_submit(self, env: dict) -> str:
        """登录完成后自动提交环境变量到青龙面板"""
        ql_url = env.get("QL_URL", "")
        ql_cid = env.get("QL_CLIENT_ID", "")
        ql_cs = env.get("QL_CLIENT_SECRET", "")

        if not ql_url or not ql_cid or not ql_cs:
            return "⚠️ 青龙面板未配置，请在青龙面板中手动设置 QL_URL / QL_CLIENT_ID / QL_CLIENT_SECRET"

        try:
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

            result = (
                f"📤 已自动提交到青龙面板\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ 成功: {success} 个\n"
            )
            if fail:
                result += f"❌ 失败: {fail} 个\n"
                result += "\n".join(msgs)
            result += (
                "\n━━━━━━━━━━━━━━━━━━━━\n"
                "请在青龙面板中创建定时任务:\n"
                "任务名: DX-Telecom\n"
                "命令: task QL-DX/main.py\n"
                "定时: 0 8,12,18 * * *"
            )
            return result

        except Exception as e:
            return f"⚠️ 自动提交青龙失败: {e}\n请稍后手动在青龙面板中配置环境变量"

    def _cmd_status(self, sender_id, group_id=None):
        """查看运行状态"""
        env = self._read_env()
        phone, pwd = self._parse_account(env)

        if phone and len(phone) >= 11:
            phone_display = f"{phone[:3]}****{phone[-4:]}"
        else:
            phone_display = "未设置"

        pwd_set = "已设置" if pwd else "未设置"

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
            f"活动: {_on_off('DX_ENABLE_ACTIVITY')}\n"
            f"秒杀: {_on_off('DX_ENABLE_FLASH_SALE')}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ 秒杀时间: {env.get('DX_FLASH_SALE_TIME', '10:00:00')}\n"
            f"🖥️  无头模式: {_on_off('DX_HEADLESS')}\n"
        )

    def _cmd_query(self, sender_id, group_id=None):
        """查询所有历史任务产物"""
        return query_results()

    def _cmd_signin(self, sender_id, group_id=None):
        return self._run_script("签到", ["--signin-only"])

    def _cmd_run(self, sender_id, group_id=None):
        return self._run_script("全部任务", [])

    def _cmd_config(self, sender_id, group_id=None):
        env = self._read_env()
        lines = ["📋 当前完整配置", "━━━━━━━━━━━━━━━━━━━━"]
        for key, desc in DX_ENV_VARS:
            val = env.get(key, "")
            if key == "DX_ACCOUNT":
                val = "***" if val else "未设置"
            elif not val:
                val = "(未设置)"
            lines.append(f"{key} = {val}")
        return "\n".join(lines)

    def _cmd_toggle(self, arg, enable: bool, sender_id, group_id=None):
        """开关功能（中文参数）"""
        toggle_map = {
            "签到": "DX_ENABLE_SIGNIN",
            "活动": "DX_ENABLE_ACTIVITY",
            "秒杀": "DX_ENABLE_FLASH_SALE",
            "signin":   "DX_ENABLE_SIGNIN",
            "activity": "DX_ENABLE_ACTIVITY",
            "flash":    "DX_ENABLE_FLASH_SALE",
        }
        key = toggle_map.get(arg.strip())
        if not key:
            return f"❌ 未知功能: {arg}\n可用: 签到 | 活动 | 秒杀"

        env = self._read_env()
        env[key] = "true" if enable else "false"
        self._write_env(env)

        status = "开启 ✅" if enable else "关闭 ❌"
        return f"{status} {arg}"

    # ---------- 脚本执行 ----------
    def _run_script(self, task_name: str, extra_args: list) -> str:
        env = self._read_env()
        phone, pwd = self._parse_account(env)
        if not phone or not pwd:
            return "⚠️ 请先执行 电信登录 设置账号密码"

        script_dir = self.project_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script_path = os.path.join(script_dir, "main.py")

        if not os.path.exists(script_path):
            return f"❌ 脚本未找到: {script_path}"

        try:
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

            return (
                f"🚀 {task_name}任务已提交执行\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"进程 PID: {proc.pid}\n"
                f"请稍后查看青龙面板日志获取结果\n"
                f"或发送 电信状态 查看配置"
            )

        except Exception as e:
            return f"❌ 执行失败: {e}"


# ==================== 会话处理器注册 ====================
def register_session_handlers(handlers: dict):
    plugin = DXPlugin()

    def dx_login_handler(text, sender_id, group_id, session):
        return plugin._login_session(sender_id, group_id, text, session)

    handlers["dx_login"] = dx_login_handler
    Log.ok("DX-Telecom 会话处理器已注册")