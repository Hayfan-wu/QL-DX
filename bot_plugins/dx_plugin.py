# -*- coding: utf-8 -*-
"""
中国电信话费自动化 - QQ机器人插件
==================================
QL-Bot 业务项目插件，提供完整的 QQ 交互逻辑。
支持多轮会话引导配置、一键提交青龙面板、手动触发任务。

命令列表:
  电信菜单                    - 帮助菜单（含活动产物+命令功能）
  电信登录                    - 多轮引导设置账号密码
  电信状态                    - 查看配置状态
  电信提交                    - 提交环境变量到青龙面板
  电信签到                    - 手动触发签到
  电信兑换                    - 手动触发金豆兑换
  电信执行                    - 执行全部任务
  电信配置                    - 查看当前所有配置
  电信开启 签到/兑换/活动/秒杀  - 开启功能
  电信关闭 签到/兑换/活动/秒杀  - 关闭功能
  签到 / 话费 / 金豆          - 快捷命令
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
    ("DX_PHONE",                   "电信手机号"),
    ("DX_PASSWORD",                "登录密码"),
    ("DX_ENABLE_SIGNIN",           "启用签到 (true/false)"),
    ("DX_ENABLE_EXCHANGE",         "启用兑换 (true/false)"),
    ("DX_ENABLE_ACTIVITY",         "启用活动扫描 (true/false)"),
    ("DX_ENABLE_FLASH_SALE",       "启用秒杀 (true/false)"),
    ("DX_MIN_BEANS_TO_EXCHANGE",   "兑换阈值金豆数"),
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
② 金豆抽奖 → 话费、金豆、优惠券
③ 见面礼   → 200金豆、翼回收20元券
④ 积分商城 → 话费、流量包、实物礼品
⑤ 口令兑换 → 话费(0.66~100元)
⑥ APP签到  → 金豆(20~35个/天)
⑦ 金豆秒杀 → 0.5元(10点)/1元(14点)话费
━━━━━━━━━━━━━━━━━━━━
🔧 命令功能
━━━━━━━━━━━━━━━━━━━━
🔑 电信登录    - 多轮引导设置账号密码
📊 电信状态    - 查看当前配置和开关状态
⚙️  电信提交    - 将.env配置一键提交到青龙面板
🎯 电信签到    - 手动触发签到翻牌任务
💎 电信兑换    - 手动触发金豆兑换话费
🚀 电信执行    - 执行全部自动化任务
🔧 电信配置    - 查看所有环境变量详情
✅ 电信开启 XX - 开启指定功能
❌ 电信关闭 XX - 关闭指定功能
━━━━━━━━━━━━━━━━━━━━
可开关: 签到 | 兑换 | 活动 | 秒杀
快捷: 签到 / 话费 / 金豆

项目: github.com/Hayfan-wu/QL-DX"""


# ==================== 插件类 ====================
class DXPlugin(Plugin):
    name = "DX-Telecom"
    commands = [
        r"^电信",
        r"^话费",
        r"^签到",
        r"^金豆",
    ]

    def __init__(self):
        super().__init__()
        self.project_dir = None
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

        # 快捷命令（非"电信"开头）
        if text == "签到":
            return self._cmd_signin(sender_id, group_id)
        if text in ("话费", "金豆"):
            return self._cmd_status(sender_id, group_id)

        # 解析"电信"子命令
        if not text.startswith("电信"):
            return MENU_TEXT

        rest = text[2:].strip()
        if not rest:
            return MENU_TEXT

        parts = rest.split(maxsplit=1)
        sub_cmd = parts[0] if parts else ""
        arg = parts[1] if len(parts) > 1 else ""

        # 子命令路由表
        if sub_cmd in ("菜单", "帮助", "help"):
            return MENU_TEXT

        if sub_cmd == "登录":
            return self._cmd_login(sender_id, group_id)

        if sub_cmd == "状态":
            return self._cmd_status(sender_id, group_id)

        if sub_cmd == "提交":
            return self._cmd_setup(sender_id, group_id)

        if sub_cmd == "签到":
            return self._cmd_signin(sender_id, group_id)

        if sub_cmd == "兑换":
            return self._cmd_exchange(sender_id, group_id)

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
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        env[k.strip()] = v.strip().strip("\"'")
        return env

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

    # ---------- 命令实现 ----------

    def _cmd_login(self, sender_id, group_id=None):
        """引导设置账号密码 - 多轮会话"""
        SessionManager.register(sender_id, "dx_login", self._login_session)
        return "🔑 请输入你的中国电信手机号（11位数字）："

    def _login_session(self, sender_id, group_id, text):
        """登录会话处理"""
        text = text.strip()

        if re.match(r"^1[3-9]\d{9}$", text):
            SessionManager.set_data(sender_id, "dx_phone", text)
            return "📱 手机号已记录，请输入登录密码："

        if SessionManager.get_data(sender_id, "dx_phone"):
            phone = SessionManager.get_data(sender_id, "dx_phone")
            pwd = text
            env = self._read_env()
            env["DX_PHONE"] = phone
            env["DX_PASSWORD"] = pwd
            self._write_env(env)

            SessionManager.clear(sender_id)
            return (
                f"✅ 账号密码已保存！\n"
                f"📱 手机号: {phone[:3]}****{phone[-4:]}\n"
                f"🔐 密码: {'*' * len(pwd)}\n\n"
                f"下一步请发送 电信提交 提交到青龙面板"
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
            return "⚠️ 请先执行 电信登录 设置账号密码"

        ql_url = env.get("QL_URL", "")
        ql_cid = env.get("QL_CLIENT_ID", "")
        ql_cs = env.get("QL_CLIENT_SECRET", "")

        if not ql_url or not ql_cid or not ql_cs:
            return (
                "⚠️ 青龙面板未配置，请先在青龙面板中设置以下环境变量:\n"
                "QL_URL=http://你的青龙IP:5700\n"
                "QL_CLIENT_ID=你的ClientID\n"
                "QL_CLIENT_SECRET=你的ClientSecret"
            )

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
                f"📤 青龙面板配置提交\n"
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
            return f"❌ 提交青龙面板失败: {e}"

    def _cmd_signin(self, sender_id, group_id=None):
        return self._run_script("签到", ["--signin-only"])

    def _cmd_exchange(self, sender_id, group_id=None):
        return self._run_script("金豆兑换", ["--exchange-only"])

    def _cmd_run(self, sender_id, group_id=None):
        return self._run_script("全部任务", [])

    def _cmd_config(self, sender_id, group_id=None):
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

    def _cmd_toggle(self, arg, enable: bool, sender_id, group_id=None):
        """开关功能（中文参数）"""
        toggle_map = {
            "签到": "DX_ENABLE_SIGNIN",
            "兑换": "DX_ENABLE_EXCHANGE",
            "活动": "DX_ENABLE_ACTIVITY",
            "秒杀": "DX_ENABLE_FLASH_SALE",
            # 兼容英文
            "signin":   "DX_ENABLE_SIGNIN",
            "exchange": "DX_ENABLE_EXCHANGE",
            "activity": "DX_ENABLE_ACTIVITY",
            "flash":    "DX_ENABLE_FLASH_SALE",
        }
        key = toggle_map.get(arg.strip())
        if not key:
            return f"❌ 未知功能: {arg}\n可用: 签到 | 兑换 | 活动 | 秒杀"

        env = self._read_env()
        env[key] = "true" if enable else "false"
        self._write_env(env)

        status = "开启 ✅" if enable else "关闭 ❌"
        return f"{status} {arg}"

    # ---------- 脚本执行 ----------
    def _run_script(self, task_name: str, extra_args: list) -> str:
        env = self._read_env()
        if not env.get("DX_PHONE") or not env.get("DX_PASSWORD"):
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
    """
    由 QL-Bot 的 project_loader 自动调用，
    注册 DX 插件的多轮会话处理器。
    """
    plugin = DXPlugin()

    def dx_login_handler(sender_id, group_id, text):
        return plugin._login_session(sender_id, group_id, text)

    handlers["dx_login"] = dx_login_handler
    Log.ok("DX-Telecom 会话处理器已注册")