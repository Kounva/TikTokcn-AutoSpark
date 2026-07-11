"""抖音表情包操作 Mixin 模块

将 Douyin 类中表情包相关方法抽离为独立 Mixin，
Douyin 类通过继承 StickerMixin 获得这些方法。
方法体内的 driver 统一用 self.driver（与 __init__ 一致，行为不变）。
"""
import time
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from backend.utils import TrueString, _dbg_report


class StickerMixin:
    """表情包相关操作混入类"""

    _sticker_categories = []
    _sticker_src_map = {}

    def _open_emoji_panel(self):
        """点击表情按钮打开表情面板。
        两步法：JS 定位按钮并标记 → ActionChains 真实点击（React 合成事件需要真实点击）。
        """
        driver = self.driver
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
        driver = self.driver
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
        driver = self.driver
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
        driver = self.driver
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

    def _switch_emoji_tab(self, tab_index):
        """切换表情面板到指定 tab（用 ActionChains 真实点击）
        选择器和 _collect_stickers 完全一致，确保 tab 顺序相同。
        点击后等待图片加载稳定，避免竞态条件。
        """
        from selenium.webdriver.common.action_chains import ActionChains
        driver = self.driver
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
        driver = self.driver
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
        driver = self.driver
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
