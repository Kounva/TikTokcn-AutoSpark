"""通用工具与数据类模块"""
import os
import json
import time
import requests
from datetime import datetime

from backend.config import BASE_DIR


def now_str():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# #region debug-point shared:reporter
def _dbg_report(hypothesis_id: str, location: str, msg: str, data=None, run_id: str = 'post-fix'):
    try:
        import urllib.request
        debug_env = os.path.join(BASE_DIR, 'logs', 'chat-sticker-sync.env')
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
