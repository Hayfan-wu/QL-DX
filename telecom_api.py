"""
中国电信话费自动化 - 核心API
=============================
基于 Playwright 实现：
- 账号密码登录（Cookie 持久化）
- 每日签到翻牌领金豆/话费
- 口令兑换话费
- 活动扫描与参与
- 限时秒杀抢购
"""

import asyncio
import json
import logging
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from config import (
    PHONE, PASSWORD, HEADLESS, TIMEOUT, PAGE_LOAD_WAIT,
    ENABLE_SIGNIN, ENABLE_ACTIVITY, ENABLE_FLASH_SALE,
    FLASH_SALE_TIME,
    URL_189_HOME, URL_LOGIN, URL_SIGNIN, URL_CODE_EXCHANGE,
    ACTIVITY_URLS, COOKIE_FILE, LOG_FILE, RESULT_FILE, SCREENSHOT_DIR, PROJECT_DIR,
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
    """加载历史产物记录"""
    if RESULT_FILE.exists():
        try:
            return json.loads(RESULT_FILE.read_text())
        except Exception:
            pass
    return {"total": {}, "history": []}


def _save_result(run_result: dict):
    """追加本次执行产物到记录文件"""
    records = _load_results()
    run_result["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    records["history"].append(run_result)

    # 累计统计
    for item in run_result.get("items", []):
        key = item.get("type", "其他")
        val = item.get("value", "")
        if key not in records["total"]:
            records["total"][key] = []
        records["total"][key].append({"time": run_result["time"], "value": val})

    RESULT_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2))


def query_results() -> str:
    """查询所有历史产物，返回格式化文本"""
    records = _load_results()
    total = records.get("total", {})
    history = records.get("history", [])

    if not history:
        return "📋 暂无任务执行记录，请先执行 电信签到 或 电信执行"

    last = history[-1]
    lines = [
        "📋 电信任务产物查询",
        "━━━━━━━━━━━━━━━━━━━━",
        f"📅 最近执行: {last.get('time', '未知')}",
        f"🔄 累计执行: {len(history)} 次",
        "━━━━━━━━━━━━━━━━━━━━",
        "📦 累计获得产物:",
    ]

    if total:
        for key, items in total.items():
            lines.append(f"  {key}: {len(items)} 次")
            # 展示最近3条
            for item in items[-3:]:
                lines.append(f"    └ {item['time']}: {item['value']}")
    else:
        lines.append("  (暂无产物记录)")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"📝 最近一次详情:")
    for item in last.get("items", []):
        lines.append(f"  {item.get('type', '?')}: {item.get('value', '?')}")

    if last.get("signin"):
        lines.append(f"  签到: {last['signin'].get('msg', '-')}")
    if last.get("error"):
        lines.append(f"  ❌ 错误: {last['error']}")

    return "\n".join(lines)


# ==================== 浏览器辅助 ====================
async def _random_delay(a: float = 0.3, b: float = 1.5):
    await asyncio.sleep(random.uniform(a, b))


async def _safe_click(page: Page, selector: str, timeout: int = 5) -> bool:
    try:
        el = await page.wait_for_selector(selector, timeout=timeout * 1000)
        if el:
            await el.click()
            return True
    except Exception:
        pass
    return False


async def _safe_fill(page: Page, selector: str, text: str, timeout: int = 5) -> bool:
    try:
        el = await page.wait_for_selector(selector, timeout=timeout * 1000)
        if el:
            await el.fill("")
            await el.fill(text)
            return True
    except Exception:
        pass
    return False


async def _safe_text(page: Page, selector: str, timeout: int = 3) -> str:
    try:
        el = await page.wait_for_selector(selector, timeout=timeout * 1000)
        return (await el.inner_text()).strip() if el else ""
    except Exception:
        return ""


async def _screenshot(page: Page, name: str):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = SCREENSHOT_DIR / f"{name}_{ts}.png"
    await page.screenshot(path=str(path))
    logger.info(f"截图: {path}")


def _save_cookies(cookies: list):
    COOKIE_FILE.write_text(json.dumps(cookies, ensure_ascii=False))


def _load_cookies() -> Optional[list]:
    if COOKIE_FILE.exists():
        try:
            return json.loads(COOKIE_FILE.read_text())
        except Exception:
            pass
    return None


# ==================== 登录模块 ====================
async def login(page: Page) -> bool:
    """
    账号密码登录中国电信网上营业厅
    优先使用 Cookie 恢复会话
    """
    logger.info("=" * 50)
    logger.info("开始登录...")

    saved = _load_cookies()
    if saved:
        logger.info("发现已保存的 Cookie，尝试恢复会话...")
        await page.context.add_cookies(saved)
        await page.goto(URL_189_HOME, wait_until="networkidle", timeout=60000)
        await _random_delay(1, 2)
        if await _check_logged_in(page):
            logger.info("Cookie 有效，已恢复登录")
            return True
        logger.info("Cookie 已过期，重新登录...")

    try:
        await page.goto(URL_LOGIN, wait_until="networkidle", timeout=60000)
        await _random_delay(2, 3)

        pwd_tab_selectors = [
            "text=密码登录", "text=账号密码",
            "a:has-text('密码')", "span:has-text('密码')",
            '[class*="password"]', "text=账号登录",
        ]
        for sel in pwd_tab_selectors:
            if await _safe_click(page, sel, timeout=3):
                logger.info("切换到密码登录")
                await _random_delay(1, 2)
                break

        phone_selectors = [
            'input[type="tel"]', 'input[placeholder*="手机"]',
            'input[name="phone"]', 'input[name="mobile"]',
            'input[name="account"]', 'input[name="username"]',
            "#phone", "#mobile", "#account", "#username",
        ]
        phone_ok = False
        for sel in phone_selectors:
            if await _safe_fill(page, sel, PHONE, timeout=3):
                phone_ok = True
                break
        if not phone_ok:
            inputs = await page.query_selector_all("input")
            if inputs:
                await inputs[0].fill(PHONE)
                phone_ok = True
        if not phone_ok:
            logger.error("未找到手机号输入框")
            await _screenshot(page, "login_no_phone_input")
            return False

        await _random_delay(0.5, 1)

        pwd_selectors = [
            'input[type="password"]', 'input[placeholder*="密码"]',
            'input[name="password"]', 'input[name="pwd"]',
            "#password", "#pwd",
        ]
        pwd_ok = False
        for sel in pwd_selectors:
            if await _safe_fill(page, sel, PASSWORD, timeout=3):
                pwd_ok = True
                break
        if not pwd_ok:
            inputs = await page.query_selector_all("input[type='password']")
            if inputs:
                await inputs[0].fill(PASSWORD)
                pwd_ok = True
        if not pwd_ok:
            logger.error("未找到密码输入框")
            await _screenshot(page, "login_no_pwd_input")
            return False

        await _random_delay(0.5, 1)
        await _safe_click(page, '[class*="agree"]', timeout=2)
        await _safe_click(page, 'input[type="checkbox"]', timeout=2)

        login_btn_selectors = [
            "button:has-text('登录')", 'button[type="submit"]',
            "a:has-text('登录')", '[class*="login-btn"]',
            "#loginBtn", "text=登 录",
        ]
        clicked = False
        for sel in login_btn_selectors:
            if await _safe_click(page, sel, timeout=3):
                clicked = True
                break
        if not clicked:
            logger.error("未找到登录按钮")
            await _screenshot(page, "login_no_btn")
            return False

        await asyncio.sleep(3)
        await _random_delay(2, 4)

        if await page.query_selector("text=验证码"):
            logger.warning("检测到验证码，尝试处理...")
            await _screenshot(page, "login_captcha")
            if HEADLESS:
                logger.error("无头模式下无法处理验证码，请先手动登录一次保存 Cookie")
                return False
            await asyncio.sleep(30)

        if await _check_logged_in(page):
            logger.info("登录成功！")
            cookies = await page.context.cookies()
            _save_cookies(cookies)
            logger.info("Cookie 已保存")
            return True
        else:
            logger.error("登录失败，请检查账号密码")
            await _screenshot(page, "login_failed")
            return False

    except Exception as e:
        logger.error(f"登录异常: {e}")
        await _screenshot(page, "login_error")
        return False


async def _check_logged_in(page: Page) -> bool:
    indicators = [
        "text=退出登录", "text=我的",
        '[class*="user-name"]', '[class*="nickname"]',
        '[class*="avatar"]', "text=已登录",
    ]
    for sel in indicators:
        try:
            if await page.query_selector(sel):
                return True
        except Exception:
            pass
    if "login" not in page.url.lower():
        return True
    return False


# ==================== 签到模块 ====================
async def signin(page: Page) -> dict:
    """每日签到翻牌领金豆/话费"""
    if not ENABLE_SIGNIN:
        return {"ok": False, "skipped": True, "msg": "签到已禁用"}

    logger.info("=" * 50)
    logger.info("执行每日签到...")

    try:
        await page.goto(URL_SIGNIN, wait_until="networkidle", timeout=30000)
        await _random_delay(2, 3)

        sign_btn_selectors = [
            "text=签到", "text=立即签到", "text=每日签到",
            "button:has-text('签到')", '[class*="sign"]',
            '[class*="checkin"]', 'a:has-text("签到")', "text=点击签到",
        ]
        for sel in sign_btn_selectors:
            if await _safe_click(page, sel, timeout=3):
                logger.info("签到点击成功")
                await _random_delay(2, 3)
                await _screenshot(page, "signin_ok")
                beans = await _get_beans(page)
                return {"ok": True, "msg": f"签到成功，金豆约 {beans}"}
            if await page.query_selector("text=已签到"):
                return {"ok": True, "msg": "今日已签到"}

        await _screenshot(page, "signin_no_btn")
        return {"ok": False, "msg": "未找到签到按钮，可能已签到或活动变更"}

    except Exception as e:
        logger.error(f"签到异常: {e}")
        return {"ok": False, "msg": str(e)}


async def _get_beans(page: Page) -> int:
    """获取当前金豆数量"""
    bean_selectors = [
        '[class*="bean-count"]', '[class*="bean-num"]',
        '[class*="point"]', '[class*="jindou"]', 'text=金豆',
    ]
    for sel in bean_selectors:
        text = await _safe_text(page, sel, timeout=2)
        m = re.search(r"(\d+)", text)
        if m:
            return int(m.group(1))
    return 0


# ==================== 活动扫描 ====================
async def scan_activities(page: Page) -> list:
    """扫描参与所有活动（签到翻牌 + 口令兑换）"""
    if not ENABLE_ACTIVITY:
        return [{"ok": False, "skipped": True, "msg": "活动扫描已禁用"}]

    logger.info("=" * 50)
    logger.info("扫描话费活动...")

    results = []
    for url in ACTIVITY_URLS:
        try:
            logger.info(f"访问: {url}")
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await _random_delay(2, 3)

            await _screenshot(page, f"activity_{ACTIVITY_URLS.index(url)}")

            btns = [
                "text=领取", "text=立即参与", "text=抽奖",
                "text=免费领取", "text=去参与", "text=立即领取",
                "text=点击领取", 'a:has-text("话费")',
                'button:has-text("领取")',
            ]
            for btn_sel in btns:
                try:
                    elements = await page.query_selector_all(btn_sel)
                    for el in elements:
                        if await el.is_visible():
                            txt = (await el.inner_text()).strip()
                            await el.click()
                            logger.info(f"  点击: [{txt}]")
                            await _random_delay(1, 2)
                            results.append({"url": url, "btn": txt})
                except Exception:
                    continue

        except Exception as e:
            logger.warning(f"活动页异常: {url} - {e}")

    return results


# ==================== 秒杀模块 ====================
async def flash_sale(page: Page) -> dict:
    """限时秒杀"""
    if not ENABLE_FLASH_SALE:
        return {"ok": False, "skipped": True, "msg": "秒杀已禁用"}

    logger.info("=" * 50)
    logger.info(f"秒杀监控，目标时间: {FLASH_SALE_TIME}")

    try:
        h, m, s = map(int, FLASH_SALE_TIME.split(":"))
    except ValueError:
        return {"ok": False, "msg": f"时间格式错误: {FLASH_SALE_TIME}"}

    while True:
        now = datetime.now()
        target = now.replace(hour=h, minute=m, second=s, microsecond=0)
        if now >= target:
            break
        wait = (target - now).total_seconds()
        if wait > 10:
            logger.info(f"距秒杀 {wait:.0f} 秒，等待中...")
            await asyncio.sleep(min(wait - 5, 30))
        else:
            await asyncio.sleep(0.1)

    logger.info("开始秒杀！")
    t0 = time.time()

    try:
        await page.goto(URL_189_HOME, wait_until="networkidle", timeout=15000)
        await _random_delay(0.5, 1)

        flash_selectors = [
            "text=秒杀", "text=抢购", "text=立即抢",
            'button:has-text("秒杀")', 'button:has-text("抢")',
            '[class*="flash"]', '[class*="seckill"]',
        ]
        for sel in flash_selectors:
            try:
                els = await page.query_selector_all(sel)
                for el in els:
                    if await el.is_visible():
                        await el.click()
                        elapsed = time.time() - t0
                        logger.info(f"秒杀点击成功！耗时 {elapsed:.2f}s")
                        await _screenshot(page, "flash_sale_ok")
                        return {"ok": True, "msg": f"秒杀完成，耗时 {elapsed:.2f}s"}
            except Exception:
                continue

        elapsed = time.time() - t0
        return {"ok": False, "msg": f"未找到秒杀按钮，耗时 {elapsed:.2f}s"}

    except Exception as e:
        return {"ok": False, "msg": str(e)}


# ==================== 主流程 ====================
async def run_all() -> dict:
    """执行全部自动化任务，返回结果汇总"""
    result = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "phone": PHONE[:3] + "****" + PHONE[-4:] if PHONE else "未设置",
        "login": False,
        "signin": {},
        "activities": [],
        "flash": {},
        "items": [],
    }

    if not PHONE or not PASSWORD:
        result["error"] = "账号或密码未配置"
        logger.error("账号或密码未配置，请在 .env 中设置 DX_ACCOUNT（格式: 手机号#密码）")
        _save_result(result)
        return result

    logger.info("=" * 60)
    logger.info(f"  中国电信话费自动化 v2.1")
    logger.info(f"  号码: {result['phone']}")
    logger.info(f"  时间: {result['time']}")
    logger.info("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => false});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN','zh','en']});
        """)

        page = await context.new_page()

        try:
            # 1. 登录
            result["login"] = await login(page)
            if not result["login"]:
                logger.warning("登录失败，跳过后续步骤")
                result["items"].append({"type": "系统", "value": "登录失败"})
                await browser.close()
                _save_result(result)
                return result

            # 2. 签到翻牌
            signin_result = await signin(page)
            result["signin"] = signin_result
            if signin_result.get("ok"):
                result["items"].append({"type": "签到", "value": signin_result.get("msg", "完成")})

            # 3. 活动扫描（签到 + 口令兑换）
            act_results = await scan_activities(page)
            result["activities"] = act_results
            if act_results and not (len(act_results) == 1 and act_results[0].get("skipped")):
                result["items"].append({"type": "活动", "value": f"参与 {len(act_results)} 个"})

            # 4. 秒杀（如果当前时间接近秒杀时间）
            now = datetime.now()
            try:
                h, m, _ = map(int, FLASH_SALE_TIME.split(":"))
                target = now.replace(hour=h, minute=m, second=0, microsecond=0)
                diff = (target - now).total_seconds()
                if 0 <= diff < 60:
                    flash_result = await flash_sale(page)
                    result["flash"] = flash_result
                    if flash_result.get("ok"):
                        result["items"].append({"type": "秒杀", "value": flash_result.get("msg", "完成")})
            except Exception:
                pass

        except Exception as e:
            logger.error(f"运行异常: {e}")
            await _screenshot(page, "fatal_error")
            result["error"] = str(e)
            result["items"].append({"type": "系统", "value": f"异常: {e}"})

        finally:
            await browser.close()

    _save_result(result)

    logger.info("=" * 60)
    logger.info("  执行结果")
    logger.info(f"  登录: {'OK' if result['login'] else 'FAIL'}")
    logger.info(f"  签到: {result['signin'].get('msg', '-')}")
    logger.info(f"  活动: {len(result['activities'])} 个")
    logger.info("=" * 60)

    return result


if __name__ == "__main__":
    asyncio.run(run_all())