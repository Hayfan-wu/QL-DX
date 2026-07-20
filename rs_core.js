/**
 * 中国电信话费自动化 - 瑞数反爬绕过核心
 * ============================================
 * 模拟浏览器 DOM 环境，执行瑞数 JS 挑战脚本获取 Cookie。
 * 配合 execjs 在 Python 中调用。
 *
 * 用法: Python 中注入 content_code 和 ts_code 后调用 main()
 *   返回: cookie 字符串 (格式: yiUIIlbdQT3fP=xxxxx)
 */

// 清除 Node.js 特征
delete __filename;
delete __dirname;
ActiveXObject = undefined;

// 全局浏览器对象模拟
window = global;
self = global;
top = global;
parent = global;
globalThis = global;

// navigator 模拟
navigator = {
    platform: "Linux aarch64",
    userAgent: "CtClient;11.0.0;Android;13;22081212C;NTIyMTcw!#!MTUzNzY"
};

// location 模拟
location = {
    href: "https://",
    origin: "",
    protocol: "",
    host: "",
    hostname: "",
    port: "",
    pathname: "",
    search: "",
    hash: ""
};

// content 占位符，运行时注入
content = "CONTENT_PLACEHOLDER";

// DOM 对象模拟
i = { length: 0 };
base = { length: 0 };

div = {
    getElementsByTagName: function (res) {
        if (res === 'i') {
            return i;
        }
        return '<div></div>';
    }
};

script = {};

meta = [
    { charset: "UTF-8" },
    {
        content: content,
        getAttribute: function (res) {
            if (res === 'r') {
                return 'm';
            }
        },
        parentNode: {
            removeChild: function (res) {
                return content;
            }
        }
    }
];

form = '<form></form>';

// 空函数处理
window.addEventListener = function (res) {};
setInterval = function () {};
setTimeout = function () {};

// document 模拟
document = {
    createElement: function (res) {
        if (res === 'div') {
            return div;
        } else if (res === 'form') {
            return form;
        }
        return res;
    },
    addEventListener: function (res) {},
    appendChild: function (res) {
        return res;
    },
    removeChild: function (res) {},
    getElementsByTagName: function (res) {
        if (res === 'script') {
            return script;
        }
        if (res === 'meta') {
            return meta;
        }
        if (res === 'base') {
            return base;
        }
    },
    getElementById: function (res) {
        if (res === 'root-hammerhead-shadow-ui') {
            return null;
        }
    }
};

window.top = window;

// ==================== 瑞数挑战代码注入点 ====================
// TS_CODE_PLACEHOLDER 会在运行时被替换为实际的瑞数 JS 代码

// ==================== 主函数 ====================
function main() {
    cookie = document.cookie.split(';')[0];
    return cookie;
}