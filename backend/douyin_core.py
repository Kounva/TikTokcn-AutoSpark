"""抖音自动化核心类模块

Douyin 类继承 StickerMixin 获得表情包相关方法，
自身保留好友/聊天/登录相关操作。
方法体内的 driver 统一用 self.driver。
"""
import time
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from backend.utils import TrueString, UserFriendsInfo, _dbg_report
from backend.douyin_sticker import StickerMixin


class Douyin(StickerMixin):
    friends_xpath_list = {}

    def __init__(self, driver):
        self.driver = driver  # 将 driver 作为实例属性

    def PrintfFrinder(self):
        print(f'\n⏭️ 好友列表 共获取{len(self.friends_xpath_list)}位:\n------------------')
        for index, value in self.friends_xpath_list.items():
            print(index)
        print('------------------')

    def Updara_FrinderList(self):
        driver = self.driver
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
        driver = self.driver
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
        driver = self.driver
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

    def Get_Chat_History(self, name: str):
        """获取当前对话的聊天记录"""
        driver = self.driver
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
        driver = self.driver
        try:
            dle_user = driver.find_element(By.XPATH,
                                           value='//*[@id="douyin_login_comp_flat_panel"]/div/div[2]/div/div[4]/p')
            dle_user.click()
        except:
            pass
