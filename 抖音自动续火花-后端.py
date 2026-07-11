import re, os, gzip, socket, random, platform
from selenium import webdriver
from selenium.webdriver import Keys
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import SessionNotCreatedException
from selenium.common.exceptions import WebDriverException
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

BROWSER_LABELS = {
    'edge': 'Microsoft Edge',
    'chrome': 'Google Chrome',
    'chromium': 'Chromium',
    'brave': 'Brave'
}

BROWSER_ALIASES = {
    'msedge': 'edge',
    'microsoft-edge': 'edge',
    'google-chrome': 'chrome',
    'google chrome': 'chrome',
    'chromium-browser': 'chromium',
    'brave-browser': 'brave',
    'brave browser': 'brave'
}

DEFAULT_MESSAGE_TEMPLATES = [
    '今天也要开心呀',
    '来给你续一下小火花',
    '忙完记得回我一下呀',
    '保持联系，火花不能断',
    '给你留个言，祝你今天顺顺利利'
]


def get_default_browser_name():
    """Windows 保持 Edge 兼容性，Linux/macOS 默认改为 Chrome。"""
    return 'edge' if os.name == 'nt' else 'chrome'


def normalize_browser_name(name):
    browser_name = (name or '').strip().lower()
    browser_name = BROWSER_ALIASES.get(browser_name, browser_name)
    return browser_name if browser_name in BROWSER_LABELS else get_default_browser_name()


def get_browser_label(browser_name):
    return BROWSER_LABELS.get(normalize_browser_name(browser_name), BROWSER_LABELS[get_default_browser_name()])


def normalize_message_templates(value):
    templates = []
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value or '').replace('||', '\n').splitlines()
    for item in raw_items:
        text = str(item or '').strip()
        if text and text not in templates:
            templates.append(text[:200])
    return templates[:30] if templates else list(DEFAULT_MESSAGE_TEMPLATES)


def clamp_int(value, default, minimum, maximum):
    try:
        out = int(value)
    except Exception:
        out = default
    return max(minimum, min(maximum, out))


def now_str():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# #region debug-point shared:reporter
def _dbg_report(hypothesis_id: str, location: str, msg: str, data=None, run_id: str = 'post-fix'):
    try:
        import urllib.request
        debug_env = os.path.join(BASE_DIR, '.dbg', 'chat-sticker-sync.env')
        debug_url = 'http://127.0.0.1:7777/event'
        debug_session = 'chat-sticker-sync'
        try:
            with open(debug_env, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('DEBUG_SERVER_URL='):
                        debug_url = line.split('=', 1)[1].strip() or debug_url
                    elif line.startswith('DEBUG_SESSION_ID='):
                        debug_session = line.split('=', 1)[1].strip() or debug_session
        except Exception:
            pass
        payload = json.dumps({
            'sessionId': debug_session,
            'runId': run_id,
            'hypothesisId': hypothesis_id,
            'location': location,
            'msg': f'[DEBUG] {msg}',
            'data': data or {},
            'ts': int(time.time() * 1000)
        }, ensure_ascii=False).encode('utf-8')
        urllib.request.urlopen(
            urllib.request.Request(debug_url, data=payload, headers={'Content-Type': 'application/json'}),
            timeout=1.5
        ).read()
    except Exception:
        pass
# #endregion


def load_config():
    """读取配置文件，不存在则返回默认配置"""
    default = {
        'port': 8080,
        'show_browser': True,
        'browser_name': get_default_browser_name(),
        'browser_path': '',
        'task_jitter_minutes': 8,
        'max_consecutive_failures': 3,
        'dedupe_window_days': 7,
        'message_templates': list(DEFAULT_MESSAGE_TEMPLATES)
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                default.update(cfg)
        except Exception:
            pass
    default['browser_name'] = normalize_browser_name(default.get('browser_name'))
    default['browser_path'] = (default.get('browser_path') or '').strip()
    default['task_jitter_minutes'] = clamp_int(default.get('task_jitter_minutes', 8), 8, 0, 60)
    default['max_consecutive_failures'] = clamp_int(default.get('max_consecutive_failures', 3), 3, 1, 10)
    default['dedupe_window_days'] = clamp_int(default.get('dedupe_window_days', 7), 7, 1, 30)
    default['message_templates'] = normalize_message_templates(default.get('message_templates'))
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


def get_profile_dir(browser_name):
    browser_name = normalize_browser_name(browser_name)
    if browser_name == 'edge':
        # 兼容旧目录，避免升级后丢失已有登录态
        return os.path.join(BASE_DIR, 'edge_user_data')
    return os.path.join(BASE_DIR, f'{browser_name}_user_data')


def build_browser_options():
    browser_name = normalize_browser_name(config.get('browser_name'))
    browser_path = (config.get('browser_path') or '').strip()
    show_browser = bool(config.get('show_browser', True))
    profile_dir = get_profile_dir(browser_name)
    os.makedirs(profile_dir, exist_ok=True)

    if browser_name == 'edge':
        options = webdriver.EdgeOptions()
        if not show_browser:
            options.add_argument('--headless=new')
        options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
        options.add_argument('log-level=3')
        options.add_argument(
            'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36'
        )
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-notifications')
        options.add_argument('--disable-popup-blocking')
        options.add_argument('--disable-web-security')
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--no-sandbox')
        options.add_argument('--start-maximized')
        options.add_argument(f'--user-data-dir={profile_dir}')
        if browser_path:
            options.binary_location = browser_path
        return options

    options = webdriver.ChromeOptions()
    if not show_browser:
        options.add_argument('--headless=new')
    options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
    options.add_argument('log-level=3')
    options.add_argument(
        'user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36'
    )
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-infobars')
    options.add_argument('--disable-notifications')
    options.add_argument('--disable-popup-blocking')
    options.add_argument('--disable-web-security')
    options.add_argument('--ignore-certificate-errors')
    options.add_argument('--no-sandbox')
    options.add_argument('--start-maximized')
    options.add_argument(f'--user-data-dir={profile_dir}')
    if browser_path:
        options.binary_location = browser_path
    return options


def create_webdriver():
    browser_name = normalize_browser_name(config.get('browser_name'))
    options = build_browser_options()
    if browser_name == 'edge':
        return webdriver.Edge(options=options)
    return webdriver.Chrome(options=options)


RISK_STATE_FILE = os.path.join(BASE_DIR, 'risk_state.json')


def load_risk_state():
    default = {
        'paused': False,
        'pause_reason': '',
        'paused_at': '',
        'consecutive_failures': 0,
        'last_error': '',
        'last_failure_at': '',
        'last_success_at': '',
        'last_sent_at': '',
        'today_send_count': 0,
        'today_send_date': '',
        'recent_messages': []
    }
    if os.path.exists(RISK_STATE_FILE):
        try:
            with open(RISK_STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
                if isinstance(state, dict):
                    default.update(state)
        except Exception:
            pass
    if not isinstance(default.get('recent_messages'), list):
        default['recent_messages'] = []
    return default


def prune_risk_state():
    today = datetime.now().strftime('%Y-%m-%d')
    if risk_state.get('today_send_date') != today:
        risk_state['today_send_date'] = today
        risk_state['today_send_count'] = 0
    keep_days = max(config.get('dedupe_window_days', 7), 7) + 2
    cutoff = datetime.now().timestamp() - keep_days * 86400
    kept = []
    for item in risk_state.get('recent_messages', []):
        try:
            sent_at = item.get('sent_at', '')
            ts = datetime.strptime(sent_at, '%Y-%m-%d %H:%M:%S').timestamp()
            if ts >= cutoff:
                kept.append(item)
        except Exception:
            continue
    risk_state['recent_messages'] = kept[-200:]


def save_risk_state():
    prune_risk_state()
    try:
        with open(RISK_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(risk_state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'⚠️ 风控状态保存失败: {e}')


def pause_risk(reason):
    risk_state['paused'] = True
    risk_state['pause_reason'] = reason
    risk_state['paused_at'] = now_str()
    save_risk_state()


def resume_risk():
    risk_state['paused'] = False
    risk_state['pause_reason'] = ''
    risk_state['paused_at'] = ''
    risk_state['consecutive_failures'] = 0
    risk_state['last_error'] = ''
    save_risk_state()


def record_send_success(name: str, content: str, source: str):
    risk_state['consecutive_failures'] = 0
    risk_state['last_error'] = ''
    risk_state['last_success_at'] = now_str()
    risk_state['last_sent_at'] = risk_state['last_success_at']
    risk_state['today_send_count'] = int(risk_state.get('today_send_count', 0)) + 1
    risk_state.setdefault('recent_messages', []).append({
        'name': name,
        'content': content[:200],
        'source': source,
        'sent_at': risk_state['last_success_at']
    })
    save_risk_state()


def record_send_failure(reason: str):
    risk_state['consecutive_failures'] = int(risk_state.get('consecutive_failures', 0)) + 1
    risk_state['last_error'] = reason[:300]
    risk_state['last_failure_at'] = now_str()
    threshold = config.get('max_consecutive_failures', 3)
    if risk_state['consecutive_failures'] >= threshold:
        pause_risk(f'连续失败 {risk_state["consecutive_failures"]} 次，已自动暂停任务。最近错误：{reason[:120]}')
    else:
        save_risk_state()


def split_message_candidates(raw_message):
    message = str(raw_message or '').strip()
    if not message:
        candidates = list(config.get('message_templates') or DEFAULT_MESSAGE_TEMPLATES)
        daily_quote = AiqingGongyu_text()
        if daily_quote and daily_quote not in candidates:
            candidates.append(daily_quote)
        return normalize_message_templates(candidates)
    return normalize_message_templates(message)


def pick_message_content(name: str, raw_message: str):
    candidates = split_message_candidates(raw_message)
    dedupe_days = config.get('dedupe_window_days', 7)
    cutoff = datetime.now().timestamp() - dedupe_days * 86400
    recent_texts = set()
    for item in risk_state.get('recent_messages', []):
        try:
            if item.get('name') != name:
                continue
            ts = datetime.strptime(item.get('sent_at', ''), '%Y-%m-%d %H:%M:%S').timestamp()
            if ts >= cutoff:
                recent_texts.add(item.get('content', ''))
        except Exception:
            continue
    available = [item for item in candidates if item not in recent_texts]
    pool = available if available else candidates
    return random.choice(pool) if pool else AiqingGongyu_text()


risk_state = load_risk_state()


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
            return TrueString(False, '操作失败')

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

    def _open_emoji_panel(self):
        """点击表情按钮打开表情面板。
        两步法：JS 定位按钮并标记 → ActionChains 真实点击（React 合成事件需要真实点击）。
        """
        # Step 1: JS 找到表情按钮，标记 data-emoji-btn 属性
        result = driver.execute_script(r'''
            function isUnsafe(el) {
                if (!el) return true;
                if (el.tagName === 'A') return true;
                if (el.getAttribute && el.getAttribute('href')) return true;
                var cls = (el.getAttribute && el.getAttribute('class')) ? el.getAttribute('class') : ((el.className||'')+'').toString();
                if (/MessageItem|MessageBubble/i.test(cls)) return true;
                if (/avatar|Avatar|user|User|nick|Nick|link|Link|profile|Profile/i.test(cls)) return true;
                if (el.getAttribute && el.getAttribute('contenteditable') === 'true') return true;
                var clsLower = cls.toLowerCase();
                if (clsLower.indexOf('send') !== -1) return true;
                var txt = (el.textContent||'').trim();
                if (txt.indexOf('发送') !== -1 || txt.indexOf('Send') !== -1) return true;
                return false;
            }

            // 清除旧标记
            var old = document.querySelectorAll('[data-emoji-btn]');
            for (var i = 0; i < old.length; i++) old[i].removeAttribute('data-emoji-btn');

            var bottomLimit = window.innerHeight * 0.5;

            // 策略1：精准匹配已确认的表情按钮 class
            var preciseSelectors = [
                '[class*="messageMsgInputiconAction"]',
                '[class*="componentsemojiemojiPanel"]',
                '[class*="emojiBtn"]', '[class*="emoji-btn"]', '[class*="EmojiBtn"]',
                '[class*="emojiPicker"]', '[class*="emoji-picker"]',
                '[data-e2e*="emoji"]', '[class*="EmojiIcon"]',
                '[class*="chatEmoji"]', '[class*="editorEmoji"]',
                'button[aria-label*="表情"]', '[title*="表情"]',
                '[class*="emoji-toggle"]', '[class*="emojiToggle"]'
            ];
            for (var s = 0; s < preciseSelectors.length; s++) {
                var els = document.querySelectorAll(preciseSelectors[s]);
                for (var i = 0; i < els.length; i++) {
                    if (isUnsafe(els[i])) continue;
                    var rect = els[i].getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0 && rect.top < window.innerHeight && rect.bottom > 0) {
                        els[i].setAttribute('data-emoji-btn', '1');
                        return {ok: true, method: 'selector:' + preciseSelectors[s], tag: els[i].tagName};
                    }
                }
            }
            // 策略2：底部区域 class 含 emoji/sticker
            var all = document.querySelectorAll('[class*="emoji"], [class*="Emoji"], [class*="sticker"], [class*="Sticker"]');
            for (var i = 0; i < all.length; i++) {
                if (isUnsafe(all[i])) continue;
                var rect = all[i].getBoundingClientRect();
                if (rect.width >= 16 && rect.height >= 16 && rect.top > bottomLimit && rect.top < window.innerHeight) {
                    all[i].setAttribute('data-emoji-btn', '1');
                    return {ok: true, method: 'bottom-scan:' + ((all[i].getAttribute('class')||'')).slice(0,60), tag: all[i].tagName};
                }
            }
            return {ok: false, method: 'none'};
        ''')
        print(f'[emoji-panel] locate result: {result}', flush=True)

        if not result or not result.get('ok'):
            return False

        # Step 2: 用 ActionChains 真实点击标记的元素
        try:
            from selenium.webdriver.common.action_chains import ActionChains
            el = driver.find_element(By.CSS_SELECTOR, '[data-emoji-btn="1"]')
            ActionChains(driver).move_to_element(el).click().perform()
            print(f'[emoji-panel] ActionChains click done', flush=True)
            driver.execute_script('var e=document.querySelector("[data-emoji-btn]"); if(e) e.removeAttribute("data-emoji-btn");')
            return True
        except Exception as e:
            print(f'[emoji-panel] ActionChains click failed: {e}', flush=True)
            try:
                driver.execute_script('var e=document.querySelector("[data-emoji-btn]"); if(e) e.click();')
                return True
            except:
                return False

    def _find_emoji_panel(self):
        """查找表情面板容器元素"""
        return driver.execute_script('''
            var selectors = [
                '[class*="emojiEmojisModal"]', '[class*="EmojiModal"]',
                '[class*="emojiPanel"]', '[class*="emoji-panel"]',
                '[class*="stickerPanel"]', '[class*="sticker-panel"]',
                '[class*="emojiModalContent"]', '[class*="emojiContainer"]',
                '[class*="emoji-content"]', '[class*="EmojiContent"]',
                '[role="dialog"][class*="emoji"]', '[class*="emoji-popover"]',
                '[class*="EmojiPopover"]', '[class*="expression"]'
            ];
            for (var s = 0; s < selectors.length; s++) {
                var els = document.querySelectorAll(selectors[s]);
                for (var i = 0; i < els.length; i++) {
                    var rect = els[i].getBoundingClientRect();
                    if (rect.width > 100 && rect.height > 100 && rect.top < window.innerHeight && rect.bottom > 0) {
                        return els[i].className || 'found';
                    }
                }
            }
            // 找浮层：页面中间偏下、大尺寸、有很多img的div
            var divs = document.querySelectorAll('div');
            for (var i = 0; i < divs.length; i++) {
                var rect = divs[i].getBoundingClientRect();
                if (rect.width > 200 && rect.height > 150 && rect.top > window.innerHeight * 0.3 && rect.bottom < window.innerHeight + 50) {
                    var imgCount = divs[i].querySelectorAll('img').length;
                    if (imgCount >= 6) return divs[i].className || 'popup';
                }
            }
            return null;
        ''')

    def _collect_stickers(self):
        """收集当前表情面板中所有表情，按 tab 分类返回。
        返回 {categories: [{tab_index, label, icon_html, stickers:[src]}], flat_list:[src], debug}
        """
        driver.set_script_timeout(45)
        return driver.execute_async_script(r'''
            var callback = arguments[arguments.length - 1];
            var categories = [];
            var flatList = [];
            var globalSeen = {};
            var dbg = {};

            function isStickerImg(img) {
                var src = img.src || img.getAttribute('data-src') || '';
                if (!src || src.length < 5) return false;
                var rect = img.getBoundingClientRect();
                if (rect.width < 12 || rect.width > 300 || rect.height < 12 || rect.height > 300) return false;
                if (src.indexOf('avatar') !== -1 || src.indexOf('/head_') !== -1) return false;
                var p = img.parentElement;
                for (var d = 0; d < 5 && p; d++) {
                    var cls = ((p.className||'')+'').toString();
                    if (/MessageItem|MessageBubble/i.test(cls)) return false;
                    p = p.parentElement;
                }
                var style = window.getComputedStyle(img);
                var parentClickable = false;
                p = img.parentElement;
                for (var d = 0; d < 5 && p; d++) {
                    var ps = window.getComputedStyle(p);
                    if (ps.cursor === 'pointer' || p.tagName === 'BUTTON' || p.getAttribute('role') === 'button') {
                        parentClickable = true; break;
                    }
                    p = p.parentElement;
                }
                if (style.cursor === 'pointer' || parentClickable) return true;
                if (src.indexOf('douyinpic') !== -1 || src.indexOf('byteimg') !== -1 ||
                    src.indexOf('tos-cn') !== -1 || src.indexOf('emoji') !== -1 ||
                    src.indexOf('sticker') !== -1 || src.indexOf('sf-tk') !== -1 ||
                    src.indexOf('.webp') !== -1 || src.indexOf('.gif') !== -1 ||
                    src.indexOf('emoticon') !== -1 || /\/\d+x\d+\//.test(src)) return true;
                return false;
            }

            function findPanel() {
                var precise = document.querySelector('[class*="componentsemojiemojiPanel"]');
                if (precise) { var pr = precise.getBoundingClientRect(); if (pr.width > 100 && pr.height > 100) return precise; }
                var candidates = [];
                var selectors = ['[class*="emojiEmojisModal"]','[class*="EmojiModal"]','[class*="emojiPanel"]','[class*="stickerPanel"]','[class*="emojiModalContent"]','[class*="emojiContainer"]','[class*="emoji-content"]','[class*="emoji-popover"]','[class*="EmojiPopover"]','[class*="expression"]','[class*="EmojiContent"]','[class*="emojiList"]','[class*="stickerList"]','[class*="EmojiList"]'];
                for (var s = 0; s < selectors.length; s++) { var els = document.querySelectorAll(selectors[s]); for (var i = 0; i < els.length; i++) candidates.push(els[i]); }
                var divs = document.querySelectorAll('div');
                for (var i = 0; i < divs.length; i++) {
                    var cls = ((divs[i].className || '') + '').toString();
                    if (/MessageItem|MessageBubble/i.test(cls)) continue;
                    var cl = cls.toLowerCase();
                    if (cl.indexOf('emoji') !== -1 || cl.indexOf('sticker') !== -1 || cl.indexOf('expression') !== -1) candidates.push(divs[i]);
                }
                var best = null, bestScore = 0;
                for (var i = 0; i < candidates.length; i++) {
                    var rect = candidates[i].getBoundingClientRect();
                    if (rect.width < 200 || rect.height < 120) continue;
                    if (rect.top < window.innerHeight * 0.25) continue;
                    if (rect.bottom > window.innerHeight + 100) continue;
                    var imgCount = candidates[i].querySelectorAll('img').length;
                    if (imgCount < 4) continue;
                    var score = (rect.top / window.innerHeight) * 10 + imgCount;
                    if (score > bestScore) { bestScore = score; best = candidates[i]; }
                }
                return best;
            }

            function collectPanelStickers(panel) {
                var stickers = [];
                var localSeen = {};
                if (!panel) return stickers;
                function collectImgs(el) {
                    var imgs = el.querySelectorAll('img');
                    for (var i = 0; i < imgs.length; i++) {
                        if (!isStickerImg(imgs[i])) continue;
                        var src = imgs[i].src || imgs[i].getAttribute('data-src') || '';
                        if (src.length > 5 && !localSeen[src]) { localSeen[src] = 1; stickers.push(src); }
                    }
                }
                collectImgs(panel);
                var scrollEl = panel;
                var scrollables = panel.querySelectorAll('div, ul, section');
                for (var i = 0; i < scrollables.length; i++) {
                    var st = window.getComputedStyle(scrollables[i]);
                    if (st.overflowY === 'auto' || st.overflowY === 'scroll') { scrollEl = scrollables[i]; break; }
                }
                var step = Math.max(100, (scrollEl.clientHeight||200) * 0.8);
                var maxScroll = scrollEl.scrollHeight || 0;
                for (var pos = step; pos < maxScroll && pos < 99999; pos += step) {
                    scrollEl.scrollTop = pos;
                    collectImgs(panel);
                }
                scrollEl.scrollTop = 0;
                return stickers;
            }

            var tabSelectors = ['[class*="emojiEmojisModalTabsubTab"]','[class*="emojiTab"]','[class*="emoji-tab"]','[class*="TabItem"]','[class*="tab-item"]','[role="tab"]','[class*="tabBar"] [class*="item"]','[class*="TabBar"] [class*="item"]'];
            var tabs = [];
            for (var s = 0; s < tabSelectors.length; s++) {
                var ts = document.querySelectorAll(tabSelectors[s]);
                for (var i = 0; i < ts.length; i++) {
                    var rect = ts[i].getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0 && rect.top < window.innerHeight) {
                        var p = ts[i], inMsg = false;
                        for (var d = 0; d < 5 && p; d++) {
                            var cls = ((p.className||'')+'').toString();
                            if (/MessageItem|MessageBubble/i.test(cls)) { inMsg = true; break; }
                            p = p.parentElement;
                        }
                        if (!inMsg) tabs.push(ts[i]);
                    }
                }
                if (tabs.length > 0) break;
            }
            var uniqueTabs = [];
            var tabSeen = {};
            for (var i = 0; i < tabs.length; i++) {
                var key = tabs[i].textContent.trim() + '_' + Math.round(tabs[i].getBoundingClientRect().left);
                if (!tabSeen[key]) { tabSeen[key] = 1; uniqueTabs.push(tabs[i]); }
            }
            uniqueTabs.sort(function(a, b) { return a.getBoundingClientRect().left - b.getBoundingClientRect().left; });
            dbg.tabCount = uniqueTabs.length;

            if (uniqueTabs.length === 0) {
                var panel = findPanel();
                dbg.panelFound = !!panel;
                var stickers = collectPanelStickers(panel);
                for (var i = 0; i < stickers.length; i++) { if (!globalSeen[stickers[i]]) { globalSeen[stickers[i]] = 1; flatList.push(stickers[i]); } }
                categories.push({tab_index: 0, label: '全部', icon_html: '', stickers: stickers});
                dbg.resultCount = flatList.length;
                callback({categories: categories, flat_list: flatList, debug: dbg});
                return;
            }

            var t = 0;
            function processTab() {
                if (t >= uniqueTabs.length) {
                    dbg.resultCount = flatList.length;
                    callback({categories: categories, flat_list: flatList, debug: dbg});
                    return;
                }
                var tabEl = uniqueTabs[t];
                var tabIndex = t;
                var label = (tabEl.textContent || '').trim().slice(0, 10) || ('分类' + (t + 1));
                var iconHtml = tabEl.innerHTML.slice(0, 500);
                try { if (typeof tabEl.click === 'function') tabEl.click(); else { var pp = tabEl.parentElement; while (pp && typeof pp.click !== 'function') pp = pp.parentElement; if (pp) pp.click(); } } catch(e) {}
                t++;
                setTimeout(function() {
                    var panel = findPanel();
                    var stickers = collectPanelStickers(panel);
                    for (var i = 0; i < stickers.length; i++) { if (!globalSeen[stickers[i]]) { globalSeen[stickers[i]] = 1; flatList.push(stickers[i]); } }
                    if (stickers.length > 0) {
                        categories.push({tab_index: tabIndex, label: label, icon_html: iconHtml, stickers: stickers});
                    }
                    processTab();
                }, 800);
            }
            processTab();
        ''')

    def _click_sticker_by_src(self, sticker_src):
        """按 src 精准定位表情图片，用 ActionChains 真实点击
        抖音图片 CDN 会随机分配节点（p3/p9/p26），同一表情域名不同，
        所以 normalizeSrc 去掉域名只比较 path 末段（文件名）。
        切换 tab 后表情图片是异步加载的，所以先等待图片数量稳定再匹配。
        """
        from selenium.webdriver.common.action_chains import ActionChains
        driver.set_script_timeout(25)
        found = driver.execute_async_script(r'''
            var callback = arguments[arguments.length - 1];
            var targetSrc = arguments[0] || '';
            if (!targetSrc) { callback({found: false, reason: 'no src'}); return; }
            // 归一化：去掉域名，只保留 path 末段（文件名），CDN 节点不同也能匹配
            function normalizeSrc(s) {
                var url = (s||'').split('#')[0].split('?')[0];
                var path = url.replace(/^https?:\/\/[^/]+\//, '');
                var parts = path.split('/');
                return parts[parts.length - 1] || path;
            }
            var nt = normalizeSrc(targetSrc);
            function findPanel() {
                var precise = document.querySelector('[class*="componentsemojiemojiPanel"]');
                if (precise) { var pr = precise.getBoundingClientRect(); if (pr.width > 100 && pr.height > 100) return precise; }
                var sels = ['[class*="emoji"]', '[class*="Emoji"]', '[class*="sticker"]', '[class*="Sticker"]', '[class*="expression"]'];
                var best = null, bestScore = 0;
                for (var s = 0; s < sels.length; s++) {
                    var els = document.querySelectorAll(sels[s]);
                    for (var i = 0; i < els.length; i++) {
                        var cls = ((els[i].className||'')+'').toString();
                        if (/MessageItem/i.test(cls)) continue;
                        var rect = els[i].getBoundingClientRect();
                        if (rect.width < 200 || rect.height < 120) continue;
                        if (rect.top < window.innerHeight * 0.25) continue;
                        if (rect.bottom > window.innerHeight + 100) continue;
                        var imgCount = els[i].querySelectorAll('img').length;
                        if (imgCount < 2) continue;
                        var score = (rect.top / window.innerHeight) * 10 + imgCount;
                        if (score > bestScore) { bestScore = score; best = els[i]; }
                    }
                }
                return best;
            }

            // ===== 等待图片加载稳定 =====
            // 切换 tab 后抖音异步加载表情图片，需要轮询直到 img 数量不再增长
            function waitForImagesStable(panel, maxWaitMs, onDone) {
                if (!panel) { onDone(0); return; }
                var lastCount = -1;
                var stableCount = 0;
                var elapsed = 0;
                var interval = 300;
                function check() {
                    var imgs = panel.querySelectorAll('img');
                    var count = imgs.length;
                    if (count === lastCount && count >= 2) {
                        stableCount++;
                        // 连续 2 次数量不变，认为加载稳定
                        if (stableCount >= 2) { onDone(count); return; }
                    } else {
                        stableCount = 0;
                    }
                    lastCount = count;
                    elapsed += interval;
                    if (elapsed >= maxWaitMs) { onDone(count); return; }
                    setTimeout(check, interval);
                }
                check();
            }

            var panel = findPanel();
            if (!panel) { callback({found: false, reason: 'no panel'}); return; }

            // 先等待图片加载稳定（最多 6 秒）
            waitForImagesStable(panel, 6000, function(finalCount) {
                // 加载稳定后，尝试匹配
                function tryMatch(imgs) {
                    for (var i = 0; i < imgs.length; i++) {
                        var src = imgs[i].src || imgs[i].getAttribute('data-src') || '';
                        if (src === targetSrc || normalizeSrc(src) === nt) return imgs[i];
                    }
                    return null;
                }
                var target = tryMatch(panel.querySelectorAll('img'));
                // 滚动查找
                if (!target) {
                    var scrollEl = panel;
                    var scrollables = panel.querySelectorAll('div, ul, section');
                    for (var i = 0; i < scrollables.length; i++) {
                        var st = window.getComputedStyle(scrollables[i]);
                        if (st.overflowY === 'auto' || st.overflowY === 'scroll') { scrollEl = scrollables[i]; break; }
                    }
                    var step = Math.max(100, (scrollEl.clientHeight||200) * 0.8);
                    var maxScroll = scrollEl.scrollHeight || 0;
                    var pos = step;
                    function scrollFind() {
                        if (pos >= maxScroll || pos >= 99999) {
                            if (target) scrollEl.scrollTop = 0;
                            finish();
                            return;
                        }
                        scrollEl.scrollTop = pos;
                        target = tryMatch(panel.querySelectorAll('img'));
                        if (target) { scrollEl.scrollTop = 0; finish(); return; }
                        pos += step;
                        setTimeout(scrollFind, 50);
                    }
                    scrollFind();
                } else {
                    finish();
                }

                function finish() {
                    if (!target) {
                        var imgs = panel.querySelectorAll('img');
                        var sample = [];
                        for (var i = 0; i < Math.min(imgs.length, 5); i++) sample.push((imgs[i].src||'').slice(-80));
                        callback({found: false, reason: 'src not found in panel',
                                  img_count: imgs.length, stable_count: finalCount,
                                  target_norm: nt.slice(-60), sample: sample});
                        return;
                    }
                    var old = document.querySelectorAll('[data-sticker-click]');
                    for (var i = 0; i < old.length; i++) old[i].removeAttribute('data-sticker-click');
                    target.setAttribute('data-sticker-click', '1');
                    try { target.scrollIntoView({block:'center', behavior:'instant'}); } catch(e) {}
                    callback({found: true, src_tail: (target.src||'').slice(-60), stable_count: finalCount});
                }
            });
        ''', sticker_src)
        print(f'[sticker] found={found}', flush=True)
        if not found or not found.get('found'):
            return False

        # Step 2: 用 ActionChains 真实点击 — 尝试 img 本身和父级容器
        # React/Vue 的 onClick 通常绑定在父容器上，不只是 img
        for level in range(4):
            selector = '[data-sticker-click="1"]'
            if level > 0:
                selector = f'[data-sticker-click="{level+1}"]'

            try:
                el = driver.find_element(By.CSS_SELECTOR, selector)
            except Exception:
                break

            ActionChains(driver).move_to_element(el).click().perform()
            print(f'[sticker] ActionChains click done (level={level})', flush=True)

            # 检查输入框是否有内容（找最大的底部输入框，排除聊天记录）
            time.sleep(0.3)
            has_content = driver.execute_script(r'''
                var eds = document.querySelectorAll('[contenteditable="true"]');
                var best = null, bestArea = 0;
                for (var i = 0; i < eds.length; i++) {
                    var rect = eds[i].getBoundingClientRect();
                    if (rect.width < 50 || rect.height < 20) continue;
                    if (rect.bottom < window.innerHeight * 0.5) continue;
                    var p = eds[i];
                    for (var d = 0; d < 5 && p; d++) {
                        var cls = ((p.className||'')+'').toString();
                        if (/MessageItem|MessageBubble/i.test(cls)) { p = null; break; }
                        p = p.parentElement;
                    }
                    if (!p) continue;
                    var area = rect.width * rect.height;
                    if (area > bestArea) { bestArea = area; best = eds[i]; }
                }
                if (!best) return false;
                return !!(best.querySelector('img') || (best.textContent || '').trim().length > 0);
            ''')
            print(f'[sticker] input has_content={has_content} (level={level})', flush=True)

            if has_content:
                # 成功！清除标记
                driver.execute_script('var es=document.querySelectorAll("[data-sticker-click]"); for(var i=0;i<es.length;i++) es[i].removeAttribute("data-sticker-click");')
                return True

            # 点击当前层没效果，标记父级容器再试
            if level < 3:
                driver.execute_script(f'''
                    var el = document.querySelector('[data-sticker-click="{level+1}"]');
                    if (el && el.parentElement) {{
                        el.removeAttribute('data-sticker-click');
                        el.parentElement.setAttribute('data-sticker-click', '{level+2}');
                    }}
                ''')

        # 清除标记
        driver.execute_script('var es=document.querySelectorAll("[data-sticker-click]"); for(var i=0;i<es.length;i++) es[i].removeAttribute("data-sticker-click");')
        print(f'[sticker] all levels tried, input still empty', flush=True)
        return False

    _sticker_categories = []
    _sticker_src_map = {}

    def _switch_emoji_tab(self, tab_index):
        """切换表情面板到指定 tab（用 ActionChains 真实点击）
        选择器和 _collect_stickers 完全一致，确保 tab 顺序相同。
        点击后等待图片加载稳定，避免竞态条件。
        """
        from selenium.webdriver.common.action_chains import ActionChains
        driver.set_script_timeout(15)
        result = driver.execute_script(r'''
            var idx = arguments[0];
            var tabSelectors = ['[class*="emojiEmojisModalTabsubTab"]','[class*="emojiTab"]','[class*="emoji-tab"]','[class*="TabItem"]','[class*="tab-item"]','[role="tab"]','[class*="tabBar"] [class*="item"]','[class*="TabBar"] [class*="item"]'];
            var tabs = [];
            for (var s = 0; s < tabSelectors.length; s++) {
                var ts = document.querySelectorAll(tabSelectors[s]);
                for (var i = 0; i < ts.length; i++) {
                    var rect = ts[i].getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0 && rect.top < window.innerHeight) {
                        var p = ts[i], inMsg = false;
                        for (var d = 0; d < 5 && p; d++) {
                            var cls = ((p.className||'')+'').toString();
                            if (/MessageItem|MessageBubble/i.test(cls)) { inMsg = true; break; }
                            p = p.parentElement;
                        }
                        if (!inMsg) tabs.push(ts[i]);
                    }
                }
                if (tabs.length > 0) break;
            }
            var seen = {}; var unique = [];
            for (var i = 0; i < tabs.length; i++) {
                var key = tabs[i].textContent.trim() + '_' + Math.round(tabs[i].getBoundingClientRect().left);
                if (!seen[key]) { seen[key] = 1; unique.push(tabs[i]); }
            }
            unique.sort(function(a, b) { return a.getBoundingClientRect().left - b.getBoundingClientRect().left; });
            if (idx >= unique.length) return {ok: false, reason: 'tab_index out of range', tab_count: unique.length};
            var old = document.querySelectorAll('[data-emoji-tab]');
            for (var i = 0; i < old.length; i++) old[i].removeAttribute('data-emoji-tab');
            unique[idx].setAttribute('data-emoji-tab', '1');
            return {ok: true, tab_count: unique.length};
        ''', tab_index)
        if not result or not result.get('ok'):
            print(f'[emoji-tab] switch failed: {result}', flush=True)
            return False
        try:
            el = driver.find_element(By.CSS_SELECTOR, '[data-emoji-tab="1"]')
            ActionChains(driver).move_to_element(el).click().perform()
            driver.execute_script('var e=document.querySelector("[data-emoji-tab]"); if(e) e.removeAttribute("data-emoji-tab");')
            print(f'[emoji-tab] switched to tab {tab_index}', flush=True)
            # 等待 tab 切换动画 + 图片开始加载
            time.sleep(1.5)
            # 再用 JS 等待面板图片数量稳定（异步加载完成）
            driver.set_script_timeout(12)
            stable = driver.execute_async_script(r'''
                var callback = arguments[arguments.length - 1];
                function findPanel() {
                    var precise = document.querySelector('[class*="componentsemojiemojiPanel"]');
                    if (precise) { var pr = precise.getBoundingClientRect(); if (pr.width > 100 && pr.height > 100) return precise; }
                    var sels = ['[class*="emojiEmojisModal"]','[class*="EmojiModal"]','[class*="emojiPanel"]','[class*="stickerPanel"]'];
                    for (var s = 0; s < sels.length; s++) {
                        var el = document.querySelector(sels[s]);
                        if (el) { var r = el.getBoundingClientRect(); if (r.width > 100 && r.height > 100) return el; }
                    }
                    return null;
                }
                var panel = findPanel();
                if (!panel) { callback({stable: false, count: 0, reason: 'no panel'}); return; }
                var lastCount = -1, stableCount = 0, elapsed = 0, interval = 300;
                function check() {
                    var count = panel.querySelectorAll('img').length;
                    if (count === lastCount && count >= 2) {
                        stableCount++;
                        if (stableCount >= 2) { callback({stable: true, count: count}); return; }
                    } else { stableCount = 0; }
                    lastCount = count;
                    elapsed += interval;
                    if (elapsed >= 4000) { callback({stable: false, count: count, reason: 'timeout'}); return; }
                    setTimeout(check, interval);
                }
                check();
            ''')
            print(f'[emoji-tab] tab {tab_index} images stable: {stable}', flush=True)
            return True
        except Exception as e:
            print(f'[emoji-tab] ActionChains failed: {e}', flush=True)
            return False

    def Get_Sticker_List(self):
        """打开表情面板，获取表情包列表"""
        try:
            if not self._open_emoji_panel():
                return {'code': 400, 'data': '未找到表情按钮，请确认已进入对话'}
            time.sleep(random.uniform(0.8, 1.5))
            # 验证面板是否真正打开（底部是否有大量 img）
            panel_check = driver.execute_script(r'''
                var vh = window.innerHeight;
                var imgs = document.querySelectorAll('img');
                var bottomImgs = 0;
                for (var i = 0; i < imgs.length; i++) {
                    var p = imgs[i].parentElement;
                    var inMessage = false;
                    for (var d = 0; d < 5 && p; d++) {
                        var cls = ((p.className||'')+'').toString();
                        if (/MessageItem|MessageBubble/i.test(cls)) { inMessage = true; break; }
                        p = p.parentElement;
                    }
                    if (inMessage) continue;
                    var r = imgs[i].getBoundingClientRect();
                    if (r.top >= vh * 0.4 && r.width >= 20 && r.height >= 20) bottomImgs++;
                }
                return {bottom_img_count: bottomImgs, panel_likely_open: bottomImgs >= 4};
            ''')
            print(f'[emoji-panel] panel_check: {panel_check}', flush=True)
            if not panel_check or not panel_check.get('panel_likely_open'):
                # 面板没真正打开，dump DOM 结构帮助诊断
                print(f'[emoji-panel] panel not open after click, dumping DOM...', flush=True)
                dump = driver.execute_script(r'''
                    var editors = document.querySelectorAll('[contenteditable="true"]');
                    var dump = [];
                    for (var i = 0; i < editors.length; i++) {
                        var er = editors[i].getBoundingClientRect();
                        if (er.top < window.innerHeight * 0.5) continue;
                        // dump 输入框向上5层父容器的所有子元素
                        var p = editors[i].parentElement;
                        for (var d = 0; d < 5 && p; d++) {
                            var pp = p.parentElement;
                            if (!pp) break;
                            var children = pp.children;
                            for (var j = 0; j < children.length && dump.length < 50; j++) {
                                var c = children[j];
                                var cr = c.getBoundingClientRect();
                                if (cr.width < 5 || cr.height < 5) continue;
                                // 递归 dump 子元素（1层）
                                var subChildren = [];
                                for (var k = 0; k < c.children.length && k < 5; k++) {
                                    var sc = c.children[k];
                                    var scr = sc.getBoundingClientRect();
                                    if (scr.width < 5 || scr.height < 5) continue;
                                    subChildren.push({
                                        tag: sc.tagName,
                                        cls: ((sc.className||'').toString()).slice(0,80),
                                        txt: (sc.textContent||'').trim().slice(0,15),
                                        cursor: window.getComputedStyle(sc).cursor
                                    });
                                }
                                dump.push({
                                    level: d,
                                    tag: c.tagName,
                                    cls: ((c.className||'').toString()).slice(0,100),
                                    txt: (c.textContent||'').trim().slice(0,20),
                                    cursor: window.getComputedStyle(c).cursor,
                                    href: c.getAttribute('href') || '',
                                    role: c.getAttribute('role') || '',
                                    ariaLabel: c.getAttribute('aria-label') || '',
                                    dataE2e: c.getAttribute('data-e2e') || '',
                                    rect:{l:Math.round(cr.left),t:Math.round(cr.top),w:Math.round(cr.width),h:Math.round(cr.height)},
                                    children: subChildren
                                });
                            }
                            p = pp;
                        }
                        break;
                    }
                    return dump;
                ''')
                print(f'[emoji-panel] === DOM DUMP (表情按钮定位) ===', flush=True)
                for item in (dump if isinstance(dump, list) else []):
                    print(f'  {item}', flush=True)
                print(f'[emoji-panel] === END DUMP ===', flush=True)
                # 尝试再点一次
                print(f'[emoji-panel] retrying...', flush=True)
                self._open_emoji_panel()
                time.sleep(random.uniform(0.8, 1.2))
            collect_result = self._collect_stickers()
            if isinstance(collect_result, dict):
                categories = collect_result.get('categories', [])
                flat_list = collect_result.get('flat_list', [])
                dbg_info = collect_result.get('debug', {})
                print(f'[collect_stickers] debug: {dbg_info}', flush=True)
                print(f'[collect_stickers] categories={len(categories)}, total={len(flat_list)}', flush=True)
                # 缓存分类数据和 src→tab_index 映射
                self._sticker_categories = categories
                self._sticker_src_map = {}
                for cat in categories:
                    for src in cat.get('stickers', []):
                        self._sticker_src_map[src] = cat.get('tab_index', 0)
            else:
                categories = []
            try:
                from selenium.webdriver.common.action_chains import ActionChains
                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            except Exception:
                pass
            if categories:
                return {'code': 200, 'data': categories}
            else:
                return {'code': 400, 'data': '未获取到表情包，抖音页面结构可能已更新'}
        except Exception:
            return {'code': 500, 'data': '获取表情包失败'}

    def Send_Sticker(self, name: str, sticker_index: int, sticker_src: str = None):
        """发送表情包：打开表情面板，点击指定表情，发送"""
        try:
            # #region debug-point B:send-sticker-entry
            _dbg_report('B', 'Send_Sticker:entry', '进入发送表情流程', {
                'name': name,
                'sticker_index': sticker_index,
                'has_sticker_src': bool(sticker_src),
                'sticker_src_tail': (sticker_src or '')[-80:]
            })
            # #endregion
            # 先关闭可能残留的表情面板（避免遮挡聊天列表导致 Open_Chat 失败）
            try:
                from selenium.webdriver.common.action_chains import ActionChains
                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                time.sleep(0.3)
            except Exception:
                pass
            if not self.Open_Chat(name):
                # #region debug-point B:open-chat-failed
                _dbg_report('B', 'Send_Sticker:open-chat', '打开聊天失败', {'name': name})
                # #endregion
                return TrueString(False, '未找到该好友')
            if not self._open_emoji_panel():
                # 面板没打开，dump 底部区域 DOM 用于调试
                bottom_dump = driver.execute_script(r'''
                    var vh = window.innerHeight;
                    var els = document.querySelectorAll('div, button, svg, img, span');
                    var out = [];
                    for (var i = 0; i < els.length && out.length < 20; i++) {
                        var r = els[i].getBoundingClientRect();
                        if (r.top < vh * 0.6 || r.top > vh) continue;
                        if (r.width < 10 || r.height < 10) continue;
                        var cls = ((els[i].className||'').toString()).slice(0,80);
                        var tag = els[i].tagName;
                        var txt = (els[i].textContent||'').trim().slice(0,30);
                        var style = window.getComputedStyle(els[i]);
                        out.push({tag:tag, cls:cls, txt:txt, cursor:style.cursor,
                                  rect:{l:Math.round(r.left),t:Math.round(r.top),w:Math.round(r.width),h:Math.round(r.height)}});
                    }
                    return out;
                ''')
                print(f'[emoji-panel] FAILED to open. Bottom area DOM dump:', flush=True)
                for item in (bottom_dump or []):
                    print(f'  {item}', flush=True)
                # #region debug-point B:open-panel-failed
                _dbg_report('B', 'Send_Sticker:open-panel', '打开表情面板失败', {'name': name, 'bottom_dump': bottom_dump})
                # #endregion
                return TrueString(False, '未找到表情按钮')
            time.sleep(random.uniform(0.3, 0.6))
            # 验证面板确实打开了：检查底部区域是否有大量 img（排除聊天记录中的表情）
            panel_check = driver.execute_script(r'''
                var vh = window.innerHeight;
                var imgs = document.querySelectorAll('img');
                var bottomImgs = 0;
                for (var i = 0; i < imgs.length; i++) {
                    // 排除聊天记录中的表情
                    var p = imgs[i].parentElement;
                    var inMessage = false;
                    for (var d = 0; d < 5 && p; d++) {
                        var cls = ((p.className||'')+'').toString();
                        if (/MessageItem|MessageBubble/i.test(cls)) { inMessage = true; break; }
                        p = p.parentElement;
                    }
                    if (inMessage) continue;
                    var r = imgs[i].getBoundingClientRect();
                    if (r.top >= vh * 0.45 && r.width >= 20 && r.height >= 20) bottomImgs++;
                }
                return {bottom_img_count: bottomImgs, panel_likely_open: bottomImgs >= 4};
            ''')
            print(f'[emoji-panel] panel_check: {panel_check}', flush=True)
            if not panel_check or not panel_check.get('panel_likely_open'):
                # 面板可能没真正打开，再试一次
                print(f'[emoji-panel] panel not detected, retrying...', flush=True)
                self._open_emoji_panel()
                time.sleep(random.uniform(0.5, 0.8))
                # 再次检查
                panel_check2 = driver.execute_script(r'''
                    var vh = window.innerHeight;
                    var imgs = document.querySelectorAll('img');
                    var bottomImgs = 0;
                    for (var i = 0; i < imgs.length; i++) {
                        var p = imgs[i].parentElement;
                        var inMessage = false;
                        for (var d = 0; d < 5 && p; d++) {
                            var cls = ((p.className||'')+'').toString();
                            if (/MessageItem|MessageBubble/i.test(cls)) { inMessage = true; break; }
                            p = p.parentElement;
                        }
                        if (inMessage) continue;
                        var r = imgs[i].getBoundingClientRect();
                        if (r.top >= vh * 0.45 && r.width >= 20 && r.height >= 20) bottomImgs++;
                    }
                    return {bottom_img_count: bottomImgs, panel_likely_open: bottomImgs >= 4};
                ''')
                print(f'[emoji-panel] panel_check2: {panel_check2}', flush=True)
                if not panel_check2 or not panel_check2.get('panel_likely_open'):
                    # 面板确实没打开，不继续点击
                    print(f'[emoji-panel] panel still not open, aborting', flush=True)
                    return TrueString(False, '表情面板未打开，请确认已进入聊天页面')
            # #region debug-point B:panel-probe
            # 改进：dump 所有底部区域候选 img，并标注 target 匹配情况，便于确认面板定位是否正确
            _dbg_report('B', 'Send_Sticker:panel_probe', '表情面板候选探测完成', driver.execute_script(r'''
                function normalizeSrc(src) { return (src || '').split('#')[0].split('?')[0]; }
                var targetSrc = arguments[0] || '';
                var normalizedTarget = normalizeSrc(targetSrc);
                var vh = window.innerHeight;
                var imgs = document.querySelectorAll('img');
                var matches = [];
                var bottomCount = 0;
                var topCount = 0;
                for (var i = 0; i < imgs.length; i++) {
                    var img = imgs[i];
                    var src = img.src || img.getAttribute('data-src') || '';
                    if (!src) continue;
                    var rect = img.getBoundingClientRect();
                    if (rect.width < 20 || rect.height < 20 || rect.width > 200 || rect.height > 200) continue;
                    if (rect.top >= vh * 0.45) bottomCount++; else topCount++;
                    var parent = img.parentElement;
                    var parentClass = parent ? ((parent.className || '').toString()) : '';
                    if (targetSrc && (src === targetSrc || normalizeSrc(src) === normalizedTarget)) {
                        matches.push({
                            src_tail: src.slice(-80),
                            class_name: (img.className || '').toString().slice(0, 120),
                            parent_class: parentClass.slice(0, 160),
                            in_panel_area: rect.top >= vh * 0.45,
                            rect: { left: Math.round(rect.left), top: Math.round(rect.top), width: Math.round(rect.width), height: Math.round(rect.height) }
                        });
                    }
                }
                return { target_match_count: matches.length, bottom_area_img_count: bottomCount, top_area_img_count: topCount, samples: matches.slice(0, 5) };
            ''', sticker_src or ''))
            # #endregion
            # 查找表情所属 tab
            tab_index = self._sticker_src_map.get(sticker_src, -1)
            if tab_index >= 0:
                print(f'[sticker] src belongs to tab {tab_index}, switching...', flush=True)
                self._switch_emoji_tab(tab_index)
            else:
                print(f'[sticker] src not in cache map, using current tab', flush=True)
            clicked = self._click_sticker_by_src(sticker_src)
            _dbg_report('B', 'Send_Sticker:click', '点击表情完成', {
                'clicked': bool(clicked),
                'has_sticker_src': bool(sticker_src),
                'tab_index': tab_index
            })
            if not clicked:
                try:
                    from selenium.webdriver.common.action_chains import ActionChains
                    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                except Exception:
                    pass
                return TrueString(False, '表情点击失败，未找到匹配的表情')
            time.sleep(random.uniform(0.3, 0.6))
            # 判断是否需要点发送按钮
            need_send = driver.execute_script(r'''
                var panelSelectors = [
                    '[class*="emojiEmojisModal"]', '[class*="EmojiModal"]',
                    '[class*="emojiPanel"]', '[class*="stickerPanel"]',
                    '[class*="emoji-popover"]', '[class*="expression"]'
                ];
                var panelVisible = false;
                for (var s = 0; s < panelSelectors.length; s++) {
                    var els = document.querySelectorAll(panelSelectors[s]);
                    for (var i = 0; i < els.length; i++) {
                        var rect = els[i].getBoundingClientRect();
                        if (rect.width > 100 && rect.height > 100 && rect.top > window.innerHeight * 0.3) {
                            panelVisible = true; break;
                        }
                    }
                    if (panelVisible) break;
                }
                return panelVisible;
            ''')
            _dbg_report('C', 'Send_Sticker:need_send', '评估是否需要额外点击发送', {'need_send': bool(need_send)})
            if need_send:
                # 点击发送按钮
                sent = driver.execute_script(r'''
                    function safeClick(el) {
                        if (!el) return false;
                        if (typeof el.click === 'function') { el.click(); return true; }
                        var p = el.parentElement;
                        while (p) { if (typeof p.click === 'function' && p.tagName !== 'A') { p.click(); return true; } p = p.parentElement; }
                        return false;
                    }
                    var sels = ['[class*="send"]', '[class*="Send"]', 'button[class*="send"]', '[class*="submit"]'];
                    for (var s = 0; s < sels.length; s++) {
                        var els = document.querySelectorAll(sels[s]);
                        for (var i = 0; i < els.length; i++) {
                            var rect = els[i].getBoundingClientRect();
                            if (rect.top > window.innerHeight * 0.5 && rect.width > 0) {
                                if (safeClick(els[i])) return 'css:' + ((els[i].className||'').toString()).slice(0,30);
                            }
                        }
                    }
                    return '';
                ''')
                _dbg_report('D', 'Send_Sticker:send_click', '点击发送按钮完成', {'sent_mode': sent or ''})
                time.sleep(random.uniform(0.2, 0.4))
            # 关闭面板
            try:
                from selenium.webdriver.common.action_chains import ActionChains
                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            except Exception:
                pass
            # 检查发送结果
            send_result = driver.execute_script(r'''
                var eds = document.querySelectorAll('[contenteditable="true"]');
                var bestEditor = null, bestArea = 0;
                for (var i = 0; i < eds.length; i++) {
                    var rect = eds[i].getBoundingClientRect();
                    if (rect.width < 50 || rect.height < 20) continue;
                    if (rect.bottom < window.innerHeight * 0.5) continue;
                    var p = eds[i];
                    for (var d = 0; d < 5 && p; d++) {
                        var cls = ((p.className||'')+'').toString();
                        if (/MessageItem|MessageBubble/i.test(cls)) { p = null; break; }
                        p = p.parentElement;
                    }
                    if (!p) continue;
                    var area = rect.width * rect.height;
                    if (area > bestArea) { bestArea = area; bestEditor = eds[i]; }
                }
                if (!bestEditor) return {ok: false, error: '未找到输入框'};
                var hasImg = !!bestEditor.querySelector('img');
                var hasText = (bestEditor.textContent || '').trim().length > 0;
                return {ok: hasImg || hasText, editorHasContent: hasImg || hasText, error: hasImg || hasText ? '' : '不能发送空白消息'};
            ''')
            _dbg_report('C', 'Send_Sticker:send_result', '发送后结果检查完成', send_result or {})
            if send_result and send_result.get('ok'):
                return TrueString(True, '表情发送成功')
            else:
                return TrueString(False, send_result.get('error', '发送失败') if send_result else '发送失败')
        except Exception as e:
            # #region debug-point E:send-sticker-exception
            _dbg_report('E', 'Send_Sticker:exception', '发送表情异常', {'error': str(e)})
            # #endregion
            return TrueString(False, str(e))

    def Get_Chat_History(self, name: str):
        """获取当前对话的聊天记录"""
        try:
            # #region debug-point A:get-chat-entry
            _dbg_report('A', 'Get_Chat_History:entry', '进入聊天记录同步流程', {'name': name})
            # #endregion
            if not self.Open_Chat(name):
                # #region debug-point A:open-chat-failed
                _dbg_report('A', 'Get_Chat_History:open_chat', '打开聊天失败', {'name': name})
                # #endregion
                return {'code': 400, 'data': '未找到该好友'}
            time.sleep(random.uniform(0.3, 0.6))
            # 跳过4个旧 XPath（调试日志已确认全部 match_count=0），直接用 JS 定位
            messages = []
            try:
                driver.set_script_timeout(8)
                js_messages = driver.execute_script(r'''
                    function isVisible(el) {
                        if (!el) return false;
                        var r = el.getBoundingClientRect();
                        if (r.width <= 0 || r.height <= 0) return false;
                        var s = window.getComputedStyle(el);
                        return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
                    }
                    function cleanText(t) { return (t||'').replace(/\s+/g,' ').trim(); }

                    var statusTexts = ['已读','送达','未读','已送达','点亮中','已撤回','该消息类型暂不能展示','系统消息'];
                    function isStatus(text) {
                        if (!text || text.length > 40) return false;
                        for (var i=0;i<statusTexts.length;i++) if (text.indexOf(statusTexts[i])!==-1) return true;
                        return false;
                    }

                    // 找输入框顶部边界（排除输入区域的消息）
                    var editorTop = window.innerHeight;
                    var eds = document.querySelectorAll('[contenteditable="true"]');
                    for (var i=0;i<eds.length;i++) {
                        if (!isVisible(eds[i])) continue;
                        var er = eds[i].getBoundingClientRect();
                        if (er.top > window.innerHeight*0.45 && er.top < editorTop) editorTop = er.top;
                    }

                    // 广义查询：找所有 MessageItem 顶层容器（parent 不含 MessageItem）
                    // 覆盖文本、图片、表情、不支持等所有消息类型
                    var allMsgs = document.querySelectorAll('[class*="MessageItem"]');
                    var seen = {};
                    var results = [];

                    for (var i=0;i<allMsgs.length;i++) {
                        var el = allMsgs[i];
                        if (!isVisible(el)) continue;
                        var r = el.getBoundingClientRect();
                        // 排除输入区域
                        if (r.top > editorTop + 8) continue;
                        // 排除完全滚出视图的
                        if (r.bottom < -200) continue;

                        // 只保留顶层容器：parent 不含 MessageItem
                        var p = el.parentElement;
                        if (p) {
                            var pcls = ((p.className||'')+'').toString();
                            if (/MessageItem/i.test(pcls)) continue;
                        }

                        // 判断方向：当前元素或祖先或后代含 isFromMe
                        var cls = ((el.className||'')+'').toString();
                        var isSelf = /isFromMe/i.test(cls);
                        if (!isSelf) {
                            // 向上查祖先
                            var pp = el.parentElement;
                            for (var d=0; d<5 && pp; d++) {
                                var pc = ((pp.className||'')+'').toString();
                                if (/isFromMe/i.test(pc)) { isSelf = true; break; }
                                pp = pp.parentElement;
                            }
                        }
                        if (!isSelf) {
                            // 向下查后代
                            var desc = el.querySelector('[class*="isFromMe"]');
                            if (desc) isSelf = true;
                        }

                        // 提取文本：优先 pureText，其次 bubbleText，最后用元素自身文本
                        var text = '';
                        var pureText = el.querySelector('[class*="pureText"]');
                        if (pureText) text = cleanText(pureText.innerText || pureText.textContent || '');
                        if (!text) {
                            var bubbleText = el.querySelector('[class*="bubbleTextContent"]');
                            if (bubbleText) text = cleanText(bubbleText.innerText || bubbleText.textContent || '');
                        }
                        if (!text) {
                            text = cleanText(el.innerText || el.textContent || '');
                        }

                        if (!text || text.length > 500) continue;
                        if (isStatus(text)) continue;

                        // 去重
                        var key = text + '|' + Math.round(r.top/6) + '|' + (isSelf ? '1' : '0');
                        if (seen[key]) continue;
                        seen[key] = 1;

                        results.push({text:text, is_self:isSelf, top:r.top});
                    }

                    // 如果 MessageItem 没找到，兜底用 MessageBoxContentrowBox
                    if (results.length === 0) {
                        var rows = document.querySelectorAll('[class*="MessageBoxContentrow"]');
                        for (var i=0;i<rows.length;i++) {
                            var el = rows[i];
                            if (!isVisible(el)) continue;
                            var r = el.getBoundingClientRect();
                            if (r.top > editorTop + 8) continue;
                            if (r.bottom < -200) continue;
                            var cls = ((el.className||'')+'').toString();
                            var isSelf = /isFromMe/i.test(cls);
                            if (!isSelf) {
                                var desc = el.querySelector('[class*="isFromMe"]');
                                if (desc) isSelf = true;
                            }
                            var text = cleanText(el.innerText || el.textContent || '');
                            if (!text || text.length > 500) continue;
                            if (isStatus(text)) continue;
                            var key = text + '|' + Math.round(r.top/6) + '|' + (isSelf ? '1' : '0');
                            if (seen[key]) continue;
                            seen[key] = 1;
                            results.push({text:text, is_self:isSelf, top:r.top});
                        }
                    }

                    results.sort(function(a,b){ return a.top - b.top; });
                    return results.map(function(it){ return {text:it.text, is_self:it.is_self}; });
                ''')
                if isinstance(js_messages, list) and js_messages:
                    messages = js_messages
            except Exception:
                pass
            # #region debug-point A:get-chat-result
            _dbg_report('A', 'Get_Chat_History:result', '聊天记录同步完成', {
                'message_count': len(messages),
                'preview': messages[:3]
            })
            # #endregion
            return {'code': 200, 'data': messages}
        except Exception as e:
            # #region debug-point E:get-chat-exception
            _dbg_report('E', 'Get_Chat_History:exception', '聊天记录同步异常', {'error': str(e)})
            # #endregion
            return {'code': 500, 'data': '获取聊天记录失败'}

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
_user_cache = {'nickname': '', 'avatar': ''}  # 用户信息缓存
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
        for task_id, task in list(scheduled_tasks.items()):
            try:
                schedule.cancel_job(task['job'])
            except Exception:
                pass
        scheduled_tasks.clear()
        init = False
        driver = None
        douyin = None
        Login_is_bool = False
        _user_cache['nickname'] = ''
        _user_cache['avatar'] = ''
        return {'code': 400, 'data': '浏览器会话已断开，请重新初始化'}


# 定时任务存储
scheduled_tasks = {}  # 格式: {任务ID: {job, time, name, msg, ...}}

# 定时任务持久化文件
TASKS_FILE = os.path.join(BASE_DIR, 'tasks.json')


def save_tasks():
    """将定时任务元数据持久化到 tasks.json"""
    tasks_meta = []
    for task_id, task in scheduled_tasks.items():
        tasks_meta.append({
            'task_id': task_id,
            'time': task.get('time', ''),
            'name': task.get('name', ''),
            'msg': task.get('msg', '')
        })
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


def schedule_task(task_id: str, play_time: str, name: str, msg: str):
    job = schedule.every().day.at(play_time).do(run_task_async, task_id)
    scheduled_tasks[task_id] = {
        'task_id': task_id,
        'time': play_time,
        'name': name,
        'msg': msg or '',
        'job': job,
        'last_result': '',
        'last_generated_text': '',
        'last_run_at': '',
        'last_jitter_seconds': 0
    }
    return scheduled_tasks[task_id]


def run_task_async(task_id: str):
    threading.Thread(target=execute_task_send, args=(task_id,), daemon=True).start()


def execute_task_send(task_id: str):
    task = scheduled_tasks.get(task_id)
    if not task:
        return
    task['last_run_at'] = now_str()
    if risk_state.get('paused'):
        task['last_result'] = '已暂停'
        return
    drv_err = check_driver()
    if drv_err:
        task['last_result'] = drv_err.get('data', '浏览器异常')
        record_send_failure(task['last_result'])
        return
    jitter_seconds = random.randint(0, config.get('task_jitter_minutes', 0) * 60) if config.get('task_jitter_minutes', 0) > 0 else 0
    task['last_jitter_seconds'] = jitter_seconds
    if jitter_seconds > 0:
        time.sleep(jitter_seconds)
    try:
        message = pick_message_content(task['name'], task.get('msg', ''))
        task['last_generated_text'] = message
        result = douyin.Send_Frinder(task['name'], message)
        if result.is_bool:
            task['last_result'] = '发送成功'
            record_send_success(task['name'], message, 'scheduled')
        else:
            task['last_result'] = result.string or '发送失败'
            record_send_failure(f'任务 {task_id} 失败：{task["last_result"]}')
    except Exception as e:
        task['last_result'] = str(e) or '发送异常'
        record_send_failure(f'任务 {task_id} 异常：{task["last_result"]}')


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
            schedule_task(task_id, play_time, name, msg)
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
            browser_name = normalize_browser_name(config.get('browser_name'))
            driver = create_webdriver()
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
            return {'code': 404, 'data': 'Cookie格式错误，请检查'}
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
        drv_err = check_driver()
        if drv_err:
            return drv_err
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
    if Login_is_bool:
        try:
            cooke = driver.get_cookies()
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
        friends_list = douyin.Updara_FrinderList()
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
        out = Douyin.Send_Frinder(douyin, name, text)
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
        result = douyin.Get_Sticker_List()
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
        out = douyin.Send_Sticker(name, sticker_index, sticker_src)
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
        result = douyin.Get_Chat_History(name)
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
    if not Login_is_bool:
        return {'code': 200, 'data': {'nickname': '', 'avatar': ''}}

    # 有缓存直接返回
    if _user_cache['nickname'] and _user_cache['nickname'] != '未知用户':
        return {'code': 200, 'data': dict(_user_cache)}

    nickname = ''
    avatar = ''

    # 方法1：同步JS提取（不使用async，避免超时问题）
    # 从页面全局变量、localStorage、cookie、DOM 同步读取
    try:
        info = driver.execute_script(r'''
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
            page = driver.page_source
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
            current = driver.current_url
            old_timeout = driver.page_load_timeout
            driver.set_page_load_timeout(8)
            try:
                driver.get('https://www.douyin.com/')
            except Exception:
                pass
            driver.set_page_load_timeout(old_timeout)
            time.sleep(2)
            # 一键登录弹窗处理
            try:
                driver.execute_script('''
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
                page = driver.page_source
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
                    av_info = driver.execute_script(r'''
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
                driver.get('https://www.douyin.com/chat?isPopup=1')
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
        return {'code': 400, 'data': '验证码发送失败'}


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
        return {'code': 400, 'data': '验证码登录失败'}


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
    for task_id, task in scheduled_tasks.items():
        if task_id.endswith(f"_{name}"):
            return {'code': 400, 'data': f'好友 {name} 已有定时任务，请先删除或修改'}

    temp = douyin.Find_Friends(name)
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


