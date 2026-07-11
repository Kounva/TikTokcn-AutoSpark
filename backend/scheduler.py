"""定时任务调度模块"""
import os
import json
import time
import random
import threading
import schedule

from backend.config import config, BASE_DIR
from backend.utils import now_str, format_time
from backend.risk_control import risk_state, pick_message_content, record_send_success, record_send_failure
from backend.browser_manager import check_driver
from backend import runtime


# 定时任务存储（字典不重新绑定，只改属性，可 from import）
scheduled_tasks = {}  # 格式: {任务ID: {job, time, name, msg, ...}}

# 定时任务持久化文件
TASKS_FILE = os.path.join(BASE_DIR, 'data', 'tasks.json')


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
        result = runtime.douyin.Send_Frinder(task['name'], message)
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
