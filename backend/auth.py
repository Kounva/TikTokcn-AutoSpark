"""认证鉴权模块"""
import hashlib
import secrets
from fastapi import Header

from backend.config import config, save_config


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


# Token存储（_valid_tokens 不重新绑定，只 add/discard，可 from import）
_valid_tokens = set()
# _last_login_ip 会被重新绑定，外部修改用 auth._last_login_ip = ...
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
