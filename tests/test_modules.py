"""
模块化架构单元测试
=================
覆盖核心模块的单元测试：
- core.login.LoginClient.login()
- core.ruishu.RuishuClient（错误处理
- core.api.TelecomAPI（基础调用）

使用 unittest.mock 模拟 httpx 响应, 无需真实网络请求。
"""

import json
import sys
import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path

# 确保可以导入项目模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx


# ---------------------------------------------------------------------------
# 辅助: 创建模拟的 httpx.Response
# ---------------------------------------------------------------------------
def _make_mock_response(status_code: int = 200, text: str = "", json_data=None):
    """构造一个 mock httpx.Response, 支持 .text, .json(), .status_code"""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = status_code

    if json_data is not None:
        json_text = json.dumps(json_data, ensure_ascii=False)
        mock_resp.text = json_text
        mock_resp.json.return_value = json_data
    else:
        mock_resp.text = text
        def _json_side_effect():
            return json.loads(text)
        mock_resp.json.side_effect = _json_side_effect

    # 模拟 headers
    mock_resp.headers = {}

    return mock_resp


# ---------------------------------------------------------------------------
# 1. LoginClient 登录模块测试
# ---------------------------------------------------------------------------
class TestLoginClient(unittest.TestCase):
    """LoginClient.login() 全面测试"""

    def setUp(self):
        from core.login import LoginClient
        self.client = LoginClient()
        self.phone = "13800138000"
        self.password = "TestPass123"

    def tearDown(self):
        self.client.close()

    @patch("core.login._save_cache")
    @patch("core.login._load_cache", return_value={})
    @patch("core.login._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_success(self, mock_rsa, mock_load, mock_save):
        """登录成功: resultCode 0000, 返回有效 token 和 userId"""
        resp_json = {
            "responseData": {
                "resultCode": "0000",
                "data": {
                    "loginSuccessResult": {
                        "userId": "user_abc_123",
                        "token": "tok_xyz_456",
                    }
                },
            }
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)

        with patch.object(self.client.client, "post", return_value=mock_resp):
            result = self.client.login(self.phone, self.password, use_cache=False)

        self.assertTrue(result.success)
        self.assertEqual(result.code, "0000")
        self.assertEqual(result.user_id, "user_abc_123")
        self.assertEqual(result.token, "tok_xyz_456")
        self.assertEqual(self.client.phone, self.phone)

    @patch("core.login._save_cache")
    @patch("core.login._load_cache", return_value={})
    @patch("core.login._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_3006_needs_sms(self, mock_rsa, mock_load, mock_save):
        """登录返回 3006 - 需要短信验证"""
        resp_json = {
            "responseData": {
                "resultCode": "3006",
                "resultDesc": "需要短信验证",
                "data": {
                    "loginFailResult": {
                        "verifyCode": "test_verify_token"
                    }
                },
            }
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)

        with patch.object(self.client.client, "post", return_value=mock_resp):
            result = self.client.login(self.phone, self.password, use_cache=False)

        self.assertFalse(result.success)
        self.assertEqual(result.code, "3006")
        self.assertEqual(result.verify_code_token, "test_verify_token")
        self.assertIn("短信", result.msg)

    @patch("core.login._save_cache")
    @patch("core.login._load_cache", return_value={})
    @patch("core.login._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_3006_data_none(self, mock_rsa, mock_load, mock_save):
        """登录返回 3006 且 data 为 None - 不应崩溃"""
        resp_json = {
            "responseData": {
                "resultCode": "3006",
                "resultDesc": "密码错误",
                "data": None,
            }
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)

        with patch.object(self.client.client, "post", return_value=mock_resp):
            result = self.client.login(self.phone, self.password, use_cache=False)

        self.assertFalse(result.success)
        self.assertEqual(result.code, "3006")
        # 不应抛出 NoneType 错误

    @patch("core.login._save_cache")
    @patch("core.login._load_cache", return_value={})
    @patch("core.login._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_error_code(self, mock_rsa, mock_load, mock_save):
        """登录失败 - 其他错误码"""
        resp_json = {
            "responseData": {
                "resultCode": "3001",
                "resultDesc": "手机号或密码有误",
            }
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)

        with patch.object(self.client.client, "post", return_value=mock_resp):
            result = self.client.login(self.phone, self.password, use_cache=False)

        self.assertFalse(result.success)
        self.assertEqual(result.code, "3001")
        self.assertIn("密码", result.msg)

    @patch("core.login._save_cache")
    @patch("core.login._load_cache", return_value={})
    @patch("core.login._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_empty_response(self, mock_rsa, mock_load, mock_save):
        """登录响应为空"""
        mock_resp = _make_mock_response(status_code=200, text="")

        with patch.object(self.client.client, "post", return_value=mock_resp):
            result = self.client.login(self.phone, self.password, use_cache=False)

        self.assertFalse(result.success)
        self.assertEqual(result.code, "-1")

    @patch("core.login._save_cache")
    @patch("core.login._load_cache", return_value={})
    @patch("core.login._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_network_error(self, mock_rsa, mock_load, mock_save):
        """网络异常"""
        with patch.object(self.client.client, "post", side_effect=httpx.ConnectError("Connection refused")):
            result = self.client.login(self.phone, self.password, use_cache=False)

        self.assertFalse(result.success)
        self.assertEqual(result.code, "EXCEPTION")

    @patch("core.login._save_cache")
    @patch("core.login._load_cache")
    @patch("core.login._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_cache_hit(self, mock_rsa, mock_load, mock_save):
        """缓存命中 - 直接返回成功，不发起网络请求"""
        import time as time_mod
        mock_load.return_value = {
            self.phone: {
                "token": "cached_tok_999",
                "userId": "cached_user_888",
                "t": int(time_mod.time() * 1000) - 3600000,
            }
        }

        post_mock = MagicMock(side_effect=RuntimeError("Should not be called!"))

        with patch.object(self.client.client, "post", post_mock):
            result = self.client.login(self.phone, self.password, use_cache=True)

        self.assertTrue(result.success)
        self.assertEqual(result.token, "cached_tok_999")
        self.assertEqual(result.user_id, "cached_user_888")
        post_mock.assert_not_called()

    @patch("core.login._save_cache")
    @patch("core.login._load_cache", return_value={})
    @patch("core.login._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_with_sms_success(self, mock_rsa, mock_load, mock_save):
        """短信验证码登录成功"""
        resp_json = {
            "responseData": {
                "resultCode": "0000",
                "data": {
                    "loginSuccessResult": {
                        "userId": "user_sms_123",
                        "token": "tok_sms_456",
                    }
                },
            }
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)

        with patch.object(self.client.client, "post", return_value=mock_resp):
            result = self.client.login_with_sms(
                self.phone, self.password, "123456", "verify_token_abc")

        self.assertTrue(result.success)
        self.assertEqual(result.user_id, "user_sms_123")
        self.assertEqual(result.token, "tok_sms_456")


# ---------------------------------------------------------------------------
# 2. RuishuClient 瑞数模块测试
# ---------------------------------------------------------------------------
class TestRuishuClient(unittest.TestCase):
    """RuishuClient 错误处理测试"""

    def setUp(self):
        from core.ruishu import RuishuClient
        self.mock_http = MagicMock()
        self.rs = RuishuClient(self.mock_http)

    def test_init_no_http_client(self):
        """未设置 HTTP 客户端应返回失败"""
        from core.ruishu import RuishuClient
        rs = RuishuClient(None)
        result = rs.init()
        self.assertFalse(result.success)
        self.assertIn("HTTP", result.msg)

    def test_init_page_request_fails(self):
        """页面请求失败应返回失败"""
        self.mock_http.post.side_effect = Exception("Network error")
        result = self.rs.init()
        self.assertFalse(result.success)
        self.assertIn("失败", result.msg)

    def test_init_page_not_200(self):
        """页面返回非200应返回失败"""
        mock_resp = _make_mock_response(status_code=500, text="Server Error")
        self.mock_http.post.return_value = mock_resp
        result = self.rs.init()
        self.assertFalse(result.success)
        self.assertIn("500", result.msg)

    def test_init_no_content_code(self):
        """页面没有 content code 应返回失败"""
        html = "<html><body>Hello</body></html>"
        mock_resp = _make_mock_response(status_code=200, text=html)
        self.mock_http.post.return_value = mock_resp
        result = self.rs.init()
        self.assertFalse(result.success)
        self.assertIn("content", result.msg)

    def test_get_headers_when_unavailable(self):
        """瑞数不可用时 get_headers 仍应返回基础请求头"""
        # 模拟连续失败
        self.rs._available = False
        headers = self.rs.get_headers(sign="test_sign")
        self.assertIn("sign", headers)
        self.assertEqual(headers["sign"], "test_sign")
        # 不应包含 Cookie（因为不可用）
        self.assertNotIn("Cookie", headers)

    def test_reset(self):
        """reset 应重置所有状态"""
        self.rs._available = False
        self.rs._fail_count = 5
        self.rs._cookies = {"test": "value"}
        self.rs.reset()
        self.assertTrue(self.rs._available)
        self.assertEqual(self.rs._fail_count, 0)
        self.assertEqual(self.rs._cookies, {})

    def test_fail_count_threshold(self):
        """连续失败超过阈值应标记为不可用"""
        html = "<html><body>No content</body></html>"
        mock_resp = _make_mock_response(status_code=200, text=html)
        self.mock_http.post.return_value = mock_resp

        # 第一次失败
        self.rs.init()
        self.assertTrue(self.rs.available)
        self.assertEqual(self.rs._fail_count, 1)

        # 第二次失败
        self.rs.init()
        self.assertTrue(self.rs.available)
        self.assertEqual(self.rs._fail_count, 2)

        # 第三次失败 - 应标记为不可用
        self.rs.init()
        self.assertFalse(self.rs.available)
        self.assertEqual(self.rs._fail_count, 3)

        # 第四次 - 应直接返回，不再请求
        self.mock_http.post.reset_mock()
        self.rs.init()
        self.mock_http.post.assert_not_called()


# ---------------------------------------------------------------------------
# 3. TelecomAPI 业务 API 模块测试
# ---------------------------------------------------------------------------
class TestTelecomAPI(unittest.TestCase):
    """TelecomAPI 基础调用测试"""

    def setUp(self):
        from core.api import TelecomAPI
        self.mock_http = MagicMock()
        self.phone = "13800138000"
        self.api = TelecomAPI(self.mock_http, self.phone, sign="test_sign_123")

    def test_user_coin_info_success(self):
        """查询金豆成功"""
        resp_json = {
            "resoultCode": 0,
            "totalCoin": 1000,
            "amountEx": 500,
            "expireDate": 1700000000000,
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)
        self.mock_http.post.return_value = mock_resp

        result = self.api.user_coin_info()
        self.assertTrue(result.ok)
        self.assertEqual(result.data.get("totalCoin"), 1000)

    def test_user_coin_info_failure(self):
        """查询金豆失败"""
        resp_json = {
            "resoultCode": 1001,
            "msg": "参数错误",
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)
        self.mock_http.post.return_value = mock_resp

        result = self.api.user_coin_info()
        self.assertFalse(result.ok)
        self.assertEqual(result.code, 1001)
        self.assertIn("参数错误", result.msg)

    def test_do_sign_success(self):
        """签到成功"""
        resp_json = {
            "resoultCode": 0,
            "data": {
                "code": 1,
                "coin": 50,
                "msg": "签到成功，获得50金豆",
            }
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)
        self.mock_http.post.return_value = mock_resp

        result = self.api.do_sign()
        self.assertTrue(result.ok)
        self.assertTrue(result.data.get("signed"))
        self.assertEqual(result.data.get("coin"), 50)

    def test_get_sign_by_ticket_success(self):
        """通过 ticket 获取 sign 成功"""
        resp_json = {
            "resoultCode": 0,
            "sign": "new_sign_token_abc",
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)
        self.mock_http.get.return_value = mock_resp

        result = self.api.get_sign_by_ticket("test_ticket_123")
        self.assertTrue(result.ok)
        self.assertEqual(self.api.sign, "new_sign_token_abc")

    def test_network_error(self):
        """网络异常应返回失败"""
        self.mock_http.post.side_effect = Exception("Connection timeout")
        result = self.api.user_coin_info()
        self.assertFalse(result.ok)
        self.assertIn("timeout", result.msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
