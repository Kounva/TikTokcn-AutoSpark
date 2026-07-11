"""抖音自动续火花 - 后端主入口

模块拆分后的主入口文件，只包含：
- FastAPI 实例与中间件
- 所有 HTTP 路由
- 前端 SPA 静态文件托管
- 服务启动逻辑

业务逻辑分散在各子模块中：
  config.py          - 配置与常量
  runtime.py         - 运行时全局状态（driver/douyin/init 等）
  utils.py           - 通用工具与数据类
  browser_manager.py - 浏览器驱动管理
  risk_control.py    - 风控与消息选择
  auth.py            - 认证鉴权
  douyin_sticker.py  - 表情包 Mixin
  douyin_core.py     - Douyin 核心类
  scheduler.py       - 定时任务调度
"""
import os
import re
import gzip
import json
import time
import base64
import random
import platform
import atexit
import uvicorn
from datetime import datetime

from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import SessionNotCreatedException
from selenium.common.exceptions import WebDriverException

from fastapi import FastAPI, Header, Request, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware

# 本项目模块
from backend.config import (
    config, save_config, BASE_DIR, DIST_DIR,
    normalize_browser_name, get_browser_label, get_profile_dir,
    clamp_int, normalize_message_templates, DEFAULT_MESSAGE_TEMPLATES,
    is_port_in_use, find_available_port,
)
from backend import runtime
from backend.runtime import _user_cache, init_lock
from backend.utils import format_time
from backend.browser_manager import create_webdriver, check_driver, cleanup_on_exit
from backend.risk_control import (
    risk_state, prune_risk_state, save_risk_state,
    pause_risk, resume_risk,
    record_send_success, record_send_failure,
)
from backend.auth import (
    hash_pwd, verify_pwd, generate_token, verify_token, remove_token,
    require_auth,
)
from backend.douyin_core import Douyin
from backend.scheduler import (
    scheduled_tasks, save_tasks, schedule_task, restore_tasks, start_scheduler,
)

# 运行时全局状态（会重新绑定的变量从 runtime 访问）
# driver / douyin / init / Login_is_bool → runtime.xxx
# _user_cache / init_lock → 已从 runtime 导入

app = FastAPI()

# CORS 配置（前后端同源，仅允许本地访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://127.0.0.1", "http://localhost:8080", "http://127.0.0.1:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# API 前缀重写中间件：将 /api/xxx 转发到 /xxx
class APIRewriteMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        if path.startswith('/api/'):
            request.scope['path'] = path[4:]
        return await call_next(request)


app.add_middleware(APIRewriteMiddleware)

# 服务启动时间
runtime.start_time = datetime.now()


# ===== 抖音操作路由 =====

@app.get('/Home')
def Home(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    return {'time': runtime.start_time}


@app.get('/Api/Init')  # 初始化浏览器
def Init(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err

    with init_lock:  # 加锁，防止重复点击触发多次初始化
        if runtime.init:
            return {'code': 200, 'data': 'init Repeated!'}
        try:
            browser_name = normalize_browser_name(config.get('browser_name'))
            runtime.driver = create_webdriver()
            runtime.driver.set_window_size(1400, 900)
            # 设置页面加载策略为 eager（DOM 就绪即可，不等所有资源）
            try:
                runtime.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            except Exception:
                pass
            # 打开抖音聊天页（设置较短的超时，避免长时间卡住）
            runtime.driver.set_page_load_timeout(30)
            try:
                runtime.driver.get('https://www.douyin.com/chat?isPopup=1')
            except Exception:
                # 页面加载超时也继续（SPA 页面可能触发超时但 DOM 已就绪）
                pass
            runtime.douyin = Douyin(runtime.driver)
            runtime.init = True
            runtime.Login_is_bool = False  # 新会话默认未登录
            _user_cache['nickname'] = ''
            _user_cache['avatar'] = ''
            start_scheduler()  # 启动调度线程
            restore_tasks()  # 恢复持久化的定时任务
            return {'code': 200, 'data': f'{get_browser_label(browser_name)} 初始化成功'}
        except SessionNotCreatedException:
            return {'code': 400, 'data': '浏览器驱动启动失败，请检查浏览器版本或切换浏览器'}
        except WebDriverException:
            browser_name = normalize_browser_name(config.get('browser_name'))
            browser_path = (config.get('browser_path') or '').strip()
            if browser_path:
                return {'code': 500, 'data': f'{get_browser_label(browser_name)} 启动失败，请检查路径是否正确: {browser_path}'}
            return {'code': 500, 'data': f'{get_browser_label(browser_name)} 启动失败，请确认已安装浏览器'}
        except Exception as e:
            return {'code': 500, 'data': f'初始化失败: {str(e) or "未知错误"}'}


@app.get('/Api/GetInit')  # 获取初始化状态
def GetInit(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    return {'code': 200, 'data': 'Yes' if runtime.init else 'No'}


@app.post('/Api/login')  # 登录 传入cooke
def Login(cooke: str = Body(default=None), gzip_flag: bool = Body(default=False), authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
    if cooke:
        try:
            decoded_bytes = base64.b64decode(cooke)
            if gzip_flag:
                try:
                    decoded_bytes = gzip.decompress(decoded_bytes)
                except Exception:
                    return {'code': 404,
                            'data': 'login-error-gzip decompress failed, check cookie format and gzip flag'}
            cookie_list = decoded_bytes.decode('utf-8')
            # 前端做了 JSON.stringify(cookie)，需要先 json.loads 去掉外层引号
            cookie_b64 = json.loads(cookie_list)
            # 再 base64 解码得到 cookie JSON
            cookie_json = base64.b64decode(cookie_b64).decode('utf-8')
            cookies = json.loads(cookie_json)
            for cookie in cookies:
                runtime.driver.add_cookie(cookie)
        except Exception as e:
            return {'code': 404, 'data': 'Cookie格式错误，请检查'}
        runtime.driver.refresh()
        try:
            login_type_element = runtime.driver.find_element(By.XPATH, '//*[@id="douyin_login_comp_flat_panel"]/picture')
            login_type = login_type_element.text
            return {'code': 404, 'data': 'login-error-cooker cant login'}
        except NoSuchElementException:
            runtime.Login_is_bool = True
            return {'code': 200, 'data': 'ok'}
    else:
        return {'code': 404, 'data': 'login-error-not cooker'}


@app.get('/Api/Pnglogin')  # 扫码登录后检查状态
def PngLogin(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
    # 刷新页面检查登录状态（无需 cookie 自循环）
    runtime.driver.refresh()
    try:
        login_type_element = runtime.driver.find_element(By.XPATH, '//*[@id="douyin_login_comp_flat_panel"]/picture')
        # 找到登录弹窗 = 未登录
        runtime.Login_is_bool = False
        return {'code': 404, 'data': '系统繁忙,请稍后重新登录'}
    except NoSuchElementException:
        # 没有登录弹窗 = 已登录
        runtime.Login_is_bool = True
        return {'code': 200, 'data': 'ok'}


@app.get('/Api/GetLogin')  # 获取登录
def GetLogin(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    # 实际检查抖音页面登录状态，而非只看缓存标记
    if not runtime.init or runtime.driver is None:
        runtime.Login_is_bool = False
        return {'code': 200, 'data': 'No'}
    try:
        # 短暂等待页面渲染（降低频率，避免频繁触发风控）
        time.sleep(0.3)
        runtime.driver.find_element(By.XPATH, '//*[@id="douyin_login_comp_flat_panel"]/picture')
        # 找到登录弹窗 = 未登录
        runtime.Login_is_bool = False
        return {'code': 200, 'data': 'No'}
    except NoSuchElementException:
        # 没有登录弹窗 = 已登录
        runtime.Login_is_bool = True
        return {'code': 200, 'data': 'Yes'}
    except Exception:
        # 页面异常时回退到缓存标记
        return {'code': 200, 'data': 'Yes' if runtime.Login_is_bool else 'No'}


@app.get('/Api/login/Init/GetLoginPng')  # 获取登录扫码
def GetLoginPng(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    try:
        drv_err = check_driver()
        if drv_err:
            return drv_err
        Douyin.LoginInit(runtime.douyin)
        try:
            error = runtime.driver.find_element(By.XPATH, '//*[@id="animate_qrcode_container"]/div[2]/div/p[1]')
            img_element = runtime.driver.find_element(By.XPATH, '//*[@id="animate_qrcode_container"]/div[2]/img')
            img_element.click()
        except:
            pass
        img_element = runtime.driver.find_element(By.XPATH, '//*[@id="animate_qrcode_container"]/div[2]/img')
        login_src = img_element.get_attribute('src')
        try:
            is_rust = runtime.driver.find_element(By.XPATH, '//*[@id="animate_qrcode_container"]/div[2]/div')
            is_rust.click()
            time.sleep(5)
            img_element = runtime.driver.find_element(By.XPATH, '//*[@id="animate_qrcode_container"]/div[2]/img')
            login_src = img_element.get_attribute('src')
        except:
            pass
        if login_src:
            return {'code': 200, 'data': login_src}
        else:
            return {'code': 404, 'data': 'cant find LoginPng src attribute'}
    except NoSuchElementException:
        return {'code': 404, 'data': 'cant find img element'}
    except Exception as e:
        msg = str(e)
        if 'InvalidSessionId' in msg or 'session' in msg.lower():
            return {'code': 500, 'data': '浏览器会话已断开，请重新初始化'}
        return {'code': 500, 'data': '获取二维码失败，请确保浏览器已正常启动'}


@app.get('/Api/login/Init/GetCooker')  # 获取cooke
def GetCooke(password: str = Query(None), authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    # 验证密码
    if not password or not verify_pwd(password):
        return {'code': 400, 'data': '密码错误'}
    drv_err = check_driver()
    if drv_err:
        return drv_err
    if runtime.Login_is_bool:
        try:
            cooke = runtime.driver.get_cookies()
            cookie_json = json.dumps(cooke)
            cookie_base64 = base64.b64encode(cookie_json.encode('utf-8')).decode('utf-8')
            return {'code': 200, 'data': {'cooke': cookie_base64}}
        except Exception as e:
            return {'code': 500, 'data': '获取Cookie失败'}
    else:
        return {'code': 400, 'data': '未登录'}


@app.get('/Api/GetFriendsList')  # 获取好友列表
def GetFrindesList(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
    try:
        friends_list = runtime.douyin.Updara_FrinderList()
        if not friends_list:
            return {'code': 404, 'data': '暂无好友或页面未加载'}
        dicts = {}
        for v in friends_list:
            dicts[v.username] = [v.avatar, v.fire]
        return {'code': 200, 'data': {'count': len(friends_list), 'list': dicts}}
    except Exception as e:
        return {'code': 404, 'data': '发送失败'}


@app.get('/Api/Send')  # 发送信息
def Send(name: str, text: str, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
    try:
        out = Douyin.Send_Frinder(runtime.douyin, name, text)
        if out.is_bool:
            record_send_success(name, text, 'manual')
            return {'code': 200, 'data': 'Send successfully'}
        else:
            record_send_failure(f'手动发送失败：{out.string or "发送失败"}')
            return {'code': 404, 'data': out.string or '发送失败'}
    except Exception as e:
        record_send_failure(f'手动发送异常：{str(e) or "发送失败"}')
        return {'code': 500, 'data': '发送失败'}


@app.get('/Api/GetStickerList')  # 获取表情包列表
def GetStickerList(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
    try:
        result = runtime.douyin.Get_Sticker_List()
        return result
    except Exception as e:
        return {'code': 500, 'data': '获取表情包失败'}


@app.get('/Api/SendSticker')  # 发送表情包
def SendSticker(name: str, sticker_index: int, sticker_src: str = Query(None), authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
    try:
        out = runtime.douyin.Send_Sticker(name, sticker_index, sticker_src)
        if out.is_bool:
            record_send_success(name, f'[sticker]{sticker_index}', 'sticker')
            return {'code': 200, 'data': '表情包发送成功'}
        else:
            record_send_failure(f'发送表情包失败：{str(out.string) if out.string else "发送失败"}')
            return {'code': 400, 'data': str(out.string) if out.string else '发送失败'}
    except Exception as e:
        record_send_failure(f'发送表情包异常：{str(e) or "发送失败"}')
        return {'code': 500, 'data': '发送表情包失败'}


@app.get('/Api/GetChatHistory')  # 获取聊天记录
def GetChatHistory(name: str, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
    try:
        result = runtime.douyin.Get_Chat_History(name)
        return result
    except Exception as e:
        return {'code': 500, 'data': '获取聊天记录失败'}


@app.get('/Api/GetUsername')  # 获取用户名和头像
def GetUserInfo(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
    if not runtime.Login_is_bool:
        return {'code': 200, 'data': {'nickname': '', 'avatar': ''}}

    # 有缓存直接返回
    if _user_cache['nickname'] and _user_cache['nickname'] != '未知用户':
        return {'code': 200, 'data': dict(_user_cache)}

    nickname = ''
    avatar = ''

    # 方法1：同步JS提取（不使用async，避免超时问题）
    # 从页面全局变量、localStorage、cookie、DOM 同步读取
    try:
        info = runtime.driver.execute_script(r'''
            var result = {nick:'', av:''};
            // 1. window 全局变量
            try {
                var sigi = window.SIGI_STATE || window.__INIT_PROPS__;
                if (sigi) {
                    var str = JSON.stringify(sigi);
                    var nm = str.match(/"nickname"\s*:\s*"([^"]+)"/);
                    if (nm && nm[1]) result.nick = nm[1];
                    var am = str.match(/"avatar_(?:thumb|medium|larger)"\s*:\s*\{[^}]*"url_list"\s*:\s*\["([^"]+)"/);
                    if (am) result.av = am[1].replace(/\\u002F/g,'/');
                }
            } catch(e) {}
            // 2. localStorage / sessionStorage 遍历所有key
            if (!result.nick) {
                try {
                    var stores = [localStorage, sessionStorage];
                    for (var s = 0; s < stores.length; s++) {
                        for (var i = 0; i < stores[s].length; i++) {
                            var k = stores[s].key(i);
                            try {
                                var v = stores[s].getItem(k);
                                if (!v || v.length < 5) continue;
                                if (v.indexOf('nickname') !== -1 || v.indexOf('avatar') !== -1 ||
                                    v.indexOf('user_info') !== -1 || k.toLowerCase().indexOf('user') !== -1) {
                                    var nm2 = v.match(/"nickname"\s*:\s*"([^"]+)"/);
                                    if (nm2 && nm2[1] && !result.nick) result.nick = nm2[1];
                                    var am2 = v.match(/"avatar_(?:thumb|medium|larger)"\s*:\s*\{[^}]*"url_list"\s*:\s*\["([^"]+)"/);
                                    if (am2 && !result.av) result.av = am2[1].replace(/\\u002F/g,'/');
                                    var am3 = v.match(/"avatar"\s*:\s*"([^"]+)"/);
                                    if (am3 && am3[1] && !result.av && am3[1].indexOf('http') === 0) result.av = am3[1];
                                }
                            } catch(e) {}
                        }
                    }
                } catch(e) {}
            }
            // 3. document.cookie 查找
            if (!result.nick) {
                try {
                    var ck = document.cookie;
                    // 抖音可能在cookie中存passport_csrf_token或odin_tt等，但昵称一般不在cookie中
                    // 不处理cookie
                } catch(e) {}
            }
            // 4. DOM提取：右上角头像和用户名
            try {
                // 头像：页面顶部所有图片
                var allImgs = document.querySelectorAll('img');
                for (var i = 0; i < allImgs.length; i++) {
                    var src = allImgs[i].src || '';
                    var r = allImgs[i].getBoundingClientRect();
                    if (src && src.length > 20 && r.top < 80 && r.top >= 0 && r.width >= 20 && r.width <= 80 && r.height >= 20 && r.height <= 80) {
                        // 排除logo
                        if (src.indexOf('logo') !== -1 || src.indexOf('Logo') !== -1) continue;
                        // douyin CDN图片
                        if (src.indexOf('douyinpic') !== -1 || src.indexOf('byteimg') !== -1 || src.indexOf('tos-cn') !== -1) {
                            // 检查是否是头像（URL特征或尺寸为圆形）
                            var style = window.getComputedStyle(allImgs[i]);
                            if (src.indexOf('avatar') !== -1 || src.indexOf('/head_') !== -1 ||
                                style.borderRadius.indexOf('%') !== -1 || parseFloat(style.borderRadius) > 10 ||
                                /\/\d+x\d+\//.test(src)) {
                                result.av = src;
                                break;
                            }
                        }
                    }
                }
            } catch(e) {}
            return result;
        ''')
        if info:
            nickname = (info.get('nick') or '').strip()
            avatar = (info.get('av') or '').strip().replace('&amp;', '&')
    except Exception:
        pass

    # 方法2：从当前页面源码正则提取（同步，最快）
    if not nickname or not avatar:
        try:
            page = runtime.driver.page_source
            if not nickname:
                for pat in [r'"nickname"\s*:\s*"([^"]+)"']:
                    m = re.search(pat, page)
                    if m and m.group(1).strip() and len(m.group(1).strip()) < 30 and m.group(1).strip() != '抖音':
                        nickname = m.group(1).strip()
                        break
            if not avatar:
                for pat in [r'"avatar_thumb"\s*:\s*\{\s*"url_list"\s*:\s*\[\s*"([^"]+)"',
                            r'"avatar_medium"\s*:\s*\{\s*"url_list"\s*:\s*\[\s*"([^"]+)"',
                            r'"avatar_larger"\s*:\s*\{\s*"url_list"\s*:\s*\[\s*"([^"]+)"']:
                    m = re.search(pat, page)
                    if m:
                        avatar = m.group(1).replace('\\u002F', '/').replace('&amp;', '&')
                        break
        except Exception:
            pass

    # 方法3：导航到抖音首页（不是个人页，首页加载快），从首页提取
    if not nickname or not avatar:
        try:
            current = runtime.driver.current_url
            old_timeout = runtime.driver.page_load_timeout
            runtime.driver.set_page_load_timeout(8)
            try:
                runtime.driver.get('https://www.douyin.com/')
            except Exception:
                pass
            runtime.driver.set_page_load_timeout(old_timeout)
            time.sleep(2)
            # 一键登录弹窗处理
            try:
                runtime.driver.execute_script('''
                    var btns = document.querySelectorAll('button, [role="button"], span, div');
                    for (var i = 0; i < btns.length; i++) {
                        if ((btns[i].textContent||'').trim().indexOf('一键登录') !== -1) { btns[i].click(); break; }
                    }
                ''')
                time.sleep(2)
            except Exception:
                pass
            # 从首页提取
            try:
                page = runtime.driver.page_source
                if not nickname:
                    for pat in [r'"nickname"\s*:\s*"([^"]+)"']:
                        m = re.search(pat, page)
                        if m and m.group(1).strip() and len(m.group(1).strip()) < 30 and m.group(1).strip() != '抖音':
                            nickname = m.group(1).strip()
                            break
                if not avatar:
                    for pat in [r'"avatar_thumb"\s*:\s*\{\s*"url_list"\s*:\s*\[\s*"([^"]+)"',
                                r'"avatar_medium"\s*:\s*\{\s*"url_list"\s*:\s*\[\s*"([^"]+)"',
                                r'"avatar_larger"\s*:\s*\{\s*"url_list"\s*:\s*\[\s*"([^"]+)"']:
                        m = re.search(pat, page)
                        if m:
                            avatar = m.group(1).replace('\\u002F', '/').replace('&amp;', '&')
                            break
            except Exception:
                pass
            # DOM提取
            if not avatar:
                try:
                    av_info = runtime.driver.execute_script(r'''
                        var imgs = document.querySelectorAll('img');
                        for (var i = 0; i < imgs.length; i++) {
                            var src = imgs[i].src || '';
                            var r = imgs[i].getBoundingClientRect();
                            if (src && r.top < 80 && r.top >= 0 && r.width >= 24 && r.width <= 60 && r.height >= 24 && r.height <= 60) {
                                if (src.indexOf('douyinpic') !== -1 || src.indexOf('byteimg') !== -1 || src.indexOf('tos-cn') !== -1) {
                                    var style = window.getComputedStyle(imgs[i]);
                                    if (src.indexOf('avatar') !== -1 || parseFloat(style.borderRadius) > 10 || /\/\d+x\d+\//.test(src)) {
                                        return src;
                                    }
                                }
                            }
                        }
                        return '';
                    ''')
                    if av_info:
                        avatar = av_info
                except Exception:
                    pass
            # 回聊天页
            try:
                runtime.driver.get('https://www.douyin.com/chat?isPopup=1')
                time.sleep(1)
            except Exception:
                pass
        except Exception:
            pass

    # 更新缓存
    if nickname and nickname != '未知用户' and nickname != '抖音':
        _user_cache['nickname'] = nickname
        _user_cache['avatar'] = avatar
        return {'code': 200, 'data': {'nickname': nickname, 'avatar': avatar}}
    else:
        return {'code': 200, 'data': {'nickname': '', 'avatar': avatar}}


@app.get('/Api/GetScrlk')  # 获取截图
def GetScrlk(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
    try:
        runtime.driver.save_screenshot("temp.png")
        with open("temp.png", "rb") as f:
            img_data = base64.b64encode(f.read()).decode('utf-8')
        os.remove("temp.png")
        return {'code': 200, 'data': img_data}
    except Exception as e:
        return {'code': 400, 'data': f'截图错误:{e}'}


@app.get('/Api/DieLogin')  # 取消登录
def DieLogin(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
    try:
        runtime.driver.delete_all_cookies()
        runtime.driver.refresh()
        runtime.Login_is_bool = False
        _user_cache['nickname'] = ''
        _user_cache['avatar'] = ''
        return {'code': 200, 'data': '已清除Cooke'}
    except Exception as e:
        return {'code': 500, 'data': '清除Cookie失败'}


@app.get('/Api/LoginPhone')  # 验证码登录
def LoginPhone(areacode: str, phone: str, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
    try:
        Douyin.LoginInit(runtime.douyin)
        areacode_value = runtime.driver.find_element(By.XPATH, '//*[@id="douyin_login_comp_normal_input_id"]/div[1]/div/input')
        areacode_value.clear()
        areacode_value.send_keys(areacode.strip())
        inp = runtime.driver.find_element(By.XPATH, '//*[@id="normal-input"]')
        inp.send_keys(phone)
        span = runtime.driver.find_element(By.XPATH, '//*[@id="douyin_login_comp_button_input_id"]/span')
        span.click()
        time.sleep(2)
        if span.text.strip() == '获取验证码':
            return {'code': 400, 'data': '验证码发送失败'}
        else:
            return {'code': 200, 'data': '验证码发送成功'}
    except Exception as e:
        return {'code': 400, 'data': '验证码发送失败'}


@app.get('/Api/LoginPhoneInput')  # 验证码登录 2 输入验证码
def LoginPhoneInput(code: str, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
    try:
        inp = runtime.driver.find_element(By.XPATH, '//*[@id="button-input"]')
        inp.send_keys(code)
        button = runtime.driver.find_element(By.XPATH, '//*[@id="douyin_login_comp_btn_id"]')
        button.click()
        time.sleep(2)
        try:
            login_div = runtime.driver.find_element(By.XPATH, '//*[@id="douyin_login_comp_flat_panel"]/picture')
            return {'code': 400, 'data': '登录失败'}
        except:
            runtime.Login_is_bool = True
            return {'code': 200, 'data': '登录成功'}
    except Exception as e:
        return {'code': 400, 'data': '验证码登录失败'}


@app.get('/Api/LoginDebug')  # 强制登录状态（调试用，需密码确认）
def LoginDebug(password: str = Query(None), authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    # 调试接口需二次密码确认，防止误用
    if not password or not verify_pwd(password):
        return {'code': 403, 'data': '需要密码确认才能使用此功能'}
    if runtime.Login_is_bool == False:
        runtime.Login_is_bool = True
        return {'code': 200, 'data': 'OK'}
    else:
        return {'code': 400, 'data': '已是登录状态,无需设定'}


# ===== 定时任务操作 =====

@app.get('/Time/add')
def add_time(time: str, name: str, text: str = None, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
    # 检查是否已存在该好友的定时任务
    for task_id, task in scheduled_tasks.items():
        if task_id.endswith(f"_{name}"):
            return {'code': 400, 'data': f'好友 {name} 已有定时任务，请先删除或修改'}

    temp = runtime.douyin.Find_Friends(name)
    if temp.is_bool:
        play_time = format_time(time)
        msg = '' if text is None else text
        # 生成唯一任务ID
        task_id = f"{play_time}_{name}"
        schedule_task(task_id, play_time, name, msg)
        save_tasks()  # 持久化
        return {'code': 200, 'data': f'已添加定时任务: {play_time}', 'task_id': task_id}
    else:
        return {'code': 404, 'data': temp.string}


@app.get('/Time/del')
def del_time(task_id: str, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    """根据任务ID删除定时任务"""
    import schedule
    if task_id in scheduled_tasks:
        task = scheduled_tasks[task_id]
        schedule.cancel_job(task['job'])
        del scheduled_tasks[task_id]
        save_tasks()  # 持久化
        return {'code': 200, 'data': f'已删除任务: {task_id}'}
    else:
        return {'code': 404, 'data': '任务ID不存在'}


@app.get('/Time/edit')
def edit_time(name: str, new_time: str, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
    """修改指定好友的定时任务时间"""
    import schedule
    # 查找该好友的现有任务
    old_task_id = None
    for task_id, task in scheduled_tasks.items():
        if task_id.endswith(f"_{name}"):
            old_task_id = task_id
            break

    if not old_task_id:
        return {'code': 404, 'data': f'好友 {name} 没有定时任务'}

    # 取消旧任务
    old_task = scheduled_tasks[old_task_id]
    schedule.cancel_job(old_task['job'])

    # 解析旧任务信息
    parts = old_task_id.split('_', 1)
    old_time = parts[0] if len(parts) == 2 else ""

    # 创建新任务（保留原消息，不覆盖）
    new_play_time = format_time(new_time)
    msg = old_task.get('msg', '')

    # 生成新任务ID并替换
    new_task_id = f"{new_play_time}_{name}"
    schedule_task(new_task_id, new_play_time, name, msg)
    del scheduled_tasks[old_task_id]
    save_tasks()  # 持久化

    return {
        'code': 200,
        'data': f'已将 {name} 的定时任务从 {old_time} 修改为 {new_play_time}',
        'old_time': old_time,
        'new_time': new_play_time,
        'task_id': new_task_id
    }


@app.get('/Time/getlist')
def get_time_list(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    """获取当前所有定时任务列表"""
    tasks = []
    for task_id, task in scheduled_tasks.items():
        # 解析任务ID获取信息
        parts = task_id.split('_', 1)
        if len(parts) == 2:
            time_str, name = parts
            tasks.append({
                'task_id': task_id,
                'time': time_str,
                'name': name,
                'next_run': str(task['job'].next_run) if task['job'].next_run else None,
                'last_result': task.get('last_result', ''),
                'last_generated_text': task.get('last_generated_text', ''),
                'last_run_at': task.get('last_run_at', ''),
                'last_jitter_seconds': task.get('last_jitter_seconds', 0),
                'jitter_minutes': config.get('task_jitter_minutes', 0)
            })
    return {'code': 200, 'data': {'count': len(tasks), 'tasks': tasks}}


# ===== 后台登录 =====

@app.get('/Api/Login/Admin')
def admin_login(username: str, password: str, request: Request = None):
    from backend import auth
    if username == 'admin' and verify_pwd(password):
        client_host = '127.0.0.1'
        if request and request.client:
            client_host = '127.0.0.1' if request.client.host in ('::1', '127.0.0.1') else request.client.host
        auth._last_login_ip = client_host
        token = generate_token()
        return {'code': 200, 'data': token}
    else:
        return {'code': 400, 'data': '登录失败'}


@app.get('/Api/GetLastLoginIP')
def get_last_login_ip(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    from backend import auth
    return {'code': 200, 'data': auth._last_login_ip}


# 退出登录
@app.get('/Api/logout')
def logout(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    token = authorization[7:]
    remove_token(token)
    return {'code': 200, 'data': '已退出登录'}


# 密码修改
@app.get('/Api/ChangePassword')
def change_password(old_password: str, new_password: str, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    from backend import auth
    if not verify_pwd(old_password):
        return {'code': 400, 'data': '原密码错误'}
    auth._password_hash = hash_pwd(new_password)
    config['password_hash'] = auth._password_hash
    config.pop('password', None)  # 确保明文已清除
    save_config(config)
    return {'code': 200, 'data': '密码修改成功'}


# ===== 端口配置 =====

@app.get('/Api/GetPort')
def get_port(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    return {'code': 200, 'data': config.get('port', 8080)}


@app.get('/Api/SetPort')
def set_port(port: int, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    try:
        if not (1 <= port <= 65535):
            return {'code': 400, 'data': '端口范围 1-65535'}
        config['port'] = port
        save_config(config)
        return {'code': 200, 'data': f'端口已保存为 {port}，重启后端后生效'}
    except Exception as e:
        return {'code': 500, 'data': '保存失败'}


@app.get('/Api/GetBrowserMode')
def get_browser_mode(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    return {'code': 200, 'data': config.get('show_browser', True)}


@app.get('/Api/SetBrowserMode')
def set_browser_mode(show: bool, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    try:
        config['show_browser'] = show
        save_config(config)
        return {'code': 200, 'data': f'浏览器显示模式已保存为 {"显示" if show else "隐藏"}，重启后端后生效'}
    except Exception as e:
        return {'code': 500, 'data': '保存失败'}


@app.get('/Api/GetBrowserConfig')
def get_browser_config(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    browser_name = normalize_browser_name(config.get('browser_name'))
    return {
        'code': 200,
        'data': {
            'browser_name': browser_name,
            'browser_label': get_browser_label(browser_name),
            'browser_path': (config.get('browser_path') or '').strip(),
            'profile_dir': get_profile_dir(browser_name),
            'platform': platform.system().lower()
        }
    }


@app.get('/Api/SetBrowserConfig')
def set_browser_config(browser_name: str, browser_path: str = Query(''), authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    browser_name = normalize_browser_name(browser_name)
    browser_path = (browser_path or '').strip()
    try:
        config['browser_name'] = browser_name
        config['browser_path'] = browser_path
        save_config(config)
        path_hint = f'，自定义路径：{browser_path}' if browser_path else '，使用系统默认安装路径'
        return {'code': 200, 'data': f'浏览器已切换为 {get_browser_label(browser_name)}{path_hint}，重启后端后生效'}
    except Exception:
        return {'code': 500, 'data': '保存失败'}


@app.get('/Api/GetRiskConfig')
def get_risk_config(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    return {
        'code': 200,
        'data': {
            'task_jitter_minutes': config.get('task_jitter_minutes', 8),
            'max_consecutive_failures': config.get('max_consecutive_failures', 3),
            'dedupe_window_days': config.get('dedupe_window_days', 7),
            'message_templates': list(config.get('message_templates') or DEFAULT_MESSAGE_TEMPLATES)
        }
    }


@app.post('/Api/SetRiskConfig')
def set_risk_config(payload: dict = Body(default=None), authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    payload = payload or {}
    try:
        config['task_jitter_minutes'] = clamp_int(payload.get('task_jitter_minutes', config.get('task_jitter_minutes', 8)), 8, 0, 60)
        config['max_consecutive_failures'] = clamp_int(payload.get('max_consecutive_failures', config.get('max_consecutive_failures', 3)), 3, 1, 10)
        config['dedupe_window_days'] = clamp_int(payload.get('dedupe_window_days', config.get('dedupe_window_days', 7)), 7, 1, 30)
        config['message_templates'] = normalize_message_templates(payload.get('message_templates', config.get('message_templates')))
        save_config(config)
        save_risk_state()
        return {'code': 200, 'data': '防封配置已保存'}
    except Exception:
        return {'code': 500, 'data': '保存失败'}


@app.get('/Api/GetRiskStatus')
def get_risk_status(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    prune_risk_state()
    recent = list(risk_state.get('recent_messages', []))[-10:]
    recent.reverse()
    return {
        'code': 200,
        'data': {
            'paused': bool(risk_state.get('paused')),
            'pause_reason': risk_state.get('pause_reason', ''),
            'paused_at': risk_state.get('paused_at', ''),
            'consecutive_failures': int(risk_state.get('consecutive_failures', 0)),
            'max_consecutive_failures': config.get('max_consecutive_failures', 3),
            'today_send_count': int(risk_state.get('today_send_count', 0)),
            'last_error': risk_state.get('last_error', ''),
            'last_failure_at': risk_state.get('last_failure_at', ''),
            'last_success_at': risk_state.get('last_success_at', ''),
            'last_sent_at': risk_state.get('last_sent_at', ''),
            'task_jitter_minutes': config.get('task_jitter_minutes', 8),
            'dedupe_window_days': config.get('dedupe_window_days', 7),
            'recent_messages': recent
        }
    }


@app.post('/Api/ResumeRisk')
def resume_risk_api(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    resume_risk()
    return {'code': 200, 'data': '风控状态已恢复，自动任务可继续运行'}


# ===== 前端静态文件托管 =====
if os.path.exists(DIST_DIR):
    # 挂载静态资源目录（如果存在）
    assets_dir = os.path.join(DIST_DIR, 'assets')
    if os.path.isdir(assets_dir):
        app.mount('/assets', StaticFiles(directory=assets_dir), name='assets')

    # SPA 路由回退：所有非 API 请求都返回 index.html 或对应静态文件
    @app.get('/{path:path}')
    async def serve_spa(path: str):
        file_path = os.path.realpath(os.path.join(DIST_DIR, path))
        # 防止路径穿越：确保文件在 DIST_DIR 内
        if not file_path.startswith(os.path.realpath(DIST_DIR)):
            return FileResponse(os.path.join(DIST_DIR, 'index.html'), media_type='text/html')
        if os.path.isfile(file_path):
            # 根据扩展名设置正确的 Content-Type
            import mimetypes
            mimetypes.add_type('application/javascript', '.js')
            mimetypes.add_type('text/css', '.css')
            content_type, _ = mimetypes.guess_type(file_path)
            return FileResponse(file_path, media_type=content_type)
        return FileResponse(os.path.join(DIST_DIR, 'index.html'), media_type='text/html')


atexit.register(cleanup_on_exit)


if __name__ == "__main__":
    saved_port = config.get('port', 8080)

    if is_port_in_use(saved_port):
        actual = find_available_port(saved_port)
        print(f'⚠️ 端口 {saved_port} 已被占用，自动切换到 {actual}')
        config['port'] = actual
        save_config(config)
    else:
        actual = saved_port
    print(f'✅ 项目已运行在 {actual} 端口')
    print(f'🚀 服务已启动：http://localhost:{actual}')

    uvicorn.run(
        app,
        host="localhost",
        port=actual,
        reload=False
    )
