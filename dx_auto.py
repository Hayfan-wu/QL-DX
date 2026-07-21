"""
中国电信话费自动化 - 主入口脚本 (青龙面板版)
================================================
基于模块化架构，分离登录、瑞数反爬、业务API。

架构:
- core/login.py    - 登录模块（服务密码登录、ticket获取）
- core/ruishu.py   - 瑞数反爬模块（独立封装，优雅降级）
- core/api.py      - 业务API模块（签到、任务、宠物乐园等）
- dx_auto.py       - 入口脚本（组装各模块，执行主流程）

核心特性:
- 登录与瑞数反爬完全解耦
- 瑞数反爬优雅降级：连续失败3次自动标记不可用
- Token 缓存避免重复登录（24小时有效）

青龙定时任务:
  命令: task dx_auto.py
  定时: 0 8,12,18 * * *

依赖安装:
  pip install httpx PyExecJS pycryptodome --break-system-packages
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

# ==================== .env 自动加载 ====================
_PROJECT_DIR = Path(__file__).resolve().parent
_ENV_FILE = _PROJECT_DIR / ".env"
if _ENV_FILE.exists():
    with open(str(_ENV_FILE), "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                if _key.strip() not in os.environ:
                    os.environ.setdefault(_key.strip(), _val.strip().strip("\"'"))

# ==================== 配置 ====================

PROJECT_DIR = Path(__file__).resolve().parent

# 账号配置
_ACCOUNT_RAW = os.environ.get("chinaTelecomAccount") or os.environ.get("DX_ACCOUNT", "")
if _ACCOUNT_RAW and "#" in _ACCOUNT_RAW:
    PHONE, PASSWORD = _ACCOUNT_RAW.split("#", 1)
else:
    PHONE = ""
    PASSWORD = ""

# 功能开关
ENABLE_SIGNIN = os.environ.get("DX_ENABLE_SIGNIN", "true").lower() in ("true", "1", "yes", "on")
ENABLE_ACTIVITY = os.environ.get("DX_ENABLE_ACTIVITY", "true").lower() in ("true", "1", "yes", "on")
ENABLE_FLASH_SALE = os.environ.get("DX_ENABLE_FLASH_SALE", "false").lower() in ("true", "1", "yes", "on")
FLASH_SALE_TIME = os.environ.get("DX_FLASH_SALE_TIME", "10:00:00")

# 文件路径
RESULT_FILE = PROJECT_DIR / "result.json"
LOG_FILE = PROJECT_DIR / "dx_telecom.log"
SCREENSHOT_DIR = PROJECT_DIR / "screenshots"

# User-Agent
UA = (
    "Mozilla/5.0 (Linux; U; Android 12; zh-cn; ONEPLUS A9000 "
    "Build/QKQ1.190716.003) AppleWebKit/533.1 (KHTML, like Gecko) "
    "Version/5.0 Mobile Safari/533.1"
)

# ==================== 日志 ====================
SCREENSHOT_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("DX-Telecom")


# ==================== 产物记录 ====================
def _load_results() -> dict:
    if RESULT_FILE.exists():
        try:
            return json.loads(RESULT_FILE.read_text())
        except Exception:
            pass
    return {"total": {}, "history": []}


def _save_result(run_result: dict):
    records = _load_results()
    run_result["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    records["history"].append(run_result)
    for item in run_result.get("items", []):
        key = item.get("type", "其他")
        val = item.get("value", "")
        if key not in records["total"]:
            records["total"][key] = []
        records["total"][key].append({"time": run_result["time"], "value": val})
    RESULT_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2))


def query_results() -> str:
    """查询所有历史任务产物 (供 bot 插件调用)"""
    records = _load_results()
    total = records.get("total", {})
    history = records.get("history", [])
    if not history:
        return "暂无任务执行记录，请先执行 电信签到 或 电信执行"
    last = history[-1]
    lines = [
        "电信任务产物查询",
        "==================================",
        f"最近执行: {last.get('time', '未知')}",
        f"累计执行: {len(history)} 次",
        "==================================",
        "累计获得产物:",
    ]
    if total:
        for key, items in total.items():
            lines.append(f"  {key}: {len(items)} 次")
            for item in items[-3:]:
                lines.append(f"    - {item['time']}: {item['value']}")
    else:
        lines.append("  (暂无产物记录)")
    lines.append("==================================")
    lines.append("最近一次详情:")
    for item in last.get("items", []):
        lines.append(f"  {item.get('type', '?')}: {item.get('value', '?')}")
    if last.get("signin"):
        lines.append(f"  签到: {last['signin'].get('msg', '-')}")
    if last.get("error"):
        lines.append(f"  [错误] {last['error']}")
    return "\n".join(lines)


# ==================== 主流程 ====================
def run_all(signin_only: bool = False) -> dict:
    """执行全部自动化任务，返回结果汇总"""
    from core.login import LoginClient
    from core.api import TelecomAPI

    result = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "phone": PHONE[:3] + "****" + PHONE[-4:] if PHONE else "未设置",
        "login": False,
        "signin": {},
        "activities": [],
        "items": [],
    }

    if not PHONE or not PASSWORD:
        result["error"] = "账号或密码未配置"
        logger.error("账号或密码未配置，请在 .env 中设置 chinaTelecomAccount（格式: 手机号#密码）")
        _save_result(result)
        return result

    logger.info("=" * 60)
    logger.info("  中国电信话费自动化")
    logger.info(f"  号码: {result['phone']}")
    logger.info(f"  时间: {result['time']}")
    logger.info("=" * 60)

    # 创建共享 HTTP 客户端
    http_client = httpx.Client(
        timeout=30,
        verify=False,
        follow_redirects=False,
        headers={
            "User-Agent": UA,
            "Connection": "keep-alive",
        },
    )

    try:
        # ========== 1. 登录 ==========
        logger.info("")
        logger.info("【第1步】登录")
        login_client = LoginClient()
        login_client.client = http_client

        login_result = login_client.login(PHONE, PASSWORD, use_cache=True)

        if not login_result.success:
            result["error"] = f"登录失败: {login_result.msg}"
            result["items"].append({"type": "系统", "value": f"登录失败 [{login_result.code}]"})
            logger.error(f"登录失败 [{login_result.code}]: {login_result.msg}")
            _save_result(result)
            return result

        result["login"] = True
        token = login_result.token
        user_id = login_result.user_id
        logger.info(f"登录成功 [{login_result.code}]: token={token[:20] if token else '无'}...")

        # ========== 2. 获取 Ticket ==========
        logger.info("")
        logger.info("【第2步】获取 Ticket")
        ticket = login_client.get_ticket()
        if not ticket:
            result["error"] = "获取 ticket 失败"
            result["items"].append({"type": "系统", "value": "ticket 获取失败"})
            logger.error("获取 ticket 失败")
            _save_result(result)
            return result
        logger.info("Ticket 获取成功")

        # ========== 3. 初始化业务 API + 获取 Sign ==========
        logger.info("")
        logger.info("【第3步】初始化业务 API")
        api = TelecomAPI(http_client, PHONE)

        sign_result = api.get_sign_by_ticket(ticket)

        if not sign_result.ok:
            logger.warning(f"获取 sign 失败: {sign_result.msg}")
            api._ruishu.reset()
            sign_result = api.get_sign_by_ticket(ticket)

            if not sign_result.ok:
                result["error"] = f"获取 sign 失败: {sign_result.msg}"
                result["items"].append({"type": "系统", "value": "sign 获取失败"})
                logger.error(f"获取 sign 最终失败: {sign_result.msg}")
                _save_result(result)
                return result

        logger.info(f"Sign 获取成功 (瑞数状态: {'可用' if api.ruishu_available else '降级'})")

        # ========== 4. 查询金豆 (初始) ==========
        logger.info("")
        logger.info("【第4步】查询金豆余额")
        import random
        time.sleep(random.uniform(0.5, 2.0))
        api.user_coin_info(notify=True)

        # ========== 5. 签到 ==========
        if ENABLE_SIGNIN:
            logger.info("")
            logger.info("【第5步】签到翻牌")
            time.sleep(random.uniform(0.5, 2.0))
            signin_result = api.user_status_info()
            result["signin"] = {
                "ok": signin_result.ok,
                "msg": signin_result.msg,
                "coin": signin_result.data.get("coin", 0),
                "signed": signin_result.data.get("signed", False),
            }
            if signin_result.ok:
                result["items"].append({"type": "签到", "value": signin_result.msg})

            # 连签兑换
            if not signin_only:
                time.sleep(random.uniform(0.5, 2.0))
                cs_result = api.continue_sign_records()
                if cs_result.ok:
                    for r in cs_result.data.get("records", []):
                        if r.ok:
                            result["items"].append({
                                "type": "连签兑换",
                                "value": r.data.get("prize", r.msg),
                            })

        # ========== 6. 首页任务 ==========
        if not signin_only and ENABLE_ACTIVITY:
            logger.info("")
            logger.info("【第6步】首页任务")
            time.sleep(random.uniform(0.5, 2.0))
            hp_result = api.homepage()
            if hp_result.ok:
                completed = hp_result.data.get("completed", [])
                result["activities"] = completed
                if completed:
                    result["items"].append({
                        "type": "活动",
                        "value": f"完成 {len(completed)} 个任务",
                    })
            else:
                logger.warning(f"首页任务获取失败: {hp_result.msg}")

        # ========== 7. 宠物乐园 ==========
        if not signin_only and ENABLE_ACTIVITY:
            logger.info("")
            logger.info("【第7步】宠物乐园")
            time.sleep(random.uniform(0.5, 2.0))
            paradise_result = api.get_paradise_info()
            if paradise_result.ok:
                feed_results = paradise_result.data.get("feed", [])
                feed_count = sum(1 for r in feed_results if r.get("ok"))
                if feed_count > 0:
                    result["items"].append({
                        "type": "宠物",
                        "value": f"喂食 {feed_count} 次",
                    })

                time.sleep(random.uniform(0.5, 2.0))
                rights_result = api.get_level_rights()
                if rights_result.ok:
                    for r in rights_result.data.get("results", []):
                        if r.get("ok"):
                            result["items"].append({
                                "type": "兑换",
                                "value": r.get("name", "权益"),
                            })

        # ========== 8. 查询最终金豆 ==========
        logger.info("")
        logger.info("【第8步】查询最终金豆")
        time.sleep(random.uniform(0.5, 2.0))
        api.user_coin_info(notify=True)

    except Exception as e:
        logger.error(f"运行异常: {e}", exc_info=True)
        result["error"] = str(e)
        result["items"].append({"type": "系统", "value": f"异常: {e}"})

    finally:
        http_client.close()

    _save_result(result)

    logger.info("")
    logger.info("=" * 60)
    logger.info("  执行结果")
    logger.info(f"  登录: {'OK' if result['login'] else 'FAIL'}")
    logger.info(f"  签到: {result['signin'].get('msg', '-')}")
    logger.info(f"  活动: {len(result.get('activities', []))} 个")
    logger.info("=" * 60)

    return result


# ==================== 直接运行 ====================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="中国电信话费自动化")
    parser.add_argument("--signin-only", action="store_true", help="仅执行签到")
    args = parser.parse_args()

    result = run_all(signin_only=args.signin_only)
    if result.get("error"):
        print(f"\n[FAIL] 执行失败: {result['error']}")
        sys.exit(1)
    else:
        print(f"\n[OK] 签到: {result.get('signin', {}).get('msg', '-')}")
        print(f"[OK] 活动: {len(result.get('activities', []))} 个")
        items = result.get("items", [])
        if items:
            items_str = " | ".join(f'{i["type"]}:{i["value"]}' for i in items)
            print(f"[OK] 产物: {items_str}")
        sys.exit(0)