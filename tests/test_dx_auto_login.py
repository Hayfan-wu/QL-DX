"""
TelecomClient.login() 方法的单元测试
=====================================
覆盖场景:
- 登录成功 (resultCode "0000", 有效 token)
- 登录失败 resultCode "3006" (responseData.data 为 None, 修复后的行为)
- 登录失败其他错误码
- 空响应处理
- 非 JSON 响应处理
- 非 dict 响应处理
- 登录成功但 token 为空
- 缓存命中场景

使用 unittest.mock 模拟 httpx 响应, 无需真实网络请求。
"""

import json
import sys
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

# 确保可以导入项目模块
sys.path.insert(0, "/workspace/QL-DX")

# 需要模拟的重量级依赖 (httpx 已在 mock 中处理, execjs / pycryptodome 仅被间接引用)
import httpx


# ---------------------------------------------------------------------------
# 辅助: 创建模拟的 httpx.Response
# ---------------------------------------------------------------------------
def _make_mock_response(status_code: int = 200, text: str = "", json_data=None):
    """构造一个 mock httpx.Response, 支持 .text, .json(), .status_code"""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = status_code

    if json_data is not None:
        # 当提供 json_data 时, text 也应该是其 JSON 字符串
        json_text = json.dumps(json_data, ensure_ascii=False)
        mock_resp.text = json_text
        mock_resp.json.return_value = json_data
    else:
        mock_resp.text = text
        # 默认尝试解析 text 为 json
        def _json_side_effect():
            return json.loads(text)
        mock_resp.json.side_effect = _json_side_effect

    return mock_resp


# ---------------------------------------------------------------------------
# 测试类
# ---------------------------------------------------------------------------
class TestTelecomClientLogin(unittest.TestCase):
    """TelecomClient.login() 全面测试"""

    # 所有测试共用: mock 掉 _load_cache / _save_cache / _rsa_encrypt 等纯工具函数
    # 避免它们干扰 login 核心逻辑

    def setUp(self):
        """每个测试前: 创建 TelecomClient, mock 掉外部依赖"""
        # 延迟导入, 避免 import 时触发 .env 加载 / 文件创建等副作用
        from dx_auto import TelecomClient

        self.client = TelecomClient()
        self.phone = "13800138000"
        self.password = "TestPass123"

    def tearDown(self):
        self.client.close()

    # ==================== 辅助 mock ====================

    @staticmethod
    def _mock_post(return_value=None):
        """mock self.client.client.post, 返回指定的 return_value"""
        return_value = return_value or MagicMock()

        def _post_side_effect(url, json=None, headers=None, content=None):
            return return_value

        return _post_side_effect

    # ==================== 1. 登录成功 ====================

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache", return_value={})
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_success(self, mock_rsa, mock_load_cache, mock_save_cache):
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

        with patch.object(self.client.client, "post", side_effect=self._mock_post(mock_resp)):
            result = self.client.login(self.phone, self.password)

        self.assertTrue(result)
        self.assertEqual(self.client.userId, "user_abc_123")
        self.assertEqual(self.client.token, "tok_xyz_456")
        self.assertEqual(self.client.phone, self.phone)

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache", return_value={})
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_success_caches_token(self, mock_rsa, mock_load_cache, mock_save_cache):
        """登录成功后应将 token 写入缓存"""
        resp_json = {
            "responseData": {
                "resultCode": "0000",
                "data": {
                    "loginSuccessResult": {
                        "userId": "user_123",
                        "token": "tok_abc",
                    }
                },
            }
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)

        with patch.object(self.client.client, "post", side_effect=self._mock_post(mock_resp)):
            result = self.client.login(self.phone, self.password)

        self.assertTrue(result)
        mock_save_cache.assert_called_once()
        saved_cache = mock_save_cache.call_args[0][0]
        self.assertIn(self.phone, saved_cache)
        self.assertEqual(saved_cache[self.phone]["token"], "tok_abc")
        self.assertEqual(saved_cache[self.phone]["userId"], "user_123")

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache", return_value={})
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_success_but_no_token(self, mock_rsa, mock_load_cache, mock_save_cache):
        """登录返回 0000 但 token 为空 => 应返回 False"""
        resp_json = {
            "responseData": {
                "resultCode": "0000",
                "data": {
                    "loginSuccessResult": {
                        "userId": "user_123",
                        "token": "",
                    }
                },
            }
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)

        with patch.object(self.client.client, "post", side_effect=self._mock_post(mock_resp)):
            result = self.client.login(self.phone, self.password)

        self.assertFalse(result)

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache", return_value={})
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_success_data_none(self, mock_rsa, mock_load_cache, mock_save_cache):
        """登录返回 0000 但 data 字段为 None => loginSuccessResult 也为 None => 无 token => False"""
        resp_json = {
            "responseData": {
                "resultCode": "0000",
                "data": None,
            }
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)

        with patch.object(self.client.client, "post", side_effect=self._mock_post(mock_resp)):
            result = self.client.login(self.phone, self.password)

        self.assertFalse(result)

    # ==================== 2. resultCode "3006" - 修复后的行为 ====================

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache", return_value={})
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_3006_data_none(self, mock_rsa, mock_load_cache, mock_save_cache):
        """
        修复前: resultCode 3006 时 responseData.data 为 None,
                访问 data.get('loginSuccessResult') 会崩溃 ('NoneType' has no attribute 'get')
        修复后: resultCode 3006 走 elif 分支, 直接返回 False, 不访问 data 字段
        """
        resp_json = {
            "responseData": {
                "resultCode": "3006",
                "resultDesc": "密码错误",
                "data": None,  # 关键: data 为 None
            }
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)

        with patch.object(self.client.client, "post", side_effect=self._mock_post(mock_resp)):
            result = self.client.login(self.phone, self.password)

        # 修复后: 应返回 False (而不是崩溃或返回 True)
        self.assertFalse(result)
        self.assertEqual(self.client.token, "")

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache", return_value={})
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_3006_no_data_field(self, mock_rsa, mock_load_cache, mock_save_cache):
        """resultCode 3006, responseData 中完全没有 data 字段"""
        resp_json = {
            "responseData": {
                "resultCode": "3006",
                "resultDesc": "需要短信验证",
            }
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)

        with patch.object(self.client.client, "post", side_effect=self._mock_post(mock_resp)):
            result = self.client.login(self.phone, self.password)

        self.assertFalse(result)

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache", return_value={})
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_3006_no_result_desc(self, mock_rsa, mock_load_cache, mock_save_cache):
        """resultCode 3006, 无 resultDesc => 使用默认提示信息"""
        resp_json = {
            "responseData": {
                "resultCode": "3006",
                "data": None,
            }
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)

        with patch.object(self.client.client, "post", side_effect=self._mock_post(mock_resp)):
            result = self.client.login(self.phone, self.password)

        self.assertFalse(result)

    # ==================== 3. 其他错误码 ====================

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache", return_value={})
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_error_code_9999(self, mock_rsa, mock_load_cache, mock_save_cache):
        """未知错误码, 走 else 分支"""
        resp_json = {
            "responseData": {
                "resultCode": "9999",
                "resultDesc": "系统繁忙",
            }
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)

        with patch.object(self.client.client, "post", side_effect=self._mock_post(mock_resp)):
            result = self.client.login(self.phone, self.password)

        self.assertFalse(result)

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache", return_value={})
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_error_code_with_msg(self, mock_rsa, mock_load_cache, mock_save_cache):
        """错误码, 使用顶层 msg 字段"""
        resp_json = {
            "msg": "参数错误",
            "responseData": {
                "resultCode": "1001",
            }
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)

        with patch.object(self.client.client, "post", side_effect=self._mock_post(mock_resp)):
            result = self.client.login(self.phone, self.password)

        self.assertFalse(result)

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache", return_value={})
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_error_code_with_header_reason(self, mock_rsa, mock_load_cache, mock_save_cache):
        """错误码, 仅有 headerInfos.reason 作为错误描述"""
        resp_json = {
            "headerInfos": {
                "reason": "账号被锁定",
            },
            "responseData": {
                "resultCode": "2001",
            }
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)

        with patch.object(self.client.client, "post", side_effect=self._mock_post(mock_resp)):
            result = self.client.login(self.phone, self.password)

        self.assertFalse(result)

    # ==================== 4. 空响应 ====================

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache", return_value={})
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_empty_response_text(self, mock_rsa, mock_load_cache, mock_save_cache):
        """响应体为空字符串"""
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.text = ""

        with patch.object(self.client.client, "post", side_effect=self._mock_post(mock_resp)):
            result = self.client.login(self.phone, self.password)

        self.assertFalse(result)

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache", return_value={})
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_none_response_text(self, mock_rsa, mock_load_cache, mock_save_cache):
        """响应 text 属性为 None (模拟某些异常情况)"""
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.text = None

        with patch.object(self.client.client, "post", side_effect=self._mock_post(mock_resp)):
            result = self.client.login(self.phone, self.password)

        self.assertFalse(result)

    # ==================== 5. 非 JSON 响应 ====================

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache", return_value={})
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_non_json_response(self, mock_rsa, mock_load_cache, mock_save_cache):
        """响应体不是合法 JSON (HTML 错误页面等)"""
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.text = "<html><body>Internal Server Error</body></html>"
        mock_resp.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)

        with patch.object(self.client.client, "post", side_effect=self._mock_post(mock_resp)):
            result = self.client.login(self.phone, self.password)

        self.assertFalse(result)

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache", return_value={})
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_plain_text_response(self, mock_rsa, mock_load_cache, mock_save_cache):
        """响应体是纯文本 (如 "Service Unavailable")"""
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 503
        mock_resp.text = "Service Unavailable"
        mock_resp.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)

        with patch.object(self.client.client, "post", side_effect=self._mock_post(mock_resp)):
            result = self.client.login(self.phone, self.password)

        self.assertFalse(result)

    # ==================== 6. 非 dict 响应 ====================

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache", return_value={})
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_response_is_list(self, mock_rsa, mock_load_cache, mock_save_cache):
        """响应 JSON 是 list 而非 dict"""
        mock_resp = _make_mock_response(status_code=200, json_data=[{"errorCode": "0000"}])

        with patch.object(self.client.client, "post", side_effect=self._mock_post(mock_resp)):
            result = self.client.login(self.phone, self.password)

        self.assertFalse(result)

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache", return_value={})
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_response_is_string(self, mock_rsa, mock_load_cache, mock_save_cache):
        """响应 JSON 是字符串 'OK'"""
        mock_resp = _make_mock_response(status_code=200, json_data="OK")

        with patch.object(self.client.client, "post", side_effect=self._mock_post(mock_resp)):
            result = self.client.login(self.phone, self.password)

        self.assertFalse(result)

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache", return_value={})
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_response_is_number(self, mock_rsa, mock_load_cache, mock_save_cache):
        """响应 JSON 是数字"""
        mock_resp = _make_mock_response(status_code=200, json_data=200)

        with patch.object(self.client.client, "post", side_effect=self._mock_post(mock_resp)):
            result = self.client.login(self.phone, self.password)

        self.assertFalse(result)

    # ==================== 7. responseData 异常情况 ====================

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache", return_value={})
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_response_data_none(self, mock_rsa, mock_load_cache, mock_save_cache):
        """responseData 字段为 None => resp_data fallback 为 {} => result_code 非已知值 => False"""
        resp_json = {
            "responseData": None,
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)

        with patch.object(self.client.client, "post", side_effect=self._mock_post(mock_resp)):
            result = self.client.login(self.phone, self.password)

        self.assertFalse(result)

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache", return_value={})
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_response_data_is_string(self, mock_rsa, mock_load_cache, mock_save_cache):
        """responseData 是字符串而非 dict => 走 else 分支"""
        resp_json = {
            "responseData": "some_error_string",
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)

        with patch.object(self.client.client, "post", side_effect=self._mock_post(mock_resp)):
            result = self.client.login(self.phone, self.password)

        self.assertFalse(result)

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache", return_value={})
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_no_response_data_key(self, mock_rsa, mock_load_cache, mock_save_cache):
        """响应中没有 responseData 键 => fallback 为 {} => 默认 result_code"""
        resp_json = {
            "resultCode": "5000",
            "msg": "服务器错误",
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)

        with patch.object(self.client.client, "post", side_effect=self._mock_post(mock_resp)):
            result = self.client.login(self.phone, self.password)

        self.assertFalse(result)

    # ==================== 8. 网络异常 ====================

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache", return_value={})
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_network_error(self, mock_rsa, mock_load_cache, mock_save_cache):
        """网络异常 (httpx.ConnectError) => 应捕获并返回 False"""
        with patch.object(self.client.client, "post", side_effect=httpx.ConnectError("Connection refused")):
            result = self.client.login(self.phone, self.password)

        self.assertFalse(result)

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache", return_value={})
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_timeout(self, mock_rsa, mock_load_cache, mock_save_cache):
        """请求超时 => 应捕获并返回 False"""
        with patch.object(self.client.client, "post", side_effect=httpx.TimeoutException("Timeout")):
            result = self.client.login(self.phone, self.password)

        self.assertFalse(result)

    # ==================== 9. 缓存命中 ====================

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache")
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_cache_hit(self, mock_rsa, mock_load_cache, mock_save_cache):
        """缓存中有有效 token => 直接返回 True, 不发起网络请求"""
        import time as time_mod
        mock_load_cache.return_value = {
            self.phone: {
                "token": "cached_tok_999",
                "userId": "cached_user_888",
                "t": int(time_mod.time() * 1000) - 3600000,  # 1小时前, 未超过24小时
            }
        }

        post_mock = MagicMock(side_effect=RuntimeError("Should not be called!"))

        with patch.object(self.client.client, "post", post_mock):
            result = self.client.login(self.phone, self.password)

        self.assertTrue(result)
        self.assertEqual(self.client.token, "cached_tok_999")
        self.assertEqual(self.client.userId, "cached_user_888")
        # post 不应被调用 (缓存命中)
        post_mock.assert_not_called()

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache")
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_cache_expired(self, mock_rsa, mock_load_cache, mock_save_cache):
        """缓存已过期 (超过24小时) => 应重新发起登录请求"""
        import time as time_mod
        mock_load_cache.return_value = {
            self.phone: {
                "token": "expired_tok",
                "userId": "expired_user",
                "t": int(time_mod.time() * 1000) - 100000000,  # 远超24小时
            }
        }

        resp_json = {
            "responseData": {
                "resultCode": "0000",
                "data": {
                    "loginSuccessResult": {
                        "userId": "new_user",
                        "token": "new_tok",
                    }
                },
            }
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)

        with patch.object(self.client.client, "post", side_effect=self._mock_post(mock_resp)):
            result = self.client.login(self.phone, self.password)

        self.assertTrue(result)
        self.assertEqual(self.client.token, "new_tok")
        self.assertEqual(self.client.userId, "new_user")

    @patch("dx_auto._save_cache")
    @patch("dx_auto._load_cache")
    @patch("dx_auto._rsa_encrypt", return_value="FAKE_ENCRYPTED")
    def test_login_cache_no_token(self, mock_rsa, mock_load_cache, mock_save_cache):
        """缓存中有条目但 token 为空 => 应重新发起登录请求"""
        import time as time_mod
        mock_load_cache.return_value = {
            self.phone: {
                "token": "",
                "userId": "cached_user",
                "t": int(time_mod.time() * 1000) - 3600000,
            }
        }

        resp_json = {
            "responseData": {
                "resultCode": "0000",
                "data": {
                    "loginSuccessResult": {
                        "userId": "fresh_user",
                        "token": "fresh_tok",
                    }
                },
            }
        }
        mock_resp = _make_mock_response(status_code=200, json_data=resp_json)

        with patch.object(self.client.client, "post", side_effect=self._mock_post(mock_resp)):
            result = self.client.login(self.phone, self.password)

        self.assertTrue(result)
        self.assertEqual(self.client.token, "fresh_tok")


if __name__ == "__main__":
    unittest.main(verbosity=2)
