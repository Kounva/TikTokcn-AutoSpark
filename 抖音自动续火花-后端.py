import re, os, gzip, socket, random
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
    except Exception as e:
        print(f'⚠️ 配置保存失败: {e}')

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

# Edge 固定用户数据目录（保持浏览器指纹一致，避免每次启动被视为新设备）
APP_PROFILE_DIR = os.path.join(BASE_DIR, 'edge_user_data')


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
    try:
        req = requests.get('https://v2.xxapi.cn/api/aiqinggongyu', timeout=5)
        if req.status_code == 200:
            json_data = req.json()
            json_data = json_data['data']
            if json_data:
                return json_data
        return '暂无今日名言'
    except Exception:
        return '暂无今日名言'


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
        self.friends_xpath_list = {}  # 每次刷新前清空，避免旧数据残留
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
        friends = self.Updara_FrinderList()
        if not friends:
            print("⚠️ 更新好友列表失败!")
            return TrueString(False, '更新好友列表失败')
        try:
            for index, value in self.friends_xpath_list.items():
                if index == name:
                    friend_id = driver.find_element(By.XPATH, value=value)
                    friend_id.click()
                    time.sleep(random.uniform(1.0, 2.5))
                    seng = driver.find_element(By.XPATH,
                                               value='//div[@class="messageEditorimChatEditorContainer"]/div/div')
                    seng.send_keys(text)
                    seng.send_keys(Keys.ENTER)
                    return TrueString(True, None)
            # 循环结束未匹配到好友
            return TrueString(False, f'未找到好友: {name}')
        except Exception as e:
            return TrueString(False, str(e))

    def Open_Chat(self, name: str):
        """点击好友进入对话窗口"""
        friends = self.Updara_FrinderList()
        if not friends:
            return False
        try:
            for index, value in self.friends_xpath_list.items():
                if index == name:
                    friend_id = driver.find_element(By.XPATH, value=value)
                    friend_id.click()
                    time.sleep(random.uniform(1.0, 2.5))
                    return True
        except:
            return False
        return False

    def Get_Sticker_List(self):
        """打开表情面板，精准获取三个 tab 的表情包"""
        try:
            # 1. 点击表情按钮打开面板（按钮在输入框附近，带 emoji/表情 标识）
            opened = driver.execute_script('''
                // 表情按钮：常见 class 或属性
                var candidates = [
                    '[class*="emojiBtn"]', '[class*="emojiPicker"]',
                    '[data-e2e*="emoji"]', '[class*="EmojiIcon"]',
                    '[class*="chatEmoji"]', '[class*="editorEmoji"]',
                    'button[aria-label*="表情"]', '[title*="表情"]'
                ];
                for (var s = 0; s < candidates.length; s++) {
                    var els = document.querySelectorAll(candidates[s]);
                    for (var i = 0; i < els.length; i++) {
                        var rect = els[i].getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0 && rect.top < window.innerHeight) {
                            els[i].click();
                            return true;
                        }
                    }
                }
                // 兜底：任何 class 含 emoji 且可见的元素
                var all = document.querySelectorAll('[class*="emoji"], [class*="Emoji"]');
                for (var i = 0; i < all.length; i++) {
                    var rect = all[i].getBoundingClientRect();
                    if (rect.width > 10 && rect.height > 10 && rect.top < window.innerHeight && rect.top > 50) {
                        all[i].click();
                        return true;
                    }
                }
                return false;
            ''')
            if not opened:
                return {'code': 400, 'data': '未找到表情按钮，请确认已进入对话'}
            time.sleep(random.uniform(1.0, 2.0))

            # 2. 逐个点击 tab 并收集表情（异步，避免忙等待阻塞浏览器）
            all_stickers = driver.execute_async_script('''
                var callback = arguments[arguments.length - 1];
                var result = [];
                var seen = {};
                var tabs = document.querySelectorAll('[class*="emojiEmojisModalTabsubTab"]');
                if (tabs.length === 0) {
                    var imgs = document.querySelectorAll('[class*="emoji"] img, [class*="Emoji"] img, [class*="sticker"] img');
                    for (var i = 0; i < imgs.length; i++) {
                        var src = imgs[i].src || '';
                        if (src && src.length > 20 && !seen[src]) { seen[src] = 1; result.push(src); }
                    }
                    callback(result);
                    return;
                }
                var t = 0;
                function processTab() {
                    if (t >= tabs.length) { callback(result); return; }
                    tabs[t].click();
                    t++;
                    setTimeout(function() {
                        var panelImgs = document.querySelectorAll('[class*="emojiEmojisModal"] img, [class*="emojiModalContent"] img, [class*="emojiPanel"] img');
                        if (panelImgs.length === 0) panelImgs = document.querySelectorAll('img');
                        for (var i = 0; i < panelImgs.length; i++) {
                            var src = panelImgs[i].src || '';
                            var rect = panelImgs[i].getBoundingClientRect();
                            if (!src || src.length < 20) continue;
                            if (src.indexOf('douyinpic') !== -1 || src.indexOf('emoji') !== -1 ||
                                src.indexOf('sf-tk') !== -1 || src.indexOf('sticker') !== -1 ||
                                (rect.width > 20 && rect.width < 200)) {
                                if (!seen[src]) { seen[src] = 1; result.push(src); }
                            }
                        }
                        processTab();
                    }, 600);
                }
                processTab();
            ''')

            # 3. 关闭表情面板
            try:
                from selenium.webdriver.common.action_chains import ActionChains
                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            except:
                pass

            if all_stickers and len(all_stickers) > 0:
                return {'code': 200, 'data': all_stickers}
            else:
                return {'code': 400, 'data': '未获取到表情包，抖音页面结构可能已更新'}
        except Exception as e:
            return {'code': 500, 'data': f'获取表情包失败: {str(e)}'}

    def Send_Sticker(self, name: str, sticker_index: int):
        """发送表情包：打开表情面板，点击指定表情，发送"""
        try:
            if not self.Open_Chat(name):
                return TrueString(False, '未找到该好友')
            # 打开表情面板
            driver.execute_script('''
                var candidates = [
                    '[class*="emojiBtn"]', '[class*="emojiPicker"]',
                    '[data-e2e*="emoji"]', '[class*="EmojiIcon"]',
                    '[class*="chatEmoji"]', '[class*="editorEmoji"]',
                    'button[aria-label*="表情"]', '[title*="表情"]'
                ];
                for (var s = 0; s < candidates.length; s++) {
                    var els = document.querySelectorAll(candidates[s]);
                    for (var i = 0; i < els.length; i++) {
                        var rect = els[i].getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) { els[i].click(); return; }
                    }
                }
                var all = document.querySelectorAll('[class*="emoji"], [class*="Emoji"]');
                for (var i = 0; i < all.length; i++) {
                    var rect = all[i].getBoundingClientRect();
                    if (rect.width > 10 && rect.height > 10 && rect.top < window.innerHeight && rect.top > 50) { all[i].click(); return; }
                }
            ''')
            time.sleep(random.uniform(1.0, 2.0))
            # 收集所有 tab 的表情并点击指定索引（异步，避免忙等待）
            clicked = driver.execute_async_script('''
                var callback = arguments[arguments.length - 1];
                var sticker_index = arguments[0];
                var imgs = [];
                var seen = {};
                var tabs = document.querySelectorAll('[class*="emojiEmojisModalTabsubTab"]');
                if (tabs.length > 0) {
                    var t = 0;
                    function processTab() {
                        if (t >= tabs.length) {
                            if (imgs.length > sticker_index) { imgs[sticker_index].click(); callback(true); }
                            else callback(false);
                            return;
                        }
                        tabs[t].click();
                        t++;
                        setTimeout(function() {
                            var panelImgs = document.querySelectorAll('[class*="emojiEmojisModal"] img, [class*="emojiModalContent"] img, [class*="emojiPanel"] img');
                            if (panelImgs.length === 0) panelImgs = document.querySelectorAll('img');
                            for (var i = 0; i < panelImgs.length; i++) {
                                var src = panelImgs[i].src || '';
                                var rect = panelImgs[i].getBoundingClientRect();
                                if (!src || src.length < 20) continue;
                                if (src.indexOf('douyinpic') !== -1 || src.indexOf('emoji') !== -1 ||
                                    src.indexOf('sf-tk') !== -1 || src.indexOf('sticker') !== -1 ||
                                    (rect.width > 20 && rect.width < 200)) {
                                    if (!seen[src]) { seen[src] = 1; imgs.push(panelImgs[i]); }
                                }
                            }
                            processTab();
                        }, 600);
                    }
                    processTab();
                } else {
                    var allImgs = document.querySelectorAll('img');
                    for (var i = 0; i < allImgs.length; i++) {
                        var src = allImgs[i].src || '';
                        var rect = allImgs[i].getBoundingClientRect();
                        if (!src || src.length < 20) continue;
                        if (src.indexOf('douyinpic') !== -1 || src.indexOf('emoji') !== -1 ||
                            src.indexOf('sf-tk') !== -1 || src.indexOf('sticker') !== -1) {
                            if (!seen[src]) { seen[src] = 1; imgs.push(allImgs[i]); }
                        }
                    }
                    if (imgs.length > sticker_index) { imgs[sticker_index].click(); callback(true); }
                    else callback(false);
                }
            ''', sticker_index)
            if not clicked:
                return TrueString(False, '表情索引无效')
            time.sleep(random.uniform(0.3, 0.8))
            seng = driver.find_element(By.XPATH,
                                       value='//div[@class="messageEditorimChatEditorContainer"]/div/div')
            seng.send_keys(Keys.ENTER)
            return TrueString(True, None)
        except Exception as e:
            return TrueString(False, e)

    def Get_Chat_History(self, name: str):
        """获取当前对话的聊天记录"""
        try:
            if not self.Open_Chat(name):
                return {'code': 400, 'data': '未找到该好友'}
            time.sleep(random.uniform(0.8, 1.5))
            # 尝试读取消息列表
            msg_xpaths = [
                '//div[contains(@class,"imChatMessage")]//div[contains(@class,"messageContent")]',
                '//div[contains(@class,"chatMessage")]//div[contains(@class,"content")]',
                '//div[contains(@class,"imChatBody")]//div[contains(@class,"text")]',
                '//div[contains(@class,"messageList")]//div[contains(@class,"content")]',
            ]
            messages = []
            for xpath in msg_xpaths:
                try:
                    elements = driver.find_elements(By.XPATH, value=xpath)
                    if elements:
                        for el in elements:
                            text = el.text.strip()
                            if text:
                                # 判断方向：自己的消息通常有特定 class
                                parent_class = el.find_element(By.XPATH, '..').get_attribute('class') or ''
                                is_self = 'self' in parent_class.lower() or 'right' in parent_class.lower() or 'sent' in parent_class.lower()
                                messages.append({'text': text, 'is_self': is_self})
                        if messages:
                            break
                except:
                    continue
            return {'code': 200, 'data': messages}
        except Exception as e:
            return {'code': 500, 'data': f'获取聊天记录失败: {str(e)}'}

    def Find_Friends(self, name: str):
        friends = self.Updara_FrinderList()
        is_find = False
        if not friends:
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

# 密码 hash 工具
def hash_pwd(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()


# 密码存储（hash 持久化到 config.json，不存明文）
# 兼容旧版：如果 config.json 中有明文 password，首次启动时自动迁移为 hash
_DEFAULT_PWD_HASH = hash_pwd('123456')  # 默认密码 123456 的 hash
if 'password_hash' in config:
    _password_hash = config['password_hash']
elif 'password' in config:
    # 旧版明文迁移
    _password_hash = hash_pwd(config['password'])
    config['password_hash'] = _password_hash
    config.pop('password', None)  # 删除明文
    save_config(config)
else:
    _password_hash = _DEFAULT_PWD_HASH


def verify_pwd(pwd: str) -> bool:
    """验证密码是否正确"""
    return hash_pwd(pwd) == _password_hash


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
        # 会话已失效，关闭旧 driver 并重置状态
        try:
            driver.quit()
        except Exception:
            pass
        # 清理旧定时任务（job 仍绑定旧的 douyin 引用）
        for task_id, job in list(scheduled_tasks.items()):
            try:
                schedule.cancel_job(job)
            except Exception:
                pass
        scheduled_tasks.clear()
        init = False
        driver = None
        douyin = None
        Login_is_bool = False
        return {'code': 400, 'data': '浏览器会话已断开，请重新初始化'}


# 定时任务存储
scheduled_tasks = {}  # 格式: {任务ID: job对象}

# 定时任务持久化文件
TASKS_FILE = os.path.join(BASE_DIR, 'tasks.json')


def save_tasks():
    """将定时任务元数据持久化到 tasks.json"""
    tasks_meta = []
    for task_id in scheduled_tasks:
        parts = task_id.split('_', 1)
        if len(parts) == 2:
            time_str, name = parts
            # 从 job 对象中提取消息参数（Send_Frinder 的第三个参数）
            msg = ''
            job = scheduled_tasks[task_id]
            try:
                msg = job.job_func.args[2] if len(job.job_func.args) > 2 else ''
            except Exception:
                pass
            tasks_meta.append({'task_id': task_id, 'time': time_str, 'name': name, 'msg': msg})
    try:
        with open(TASKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(tasks_meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'⚠️ 定时任务持久化失败: {e}')


def load_tasks_meta():
    """从 tasks.json 读取任务元数据"""
    if not os.path.exists(TASKS_FILE):
        return []
    try:
        with open(TASKS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def restore_tasks():
    """浏览器初始化后，从持久化文件恢复定时任务"""
    meta_list = load_tasks_meta()
    restored = 0
    for meta in meta_list:
        try:
            task_id = meta.get('task_id', '')
            play_time = meta.get('time', '22:00')
            name = meta.get('name', '')
            msg = meta.get('msg', '')
            if not name or task_id in scheduled_tasks:
                continue
            # 若无保存的消息，用随机名言
            if not msg:
                msg = AiqingGongyu_text()
            job = schedule.every().day.at(play_time).do(douyin.Send_Frinder, name, msg)
            scheduled_tasks[task_id] = job
            restored += 1
        except Exception as e:
            print(f'⚠️ 恢复任务失败: {e}')
            continue
    if restored > 0:
        print(f'✅ 已恢复 {restored} 个定时任务')


# 定时线程
_scheduler_started = False  # 防止重复启动调度线程


def run_schedule():
    """后台线程运行定时任务"""
    while True:
        schedule.run_pending()
        time.sleep(1)


def start_scheduler():
    """启动定时任务调度线程（仅启动一次）"""
    global _scheduler_started
    if _scheduler_started:
        return
    scheduler_thread = threading.Thread(target=run_schedule, daemon=True)
    scheduler_thread.start()
    _scheduler_started = True


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
            # 设置页面加载策略为 eager（DOM 就绪即可，不等所有资源）
            try:
                driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            except Exception:
                pass
            # 打开抖音聊天页（设置较短的超时，避免长时间卡住）
            driver.set_page_load_timeout(30)
            try:
                driver.get('https://www.douyin.com/chat?isPopup=1')
            except Exception:
                # 页面加载超时也继续（SPA 页面可能触发超时但 DOM 已就绪）
                pass
            douyin = Douyin(driver)
            init = True
            Login_is_bool = False  # 新会话默认未登录
            start_scheduler()  # 启动调度线程
            restore_tasks()  # 恢复持久化的定时任务
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
                    return {'code': 404,
                            'data': 'login-error-gzip decompress failed, check cookie format and gzip flag'}
            cookie_list = decoded_bytes.decode('utf-8')
            # 前端做了 JSON.stringify(cookie)，需要先 json.loads 去掉外层引号
            cookie_b64 = json.loads(cookie_list)
            # 再 base64 解码得到 cookie JSON
            cookie_json = base64.b64decode(cookie_b64).decode('utf-8')
            cookies = json.loads(cookie_json)
            for cookie in cookies:
                driver.add_cookie(cookie)
        except Exception as e:
            return {'code': 404, 'data': f'login-error-cookie parse error: {str(e)}'}
        driver.refresh()
        try:
            login_type_element = driver.find_element(By.XPATH, '//*[@id="douyin_login_comp_flat_panel"]/picture')
            login_type = login_type_element.text
            return {'code': 404, 'data': 'login-error-cooker cant login'}
        except NoSuchElementException:
            Login_is_bool = True
            return {'code': 200, 'data': 'ok'}
    else:
        return {'code': 404, 'data': 'login-error-not cooker'}


@app.get('/Api/Pnglogin')  # 扫码登录后检查状态
def PngLogin(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    global Login_is_bool
    drv_err = check_driver()
    if drv_err:
        return drv_err
    # 刷新页面检查登录状态（无需 cookie 自循环）
    driver.refresh()
    try:
        login_type_element = driver.find_element(By.XPATH, '//*[@id="douyin_login_comp_flat_panel"]/picture')
        # 找到登录弹窗 = 未登录
        Login_is_bool = False
        return {'code': 404, 'data': '系统繁忙,请稍后重新登录'}
    except NoSuchElementException:
        # 没有登录弹窗 = 已登录
        Login_is_bool = True
        return {'code': 200, 'data': 'ok'}


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
        # 短暂等待页面渲染（降低频率，避免频繁触发风控）
        time.sleep(0.3)
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
    if not password or not verify_pwd(password):
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
        if not friends_list:
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
        out = Douyin.Send_Frinder(douyin, name, text)
        if out.is_bool:
            return {'code': 200, 'data': 'Send successfully'}
        else:
            return {'code': 404, 'data': out.string or '发送失败'}
    except Exception as e:
        return {'code': 500, 'data': f'发送失败: {str(e)}'}


@app.get('/Api/GetStickerList')  # 获取表情包列表
def GetStickerList(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
    try:
        result = douyin.Get_Sticker_List()
        return result
    except Exception as e:
        return {'code': 500, 'data': f'获取表情包失败: {str(e)}'}


@app.get('/Api/SendSticker')  # 发送表情包
def SendSticker(name: str, sticker_index: int, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
    try:
        out = douyin.Send_Sticker(name, sticker_index)
        if out.is_bool:
            return {'code': 200, 'data': '表情包发送成功'}
        else:
            return {'code': 400, 'data': str(out.string) if out.string else '发送失败'}
    except Exception as e:
        return {'code': 500, 'data': f'发送表情包失败: {str(e)}'}


@app.get('/Api/GetChatHistory')  # 获取聊天记录
def GetChatHistory(name: str, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
    try:
        result = douyin.Get_Chat_History(name)
        return result
    except Exception as e:
        return {'code': 500, 'data': f'获取聊天记录失败: {str(e)}'}


@app.get('/Api/GetUsername')  # 获取用户名和头像
def GetUserInfo(authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
    if Login_is_bool:
        try:
            nickname = ''
            avatar = ''

            # 先从聊天页 DOM 尝试提取
            try:
                user_info = driver.execute_script('''
                    var nick = '', av = '';
                    var nickEl = document.querySelector('[data-e2e="user-info"] .nickname, .avatar-nickname, .nickname, [class*="userName"], [class*="nickname"]');
                    if (nickEl && nickEl.textContent) nick = nickEl.textContent.trim();
                    var imgs = document.querySelectorAll('img');
                    for (var i = 0; i < imgs.length; i++) {
                        var src = imgs[i].src || '';
                        if (src && src.indexOf('douyinpic') !== -1 && (src.indexOf('avatar') !== -1 || src.indexOf('head') !== -1)) { av = src; break; }
                    }
                    return {nick: nick, av: av};
                ''')
                if user_info:
                    nickname = user_info.get('nick', '') if isinstance(user_info, dict) else ''
                    avatar = user_info.get('av', '') if isinstance(user_info, dict) else ''
            except Exception:
                pass

            # 聊天页拿不到，去个人主页获取（模拟正常浏览行为，停留随机时间）
            if not nickname or not avatar:
                current_url = driver.current_url
                try:
                    driver.get('https://www.douyin.com/user/self?from_tab_name=main')
                    # 随机停留 3~6 秒，模拟正常浏览
                    time.sleep(random.uniform(3, 6))
                    user_info2 = driver.execute_script('''
                        var nick = '', av = '';
                        var h1 = document.querySelector('h1, [data-e2e="user-info"] h1, [class*="nickname"], [class*="userName"]');
                        if (h1 && h1.textContent) nick = h1.textContent.trim();
                        var imgs = document.querySelectorAll('img');
                        for (var i = 0; i < imgs.length; i++) {
                            var src = imgs[i].src || '';
                            if (src && src.indexOf('douyinpic') !== -1 && (src.indexOf('avatar') !== -1 || src.indexOf('head') !== -1)) { av = src; break; }
                        }
                        return {nick: nick, av: av};
                    ''')
                    if user_info2:
                        if not nickname:
                            nickname = user_info2.get('nick', '') if isinstance(user_info2, dict) else ''
                        if not avatar:
                            avatar = user_info2.get('av', '') if isinstance(user_info2, dict) else ''
                finally:
                    # 回到聊天页（也停留一会，模拟自然切换）
                    time.sleep(random.uniform(1, 2))
                    try:
                        driver.get(current_url)
                        time.sleep(random.uniform(1.0, 2.0))
                    except Exception:
                        pass

            # 正则兜底
            if not nickname or not avatar:
                page = driver.page_source
                if not nickname:
                    for pat in [r'\\"nickname\\":\\"([^\\"]+)\\"', r'"nickname":"([^"]+)"']:
                        m = re.search(pat, page)
                        if m:
                            nickname = m.group(1).strip()
                            break
                if not avatar:
                    for pat in [r'\\"avatar_thumb\\":\{\\"url_list\\":\["([^\\"]+)\\"', r'\\"avatar_medium\\":\{\\"url_list\\":\["([^\\"]+)\\"']:
                        m = re.search(pat, page)
                        if m:
                            avatar = m.group(1).replace('\\u002F', '/')
                            break

            if nickname:
                return {'code': 200, 'data': {'nickname': nickname, 'avatar': avatar}}
            else:
                return {'code': 400, 'data': {'nickname': '', 'avatar': ''}, 'msg': '已登录,但未获取到用户名'}
        except Exception as e:
            return {'code': 500, 'data': f'获取用户信息失败: {str(e)}'}
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
    global Login_is_bool
    drv_err = check_driver()
    if drv_err:
        return drv_err
    try:
        driver.delete_all_cookies()
        driver.refresh()
        Login_is_bool = False
        return {'code': 200, 'data': '已清除Cooke'}
    except Exception as e:
        return {'code': 500, 'data': f'清除Cookie失败: {str(e)}'}


@app.get('/Api/LoginPhone')  # 验证码登录
def LoginPhone(areacode: str, phone: str, authorization: str = Header(None)):
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
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
        return {'code': 400, 'data': str(e)}


@app.get('/Api/LoginPhoneInput')  # 验证码登录 2 输入验证码
def LoginPhoneInput(code: str, authorization: str = Header(None)):
    global Login_is_bool
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    drv_err = check_driver()
    if drv_err:
        return drv_err
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
        return {'code': 400, 'data': str(e)}


@app.get('/Api/LoginDebug')  # 强制登录状态（调试用，需密码确认）
def LoginDebug(password: str = Query(None), authorization: str = Header(None)):
    global Login_is_bool
    auth_err = require_auth(authorization)
    if auth_err:
        return auth_err
    # 调试接口需二次密码确认，防止误用
    if not password or not verify_pwd(password):
        return {'code': 403, 'data': '需要密码确认才能使用此功能'}
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
    drv_err = check_driver()
    if drv_err:
        return drv_err
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
    if task_id in scheduled_tasks:
        job = scheduled_tasks[task_id]
        schedule.cancel_job(job)
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

    # 创建新任务（保留原消息，不覆盖）
    new_play_time = format_time(new_time)
    # 从旧 job 提取原消息
    old_msg = ''
    try:
        old_msg = old_job.job_func.args[2] if len(old_job.job_func.args) > 2 else ''
    except Exception:
        pass
    msg = old_msg if old_msg else AiqingGongyu_text()
    new_job = schedule.every().day.at(new_play_time).do(douyin.Send_Frinder, name, msg)

    # 生成新任务ID并替换
    new_task_id = f"{new_play_time}_{name}"
    scheduled_tasks[new_task_id] = new_job
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
    if username == 'admin' and verify_pwd(password):
        client_host = '127.0.0.1'
        if request and request.client:
            client_host = '127.0.0.1' if request.client.host in ('::1', '127.0.0.1') else request.client.host
        _last_login_ip = client_host
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
    global _password_hash
    if not verify_pwd(old_password):
        return {'code': 400, 'data': '原密码错误'}
    _password_hash = hash_pwd(new_password)
    config['password_hash'] = _password_hash
    config.pop('password', None)  # 确保明文已清除
    save_config(config)
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


import atexit


def cleanup_on_exit():
    """程序退出时清理浏览器进程"""
    global driver, init
    if init and driver:
        try:
            driver.quit()
        except Exception:
            pass


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


