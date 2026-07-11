"""运行时全局状态模块

存放会被重新绑定的全局变量（driver/douyin/init 等）。
其他模块访问时必须用 `import runtime; runtime.xxx` 形式，
不能用 `from runtime import xxx`，否则重新绑定后引用失效。
"""
import threading


# 浏览器驱动与会话状态（会被重新绑定，必须用 runtime.xxx 访问）
driver = None
douyin = None
init = False
Login_is_bool = False

# 用户信息缓存（字典本身不重新绑定，只改属性，可 from import）
_user_cache = {'nickname': '', 'avatar': ''}

# 初始化锁（不重新绑定，可 from import）
init_lock = threading.Lock()

# 服务启动时间（在主入口设置）
start_time = None
