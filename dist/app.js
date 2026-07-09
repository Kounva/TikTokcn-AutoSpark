const { createApp, ref, reactive, computed, onMounted, watch } = Vue;
const onActivated = Vue.onActivated || function(fn) {};
const { createRouter, createWebHistory } = VueRouter;
const { ElMessage, ElMessageBox } = ElementPlus;

// ===== API =====
const api = axios.create({ baseURL: '/api', timeout: 10000 });
api.interceptors.request.use(config => {
  const token = localStorage.getItem('token') || localStorage.getItem('douyin_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
}, error => Promise.reject(error));
api.interceptors.response.use(response => {
  const ct = response.headers['content-type'];
  if (ct && ct.includes('application/json')) {
    const res = response.data;
    if (res && res.code !== undefined && res.code == 401) {
      const hadToken = !!response.config?.headers?.Authorization;
      localStorage.removeItem('token'); localStorage.removeItem('douyin_token');
      if (hadToken) { ElMessage.error('登录已过期，请重新登录'); setTimeout(() => window.location.replace('/login'), 1500); }
      return Promise.reject(new Error(res.data || '未授权'));
    }
    if (res && res.code !== undefined && res.code != 200 && res.code != '200') {
      ElMessage.error(res.data || res.msg || res.message || '请求失败');
      return Promise.reject(new Error(res.data || '请求失败'));
    }
    return res;
  }
  return response;
}, error => {
  if (error.response) {
    const status = error.response.status, data = error.response.data;
    if (status === 401) {
      const hadToken = !!error.config?.headers?.Authorization;
      localStorage.removeItem('token'); localStorage.removeItem('douyin_token');
      if (hadToken) { ElMessage.error('登录已过期，请重新登录'); setTimeout(() => window.location.replace('/login'), 1500); }
      return;
    } else if (status === 500) ElMessage.error('服务器内部错误');
    else if (status === 404) ElMessage.error('请求的资源不存在');
    else { const msg = data?.data || data?.msg || data?.message || error.message || `请求失败 (${status})`; ElMessage.error(msg); }
  } else if (error.request) ElMessage.error('无法连接到服务器，请检查后端服务是否启动');
  else ElMessage.error(error.message || '网络错误');
  return Promise.reject(error);
});

const API = {
  initBrowser: () => api.get('/Api/Init', { timeout: 60000 }),
  getInitStatus: () => api.get('/Api/GetInit'),
  getLoginStatus: () => api.get('/Api/GetLogin'),
  pnglogin: () => api.get('/Api/Pnglogin'),
  getScrlk: () => api.get('/Api/GetScrlk'),
  login: async (cookie) => {
    const jsonStr = JSON.stringify(cookie);
    const bytes = new TextEncoder().encode(jsonStr);
    const cs = new CompressionStream('gzip');
    const writer = cs.writable.getWriter(); writer.write(bytes); writer.close();
    const output = await new Response(cs.readable).arrayBuffer();
    const base64 = btoa(String.fromCharCode(...new Uint8Array(output)));
    return api.post('/Api/login', { cooke: base64, gzip_flag: true });
  },
  getLoginPng: () => api.get('/Api/login/Init/GetLoginPng'),
  dieLogin: () => api.get('/Api/DieLogin'),
  getCooker: (password) => api.get('/Api/login/Init/GetCooker', { params: { password } }),
  sendVerifyCode: (areacode, phone) => api.get('/Api/LoginPhone', { params: { areacode, phone } }),
  submitVerifyCode: (code) => api.get('/Api/LoginPhoneInput', { params: { code } }),
  logout: () => api.get('/Api/logout'),
  getFriendsList: () => api.get('/Api/GetFriendsList'),
  sendMessage: (name, text) => api.get('/Api/Send', { params: { name, text } }),
  addTask: (time, name, text) => api.get('/Time/add', { params: { time, name, text } }),
  delTask: (task_id) => api.get('/Time/del', { params: { task_id } }),
  editTask: (name, new_time) => api.get('/Time/edit', { params: { name, new_time } }),
  getTaskList: () => api.get('/Time/getlist'),
  getUsername: () => api.get('/Api/GetUsername'),
  changePassword: (old_password, new_password) => api.get('/Api/ChangePassword', { params: { old_password, new_password } }),
  getLastLoginIP: () => api.get('/Api/GetLastLoginIP'),
  forceLogin: () => api.get('/Api/LoginDebug'),
  getPort: () => api.get('/Api/GetPort'),
  setPort: (port) => api.get('/Api/SetPort', { params: { port } }),
  getBrowserMode: () => api.get('/Api/GetBrowserMode'),
  setBrowserMode: (show) => api.get('/Api/SetBrowserMode', { params: { show } }),
  getStickerList: () => api.get('/Api/GetStickerList'),
  sendSticker: (name, sticker_index) => api.get('/Api/SendSticker', { params: { name, sticker_index } }),
  getChatHistory: (name) => api.get('/Api/GetChatHistory', { params: { name } }),
  getHome: () => api.get('/Home'),
};

// ===== Global State =====
const browserStatus = ref(false);
const loginStatus = ref(false);
const friendsList = ref([]);
const hasLoaded = ref(false);
const homeLoaded = ref(false);
const douyinAvatar = ref(localStorage.getItem('douyin_avatar') || '');
const douyinNickname = ref(localStorage.getItem('douyin_username') || '');
const setBrowserStatus = (s) => browserStatus.value = s;
const setLoginStatus = (s) => loginStatus.value = s;
const setFriendsList = (l) => { friendsList.value = l; hasLoaded.value = true; };
const setHomeLoaded = () => homeLoaded.value = true;
const setDouyinUser = (nickname, avatar) => {
  douyinNickname.value = nickname || '';
  douyinAvatar.value = avatar || '';
  if (nickname) localStorage.setItem('douyin_username', nickname); else localStorage.removeItem('douyin_username');
  if (avatar) localStorage.setItem('douyin_avatar', avatar); else localStorage.removeItem('douyin_avatar');
};

// ===== User Store =====
const userStore = reactive({
  token: localStorage.getItem('token') || '',
  userInfo: JSON.parse(localStorage.getItem('userInfo') || '{}'),
  get isLoggedIn() { return !!this.token; },
  async login(username, password) {
    try {
      const res = await axios.get('/api/Api/Login/Admin', { params: { username, password } });
      if (res.data.code == 200 || res.data.code == '200') {
        this.token = res.data.data;
        this.userInfo = { username, loginTime: new Date().toISOString() };
        localStorage.setItem('token', this.token);
        localStorage.setItem('userInfo', JSON.stringify(this.userInfo));
        axios.defaults.headers.common['Authorization'] = `Bearer ${this.token}`;
        return { success: true, message: '登录成功' };
      }
      return { success: false, message: res.data.data || '登录失败' };
    } catch (error) {
      return { success: false, message: error.response?.data?.data || error.message || '登录失败' };
    }
  },
  logout() {
    this.token = ''; this.userInfo = {};
    localStorage.removeItem('token'); localStorage.removeItem('userInfo');
    delete axios.defaults.headers.common['Authorization'];
  },
  restoreSession() {
    if (this.token) axios.defaults.headers.common['Authorization'] = `Bearer ${this.token}`;
  }
});

// ===== Login Component =====
const Login = {
  template: `
  <div class="login-page">
    <div class="login-orb login-orb-1"></div>
    <div class="login-orb login-orb-2"></div>
    <div class="login-orb login-orb-3"></div>
    <div class="login-shell">
      <div class="login-card">
        <div class="login-header">
          <div class="login-logo">
            <div class="login-logo-ring"></div>
            <span class="login-logo-emoji">🔥</span>
          </div>
          <h1 class="login-title">抖音火花助手</h1>
          <p class="login-subtitle">SPARK ASSISTANT</p>
        </div>
        <el-form ref="loginFormRef" :model="loginForm" :rules="loginRules" @keyup.enter="handleLogin">
          <el-form-item prop="username" class="login-form-item">
            <el-input v-model="loginForm.username" placeholder="请输入用户名" size="large" :prefix-icon="UserIcon" />
          </el-form-item>
          <el-form-item prop="password" class="login-form-item">
            <el-input v-model="loginForm.password" type="password" placeholder="请输入密码" size="large" :prefix-icon="LockIcon" show-password />
          </el-form-item>
          <el-form-item class="login-btn-wrap">
            <el-button type="primary" size="large" :loading="loading" class="login-btn" @click="handleLogin">
              {{ loading ? '登录中...' : '登 录' }}
            </el-button>
          </el-form-item>
        </el-form>
      </div>
    </div>
  </div>`,
  setup() {
    const router = VueRouter.useRouter();
    const loginFormRef = ref(null);
    const loading = ref(false);
    const loginForm = reactive({ username: '', password: '' });
    const loginRules = {
      username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
      password: [{ required: true, message: '请输入密码', trigger: 'blur' }, { min: 1, message: '密码不能为空', trigger: 'blur' }]
    };
    const handleLogin = async () => {
      if (!loginFormRef.value) return;
      await loginFormRef.value.validate(async (valid) => {
        if (valid) {
          loading.value = true;
          try {
            const result = await userStore.login(loginForm.username, loginForm.password);
            if (result.success) { ElMessage.success(result.message); router.push('/'); }
            else ElMessage.error(result.message);
          } catch (e) { ElMessage.error('登录失败'); }
          finally { loading.value = false; }
        }
      });
    };
    return { loginFormRef, loading, loginForm, loginRules, handleLogin, UserIcon: ElementPlusIconsVue.User, LockIcon: ElementPlusIconsVue.Lock };
  }
};

// ===== Layout Component =====
const Layout = {
  template: `
  <div class="app-shell">
    <div v-if="isMobile && sidebarVisible" class="sidebar-overlay" @click="closeSidebar"></div>
    <aside class="sidebar" :class="{ collapsed: isCollapsed && !isMobile, 'sidebar-mobile': isMobile, 'sidebar-mobile-visible': sidebarVisible }">
      <div class="sidebar-header">
        <span class="sidebar-logo">🔥</span>
        <span v-if="!isCollapsed || (isMobile && sidebarVisible)" class="sidebar-title">抖音火花助手</span>
      </div>
      <div class="sidebar-menu">
        <div v-for="(item, idx) in menuList" :key="item.path" class="sidebar-item anim-fade-up" :class="{ active: activeMenu === item.path, ['stagger-' + (idx+1)]: true }" @click="handleMenuSelect(item.path)">
          <el-icon><component :is="item.icon" /></el-icon>
          <span class="sidebar-item-text">{{ item.title }}</span>
        </div>
      </div>
      <div class="sidebar-footer">
        <a href="https://github.com/Kounva/TikTokcn-AutoSpark" target="_blank" style="color:var(--text-muted);text-decoration:none;font-size:12px;display:flex;align-items:center;gap:6px">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/></svg>
          <span v-if="!isCollapsed || isMobile" class="sidebar-footer-text">GitHub</span>
        </a>
      </div>
    </aside>
    <div class="main-area">
      <header class="topbar">
        <div class="topbar-left">
          <el-icon v-if="isMobile" class="topbar-menu-btn" @click="toggleSidebar"><component is="Expand" v-if="!sidebarVisible" /><component is="Fold" v-else /></el-icon>
          <div class="topbar-title">{{ currentMenuTitle }}</div>
        </div>
        <div class="topbar-right">
          <div class="topbar-user">
            <div class="topbar-avatar" :class="{ 'has-img': douyinAvatar }">
              <img v-if="douyinAvatar" :src="douyinAvatar" alt="头像" @error="douyinAvatar = ''" />
              <span v-else>{{ (userStore.userInfo.username || 'A')[0].toUpperCase() }}</span>
            </div>
            <span class="topbar-username">{{ douyinNickname || userStore.userInfo.username || 'Admin' }}</span>
          </div>
          <el-dropdown @command="handleCommand">
            <el-icon style="cursor:pointer;font-size:18px;color:var(--text-secondary)"><component is="ArrowDown" /></el-icon>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>
      <div class="page-body"><router-view v-slot="{ Component }"><transition name="fade" mode="out-in"><component :is="Component" /></transition></router-view></div>
    </div>
  </div>`,
  setup() {
    const router = VueRouter.useRouter();
    const route = VueRouter.useRoute();
    const isCollapsed = ref(false);
    const isMobile = ref(false);
    const sidebarVisible = ref(false);
    const checkMobile = () => {
      isMobile.value = window.innerWidth < 768;
      if (isMobile.value) { isCollapsed.value = true; sidebarVisible.value = false; }
      else sidebarVisible.value = true;
    };
    const toggleSidebar = () => { if (isMobile.value) sidebarVisible.value = !sidebarVisible.value; else isCollapsed.value = !isCollapsed.value; };
    const closeSidebar = () => { if (isMobile.value) sidebarVisible.value = false; };
    onMounted(() => { checkMobile(); window.addEventListener('resize', checkMobile);
      if (loginStatus.value && !douyinNickname.value) { API.getUsername().then(res => { if (res.code == 200 && res.data) setDouyinUser(res.data.nickname || '', res.data.avatar || ''); }).catch(() => {}); }
    });
    const menuList = [
      { path: '/home', title: '首页', icon: 'House' },
      { path: '/friends', title: '好友列表', icon: 'User' },
      { path: '/chat', title: '聊天', icon: 'ChatDotRound' },
      { path: '/tasks', title: '定时任务', icon: 'Clock' },
      { path: '/settings', title: '设置', icon: 'Setting' }
    ];
    const activeMenu = computed(() => route.path);
    const currentMenuTitle = computed(() => { const m = menuList.find(i => i.path === activeMenu.value); return m ? m.title : ''; });
    const handleMenuSelect = (path) => { router.push(path); if (isMobile.value) sidebarVisible.value = false; };
    const handleCommand = (cmd) => {
      if (cmd === 'logout') {
        ElMessageBox.confirm('确定要退出登录吗？', '提示', { type: 'warning' }).then(async () => {
          try { await API.logout(); } catch (e) {}
          userStore.logout(); setDouyinUser('', ''); localStorage.removeItem('douyin_username_loaded'); router.push('/login');
        }).catch(() => {});
      }
    };
    return { isCollapsed, isMobile, sidebarVisible, toggleSidebar, closeSidebar, menuList, activeMenu, currentMenuTitle, handleMenuSelect, handleCommand, userStore, browserStatus, douyinAvatar, douyinNickname };
  }
};

// ===== Home Component =====
const Home = {
  template: `
  <div>
    <div class="home-hero anim-fade-up">
      <h1 class="home-hero-title">👋 欢迎使用抖音火花助手</h1>
      <p class="home-hero-sub">自动化管理你的抖音好友火花，保持联系不间断</p>
    </div>
    <div class="stats-row">
      <div class="stat-tile anim-fade-up stagger-1" :style="{ cursor: initLoading ? 'wait' : 'pointer', opacity: initLoading ? 0.6 : 1 }" @click="initBrowser">
        <div class="stat-tile-icon coral"><el-icon><component is="Monitor" /></el-icon></div>
        <div class="stat-tile-label">浏览器状态</div>
        <div class="stat-tile-value">{{ initLoading ? '初始化中...' : (browserStatus ? '已初始化' : '未初始化') }}<span class="status-pill" :class="browserStatus ? 'online' : 'offline'"></span></div>
      </div>
      <div class="stat-tile anim-fade-up stagger-2">
        <div class="stat-tile-icon amber"><el-icon><component is="Key" /></el-icon></div>
        <div class="stat-tile-label">登录状态</div>
        <div class="stat-tile-value">{{ loginStatus ? '已登录' : '未登录' }}<span class="status-pill" :class="loginStatus ? 'online' : 'offline'"></span></div>
      </div>
      <div class="stat-tile anim-fade-up stagger-3">
        <div class="stat-tile-icon green"><el-icon><component is="User" /></el-icon></div>
        <div class="stat-tile-label">好友数量</div>
        <div class="stat-tile-value">{{ friendsCount }} <span style="font-size:14px;color:var(--text-muted)">人</span></div>
      </div>
      <div class="stat-tile anim-fade-up stagger-4" style="cursor:pointer" @click="$router.push('/tasks')">
        <div class="stat-tile-icon blue"><el-icon><component is="Clock" /></el-icon></div>
        <div class="stat-tile-label">定时任务</div>
        <div class="stat-tile-value">{{ taskCount }} <span style="font-size:14px;color:var(--text-muted)">个</span></div>
      </div>
    </div>
    <el-row :gutter="20" style="margin-bottom:24px">
      <el-col :xs="24" :lg="14">
        <div class="glass-shell anim-fade-up stagger-2">
          <div class="glass-core">
            <div class="panel-title"><div class="panel-title-icon"><el-icon><component is="Operation" /></el-icon></div>快速操作</div>
            <div class="action-grid">
              <div class="action-tile" :style="{ opacity: initLoading ? 0.6 : 1, cursor: initLoading ? 'wait' : 'pointer' }" @click="initBrowser">
                <div class="action-tile-icon coral"><el-icon><component is="Monitor" /></el-icon></div>
                <div class="action-tile-label">{{ initLoading ? '初始化中...' : '初始化浏览器' }}</div>
                <div class="action-tile-hint">启动自动化环境</div>
              </div>
              <div class="action-tile" @click="refreshFriends">
                <div class="action-tile-icon amber"><el-icon><component is="Refresh" /></el-icon></div>
                <div class="action-tile-label">刷新好友列表</div>
                <div class="action-tile-hint">更新好友数据</div>
              </div>
              <div class="action-tile" @click="$router.push('/tasks')">
                <div class="action-tile-icon green"><el-icon><component is="Clock" /></el-icon></div>
                <div class="action-tile-label">管理任务</div>
                <div class="action-tile-hint">添加或修改</div>
              </div>
              <div class="action-tile" @click="$router.push('/settings')">
                <div class="action-tile-icon blue"><el-icon><component is="Setting" /></el-icon></div>
                <div class="action-tile-label">系统设置</div>
                <div class="action-tile-hint">配置账户</div>
              </div>
            </div>
          </div>
        </div>
      </el-col>
      <el-col :xs="24" :lg="10">
        <div class="glass-shell anim-fade-up stagger-3">
          <div class="glass-core">
            <div class="panel-title"><div class="panel-title-icon"><el-icon><component is="InfoFilled" /></el-icon></div>系统信息</div>
            <div class="info-row"><span class="info-row-label">系统版本</span><span class="info-row-value">v1.0.0</span></div>
            <div class="info-row"><span class="info-row-label">运行时间</span><span class="info-row-value" style="color:var(--success)">{{ uptime }}</span></div>
            <div class="info-row"><span class="info-row-label">后端地址</span><span class="info-row-value">{{ backendPort }}</span></div>
            <div class="info-row"><span class="info-row-label">运行状态</span><el-tag :type="browserStatus && loginStatus ? 'success' : 'warning'" size="small">{{ browserStatus && loginStatus ? '正常' : '待初始化' }}</el-tag></div>
          </div>
        </div>
      </el-col>
    </el-row>
    <div class="glass-shell anim-fade-up stagger-4">
      <div class="glass-core">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
          <div class="panel-title" style="margin-bottom:0"><div class="panel-title-icon"><el-icon><component is="Calendar" /></el-icon></div>最近定时任务</div>
          <el-button type="primary" link @click="$router.push('/tasks')">查看全部 <el-icon><component is="ArrowRight" /></el-icon></el-button>
        </div>
        <el-empty v-if="recentTasks.length === 0" description="暂无定时任务">
          <el-button type="primary" @click="$router.push('/tasks')">添加任务</el-button>
        </el-empty>
        <el-table v-else :data="recentTasks" stripe style="width:100%">
          <el-table-column type="index" label="#" width="60" align="center" />
          <el-table-column prop="name" label="好友" min-width="120" />
          <el-table-column prop="time" label="执行时间" width="120" align="center">
            <template #default="{ row }"><el-tag type="info" effect="plain">{{ row.time }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="next_run" label="下次执行" min-width="180">
            <template #default="{ row }"><span style="color:var(--text-secondary);font-size:13px">{{ row.next_run || '未设置' }}</span></template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </div>`,
  setup() {
    const friendsCount = ref(0), taskCount = ref(0), recentTasks = ref([]), initLoading = ref(false), uptime = ref('--');
    const backendPort = 'http://127.0.0.1:' + (window.location.port || '8088');
    const formatUptime = (st) => {
      const s = new Date(st), n = new Date(), d = Math.floor((n - s) / 1000);
      const days = Math.floor(d / 86400), h = Math.floor((d % 86400) / 3600), m = Math.floor((d % 3600) / 60), sec = d % 60;
      const p = []; if (days > 0) p.push(`${days}天`); if (h > 0 || days > 0) p.push(`${h}小时`); if (m > 0 || h > 0 || days > 0) p.push(`${m}分`); p.push(`${sec}秒`); return p.join(' ');
    };
    const checkBrowserStatus = async () => {
      try { const res = await API.getInitStatus(); browserStatus.value = res.data === 'Yes'; setBrowserStatus(browserStatus.value);
        if (!browserStatus.value) ElMessageBox.confirm('浏览器未初始化，是否立即初始化？', '提示', { confirmButtonText: '立即初始化', cancelButtonText: '稍后', type: 'warning' }).then(async () => await initBrowser()).catch(() => {});
      } catch (e) { browserStatus.value = false; setBrowserStatus(false); }
    };
    const checkLoginStatus = async () => { try { const res = await API.getLoginStatus(); loginStatus.value = res.data === 'Yes'; setLoginStatus(loginStatus.value); if (loginStatus.value && !douyinNickname.value) { try { const u = await API.getUsername(); if (u.code == 200 && u.data) setDouyinUser(u.data.nickname || '', u.data.avatar || ''); } catch (e) {} } else if (!loginStatus.value) { setDouyinUser('', ''); } } catch (e) { loginStatus.value = false; setLoginStatus(false); } };
    const refreshFriends = async () => {
      try { const res = await API.getFriendsList(); const list = res.data.list || {}; const fl = Object.entries(list).map(([name, [avatar, fire]]) => ({ name, avatar, fire })); setFriendsList(fl); friendsCount.value = res.data.count || 0; ElMessage.success('刷新成功');
      } catch (e) {
        const unauth = e.response?.status === 401 || e.message?.includes('未授权') || e.message?.includes('登录已过期');
        if (unauth) ElMessageBox.confirm('您还未登录抖音账号，是否前往登录？', '提示', { confirmButtonText: '前往登录', cancelButtonText: '取消', type: 'warning' }).then(() => window.location.href = '/settings').catch(() => {});
        else ElMessage.error('刷新失败');
      }
    };
    const loadTaskList = async () => { try { const res = await API.getTaskList(); taskCount.value = res.data.count || 0; recentTasks.value = res.data.tasks?.slice(0, 5) || []; localStorage.setItem('douyin_tasks', JSON.stringify(res.data.tasks || [])); } catch (e) {} };
    const initBrowser = async () => {
      if (initLoading.value) return;  // 防止重复点击
      initLoading.value = true;
      try { const res = await API.initBrowser(); if (res.code === 200) { browserStatus.value = true; setBrowserStatus(true); setDouyinUser('', ''); localStorage.removeItem('douyin_username_loaded'); ElMessage.success('浏览器初始化成功'); await checkLoginStatus(); if (!loginStatus.value) ElMessageBox.confirm('浏览器初始化成功，但您还未登录抖音账号，是否前往登录？', '提示', { confirmButtonText: '前往登录', cancelButtonText: '稍后', type: 'warning' }).then(() => window.location.href = '/settings').catch(() => {}); } }
      catch (e) { ElMessage.error('浏览器初始化失败'); } finally { initLoading.value = false; }
    };
    onMounted(async () => {
      if (!homeLoaded.value) {
        await checkBrowserStatus(); await checkLoginStatus();
        if (browserStatus.value && loginStatus.value) { await refreshFriends(); await loadTaskList(); }
        try { const res = await API.getHome(); if (res.time) { localStorage.setItem('douyin_start_time', res.time); uptime.value = formatUptime(res.time); setInterval(() => uptime.value = formatUptime(res.time), 1000); } } catch (e) { uptime.value = '获取失败'; }
        setHomeLoaded();
      } else { friendsCount.value = friendsList.value.length; const t = JSON.parse(localStorage.getItem('douyin_tasks') || '[]'); taskCount.value = t.length; recentTasks.value = t.slice(0, 5); const st = localStorage.getItem('douyin_start_time'); if (st) { uptime.value = formatUptime(st); setInterval(() => uptime.value = formatUptime(st), 1000); } }
    });
    return { friendsCount, taskCount, recentTasks, initLoading, uptime, backendPort, browserStatus, loginStatus, initBrowser, refreshFriends };
  }
};

// ===== Friends Component =====
const Friends = {
  template: `
  <div class="glass-shell anim-fade-up">
    <div class="glass-core">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
        <div class="panel-title" style="margin-bottom:0"><div class="panel-title-icon"><el-icon><component is="User" /></el-icon></div>好友列表</div>
        <div style="display:flex;gap:10px">
          <el-button v-if="!selectionMode" type="primary" :icon="ElementPlusIconsVue.Refresh" @click="loadFriends" :loading="loading">刷新</el-button>
          <el-button v-if="!selectionMode" type="success" :icon="ElementPlusIconsVue.Tickets" @click="selectionMode = true">多选</el-button>
          <template v-if="selectionMode">
            <el-button type="success" :icon="ElementPlusIconsVue.Check" @click="openBatchTaskDialog">创建任务 ({{ selectedFriends.length }})</el-button>
            <el-button :icon="ElementPlusIconsVue.Close" @click="cancelSelection">取消</el-button>
          </template>
        </div>
      </div>
      <div class="toolbar-row">
        <el-input v-model="searchKeyword" placeholder="搜索好友..." :prefix-icon="ElementPlusIconsVue.Search" clearable style="max-width:240px" />
        <el-select v-model="fireFilter" placeholder="火花筛选" clearable style="width:140px">
          <el-option label="全部" value="all" /><el-option label="有火花" value="has" /><el-option label="无火花" value="none" />
        </el-select>
      </div>
      <el-table v-loading="loading" :data="filteredFriends" stripe style="width:100%" @selection-change="handleSelectionChange">
        <el-table-column v-if="selectionMode" type="selection" width="50" />
        <el-table-column type="index" label="序号" :width="selectionMode ? 80 : 60" />
        <el-table-column label="头像" width="80"><template #default="{ row }"><el-avatar :size="40" :src="row.avatar"><el-icon><component is="User" /></el-icon></el-avatar></template></el-table-column>
        <el-table-column prop="name" label="昵称" min-width="120" />
        <el-table-column prop="fire" label="火花天数" width="100"><template #default="{ row }"><el-tag v-if="isFireActive(row.fire)" type="warning">{{ row.fire }}🔥</el-tag><el-tag v-else type="info">无火花</el-tag></template></el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-dropdown @command="(cmd) => handleCommand(cmd, row)" trigger="click">
              <el-button type="primary" size="small">操作<el-icon class="el-icon--right"><component is="ArrowDown" /></el-icon></el-button>
              <template #dropdown><el-dropdown-menu><el-dropdown-item command="send">发起聊天</el-dropdown-item><el-dropdown-item command="create">创建任务</el-dropdown-item></el-dropdown-menu></template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && filteredFriends.length === 0" description="暂无好友数据" />
      <el-dialog v-model="sendDialogVisible" title="发送消息" width="500px" destroy-on-close append-to-body>
        <el-form :model="sendForm" label-width="80px"><el-form-item label="好友"><el-input v-model="sendForm.name" disabled /></el-form-item><el-form-item label="消息内容"><el-input v-model="sendForm.text" type="textarea" :rows="4" placeholder="请输入消息内容" /></el-form-item></el-form>
        <template #footer><el-button @click="sendDialogVisible = false">取消</el-button><el-button type="primary" @click="handleSend" :loading="sendLoading">发送</el-button></template>
      </el-dialog>
      <el-dialog v-model="taskDialogVisible" title="创建定时任务" width="500px" destroy-on-close append-to-body>
        <el-form :model="taskForm" label-width="80px"><el-form-item label="好友"><el-input v-model="taskForm.name" disabled /></el-form-item><el-form-item label="执行时间"><el-time-picker v-model="taskForm.time" format="HH:mm" value-format="HH:mm" placeholder="选择时间" style="width:100%" /></el-form-item><el-form-item label="消息内容"><el-input v-model="taskForm.text" type="textarea" :rows="3" placeholder="留空将使用每日名言" /></el-form-item></el-form>
        <template #footer><el-button @click="taskDialogVisible = false">取消</el-button><el-button type="primary" @click="handleCreateTask" :loading="taskLoading">创建</el-button></template>
      </el-dialog>
      <el-dialog v-model="batchTaskDialogVisible" title="批量创建定时任务" width="600px" destroy-on-close append-to-body>
        <div style="display:flex;flex-wrap:wrap;align-items:center;max-height:120px;overflow-y:auto">
          <span style="font-weight:500;margin-right:8px">已选 ({{ selectedFriends.length }})：</span>
          <el-tag v-for="f in selectedFriends" :key="f.name" style="margin:4px">{{ f.name }}</el-tag>
        </div><el-divider />
        <el-form :model="batchTaskForm" label-width="80px"><el-form-item label="执行时间"><el-time-picker v-model="batchTaskForm.time" format="HH:mm" value-format="HH:mm" placeholder="选择时间" style="width:100%" /></el-form-item><el-form-item label="消息内容"><el-input v-model="batchTaskForm.text" type="textarea" :rows="3" placeholder="留空将使用每日名言" /></el-form-item></el-form>
        <template #footer><el-button @click="batchTaskDialogVisible = false">取消</el-button><el-button type="primary" @click="handleBatchCreateTask" :loading="batchTaskLoading">批量创建 ({{ selectedFriends.length }})</el-button></template>
      </el-dialog>
    </div>
  </div>`,
  setup() {
    const router = VueRouter.useRouter();
    const loading = ref(false), searchKeyword = ref(''), fireFilter = ref('');
    const isFireActive = (fire) => { if (!fire) return false; const n = Number(fire); return !isNaN(n) ? n > 0 : true; };
    const sendDialogVisible = ref(false), sendLoading = ref(false), sendForm = ref({ name: '', text: '' });
    const taskDialogVisible = ref(false), taskLoading = ref(false), taskForm = ref({ name: '', time: '', text: '' });
    const selectionMode = ref(false), selectedFriends = ref([]), batchTaskDialogVisible = ref(false), batchTaskLoading = ref(false), batchTaskForm = ref({ time: '', text: '' });
    const filteredFriends = computed(() => {
      let list = friendsList.value;
      if (searchKeyword.value) { const k = searchKeyword.value.toLowerCase(); list = list.filter(f => f.name.toLowerCase().includes(k)); }
      if (fireFilter.value && fireFilter.value !== 'all') list = list.filter(f => fireFilter.value === 'has' ? isFireActive(f.fire) : !isFireActive(f.fire));
      return list;
    });
    const loadFriends = async () => {
      loading.value = true;
      try { const res = await API.getFriendsList(); if (res.code === 200) { const list = res.data.list || {}; const fl = Object.entries(list).map(([name, [avatar, fire]]) => ({ name, avatar, fire })); setFriendsList(fl); } }
      catch (e) { ElMessage.error('加载好友列表失败'); } finally { loading.value = false; }
    };
    const handleSend = async () => { if (!sendForm.value.text.trim()) { ElMessage.warning('请输入消息内容'); return; } sendLoading.value = true; try { await API.sendMessage(sendForm.value.name, sendForm.value.text); ElMessage.success('发送成功'); sendDialogVisible.value = false; } catch (e) { ElMessage.error('发送失败'); } finally { sendLoading.value = false; } };
    const handleCommand = (cmd, row) => { if (cmd === 'send') { router.push({ path: '/chat', query: { name: row.name } }); } else if (cmd === 'create') { taskForm.value = { name: row.name, time: '', text: '' }; taskDialogVisible.value = true; } };
    const handleCreateTask = async () => { if (!taskForm.value.time) { ElMessage.warning('请选择时间'); return; } taskLoading.value = true; try { await API.addTask(taskForm.value.time, taskForm.value.name, taskForm.value.text || null); ElMessage.success('创建成功'); taskDialogVisible.value = false; } catch (e) { ElMessage.error('创建失败'); } finally { taskLoading.value = false; } };
    const handleSelectionChange = (rows) => selectedFriends.value = rows;
    const cancelSelection = () => { selectionMode.value = false; selectedFriends.value = []; };
    const openBatchTaskDialog = () => { if (selectedFriends.value.length === 0) { ElMessage.warning('请先选择好友'); return; } batchTaskForm.value = { time: '', text: '' }; batchTaskDialogVisible.value = true; };
    const handleBatchCreateTask = async () => { if (!batchTaskForm.value.time) { ElMessage.warning('请选择时间'); return; } batchTaskLoading.value = true; let s = 0, f = 0; try { for (const fr of selectedFriends.value) { try { await API.addTask(batchTaskForm.value.time, fr.name, batchTaskForm.value.text || null); s++; } catch { f++; } } if (f === 0) ElMessage.success(`批量创建成功，共 ${s} 个任务`); else ElMessage.warning(`完成：成功 ${s} 个，失败 ${f} 个`); batchTaskDialogVisible.value = false; cancelSelection(); } finally { batchTaskLoading.value = false; } };
    return { loading, searchKeyword, fireFilter, isFireActive, filteredFriends, loadFriends, sendDialogVisible, sendLoading, sendForm, handleSend, handleCommand, taskDialogVisible, taskLoading, taskForm, handleCreateTask, selectionMode, selectedFriends, batchTaskDialogVisible, batchTaskLoading, batchTaskForm, handleSelectionChange, cancelSelection, openBatchTaskDialog, handleBatchCreateTask, ElementPlusIconsVue };
  }
};

// ===== Chat Component =====
const Chat = {
  template: `
  <div class="glass-shell anim-fade-up chat-shell">
    <div class="glass-core chat-core">
      <div class="chat-container">
        <!-- 左侧好友列表 -->
        <div class="chat-sidebar">
          <div class="chat-sidebar-header">
            <el-input v-model="searchKeyword" placeholder="搜索好友..." :prefix-icon="ElementPlusIconsVue.Search" clearable size="small" />
            <el-button :icon="ElementPlusIconsVue.Refresh" @click="loadFriends" :loading="friendsLoading" size="small" circle style="margin-left:8px;flex-shrink:0" />
          </div>
          <div class="chat-friend-list">
            <div v-for="friend in filteredFriends" :key="friend.name"
                 class="chat-friend-item" :class="{ active: currentChat === friend.name }"
                 @click="selectFriend(friend)">
              <el-avatar :size="40" :src="friend.avatar"><el-icon><component is="User" /></el-icon></el-avatar>
              <div class="chat-friend-info">
                <div class="chat-friend-name">{{ friend.name }}</div>
                <div class="chat-friend-fire" v-if="isFireActive(friend.fire)">{{ friend.fire }} 🔥</div>
              </div>
            </div>
            <el-empty v-if="!friendsLoading && filteredFriends.length === 0" description="暂无好友" :image-size="60" />
          </div>
        </div>

        <!-- 右侧聊天区域 -->
        <div class="chat-main">
          <template v-if="currentChat">
            <div class="chat-header">
              <div class="chat-header-info">
                <span class="chat-header-name">{{ currentChat }}</span>
              </div>
              <el-button :icon="ElementPlusIconsVue.Refresh" @click="loadChatHistory" :loading="historyLoading" size="small" text>刷新记录</el-button>
            </div>

            <div class="chat-messages" ref="messagesContainer">
              <div v-if="historyLoading" class="chat-loading">
                <el-icon class="is-loading" style="font-size:28px;color:var(--text-muted)"><component is="Loading" /></el-icon>
                <span style="margin-left:8px;color:var(--text-muted)">加载消息中...</span>
              </div>
              <template v-else>
                <div v-for="(msg, i) in chatMessages" :key="i"
                     class="chat-msg-row" :class="msg.is_self ? 'self' : 'other'">
                  <div class="chat-avatar">
                    <el-avatar :size="32" :src="msg.is_self ? (douyinAvatar || undefined) : currentFriendAvatar">
                      <el-icon><component is="User" /></el-icon>
                    </el-avatar>
                  </div>
                  <div class="chat-bubble" :class="msg.is_self ? 'bubble-self' : 'bubble-other'">{{ msg.text }}</div>
                </div>
                <div v-if="chatMessages.length === 0" class="chat-empty">
                  <el-icon style="font-size:40px;color:var(--text-muted)"><component is="ChatLineRound" /></el-icon>
                  <p style="color:var(--text-muted);margin-top:8px">暂无消息记录，发送一条消息开始对话</p>
                </div>
              </template>
            </div>

            <!-- 表情面板 -->
            <transition name="sticker-slide">
              <div v-if="stickerPanelVisible" class="sticker-panel">
                <div v-if="stickerLoading" class="sticker-loading">
                  <el-icon class="is-loading" style="font-size:24px"><component is="Loading" /></el-icon>
                  <span style="margin-left:8px">加载表情包中...</span>
                </div>
                <div v-else-if="stickerList.length > 0" class="sticker-grid">
                  <div v-for="(src, i) in stickerList" :key="i" class="sticker-item" @click="sendSticker(i)">
                    <img :src="src" :alt="'表情' + (i+1)" loading="lazy" />
                  </div>
                </div>
                <el-empty v-else description="未获取到表情包" :image-size="50" />
              </div>
            </transition>

            <!-- 输入区域 -->
            <div class="chat-input-area">
              <button class="sticker-btn" @click="toggleStickerPanel" :class="{ active: stickerPanelVisible }" :disabled="stickerLoading" title="表情包">😀</button>
              <el-input v-model="messageText" placeholder="输入消息，回车发送..."
                        @keyup.enter="sendMessage" :disabled="sendLoading"
                        type="textarea" :autosize="{ minRows: 1, maxRows: 4 }"
                        resize="none" style="flex:1" />
              <el-button type="primary" @click="sendMessage" :loading="sendLoading"
                         :disabled="!messageText.trim()" :icon="ElementPlusIconsVue.Promotion">发送</el-button>
            </div>
          </template>

          <!-- 未选择好友时的占位 -->
          <div v-else class="chat-placeholder">
            <el-icon style="font-size:64px;color:var(--text-muted);opacity:0.5"><component is="ChatDotRound" /></el-icon>
            <p style="color:var(--text-muted);margin-top:16px;font-size:15px">选择好友开始聊天</p>
            <p style="color:var(--text-muted);margin-top:4px;font-size:12px;opacity:0.7">支持发送文字和抖音内置表情包</p>
          </div>
        </div>
      </div>
    </div>
  </div>`,
  setup() {
    const route = VueRouter.useRoute();
    const searchKeyword = ref('');
    const currentChat = ref('');
    const currentFriendAvatar = ref('');
    const chatMessages = ref([]);
    const messageText = ref('');
    const stickerPanelVisible = ref(false);
    const stickerList = ref([]);
    const stickerLoading = ref(false);
    const stickerLoaded = ref(false);
    const sendLoading = ref(false);
    const historyLoading = ref(false);
    const friendsLoading = ref(false);
    const messagesContainer = ref(null);

    const isFireActive = (fire) => { if (!fire) return false; const n = Number(fire); return !isNaN(n) ? n > 0 : true; };

    const filteredFriends = computed(() => {
      let list = friendsList.value;
      if (searchKeyword.value) { const k = searchKeyword.value.toLowerCase(); list = list.filter(f => f.name.toLowerCase().includes(k)); }
      return list;
    });

    const loadFriends = async () => {
      friendsLoading.value = true;
      try { const res = await API.getFriendsList(); if (res.code === 200) { const list = res.data.list || {}; setFriendsList(Object.entries(list).map(([name, [avatar, fire]]) => ({ name, avatar, fire }))); } }
      catch (e) { ElMessage.error('加载好友列表失败'); } finally { friendsLoading.value = false; }
    };

    const scrollToBottom = () => {
      setTimeout(() => {
        if (messagesContainer.value) messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
      }, 50);
    };

    const selectFriend = async (friend) => {
      currentChat.value = friend.name;
      currentFriendAvatar.value = friend.avatar || '';
      chatMessages.value = [];
      stickerPanelVisible.value = false;
      await loadChatHistory();
    };

    const loadChatHistory = async () => {
      if (!currentChat.value) return;
      historyLoading.value = true;
      try {
        const res = await API.getChatHistory(currentChat.value);
        if (res.code === 200 && Array.isArray(res.data)) {
          chatMessages.value = res.data;
          scrollToBottom();
        } else {
          chatMessages.value = [];
        }
      } catch (e) {
        chatMessages.value = [];
      } finally {
        historyLoading.value = false;
      }
    };

    const sendMessage = async () => {
      const text = messageText.value.trim();
      if (!text || !currentChat.value || sendLoading.value) return;
      sendLoading.value = true;
      try {
        await API.sendMessage(currentChat.value, text);
        chatMessages.value.push({ text, is_self: true });
        messageText.value = '';
        scrollToBottom();
        ElMessage.success('发送成功');
      } catch (e) {
        ElMessage.error('发送失败');
      } finally {
        sendLoading.value = false;
      }
    };

    const loadStickers = async () => {
      stickerLoading.value = true;
      try {
        const res = await API.getStickerList();
        if (res.code === 200 && Array.isArray(res.data)) {
          stickerList.value = res.data;
          stickerLoaded.value = true;
        } else {
          stickerList.value = [];
          ElMessage.warning(res.data || '未获取到表情包');
        }
      } catch (e) {
        ElMessage.error('获取表情包失败');
      } finally {
        stickerLoading.value = false;
      }
    };

    const toggleStickerPanel = () => {
      stickerPanelVisible.value = !stickerPanelVisible.value;
      if (stickerPanelVisible.value && !stickerLoaded.value) {
        loadStickers();
      }
    };

    const sendSticker = async (index) => {
      if (!currentChat.value || sendLoading.value) return;
      sendLoading.value = true;
      stickerPanelVisible.value = false;
      try {
        await API.sendSticker(currentChat.value, index);
        ElMessage.success('表情包已发送');
        await loadChatHistory();
      } catch (e) {
        ElMessage.error('表情包发送失败');
      } finally {
        sendLoading.value = false;
      }
    };

    onMounted(async () => {
      if (friendsList.value.length === 0) await loadFriends();
      // 从路由参数自动选中好友
      const targetName = route.query.name;
      if (targetName) {
        const friend = friendsList.value.find(f => f.name === targetName);
        if (friend) await selectFriend(friend);
        else ElMessage.warning('未找到该好友');
      }
    });

    return {
      searchKeyword, currentChat, currentFriendAvatar, chatMessages, messageText,
      stickerPanelVisible, stickerList, stickerLoading, sendLoading, historyLoading,
      friendsLoading, messagesContainer, filteredFriends, isFireActive,
      loadFriends, selectFriend, loadChatHistory, sendMessage,
      toggleStickerPanel, sendSticker, douyinAvatar, ElementPlusIconsVue
    };
  }
};

// ===== Tasks Component =====
const Tasks = {
  template: `
  <div class="glass-shell anim-fade-up">
    <div class="glass-core">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
        <div class="panel-title" style="margin-bottom:0"><div class="panel-title-icon"><el-icon><component is="Clock" /></el-icon></div>定时任务管理</div>
        <div style="display:flex;gap:10px">
          <el-button v-if="!selectionMode" type="primary" :icon="ElementPlusIconsVue.Refresh" @click="refreshAll" :loading="loading">刷新</el-button>
          <el-button v-if="!selectionMode" type="success" :icon="ElementPlusIconsVue.Plus" @click="openAddDialog">添加任务</el-button>
          <template v-if="selectionMode">
            <el-button type="danger" :icon="ElementPlusIconsVue.Delete" @click="handleBatchDelete" :loading="batchDeleteLoading">删除 ({{ selectedTasks.length }})</el-button>
            <el-button :icon="ElementPlusIconsVue.Close" @click="cancelSelection">取消</el-button>
          </template>
          <el-button v-if="!selectionMode && taskList.length > 0" :icon="ElementPlusIconsVue.Tickets" @click="selectionMode = true">多选</el-button>
        </div>
      </div>
      <el-table v-loading="loading" :data="taskList" stripe style="width:100%" @selection-change="handleSelectionChange">
        <el-table-column v-if="selectionMode" type="selection" width="50" />
        <el-table-column type="index" label="序号" :width="selectionMode ? 80 : 60" />
        <el-table-column prop="name" label="好友" min-width="120" />
        <el-table-column prop="time" label="执行时间" width="100" />
        <el-table-column prop="next_run" label="下次执行" min-width="160" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button type="warning" size="small" @click="openEditDialog(row)">修改时间</el-button>
            <el-button type="danger" size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && taskList.length === 0" description="暂无定时任务"><el-button type="primary" @click="openAddDialog">添加第一个任务</el-button></el-empty>
      <el-dialog v-model="dialogVisible" :title="dialogMode === 'add' ? '添加定时任务' : '修改执行时间'" width="500px" destroy-on-close append-to-body>
        <el-form :model="taskForm" label-width="80px">
          <el-form-item label="好友"><el-select v-model="taskForm.name" placeholder="选择好友" filterable :disabled="dialogMode === 'edit'" style="width:100%"><el-option v-for="f in availableFriends" :key="f.name" :label="f.name" :value="f.name" /></el-select></el-form-item>
          <el-form-item label="执行时间"><el-time-picker v-model="taskForm.time" format="HH:mm" value-format="HH:mm" placeholder="选择时间" style="width:100%" /></el-form-item>
          <el-form-item v-if="dialogMode === 'add'" label="消息内容"><el-input v-model="taskForm.text" type="textarea" :rows="3" placeholder="留空将使用每日名言" /></el-form-item>
        </el-form>
        <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" @click="handleSubmit" :loading="submitLoading">{{ dialogMode === 'add' ? '添加' : '修改' }}</el-button></template>
      </el-dialog>
    </div>
  </div>`,
  setup() {
    const loading = ref(false), taskList = ref([]), isFirstLoad = ref(true);
    const selectionMode = ref(false), selectedTasks = ref([]), batchDeleteLoading = ref(false);
    const dialogVisible = ref(false), dialogMode = ref('add'), submitLoading = ref(false);
    const taskForm = ref({ name: '', time: '', text: '' });
    const availableFriends = computed(() => { const ex = taskList.value.map(t => t.name); return friendsList.value.filter(f => !ex.includes(f.name)); });
    const refreshAll = async () => {
      loading.value = true;
      try { const [tr, fr] = await Promise.all([API.getTaskList(), API.getFriendsList()]);
        if (tr.code === 200) { taskList.value = tr.data.tasks || []; localStorage.setItem('douyin_tasks', JSON.stringify(tr.data.tasks || [])); }
        if (fr.code === 200) { const list = fr.data.list || {}; setFriendsList(Object.entries(list).map(([name, [avatar, fire]]) => ({ name, avatar, fire }))); }
      } catch (e) { ElMessage.error('刷新失败'); } finally { loading.value = false; }
    };
    const openAddDialog = () => { dialogMode.value = 'add'; taskForm.value = { name: '', time: '', text: '' }; dialogVisible.value = true; };
    const openEditDialog = (t) => { dialogMode.value = 'edit'; taskForm.value = { name: t.name, time: t.time, text: '' }; dialogVisible.value = true; };
    const handleSubmit = async () => { if (!taskForm.value.name && dialogMode.value === 'add') { ElMessage.warning('请选择好友'); return; } if (!taskForm.value.time) { ElMessage.warning('请选择时间'); return; } submitLoading.value = true; try { if (dialogMode.value === 'add') { await API.addTask(taskForm.value.time, taskForm.value.name, taskForm.value.text || null); ElMessage.success('添加成功'); } else { await API.editTask(taskForm.value.name, taskForm.value.time); ElMessage.success('修改成功'); } dialogVisible.value = false; await refreshAll(); } catch (e) { ElMessage.error(dialogMode.value === 'add' ? '添加失败' : '修改失败'); } finally { submitLoading.value = false; } };
    const handleDelete = async (t) => { try { await ElMessageBox.confirm(`确定要删除 ${t.name} 的定时任务吗？`, '提示', { type: 'warning' }); await API.delTask(t.task_id); ElMessage.success('删除成功'); await refreshAll(); } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败'); } };
    const handleSelectionChange = (rows) => selectedTasks.value = rows;
    const cancelSelection = () => { selectionMode.value = false; selectedTasks.value = []; };
    const handleBatchDelete = async () => { if (selectedTasks.value.length === 0) { ElMessage.warning('请先选择要删除的任务'); return; } try { await ElMessageBox.confirm(`确定要删除选中的 ${selectedTasks.value.length} 个任务吗？`, '批量删除', { type: 'warning' }); batchDeleteLoading.value = true; let s = 0, f = 0; for (const t of selectedTasks.value) { try { await API.delTask(t.task_id); s++; } catch { f++; } } if (f === 0) ElMessage.success(`批量删除成功，共 ${s} 个`); else ElMessage.warning(`完成：成功 ${s} 个，失败 ${f} 个`); cancelSelection(); await refreshAll(); } catch (e) { if (e !== 'cancel') ElMessage.error('批量删除失败'); } finally { batchDeleteLoading.value = false; } };
    onMounted(async () => { if (isFirstLoad.value) { await refreshAll(); isFirstLoad.value = false; } else { const c = localStorage.getItem('douyin_tasks'); if (c) taskList.value = JSON.parse(c); } });
    return { loading, taskList, selectionMode, selectedTasks, batchDeleteLoading, dialogVisible, dialogMode, submitLoading, taskForm, availableFriends, refreshAll, openAddDialog, openEditDialog, handleSubmit, handleDelete, handleSelectionChange, cancelSelection, handleBatchDelete, ElementPlusIconsVue };
  }
};

// ===== Settings Component =====
const Settings = {
  template: `
  <div class="settings-stack">
    <div class="glass-shell anim-fade-up stagger-1">
      <div class="glass-core">
        <div class="panel-title"><div class="panel-title-icon"><el-icon><component is="Key" /></el-icon></div>账户配置</div>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="登录状态"><el-tag :type="loginStatus ? 'success' : 'danger'" effect="dark">{{ loginStatus ? (username ? '已登录: ' + username : '已登录') : '未登录' }}</el-tag></el-descriptions-item>
        </el-descriptions>
        <div style="margin-top:20px;display:flex;gap:12px;flex-wrap:wrap">
          <el-button type="primary" :icon="ElementPlusIconsVue.Key" @click="handleLogin" :loading="loginLoading" :disabled="loginStatus">扫码登录</el-button>
          <el-button type="primary" :icon="ElementPlusIconsVue.Message" @click="phoneDialogVisible = true" :disabled="loginStatus">验证码登录</el-button>
          <el-button :icon="ElementPlusIconsVue.Edit" @click="manualDialogVisible = true" :disabled="loginStatus">手动登录</el-button>
          <el-button :icon="ElementPlusIconsVue.Refresh" @click="handleRefreshStatus" :loading="refreshStatusLoading">刷新状态</el-button>
          <el-button :icon="ElementPlusIconsVue.Document" @click="cookieDialogVisible = true">获取Cookie</el-button>
          <el-button :icon="ElementPlusIconsVue.SwitchButton" type="danger" @click="handleDieLogin">强制退出</el-button>
        </div>
      </div>
    </div>
    <div class="glass-shell anim-fade-up stagger-2">
      <div class="glass-core">
        <div class="panel-title"><div class="panel-title-icon"><el-icon><component is="Lock" /></el-icon></div>后台配置</div>
        <div style="display:flex;align-items:center;gap:20px;flex-wrap:wrap">
          <div style="display:flex;align-items:center;padding:8px 16px;background:var(--glass-2);border-radius:var(--r-sm);border:1px solid var(--glass-border)"><span style="color:var(--text-secondary);font-size:13px;margin-right:8px">上次登录IP：</span><span style="color:var(--text-primary);font-size:13px;font-weight:500">{{ lastLoginIP }}</span></div>
          <el-button type="primary" :icon="ElementPlusIconsVue.Lock" @click="passwordDialogVisible = true">修改密码</el-button>
        </div>
      </div>
    </div>
    <div class="glass-shell anim-fade-up stagger-3">
      <div class="glass-core">
        <div class="panel-title"><div class="panel-title-icon"><el-icon><component is="Picture" /></el-icon></div>调试功能</div>
        <div style="display:flex;gap:12px;flex-wrap:wrap">
          <el-button type="primary" :icon="ElementPlusIconsVue.Picture" @click="handleGetScreenshot" :loading="screenshotLoading">浏览器截图</el-button>
          <el-button type="warning" :icon="ElementPlusIconsVue.WarnTriangleFilled" @click="handleForceLogin">强制登录状态</el-button>
        </div>
      </div>
    </div>
    <div class="glass-shell anim-fade-up stagger-4">
      <div class="glass-core">
        <div class="panel-title"><div class="panel-title-icon"><el-icon><component is="Setting" /></el-icon></div>服务端口</div>
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
          <div style="display:flex;align-items:center;gap:10px;padding:8px 16px;background:var(--glass-2);border-radius:var(--r-sm);border:1px solid var(--glass-border)">
            <span style="color:var(--text-secondary);font-size:13px">当前端口：</span>
            <span style="color:var(--coral);font-size:15px;font-weight:700">{{ currentPort }}</span>
          </div>
          <el-input v-model="portForm.new_port" placeholder="输入新端口" style="width:140px" @keyup.enter="handleSetPort" />
          <el-button type="primary" :icon="ElementPlusIconsVue.Check" @click="handleSetPort" :loading="portLoading">保存</el-button>
          <span style="color:var(--text-muted);font-size:12px">修改后需重启后端生效</span>
        </div>
      </div>
    </div>
    <div class="glass-shell anim-fade-up stagger-4">
      <div class="glass-core">
        <div class="panel-title"><div class="panel-title-icon"><el-icon><component is="Monitor" /></el-icon></div>浏览器显示</div>
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
          <div style="display:flex;align-items:center;gap:10px;padding:8px 16px;background:var(--glass-2);border-radius:var(--r-sm);border:1px solid var(--glass-border)">
            <span style="color:var(--text-secondary);font-size:13px">当前模式：</span>
            <span :style="{ color: browserMode ? 'var(--success)' : 'var(--text-muted)', fontSize: '15px', fontWeight: 700 }">{{ browserMode ? '显示窗口' : '隐藏（无头）' }}</span>
          </div>
          <el-switch v-model="browserMode" :loading="browserModeLoading" @change="handleSetBrowserMode" active-text="显示" inactive-text="隐藏" />
          <span style="color:var(--text-muted);font-size:12px">无头模式易崩溃，建议显示窗口</span>
        </div>
      </div>
    </div>
    <el-dialog v-model="manualDialogVisible" title="手动登录" width="500px" destroy-on-close append-to-body><el-form :model="manualForm" label-width="120px"><el-form-item label="Base64Cookie"><el-input v-model="manualForm.cookie" type="textarea" :rows="6" placeholder="请输入登录Base64Cookie" /></el-form-item></el-form><template #footer><el-button @click="manualDialogVisible = false">取消</el-button><el-button type="primary" @click="handleManualLogin" :loading="manualLoading">验证登录</el-button></template></el-dialog>
    <el-dialog v-model="cookieDialogVisible" title="获取Cookie" width="400px" destroy-on-close append-to-body><el-form :model="cookieForm" label-width="100px"><el-form-item label="确认密码"><el-input v-model="cookieForm.password" type="password" placeholder="请输入密码确认" @keyup.enter="handleGetCookie" /></el-form-item></el-form><template #footer><el-button @click="cookieDialogVisible = false">取消</el-button><el-button type="primary" @click="handleGetCookie" :loading="cookieLoading">获取Cookie</el-button></template></el-dialog>
    <el-dialog v-model="phoneDialogVisible" title="验证码登录" width="400px" destroy-on-close append-to-body><el-form :model="phoneForm" label-width="80px"><el-form-item label="手机号"><div style="display:flex;gap:8px"><el-input v-model="phoneForm.areacode" placeholder="+86" style="width:70px;flex-shrink:0" @keyup.enter="handleSendCode" /><el-input v-model="phoneForm.phone" placeholder="请输入手机号" style="flex:1" @keyup.enter="handleSendCode" /></div></el-form-item><el-form-item label="验证码"><div style="display:flex;gap:10px"><el-input v-model="phoneForm.code" placeholder="请输入验证码" style="flex:1" @keyup.enter="handlePhoneLogin" /><el-button @click="handleSendCode" :disabled="codeCountdown > 0" :loading="codeLoading">{{ codeCountdown > 0 ? codeCountdown + 's' : '发送验证码' }}</el-button></div></el-form-item></el-form><template #footer><el-button @click="phoneDialogVisible = false">取消</el-button><el-button type="primary" @click="handlePhoneLogin" :loading="phoneLoading">登录</el-button></template></el-dialog>
    <el-dialog v-model="qrDialogVisible" title="抖音扫码登录" width="350px" destroy-on-close append-to-body><div style="display:flex;justify-content:center;align-items:center;min-height:300px"><div v-if="qrcodeUrl" style="text-align:center"><img :src="qrcodeUrl" alt="登录二维码" style="width:250px;height:250px;border:1px solid var(--glass-border);border-radius:var(--r-md);padding:8px;background:var(--bg-elevated);box-shadow:var(--shadow-glow-coral)" /><p style="margin-top:15px;color:var(--text-secondary);font-size:14px">请使用抖音App扫码登录</p></div><div v-else-if="loading" style="text-align:center;color:var(--text-muted)"><el-icon class="is-loading" style="font-size:48px;margin-bottom:10px"><component is="Loading" /></el-icon><p>正在加载二维码...</p></div></div><div style="display:flex;justify-content:center;gap:12px;margin-top:20px;padding-top:15px;border-top:1px solid var(--glass-border)"><el-button :icon="ElementPlusIconsVue.Refresh" @click="handleRefreshCode" :loading="refreshLoading" size="small">刷新验证码</el-button><el-button :icon="ElementPlusIconsVue.View" @click="handleCheckLogin" :loading="checkLoading" size="small">获取登录状态</el-button></div></el-dialog>
    <el-dialog v-model="passwordDialogVisible" title="修改密码" width="400px" destroy-on-close append-to-body><el-form :model="passwordForm" label-width="90px"><el-form-item label="原密码"><el-input v-model="passwordForm.old_password" type="password" placeholder="请输入原密码" show-password /></el-form-item><el-form-item label="新密码"><el-input v-model="passwordForm.new_password" type="password" placeholder="请输入新密码" show-password /></el-form-item></el-form><template #footer><el-button @click="passwordDialogVisible = false">取消</el-button><el-button type="primary" @click="handleChangePassword" :loading="passwordLoading">确认修改</el-button></template></el-dialog>
    <el-dialog v-model="screenshotPreviewVisible" title="浏览器截图" width="600px" destroy-on-close append-to-body><img :src="screenshotUrl" alt="浏览器截图" style="max-width:100%;max-height:70vh;display:block;margin:0 auto" /></el-dialog>
  </div>`,
  setup() {
    const loginLoading = ref(false), refreshLoading = ref(false), checkLoading = ref(false), refreshStatusLoading = ref(false);
    const qrDialogVisible = ref(false), qrcodeUrl = ref(''), loading = ref(false);
    const manualDialogVisible = ref(false), manualLoading = ref(false), manualForm = ref({ cookie: '' });
    const username = ref(localStorage.getItem('douyin_username') || ''), usernameLoaded = ref(localStorage.getItem('douyin_username_loaded') === '1');
    const passwordDialogVisible = ref(false), passwordLoading = ref(false), passwordForm = ref({ old_password: '', new_password: '' });
    const lastLoginIP = ref(localStorage.getItem('douyin_last_login_ip') || '加载中...'), settingsLoaded = ref(localStorage.getItem('douyin_settings_loaded') === '1');
    const cookieDialogVisible = ref(false), cookieLoading = ref(false), cookieForm = ref({ password: '' });
    const screenshotLoading = ref(false), screenshotUrl = ref(''), screenshotPreviewVisible = ref(false);
    const phoneDialogVisible = ref(false), phoneLoading = ref(false), codeLoading = ref(false), codeCountdown = ref(0);
    const phoneForm = ref({ areacode: '+86', phone: '', code: '' });
    const currentPort = ref(8080), portForm = ref({ new_port: '' }), portLoading = ref(false);
    const browserMode = ref(true), browserModeLoading = ref(false);

    const fetchLastLoginIP = async () => { try { const res = await API.getLastLoginIP(); if (res.code == 200) { lastLoginIP.value = res.data || '无'; localStorage.setItem('douyin_last_login_ip', lastLoginIP.value); } } catch (e) { lastLoginIP.value = '获取失败'; } };
    const fetchUsername = async () => { try { const res = await API.getUsername(); if (res.code == 200 && res.data) { const nick = res.data.nickname || ''; const av = res.data.avatar || ''; username.value = nick; usernameLoaded.value = true; setDouyinUser(nick, av); localStorage.setItem('douyin_username_loaded', '1'); } } catch (e) {} };
    const checkLoginStatus = async () => { try { const res = await API.getLoginStatus(); loginStatus.value = res.data === 'Yes'; setLoginStatus(loginStatus.value); if (loginStatus.value && !usernameLoaded.value) await fetchUsername(); } catch (e) { loginStatus.value = false; setLoginStatus(false); } };
    const handleRefreshStatus = async () => { refreshStatusLoading.value = true; try { usernameLoaded.value = false; setDouyinUser('', ''); localStorage.removeItem('douyin_username_loaded'); await checkLoginStatus(); await fetchLastLoginIP(); ElMessage.success(loginStatus.value ? '已登录' : '未登录'); } finally { refreshStatusLoading.value = false; } };
    const fetchFriendsList = async () => { try { const res = await API.getFriendsList(); if (res.code === 200) { const list = res.data.list || {}; setFriendsList(Object.entries(list).map(([name, [avatar, fire]]) => ({ name, avatar, fire }))); } } catch (e) {} };
    const handleCheckLogin = async () => { checkLoading.value = true; try { const res = await API.pnglogin(); loginStatus.value = res.code == 200; setLoginStatus(loginStatus.value); if (loginStatus.value) { ElMessage.success('登录成功'); qrDialogVisible.value = false; username.value = ''; usernameLoaded.value = false; setDouyinUser('', ''); localStorage.removeItem('douyin_username_loaded'); await fetchUsername(); await fetchFriendsList(); } else ElMessage.warning('未登录，请继续扫码'); } catch (e) { ElMessage.error('扫码登录失败，请重试'); } finally { checkLoading.value = false; } };
    const handleRefreshCode = async () => { refreshLoading.value = true; try { await API.initBrowser(); const res = await API.getLoginPng(); if (res.data) { qrcodeUrl.value = res.data; qrDialogVisible.value = true; ElMessage.success('刷新成功'); } else ElMessage.error('获取二维码失败'); } catch (e) { ElMessage.error('刷新失败，请确保浏览器已初始化'); } finally { refreshLoading.value = false; } };
    const handleManualLogin = async () => { if (!manualForm.value.cookie.trim()) { ElMessage.warning('请输入Base64Cookie'); return; } manualLoading.value = true; try { const res = await API.login(manualForm.value.cookie); if (res.data === 'ok') { ElMessage.success('登录成功'); loginStatus.value = true; setLoginStatus(true); manualDialogVisible.value = false; username.value = ''; usernameLoaded.value = false; setDouyinUser('', ''); localStorage.removeItem('douyin_username_loaded'); await fetchUsername(); await fetchFriendsList(); } else ElMessage.error('登录失败，Cookie无效'); } catch (e) { ElMessage.error('登录失败，请检查Cookie'); } finally { manualLoading.value = false; } };
    const handleChangePassword = async () => { if (!passwordForm.value.old_password) { ElMessage.warning('请输入原密码'); return; } if (!passwordForm.value.new_password) { ElMessage.warning('请输入新密码'); return; } if (passwordForm.value.old_password === passwordForm.value.new_password) { ElMessage.warning('新密码不能与原密码相同'); return; } passwordLoading.value = true; try { const res = await API.changePassword(passwordForm.value.old_password, passwordForm.value.new_password); if (res.code == 200) { ElMessage.success('密码修改成功'); passwordDialogVisible.value = false; passwordForm.value.old_password = ''; passwordForm.value.new_password = ''; } else ElMessage.error(res.data || '修改失败'); } catch (e) { ElMessage.error('修改失败'); } finally { passwordLoading.value = false; } };
    const handleGetCookie = async () => { if (!cookieForm.value.password) { ElMessage.warning('请输入密码'); return; } cookieLoading.value = true; try { const res = await API.getCooker(cookieForm.value.password); if (res.code == 200) { const ta = document.createElement('textarea'); ta.value = res.data.cooke; ta.style.position = 'fixed'; ta.style.left = '-9999px'; document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); ElMessage.success('Cookie已复制到剪贴板'); cookieDialogVisible.value = false; cookieForm.value.password = ''; } catch { ElMessage.error('复制失败'); } finally { document.body.removeChild(ta); } } else ElMessage.error(res.data || '获取失败，密码错误'); } catch (e) { ElMessage.error('获取失败'); } finally { cookieLoading.value = false; } };
    const handleDieLogin = async () => { try { await API.dieLogin(); setLoginStatus(false); setDouyinUser('', ''); localStorage.removeItem('douyin_token'); ElMessage.success('已强制退出登录'); } catch (e) { ElMessage.error('强制退出失败'); } };
    const handleSendCode = async () => { if (!phoneForm.value.phone) { ElMessage.warning('请输入手机号'); return; } codeLoading.value = true; try { const res = await API.sendVerifyCode(phoneForm.value.areacode, phoneForm.value.phone); if (res.code == 200) { ElMessage.success('验证码发送成功'); codeCountdown.value = 60; const timer = setInterval(() => { codeCountdown.value--; if (codeCountdown.value <= 0) clearInterval(timer); }, 1000); } else ElMessage.error(res.data || '验证码发送失败'); } catch (e) { ElMessage.error('验证码发送失败，请确保浏览器已初始化'); } finally { codeLoading.value = false; } };
    const handlePhoneLogin = async () => { if (!phoneForm.value.phone) { ElMessage.warning('请输入手机号'); return; } if (!phoneForm.value.code) { ElMessage.warning('请输入验证码'); return; } phoneLoading.value = true; try { const res = await API.submitVerifyCode(phoneForm.value.code); if (res.code == 200) { ElMessage.success('登录成功'); phoneDialogVisible.value = false; setLoginStatus(true); username.value = ''; usernameLoaded.value = false; setDouyinUser('', ''); localStorage.removeItem('douyin_username_loaded'); await fetchUsername(); } else ElMessage.error(res.data || '登录失败'); } catch (e) { ElMessage.error('登录失败，请重试'); } finally { phoneLoading.value = false; } };
    const handleGetScreenshot = async () => { screenshotLoading.value = true; screenshotUrl.value = ''; try { const res = await API.getScrlk(); if (res.code == 200) { screenshotUrl.value = 'data:image/png;base64,' + res.data; screenshotPreviewVisible.value = true; } else ElMessage.error(res.data || '获取截图失败'); } catch (e) { ElMessage.error('获取截图失败，请确保已登录'); } finally { screenshotLoading.value = false; } };
    const handleForceLogin = async () => { try { const res = await API.forceLogin(); if (res.code == 200) ElMessage.success(res.data || '强制登录状态成功'); else ElMessage.error(res.data || '强制登录状态失败'); } catch (e) { ElMessage.error('强制登录状态失败'); } };
    const fetchPort = async () => { try { const res = await API.getPort(); if (res.code == 200) currentPort.value = res.data; } catch (e) {} };
    const handleSetPort = async () => { const p = parseInt(portForm.value.new_port); if (!p) { ElMessage.warning('请输入端口号'); return; } if (p < 1 || p > 65535) { ElMessage.warning('端口范围 1-65535'); return; } portLoading.value = true; try { const res = await API.setPort(p); if (res.code == 200) { ElMessage.success(res.data || '保存成功，重启后端后生效'); currentPort.value = p; portForm.value.new_port = ''; } else ElMessage.error(res.data || '保存失败'); } catch (e) { ElMessage.error('保存失败'); } finally { portLoading.value = false; } };
    const fetchBrowserMode = async () => { try { const res = await API.getBrowserMode(); if (res.code == 200) browserMode.value = res.data; } catch (e) {} };
    const handleSetBrowserMode = async () => { browserModeLoading.value = true; try { const res = await API.setBrowserMode(browserMode.value); if (res.code == 200) ElMessage.success(res.data || '保存成功，重启后端后生效'); else { ElMessage.error(res.data || '保存失败'); browserMode.value = !browserMode.value; } } catch (e) { ElMessage.error('保存失败'); browserMode.value = !browserMode.value; } finally { browserModeLoading.value = false; } };
    const handleLogin = async () => { loginLoading.value = true; loading.value = true; qrcodeUrl.value = ''; qrDialogVisible.value = true; try { await API.initBrowser(); const res = await API.getLoginPng(); if (res.data) { qrcodeUrl.value = res.data; ElMessage.success('请使用抖音App扫码登录'); } else { ElMessage.error('获取二维码失败'); qrDialogVisible.value = false; } } catch (e) { ElMessage.error('登录初始化失败，请确保浏览器已启动'); qrDialogVisible.value = false; } finally { loginLoading.value = false; loading.value = false; } };

    onMounted(async () => { if (!settingsLoaded.value) { await checkLoginStatus(); await fetchLastLoginIP(); localStorage.setItem('douyin_settings_loaded', '1'); } await fetchPort(); await fetchBrowserMode(); });
    onActivated(async () => { lastLoginIP.value = localStorage.getItem('douyin_last_login_ip') || '加载中...'; });

    return { loginLoading, refreshLoading, checkLoading, refreshStatusLoading, qrDialogVisible, qrcodeUrl, loading, manualDialogVisible, manualLoading, manualForm, username, passwordDialogVisible, passwordLoading, passwordForm, lastLoginIP, cookieDialogVisible, cookieLoading, cookieForm, screenshotLoading, screenshotUrl, screenshotPreviewVisible, phoneDialogVisible, phoneLoading, codeLoading, codeCountdown, phoneForm, currentPort, portForm, portLoading, browserMode, browserModeLoading, handleSetBrowserMode, handleLogin, handleRefreshStatus, handleCheckLogin, handleRefreshCode, handleManualLogin, handleChangePassword, handleGetCookie, handleDieLogin, handleSendCode, handlePhoneLogin, handleGetScreenshot, handleForceLogin, handleSetPort, loginStatus, ElementPlusIconsVue };
  }
};

// ===== Router =====
const routes = [
  { path: '/login', name: 'Login', component: Login, meta: { requiresAuth: false } },
  { path: '/', component: Layout, meta: { requiresAuth: true }, redirect: '/home', children: [
    { path: 'home', name: 'Home', component: Home },
    { path: 'friends', name: 'Friends', component: Friends },
    { path: 'chat', name: 'Chat', component: Chat },
    { path: 'tasks', name: 'Tasks', component: Tasks },
    { path: 'settings', name: 'Settings', component: Settings }
  ]}
];
const router = createRouter({ history: createWebHistory(), routes });

// ===== Boot =====
window.addEventListener('error', (e) => { console.error('Global error:', e.message, e.filename, e.lineno); });
window.addEventListener('unhandledrejection', (e) => { console.error('Unhandled rejection:', e.reason); });

try {
  var hint = document.getElementById('loading-hint');
  if (hint) hint.remove();

  const app = createApp({ template: '<router-view />' });
  app.config.errorHandler = (err, vm, info) => {
    console.error('Vue渲染错误:', err.message, '\nInfo:', info, '\nStack:', err.stack);
  };

  app.use(router);
  app.use(ElementPlus);

  for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component);
  }

  userStore.restoreSession();

  router.beforeEach((to, from) => {
    if (to.meta.requiresAuth && !userStore.isLoggedIn) return '/login';
    else if (to.path === '/login' && userStore.isLoggedIn) return '/';
  });

  app.mount('#app');
  console.log('App started');
} catch (e) {
  console.error('App init error:', e);
  document.body.innerHTML = '<div style="color:#dc2626;padding:40px;font-family:monospace;background:#f5f4f1;min-height:100vh"><h2>应用初始化失败</h2><pre style="white-space:pre-wrap">' + e.message + '\n\n' + (e.stack || '') + '</pre></div>';
}
