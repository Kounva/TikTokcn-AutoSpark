import re, os, gzip, socket
from selenium import webdriver
from selenium.webdriver import Keys
from selenium.webdriver.edge.service import Service
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import SessionNotCreatedException
from selenium.webdriver.common.by import By
import schedule, requests
import time, uvicorn
from datetime import datetime
import json, base64
from fastapi import FastAPI, Header, Request, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
import threading, hashlib, secrets

# 路径配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, 'dist')

# 配置文件
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

def load_config():
    """读取配置文件，不存在则返回默认配置"""
    default = {'port': 8080, 'show_browser': True}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                default.update(cfg)
        except Exception:
            pass
    return default

def save_config(cfg):
    """保存配置到文件"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def is_port_in_use(port):
    """检测端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def find_available_port(preferred):
    """从首选端口开始找可用端口，最多尝试 20 个"""
    for offset in range(20):
        candidate = preferred + offset
        if not is_port_in_use(candidate):
            return candidate
    # 首选附近都满了，让系统分配随机端口
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('localhost', 0))
        return s.getsockname()[1]

config = load_config()

service = Service()
options = webdriver.EdgeOptions()
# 默认显示浏览器（无头模式不稳定易崩溃），可通过设置页修改
off_ui = not config.get('show_browser', True)

import tempfile
# Edge 临时用户数据目录（用系统临时目录，程序退出后由系统清理）
APP_PROFILE_DIR = tempfile.mkdtemp(prefix='edge_spark_')


def unban_config():
    if off_ui:
        options.add_argument("--headless")  # 启用无头模式
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    options.add_argument('log-level=3')
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.5481.177 Safari/537.36")
    options.add_experimental_option('excludeSwitches', ['enable-automation', 'useAutomationExtension'])
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-infobars')
    options.add_argument('--disable-notifications')
    options.add_argument('--disable-popup-blocking')
    options.add_argument('--disable-web-security')
    options.add_argument('--ignore-certificate-errors')
    options.add_argument('--no-sandbox')
    options.add_argument('--start-maximized')
    # 使用程序专用 profile（每次启动的临时会话）
    options.add_argument(f'--user-data-dir={APP_PROFILE_DIR}')


def AiqingGongyu_text():
    req = requests.get('https://v2.xxapi.cn/api/aiqinggongyu')
    if req.status_code == 200:
        json_data = req.json()
        json_data = json_data['data']
        if json_data:
            return json_data
        else:
            return '暂无今日名言'
    else:
        return '暂无今日名言'


def Get_Cooke():
    driver.get('https://www.douyin.com/')
    for_OFF = True
    print('🕰️ 请登录抖音[且保持游览器为全屏!].....')
    while for_OFF:
        try:
            # 尝试获取 login_type 元素
            login_type_element = driver.find_element(By.XPATH,
                                                     '/html/body/div[2]/div[1]/div[4]/div[1]/div[1]/header/div/div/div[2]/div/pace-island/div/div[5]/div/div[1]/button/span/p')
        except NoSuchElementException:
            cooke = driver.get_cookies()
            print(f'✅ Cooke获取成功,您的Cooke为 [请完整复制到cookies_list变量中]:\n{cooke}')
            driver.close()
            exit()


def format_time(time_str: str) -> str:
    """
    将时间字符串格式化为 HH:MM 格式
    例如: "9:23" -> "09:23", "9:5" -> "09:05", "09:23" -> "09:23"
    """
    if not time_str:
        return '22:00'

    # 统一替换中文冒号
    time_str = time_str.replace('：', ':').strip()

    try:
        # 分割小时和分钟
        parts = time_str.split(':')
        if len(parts) != 2:
            print(f'⚠️ 时间格式错误，使用默认时间 22:00')
            return '22:00'

        hour = int(parts[0])
        minute = int(parts[1])

        # 验证范围
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            print(f'⚠️ 时间范围错误，使用默认时间 22:00')
            return '22:00'

        # 格式化为两位数字
        return f"{hour:02d}:{minute:02d}"

    except ValueError:
        print(f'⚠️ 时间解析错误，使用默认时间 22:00')
        return '22:00'


class TrueString:
    def __init__(self, is_bool, string):
        self.is_bool = is_bool
        self.string = string


class UserFriendsInfo:
    def __init__(self, username, avatar, fire):
        self.username = username
        self.avatar = avatar
        self.fire = fire


class Douyin:
    friends_xpath_list = {}

    def __init__(self, driver):
        self.driver = driver  # 将 driver 作为实例属性

    def PrintfFrinder(self):

        print(f'\n⏭️ 好友列表 共获取{len(self.friends_xpath_list)}位:\n------------------')
        for index, value in self.friends_xpath_list.items():
            print(index)
        print('------------------')

    def Updara_FrinderList(self):
        friends_xpath = '//div[@class="conversationConversationListwrapper"]/div/div/div'
        msg_main_list = driver.find_elements(By.XPATH, friends_xpath)
        temp_list = []
        for msg_len in range(1, len(msg_main_list) + 1):
            new_xpath = f'//div[@class="conversationConversationListwrapper"]/div/div[{msg_len + 1}]/div[1]/div[2]/div[1]/div[1]'
            avatar_xpath = f'//div[@class="conversationConversationListwrapper"]/div/div[{msg_len + 1}]/div[1]/div[1]/div/span/img'
            avatar_xpath2 = f'//div[@class="conversationConversationListwrapper"]/div/div[{msg_len + 1}]/div/div/img'
            fire_xpath = f'//div[@class="conversationConversationListwrapper"]/div/div[{msg_len + 1}]/div[1]/div[2]/div[1]/div[2]/div[1]/div/div'
            friends_get = driver.find_element(By.XPATH, value=new_xpath)
            friends_text = friends_get.text
            try:
                avatar_get = driver.find_element(By.XPATH, value=avatar_xpath)
                avatar = avatar_get.get_attribute('src')
            except:
                avatar_get = driver.find_element(By.XPATH, value=avatar_xpath2)
                avatar = avatar_get.get_attribute('src')
            self.friends_xpath_list[friends_text] = new_xpath
            try:
                fire_count = driver.find_element(By.XPATH, value=fire_xpath).text.strip()
            except:
                fire_count = ''
            temp_list.append(UserFriendsInfo(friends_text, avatar, fire_count))
        return temp_list

    def Send_Frinder(self, name: str, text: str):
        count = self.Updara_FrinderList()
        if count == 0:
            print("⚠️ 更新好友列表失败!")
        else:
            try:
                for index, value in self.friends_xpath_list.items():
                    if index == name:
                        friend_id = driver.find_element(By.XPATH, value=value)
                        friend_id.click()
                        time.sleep(1.5)
                        seng = driver.find_element(By.XPATH,
                                                   value='//div[@class="messageEditorimChatEditorContainer"]/div/div')
                        seng.send_keys(text)
                        seng.send_keys(Keys.ENTER)
                        return TrueString(True, None)
            except Exception as e:
                return TrueString(False, e)

    def Find_Friends(self, name: str):
        count = self.Updara_FrinderList()
        is_find = False
        if count == 0:
            return TrueString(False, '未初始化好友')
        try:
            for index, value in self.friends_xpath_list.items():
                if index == name:
                    is_find = True
            return TrueString(is_find, None)
        except Exception as e:
            return TrueString(False, e)

    def LoginInit(self):
        try:
            dle_user = driver.find_element(By.XPATH,
                                           value='//*[@id="douyin_login_comp_flat_panel"]/div/div[2]/div/div[4]/p')
            dle_user.click()
        except:
            pass


init = False
init_lock = threading.Lock()  # 防止并发初始化
Login_is_bool = False
app = FastAPI()

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

# 密码存储 (内存中，生产环境建议存入文件或数据库)
_password = '123456'  # 默认密码


def hash_pwd(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()


# Token存储
_valid_tokens = set()
_last_login_ip = '无'


def generate_token() -> str:
    token = secrets.token_hex(32)
    _valid_tokens.add(token)
    return token


def verify_token(token: str) -> bool:
    return token in _valid_tokens


def remove_token(token: str):
    _valid_tokens.discard(token)


def require_auth(authorization: str = Header(None)):
    if not authorization or not authorization.startswith('Bearer '):
        return {'code': 401, 'data': '未授权'}
    token = authorization[7:]
    if not verify_token(token):
        return {'code': 401, 'data': '未授权'}
    return None


def check_driver():
    """检查浏览器会话是否有效，无效则重置状态并返回错误响应"""
    global init, driver, douyin, Login_is_bool
    if not init or driver is None:
        return {'code': 400, 'data': '浏览器未初始化，请先点击初始化'}
    try:
        # 用一个轻量操作探测会话是否存活
        driver.current_url
        return None
    except Exception:
        # 会话已失效，重置状态
        init = False
        driver = None
        douyin = None
        Login_is_bool = False
        return {'code': 400, 'data': '浏览器会话已断开，请重新初始化'}


# 定时任务存储
scheduled_tasks = {}  # 格式: {任务ID: job对象}


# 定时线程
def run_schedule():
    """后台线程运行定时任务"""
    while True:
        schedule.run_pending()
        time.sleep(1)


def start_scheduler():
    """启动定时任务调度线程"""
    scheduler_thread = threading.Thread(target=run_schedule, daemon=True)
    scheduler_thread.start()
    return scheduler_thread


start_time = datetime.now()


# 抖音操作
@app.get('/Home')
def Home(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    return {'time': start_time}


@app.get('/Api/Init')  # 初始化浏览器
def Init(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err

    global init, driver, douyin, Login_is_bool

    with init_lock:  # 加锁，防止重复点击触发多次初始化
        if init:
            return {'code': 200, 'data': 'init Repeated!'}
        try:
            unban_config()
            driver = webdriver.Edge(service=service, options=options)
            driver.set_window_size(1400, 900)
            driver.get('https://www.douyin.com/chat?isPopup=1 ')
            douyin = Douyin(driver)
            init = True
            Login_is_bool = False  # 新会话默认未登录
            start_scheduler()  # 启动调度线程
            return {'code': 200, 'data': 'success'}
        except SessionNotCreatedException as e:
            if "This version of Microsoft Edge WebDriver only supports" in str(e):
                return {'code': 400, 'data': '需要更新浏览器驱动!'}
            return {'code': 400, 'data': f'浏览器会话创建失败: {str(e)}'}
        except Exception as e:
            return {'code': 500, 'data': f'初始化失败: {str(e)}'}


@app.get('/Api/GetInit')  # 获取初始化状态
def GetInit(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    return {'code': 200, 'data': 'Yes' if init else 'No'}


@app.post('/Api/login')  # 登录 传入cooke
def Login(cooke: str = Body(default=None), gzip_flag: bool = Body(default=False), authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    global Login_is_bool
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
                    return {'code': '404',
                            'data': 'login-error-gzip decompress failed, check cookie format and gzip flag'}
            cookie_list = decoded_bytes.decode('utf-8')
            cookies = json.loads(base64.b64decode(cookie_list).decode('utf-8'))
            for cookie in cookies:
                driver.add_cookie(cookie)
        except Exception as e:
            return {'code': '404', 'data': f'login-error-cookie parse error: {str(e)}'}
        driver.refresh()
        try:
            login_type_element = driver.find_element(By.XPATH, '//*[@id="douyin_login_comp_flat_panel"]/picture')
            login_type = login_type_element.text
            return {'code': '404', 'data': 'login-error-cooker cant login'}
        except NoSuchElementException:
            Login_is_bool = True
            return {'code': '200', 'data': 'ok'}
    else:
        return {'code': '404', 'data': 'login-error-not cooker'}  # # @#z


@app.get('/Api/Pnglogin')  # 扫码登录
def PngLogin(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    global Login_is_bool
    drv_err = check_driver()
    if drv_err:
        return drv_err
    cooke = driver.get_cookies()
    if cooke:
        try:
            for cookie in cooke:
                driver.add_cookie(cookie)
        except Exception as e:
            return {'code': '404', 'data': f'login-error-cookie parse error: {str(e)}'}
        driver.refresh()
        try:
            login_type_element = driver.find_element(By.XPATH, '//*[@id="douyin_login_comp_flat_panel"]/picture')
            login_type = login_type_element.text
            driver.refresh()
            return {'code': '404', 'data': '系统繁忙,请稍后重新登录'}
        except NoSuchElementException:
            Login_is_bool = True
            return {'code': '200', 'data': 'ok'}
    else:
        return {'code': '404', 'data': 'login-error-not cooker'}  # # @#z


@app.get('/Api/GetLogin')  # 获取登录
def GetLogin(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    global Login_is_bool
    # 实际检查抖音页面登录状态，而非只看缓存标记
    if not init or driver is None:
        Login_is_bool = False
        return {'code': 200, 'data': 'No'}
    try:
        # 等待页面加载完成，避免误判（刚初始化时页面还没渲染登录弹窗）
        time.sleep(1.5)
        driver.find_element(By.XPATH, '//*[@id="douyin_login_comp_flat_panel"]/picture')
        # 找到登录弹窗 = 未登录
        Login_is_bool = False
        return {'code': 200, 'data': 'No'}
    except NoSuchElementException:
        # 没有登录弹窗 = 已登录
        Login_is_bool = True
        return {'code': 200, 'data': 'Yes'}
    except Exception:
        # 页面异常时回退到缓存标记
        return {'code': 200, 'data': 'Yes' if Login_is_bool else 'No'}


@app.get('/Api/login/Init/GetLoginPng')  # 获取登录扫码
def GetLoginPng(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    try:
        if not init or driver is None:
            return {'code': 400, 'data': '浏览器未初始化，请先点击初始化'}
        Douyin.LoginInit(douyin)
        try:
            error = driver.find_element(By.XPATH, '//*[@id="animate_qrcode_container"]/div[2]/div/p[1]')
            img_element = driver.find_element(By.XPATH, '//*[@id="animate_qrcode_container"]/div[2]/img')
            img_element.click()
        except:
            pass
        img_element = driver.find_element(By.XPATH, '//*[@id="animate_qrcode_container"]/div[2]/img')
        login_src = img_element.get_attribute('src')
        try:
            is_rust = driver.find_element(By.XPATH, '//*[@id="animate_qrcode_container"]/div[2]/div')
            is_rust.click()
            time.sleep(5)
            img_element = driver.find_element(By.XPATH, '//*[@id="animate_qrcode_container"]/div[2]/img')
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
        return {'code': 500, 'data': f'获取二维码失败: {str(e)}'}


@app.get('/Api/login/Init/GetCooker')  # 获取cooke
def GetCooke(password: str = Query(None), authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    # 验证密码
    if not password or hash_pwd(password) != hash_pwd(_password):
        return {'code': 400, 'data': '密码错误'}
    drv_err = check_driver()
    if drv_err:
        return drv_err
    if Login_is_bool:
        try:
            cooke = driver.get_cookies()
            cookie_json = json.dumps(cooke)
            cookie_base64 = base64.b64encode(cookie_json.encode('utf-8')).decode('utf-8')
            return {'code': 200, 'data': {'cooke': cookie_base64}}
        except Exception as e:
            return {'code': 500, 'data': f'获取Cookie失败: {str(e)}'}
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
        friends_list = douyin.Updara_FrinderList()
        if len(friends_list) == 0:
            return {'code': 404, 'data': '暂无好友或页面未加载'}
        dicts = {}
        for v in friends_list:
            dicts[v.username] = [v.avatar, v.fire]
        return {'code': 200, 'data': {'count': len(friends_list), 'list': dicts}}
    except Exception as e:
        return {'code': 404, 'data': str(e)}


@app.get('/Api/Send')  # 发送信息
def Send(name: str, text: str, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
    try:
        Douyin.Updara_FrinderList(douyin)
        out = Douyin.Send_Frinder(douyin, name, text)
        if out.is_bool:
            return {'code': 200, 'data': 'Send successfully'}
        else:
            return {'code': 404, 'data': out.string}
    except Exception as e:
        return {'code': 500, 'data': f'发送失败: {str(e)}'}


@app.get('/Api/GetUsername')  # 获取用户名
def GetUserInfo(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
    if Login_is_bool:
        try:
            match = re.search(r'\\"nickname\\":\\"([^\\"]+)\\"', driver.page_source)
            if match:
                text = match.group(0)
                clean = text.replace('\\"', '"')
                data = json.loads('{' + clean + '}')
                return {'code': 200, 'data': data['nickname']}
            else:
                return {'code': 400, 'data': '已登录,但未获取到用户名'}
        except Exception as e:
            return {'code': 500, 'data': f'获取用户名失败: {str(e)}'}
    else:
        return {'code': 400, 'data': '未登录'}


@app.get('/Api/GetScrlk')  # 获取截图
def GetScrlk(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
    try:
        driver.save_screenshot("temp.png")
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
        driver.delete_all_cookies()
        driver.refresh()
        return {'code': 200, 'data': '已清除Cooke'}
    except Exception as e:
        return {'code': 500, 'data': f'清除Cookie失败: {str(e)}'}


@app.get('/Api/LoginPhone')  # 验证码登录
def authorization(areacode: str, phone: str, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    try:
        Douyin.LoginInit(douyin)
        areacode_value = driver.find_element(By.XPATH, '//*[@id="douyin_login_comp_normal_input_id"]/div[1]/div/input')
        areacode_value.clear()
        areacode_value.send_keys(areacode.strip())
        inp = driver.find_element(By.XPATH, '//*[@id="normal-input"]')
        inp.send_keys(phone)
        span = driver.find_element(By.XPATH, '//*[@id="douyin_login_comp_button_input_id"]/span')
        span.click()
        time.sleep(2)
        if span.text.strip() == '获取验证码':
            return {'code': 400, 'data': '验证码发送失败'}
        else:
            return {'code': 200, 'data': '验证码发送成功'}
    except Exception as e:
        return {'code': 400, 'data': e}


@app.get('/Api/LoginPhoneInput')  # 验证码登录 2 输入验证码
def authorizations(code: str, authorization: str = Header(None)):
    global Login_is_bool
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    try:
        inp = driver.find_element(By.XPATH, '//*[@id="button-input"]')
        inp.send_keys(code)
        button = driver.find_element(By.XPATH, '//*[@id="douyin_login_comp_btn_id"]')
        button.click()
        time.sleep(2)
        try:
            login_div = driver.find_element(By.XPATH, '//*[@id="douyin_login_comp_flat_panel"]/picture')
            return {'code': 400, 'data': '登录失败'}
        except:
            Login_is_bool = True
            return {'code': 200, 'data': '登录成功'}
    except Exception as e:
        return {'code': 400, 'data': e}


@app.get('/Api/LoginDebug')
def LoginDebug(authorization: str = Header(None)):
    global Login_is_bool
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    if Login_is_bool == False:
        Login_is_bool = True
        return {'code': 200, 'data': 'OK'}
    else:
        return {'code': 400, 'data': '已是登录状态,无需设定'}


# 定时任务操作
@app.get('/Time/add')
def add_time(time: str, name: str, text: str = None, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    # 检查是否已存在该好友的定时任务
    for task_id, job in scheduled_tasks.items():
        if task_id.endswith(f"_{name}"):
            return {'code': 400, 'data': f'好友 {name} 已有定时任务，请先删除或修改'}

    temp = douyin.Find_Friends(name)
    if temp.is_bool:
        play_time = format_time(time)
        msg = AiqingGongyu_text() if text == None else text
        # 添加定时任务并保存job对象
        job = schedule.every().day.at(play_time).do(douyin.Send_Frinder, name, msg)
        # 生成唯一任务ID
        task_id = f"{play_time}_{name}"
        scheduled_tasks[task_id] = job
        return {'code': 200, 'data': f'已添加定时任务: {play_time}', 'task_id': task_id}
    else:
        return {'code': 404, 'data': temp.string}


@app.get('/Time/del')
def del_time(task_id: str, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    """根据任务ID删除定时任务"""
    if task_id in scheduled_tasks:
        job = scheduled_tasks[task_id]
        schedule.cancel_job(job)
        del scheduled_tasks[task_id]
        return {'code': 200, 'data': f'已删除任务: {task_id}'}
    else:
        return {'code': 404, 'data': '任务ID不存在'}


@app.get('/Time/edit')
def edit_time(name: str, new_time: str, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    """修改指定好友的定时任务时间"""
    # 查找该好友的现有任务
    old_task_id = None
    for task_id, job in scheduled_tasks.items():
        if task_id.endswith(f"_{name}"):
            old_task_id = task_id
            break

    if not old_task_id:
        return {'code': 404, 'data': f'好友 {name} 没有定时任务'}

    # 取消旧任务
    old_job = scheduled_tasks[old_task_id]
    schedule.cancel_job(old_job)

    # 解析旧任务信息
    parts = old_task_id.split('_', 1)
    old_time = parts[0] if len(parts) == 2 else ""

    # 创建新任务
    new_play_time = format_time(new_time)
    msg = AiqingGongyu_text()  # 获取新的名言
    new_job = schedule.every().day.at(new_play_time).do(douyin.Send_Frinder, name, msg)

    # 生成新任务ID并替换
    new_task_id = f"{new_play_time}_{name}"
    scheduled_tasks[new_task_id] = new_job
    del scheduled_tasks[old_task_id]

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
    for task_id, job in scheduled_tasks.items():
        # 解析任务ID获取信息
        parts = task_id.split('_', 1)
        if len(parts) == 2:
            time_str, name = parts
            tasks.append({
                'task_id': task_id,
                'time': time_str,
                'name': name,
                'next_run': str(job.next_run) if job.next_run else None
            })
    return {'code': 200, 'data': {'count': len(tasks), 'tasks': tasks}}


# 后台登录
@app.get('/Api/Login/Admin')
def admin_login(username: str, password: str, request: Request = None):
    global _last_login_ip
    if username == 'admin' and hash_pwd(password) == hash_pwd(_password):
        _last_login_ip = '127.0.0.1' if request and request.client.host in ('::1', '127.0.0.1') else (request.client.host if request else '127.0.0.1')
        token = generate_token()
        return {'code': 200, 'data': token}
    else:
        return {'code': 400, 'data': '登录失败'}


@app.get('/Api/GetLastLoginIP')
def get_last_login_ip(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    return {'code': 200, 'data': _last_login_ip}


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
    global _password
    if hash_pwd(old_password) != hash_pwd(_password):
        return {'code': 400, 'data': '原密码错误'}
    _password = new_password
    return {'code': 200, 'data': '密码修改成功'}


# 端口配置
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
        return {'code': 500, 'data': f'保存失败: {str(e)}'}


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
        return {'code': 500, 'data': f'保存失败: {str(e)}'}


# ===== 前端静态文件托管 =====
if os.path.exists(DIST_DIR):
    # 挂载静态资源目录（如果存在）
    assets_dir = os.path.join(DIST_DIR, 'assets')
    if os.path.isdir(assets_dir):
        app.mount('/assets', StaticFiles(directory=assets_dir), name='assets')

    # SPA 路由回退：所有非 API 请求都返回 index.html 或对应静态文件
    @app.get('/{path:path}')
    async def serve_spa(path: str):
        file_path = os.path.join(DIST_DIR, path)
        if os.path.isfile(file_path):
            # 根据扩展名设置正确的 Content-Type
            import mimetypes
            mimetypes.add_type('application/javascript', '.js')
            mimetypes.add_type('text/css', '.css')
            content_type, _ = mimetypes.guess_type(file_path)
            return FileResponse(file_path, media_type=content_type)
        return FileResponse(os.path.join(DIST_DIR, 'index.html'), media_type='text/html')


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


