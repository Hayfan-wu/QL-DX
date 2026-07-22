# -*- coding: utf-8 -*-
"""
中国电信话费自动化 - QQ机器人插件
==================================
QL-Bot 业务项目插件，提供 QQ 交互逻辑。

命令列表:
  电信菜单          - 帮助菜单
  电信登录          - 设置账号密码+AndroidID，自动提交青龙
  电信状态          - 查看配置状态
  电信查询          - 查看最近一次执行结果
  电信执行          - 执行全部自动化任务
  电信开启/关闭 XX  - 开关功能
  签到 / 话费 / 金豆 - 快捷命令
"""

import os
import re
import subprocess
import sys
import threading

from bot.plugins.base import Plugin
from bot.utils import Log
from bot.ql_api import ql
from bot.session import sessions

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _import_dx():
    sys.path.insert(0, _PROJECT_DIR)
    import dx_auto
    return dx_auto


DX_ENV_VARS = [
    ("dxlin", "电信账号（格式: 手机号#密码#AndroidID）"),
    ("chinaTelecomAccount", "电信账号（兼容格式: 手机号#密码）"),
    ("DX_ANDROID_ID", "AndroidID"),
    ("DX_ENABLE_SIGNIN", "启用签到 (true/false)"),
    ("DX_ENABLE_ACTIVITY", "启用活动扫描 (true/false)"),
    ("DX_ENABLE_LOTTERY", "启用抽奖 (true/false)"),
    ("DX_ENABLE_EXCHANGE", "启用宠物等级权益兑换话费券 (true/false)"),
    ("DX_ENABLE_FLASH_SALE", "启用话费券秒杀 (true/false)"),
    ("DX_FLASH_SALE_TIME", "秒杀时间 (HH:MM:SS)"),
]

MENU_TEXT = """📱 中国电信话费自动化

🎯 快捷: 签到 | 话费 | 金豆

🔑 电信登录  - 设置账号密码+AndroidID
📊 电信状态  - 查看配置和开关
📋 电信查询  - 查看最近一次结果
🚀 电信执行  - 执行全部任务
✅ 电信开启 XX
❌ 电信关闭 XX

可开关: 签到 | 活动 | 抽奖 | 兑换 | 秒杀

AndroidID: https://commissions-yields-exception-personally.trycloudflare.com/"""


class DXPlugin(Plugin):
    name = "DX-Telecom"
    commands = ["电信", "话费", "金豆", "签到"]

    def __init__(self):
        super().__init__()
        self.project_dir = _PROJECT_DIR
        self._env_path = None

    def match(self, text):
        return any(text.strip().startswith(cmd) for cmd in self.commands)

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
        sub = parts[0]
        arg = parts[1] if len(parts) > 1 else ""

        if sub in ("菜单", "帮助", "help"):
            return MENU_TEXT
        if sub == "登录":
            return self._cmd_login(sender_id, group_id)
        if sub == "状态":
            return self._cmd_status(sender_id, group_id)
        if sub == "查询":
            return self._cmd_query(sender_id, group_id)
        if sub == "执行":
            return self._cmd_run(sender_id, group_id)
        if sub == "开启":
            return self._cmd_toggle(arg, True, sender_id, group_id)
        if sub == "关闭":
            return self._cmd_toggle(arg, False, sender_id, group_id)

        return MENU_TEXT

    # ---------- 环境文件 ----------
    def _get_env_path(self):
        if self._env_path:
            return self._env_path
        self._env_path = os.path.join(self.project_dir, ".env")
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
        example = os.path.join(os.path.dirname(path), ".env.example")
        if os.path.exists(example):
            import shutil
            shutil.copy(example, path)
        else:
            self._write_env({})

    def _write_env(self, env: dict):
        p = self._get_env_path()
        lines = ["# 中国电信话费自动化", ""]
        for key, desc in DX_ENV_VARS:
            val = env.get(key, "")
            lines.append(f"# {desc}")
            lines.append(f"{key}={val}")
            lines.append("")
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def _parse_account(self, env: dict) -> tuple:
        raw = env.get("dxlin", "")
        if raw and "#" in raw:
            parts = raw.split("#")
            if len(parts) >= 3:
                return parts[0].strip(), parts[1].strip(), parts[2].strip()
            elif len(parts) == 2:
                return parts[0].strip(), parts[1].strip(), ""
        old = env.get("chinaTelecomAccount") or env.get("DX_ACCOUNT", "")
        if old and "#" in old:
            p = old.split("#", 1)
            return p[0].strip(), p[1].strip(), env.get("DX_ANDROID_ID", "")
        return ("", "", "")

    # ---------- 命令实现 ----------

    def _cmd_login(self, sender_id, group_id=None):
        sessions.set(sender_id, group_id, "dx_login", {})
        return ("🔑 请输入手机号（11位）：\n"
                "💡 AndroidID 获取: https://commissions-yields-exception-personally.trycloudflare.com/")

    def _login_session(self, sender_id, group_id, text, session):
        text = text.strip()
        data = session.get("data", {})

        if "phone" not in data and re.match(r"^1[3-9]\d{9}$", text):
            data["phone"] = text
            session["data"] = data
            return "📱 请输入登录密码："

        if "phone" in data and "password" not in data:
            data["password"] = text
            session["data"] = data
            return "📱 请输入 AndroidID："

        if "password" in data and "android_id" not in data:
            data["android_id"] = text
            phone, pwd, aid = data["phone"], data["password"], data["android_id"]
            account = f"{phone}#{pwd}#{aid}"

            env = self._read_env()
            env["dxlin"] = account
            self._write_env(env)
            sessions.clear(sender_id, group_id)

            submit = self._auto_submit(env)
            return (
                f"✅ 已保存！\n"
                f"📱 {phone[:3]}****{phone[-4:]}\n"
                f"🔐 {'*' * len(pwd)}\n"
                f"📱 {aid[:4]}****{aid[-4:]}\n\n"
                f"{submit}"
            )

        return "⚠️ 请先输入正确的手机号"

    def _auto_submit(self, env: dict) -> str:
        ql_url = env.get("QL_URL", "")
        ql_cid = env.get("QL_CLIENT_ID", "")
        ql_cs = env.get("QL_CLIENT_SECRET", "")

        if not ql_url or not ql_cid or not ql_cs:
            return "⚠️ 青龙未配置，请手动设置 QL_URL / QL_CLIENT_ID / QL_CLIENT_SECRET"

        try:
            ql.base_url = ql_url.rstrip("/")
            ql.client_id = ql_cid
            ql.client_secret = ql_cs
            ql.token = None

            ok = 0
            fail = 0
            for key, desc in DX_ENV_VARS:
                val = env.get(key, "")
                if not val:
                    continue
                try:
                    existing = ql.list_envs(search_value=key)
                    found = [e for e in existing if e.get("name") == key]
                    if found:
                        eid = found[0].get("id") or found[0].get("_id")
                        ql.update_env(eid, key, val, f"DX: {desc}")
                    else:
                        ql.create_env(key, val, f"DX: {desc}")
                    ok += 1
                except Exception:
                    fail += 1

            result = f"📤 青龙提交: ✅{ok}"
            if fail:
                result += f" ❌{fail}"
            result += (
                "\n定时任务:\n"
                "  任务名: DX-Telecom\n"
                "  命令: task dx_auto.py\n"
                "  定时: 0 8,12,18 * * *"
            )
            return result
        except Exception as e:
            return f"⚠️ 青龙提交失败: {e}"

    def _cmd_status(self, sender_id, group_id=None):
        env = self._read_env()
        phone, pwd, aid = self._parse_account(env)

        phone_d = f"{phone[:3]}****{phone[-4:]}" if phone else "未设置"
        pwd_s = "已设置" if pwd else "未设置"
        aid_s = "已设置" if aid else "未设置"

        def on(key):
            return "✅" if env.get(key, "true").lower() in ("true", "1", "yes", "on") else "❌"

        return (
            f"📊 状态\n"
            f"📱 {phone_d} | 🔐{pwd_s} | 📱{aid_s}\n"
            f"签到{on('DX_ENABLE_SIGNIN')} 活动{on('DX_ENABLE_ACTIVITY')} "
            f"抽奖{on('DX_ENABLE_LOTTERY')} 兑换{on('DX_ENABLE_EXCHANGE')} "
            f"秒杀{on('DX_ENABLE_FLASH_SALE')}\n"
            f"⏰ {env.get('DX_FLASH_SALE_TIME', '10:00:00')}"
        )

    def _cmd_query(self, sender_id, group_id=None):
        try:
            dx = _import_dx()
            return dx.query_results()
        except Exception as e:
            return f"❌ 查询失败: {e}"

    def _cmd_signin(self, sender_id, group_id=None):
        return self._run_script("签到", signin_only=True)

    def _cmd_run(self, sender_id, group_id=None):
        return self._run_script("全部任务", signin_only=False)

    def _cmd_toggle(self, arg, enable: bool, sender_id, group_id=None):
        toggle_map = {
            "签到": "DX_ENABLE_SIGNIN", "活动": "DX_ENABLE_ACTIVITY",
            "抽奖": "DX_ENABLE_LOTTERY", "兑换": "DX_ENABLE_EXCHANGE",
            "秒杀": "DX_ENABLE_FLASH_SALE",
            "signin": "DX_ENABLE_SIGNIN", "activity": "DX_ENABLE_ACTIVITY",
            "lottery": "DX_ENABLE_LOTTERY", "exchange": "DX_ENABLE_EXCHANGE",
            "flash": "DX_ENABLE_FLASH_SALE",
        }
        key = toggle_map.get(arg.strip())
        if not key:
            return f"❌ 未知: {arg}\n可用: 签到|活动|抽奖|兑换|秒杀"

        env = self._read_env()
        env[key] = "true" if enable else "false"
        self._write_env(env)
        return f"{'开启✅' if enable else '关闭❌'} {arg}"

    def _run_script(self, task_name: str, signin_only: bool = False) -> str:
        env = self._read_env()
        phone, pwd, aid = self._parse_account(env)
        if not phone or not pwd:
            return "⚠️ 请先执行 电信登录"
        if not aid:
            return "⚠️ 缺少 AndroidID，请重新执行 电信登录"

        script = os.path.join(self.project_dir, "dx_auto.py")
        if not os.path.exists(script):
            return f"❌ 脚本未找到"

        args = [sys.executable, script]
        if signin_only:
            args.append("--signin-only")

        def _bg():
            try:
                ec = os.environ.copy()
                ec.update(env)
                proc = subprocess.run(args, cwd=self.project_dir, env=ec,
                                      capture_output=True, text=True, timeout=300)
                Log.ok(f"DX {task_name} 完成")
            except Exception as e:
                Log.error(f"DX {task_name} 异常: {e}")

        threading.Thread(target=_bg, daemon=True).start()
        return f"🚀 {task_name}已提交，完成后发送 电信查询 查看结果"


def register_session_handlers(handlers: dict):
    handlers["dx_login"] = lambda text, sid, gid, sess: DXPlugin()._login_session(sid, gid, text, sess)
    Log.ok("DX-Telecom 已注册")
