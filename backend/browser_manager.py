"""浏览器驱动管理模块"""
import os
from selenium import webdriver
from selenium.common.exceptions import SessionNotCreatedException, WebDriverException
from selenium.webdriver.common.by import By

from backend.config import config, normalize_browser_name, get_profile_dir
from backend import runtime


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


def check_driver():
    """检查浏览器会话是否有效，无效则重置状态并返回错误响应"""
    # 延迟导入，避免循环依赖
    from backend.scheduler import scheduled_tasks
    import schedule

    if not runtime.init or runtime.driver is None:
        return {'code': 400, 'data': '浏览器未初始化，请先点击初始化'}
    try:
        # 用一个轻量操作探测会话是否存活
        runtime.driver.current_url
        return None
    except Exception:
        # 会话已失效，关闭旧 driver 并重置状态
        try:
            runtime.driver.quit()
        except Exception:
            pass
        # 清理旧定时任务（job 仍绑定旧的 douyin 引用）
        for task_id, task in list(scheduled_tasks.items()):
            try:
                schedule.cancel_job(task['job'])
            except Exception:
                pass
        scheduled_tasks.clear()
        runtime.init = False
        runtime.driver = None
        runtime.douyin = None
        runtime.Login_is_bool = False
        runtime._user_cache['nickname'] = ''
        runtime._user_cache['avatar'] = ''
        return {'code': 400, 'data': '浏览器会话已断开，请重新初始化'}


def cleanup_on_exit():
    """程序退出时清理浏览器进程"""
    if runtime.init and runtime.driver:
        try:
            runtime.driver.quit()
        except Exception:
            pass
