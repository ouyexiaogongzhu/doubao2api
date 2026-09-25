"""页面行为模拟：让浏览器持续产生真实感交互遥测。

字节风控会给"零交互凭空发消息"的会话打高风险分。Humanizer 用贝塞尔
鼠标轨迹、微滚动和随机停顿在页面事件流里伪造真人活跃信号：
- warm_up(): 会话建立后的一次性预热
- nudge():   每次发请求前的轻动作
- heartbeat_loop(): 后台死循环，长期维持遥测

仅用 stdlib + asyncio，页面操作走传入的 Playwright page 对象。
"""

import asyncio
import logging
import random

log = logging.getLogger(__name__)

_FALLBACK_VIEWPORT = (1200, 700)


def _bezier_points(p0, p1, p2, p3, n):
    """三次贝塞尔插值，n 个点（含首尾）。"""
    pts = []
    for i in range(n):
        t = i / (n - 1)
        u = 1 - t
        x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
        pts.append((x, y))
    return pts


class Humanizer:
    def __init__(self, page):
        self.page = page
        self._warned = False

    def _safe(self, coro_fn):
        """执行页面操作，导航/closed 等异常静默降级，只 warning 一次。"""
        try:
            return coro_fn()
        except Exception as e:
            if not self._warned:
                log.warning("humanize: page interaction failed (%s), degrading silently", e)
                self._warned = True
            return None

    def _active_region(self):
        """视口中部的安全活动区，避开边缘。"""
        try:
            vp = self.page.viewport_size
            w, h = (vp["width"], vp["height"]) if vp else _FALLBACK_VIEWPORT
        except Exception:
            w, h = _FALLBACK_VIEWPORT
        return int(w * 0.2), int(w * 0.8), int(h * 0.2), int(h * 0.8)

    def _rand_point(self, x0, x1, y0, y1):
        return (random.uniform(x0, x1), random.uniform(y0, y1))

    async def _bezier_move(self):
        x0, x1, y0, y1 = self._active_region()
        start = self._rand_point(x0, x1, y0, y1)
        end = self._rand_point(x0, x1, y0, y1)
        c1 = self._rand_point(x0, x1, y0, y1)
        c2 = self._rand_point(x0, x1, y0, y1)
        for x, y in _bezier_points(start, c1, c2, end, random.randint(15, 25)):
            try:
                await self.page.mouse.move(x, y)
                await asyncio.sleep(random.uniform(0.008, 0.02))
            except Exception as e:
                self._warn_once(e)
                return

    def _warn_once(self, e):
        if not self._warned:
            log.warning("humanize: page interaction failed (%s), degrading silently", e)
            self._warned = True

    async def _micro_scroll(self):
        try:
            await self.page.mouse.wheel(0, random.randint(60, 180))
            if random.random() < 0.4:  # 偶尔滚回一点
                await asyncio.sleep(random.uniform(0.15, 0.4))
                await self.page.mouse.wheel(0, -random.randint(40, 120))
        except Exception as e:
            self._warn_once(e)

    async def warm_up(self):
        """启动预热：3~5 次贝塞尔移动 + 一次微滚动 + 随机停顿 1~3s。"""
        for _ in range(random.randint(3, 5)):
            await self._bezier_move()
            await asyncio.sleep(random.uniform(0.2, 0.6))
        await self._micro_scroll()
        await asyncio.sleep(random.uniform(1, 3))

    async def nudge(self):
        """单次轻动作：1 次鼠标移动 + 300~800ms 停顿。供请求前调用。"""
        await self._bezier_move()
        await asyncio.sleep(random.uniform(0.3, 0.8))

    async def heartbeat_loop(self):
        """死循环：随机睡 90~240s → 1~2 次移动 + 偶尔微滚动。永不抛异常。"""
        while True:
            await asyncio.sleep(random.uniform(90, 240))
            try:
                if self.page.is_closed():
                    return
            except Exception:
                return
            try:
                for _ in range(random.randint(1, 2)):
                    await self._bezier_move()
                if random.random() < 0.3:
                    await self._micro_scroll()
            except Exception as e:
                self._warn_once(e)
