"""
中国电信瑞数反爬模块
=====================
独立封装瑞数反爬 Cookie 生成逻辑，与登录、业务API解耦。

核心特性:
- 健壮的错误处理：瑞数失败不影响主流程，仅降级
- Cookie 缓存：避免重复执行 JS 挑战
- 动态适配：自动提取页面中的 content/ts/external JS
- 优雅降级：瑞数不可用时记录警告，业务API继续尝试

使用方式:
    from core.ruishu import RuishuClient
    rs = RuishuClient(http_client)
    rs.init()  # 初始化瑞数Cookie
    headers = rs.get_headers(sign="xxx")  # 获取带瑞数Cookie的请求头
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("DX.Ruishu")

# ==================== 配置 ====================

PROJECT_DIR = Path(__file__).resolve().parent.parent
RS_CORE_JS = PROJECT_DIR / "rs_core.js"

# 瑞数初始化 URL（任意 wappark 页面均可）
RS_INIT_URL = "https://wappark.189.cn/jt-sign/webSign/homepage"

# Cookie 缓存有效期（秒）
RS_COOKIE_TTL = 1800  # 30分钟


class RuishuResult:
    """瑞数初始化结果"""

    def __init__(self, success: bool, cookies: dict = None, msg: str = ""):
        self.success = success
        self.cookies = cookies or {}
        self.msg = msg

    def __bool__(self) -> bool:
        return self.success

    def __repr__(self) -> str:
        if self.success:
            return f"RuishuResult(success=True, cookies={list(self.cookies.keys())})"
        return f"RuishuResult(success=False, msg={self.msg})"


class RuishuClient:
    """瑞数反爬客户端

    负责:
    1. 请求目标页面提取瑞数挑战代码
    2. 组装并执行 JS 生成 Cookie
    3. 缓存 Cookie 避免重复计算
    4. 提供带瑞数 Cookie 的请求头
    """

    def __init__(self, http_client=None, init_url: str = RS_INIT_URL):
        """
        Args:
            http_client: httpx.Client 实例（外部传入，复用连接）
            init_url: 用于初始化瑞数的页面 URL
        """
        self.http = http_client
        self.init_url = init_url
        self._cookies: dict = {}
        self._js_ctx = None
        self._init_time: float = 0
        self._available: bool = True  # 瑞数是否可用（多次失败后标记为不可用）
        self._fail_count: int = 0
        self._max_fail = 3  # 连续失败次数阈值

    # ---------- 公共接口 ----------

    def init(self, force: bool = False) -> RuishuResult:
        """初始化瑞数 Cookie

        Args:
            force: 是否强制重新初始化（忽略缓存）

        Returns:
            RuishuResult
        """
        # 检查是否已被标记为不可用
        if not self._available:
            logger.debug("瑞数已被标记为不可用，跳过初始化")
            return RuishuResult(False, msg="瑞数连续失败，已降级")

        # 检查缓存
        if not force and self._cookies and self._is_cache_valid():
            logger.debug("瑞数 Cookie 缓存有效，跳过初始化")
            return RuishuResult(True, self._cookies, "缓存命中")

        if self.http is None:
            logger.warning("HTTP 客户端未设置，无法初始化瑞数")
            return RuishuResult(False, msg="HTTP 客户端未设置")

        try:
            result = self._do_init()
            if result.success:
                self._fail_count = 0
                self._cookies = result.cookies
                self._init_time = time.time()
                logger.info("瑞数 Cookie 初始化成功")
            else:
                self._fail_count += 1
                if self._fail_count >= self._max_fail:
                    self._available = False
                    logger.warning(f"瑞数连续失败 {self._max_fail} 次，已标记为不可用")
            return result
        except Exception as e:
            self._fail_count += 1
            if self._fail_count >= self._max_fail:
                self._available = False
            logger.error(f"瑞数初始化异常: {e}")
            return RuishuResult(False, msg=str(e))

    def get_headers(self, sign: str = "") -> dict:
        """获取带瑞数 Cookie 的请求头

        即使瑞数初始化失败，也会返回基础请求头，不影响业务调用。

        Args:
            sign: sign token（从 SSO 获取）

        Returns:
            请求头 dict
        """
        headers = {}

        # 尝试初始化（如果还没初始化过）
        if not self._cookies and self._available:
            self.init()

        # 组装 Cookie
        if self._cookies:
            cookie_parts = []
            for k, v in self._cookies.items():
                if v:
                    cookie_parts.append(f"{k}={v}")
            if cookie_parts:
                headers["Cookie"] = "; ".join(cookie_parts)

        if sign:
            headers["sign"] = sign

        return headers

    @property
    def available(self) -> bool:
        """瑞数是否可用"""
        return self._available

    @property
    def cookies(self) -> dict:
        """当前瑞数 Cookie"""
        return self._cookies.copy()

    def reset(self):
        """重置瑞数状态（清除缓存和失败计数）"""
        self._cookies = {}
        self._js_ctx = None
        self._init_time = 0
        self._available = True
        self._fail_count = 0
        logger.debug("瑞数状态已重置")

    # ---------- 内部实现 ----------

    def _is_cache_valid(self) -> bool:
        """检查缓存是否有效"""
        if not self._init_time:
            return False
        return (time.time() - self._init_time) < RS_COOKIE_TTL

    def _do_init(self) -> RuishuResult:
        """执行瑞数初始化核心逻辑"""
        logger.info("=" * 50)
        logger.info("初始化瑞数反爬 Cookie...")

        # 1. 请求目标页面
        try:
            resp = self.http.post(self.init_url)
        except Exception as e:
            return RuishuResult(False, msg=f"请求页面失败: {e}")

        if resp.status_code != 200:
            return RuishuResult(False, msg=f"页面返回 {resp.status_code}")

        text = resp.text
        if not text:
            return RuishuResult(False, msg="页面响应为空")

        # 2. 提取 Set-Cookie (yiUIIlbdQT3fO)
        yiUIIlbdQT3fO = self._extract_rs_o_cookie(resp)

        # 3. 提取 content code
        content_code = self._extract_content_code(text)
        if not content_code:
            return RuishuResult(False, msg="未找到 content code")

        # 4. 提取 ts code
        ts_code = self._extract_ts_code(text)
        if not ts_code:
            return RuishuResult(False, msg="未找到 ts code")

        # 5. 提取外部 JS URL
        js_full_url = self._extract_external_js_url(text, self.init_url)
        if not js_full_url:
            return RuishuResult(False, msg="未找到外部 JS URL")

        # 6. 下载外部 JS
        try:
            js_resp = self.http.get(js_full_url)
        except Exception as e:
            return RuishuResult(False, msg=f"下载外部 JS 失败: {e}")

        if js_resp.status_code != 200:
            return RuishuResult(False, msg=f"外部 JS 返回 {js_resp.status_code}")

        external_js = js_resp.text
        if not external_js:
            return RuishuResult(False, msg="外部 JS 为空")

        # 7. 组装并执行 JS
        try:
            import execjs
        except ImportError:
            return RuishuResult(False, msg="PyExecJS 未安装")

        if not RS_CORE_JS.exists():
            return RuishuResult(False, msg=f"瑞数核心 JS 不存在: {RS_CORE_JS}")

        try:
            rs_template = RS_CORE_JS.read_text(encoding="utf-8")
            combined_js = rs_template.replace(
                '"CONTENT_PLACEHOLDER"', json.dumps(content_code)
            ).replace(
                "// TS_CODE_PLACEHOLDER", ts_code + "\n" + external_js
            )

            ctx = execjs.compile(combined_js)
            cookie_result = ctx.call("main")

            yiUIIlbdQT3fP = ""
            if isinstance(cookie_result, str) and "=" in cookie_result:
                yiUIIlbdQT3fP = cookie_result.split("=", 1)[1]
            elif isinstance(cookie_result, str):
                yiUIIlbdQT3fP = cookie_result

            if not yiUIIlbdQT3fP:
                return RuishuResult(False, msg="JS 执行结果无效")

            self._js_ctx = ctx
            cookies = {
                "yiUIIlbdQT3fO": yiUIIlbdQT3fO,
                "yiUIIlbdQT3fP": yiUIIlbdQT3fP,
            }

            return RuishuResult(True, cookies, "初始化成功")

        except Exception as e:
            return RuishuResult(False, msg=f"JS 执行失败: {e}")

    @staticmethod
    def _extract_rs_o_cookie(resp) -> str:
        """从响应头提取 yiUIIlbdQT3fO Cookie"""
        try:
            if "set-cookie" in resp.headers:
                cookies = resp.headers.get_list("set-cookie")
                for ck in cookies:
                    if "yiUIIlbdQT3fO" in ck:
                        parts = ck.split(";", 1)[0].split("=", 1)
                        if len(parts) == 2:
                            return parts[1]
        except Exception:
            pass
        return ""

    @staticmethod
    def _extract_content_code(text: str) -> str:
        """提取 content code"""
        # 尝试多种匹配模式
        patterns = [
            r' content="([^"]*)" r=',
            r'<meta[^>]*content="([^"]*)"[^>]*r=',
            r'content="([^"]+)"\s+r=',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return ""

    @staticmethod
    def _extract_ts_code(text: str) -> str:
        """提取 $_ts 代码块"""
        patterns = [
            r'\$_ts=window([^<]*)</script><script',
            r'\$_ts=window(.*?)\$_ts\.lcd\(\);',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                return "$_ts=window" + match.group(1)
        return ""

    @staticmethod
    def _extract_external_js_url(text: str, base_url: str) -> str:
        """提取外部 JS URL"""
        patterns = [
            r'\$_ts\.lcd\(\);</script><script[^>]*src="([^"]*)"',
            r'<script[^>]*src="([^"]*\.js[^"]*)"[^>]*>',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                js_path = match.group(1)
                if js_path.startswith("http"):
                    return js_path
                # 拼接完整 URL
                parsed = urlparse(base_url)
                return f"{parsed.scheme}://{parsed.netloc}{js_path}"
        return ""
