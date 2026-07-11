"""配置与常量模块"""
import os
import json
import socket
import platform


# 路径配置（BASE_DIR 指向项目根目录，即 backend/ 的上级目录）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(BASE_DIR, 'dist')

# 配置文件
CONFIG_FILE = os.path.join(BASE_DIR, 'data', 'config.json')

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


def get_profile_dir(browser_name):
    browser_name = normalize_browser_name(browser_name)
    if browser_name == 'edge':
        # 兼容旧目录，避免升级后丢失已有登录态
        return os.path.join(BASE_DIR, 'edge_user_data')
    return os.path.join(BASE_DIR, f'{browser_name}_user_data')


# 全局配置对象（模块加载时读取一次，之后只修改属性不重新绑定）
config = load_config()
