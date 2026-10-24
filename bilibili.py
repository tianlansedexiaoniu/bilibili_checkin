import requests
from loguru import logger

class BilibiliTask:
    def __init__(self, cookie):
        self.cookie = cookie
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Referer': 'https://www.bilibili.com/',
            'Cookie': cookie
        }
        self.csrf = self._get_csrf()

    def _get_csrf(self):
        for item in self.cookie.split(';'):
            if item.strip().startswith('bili_jct'):
                return item.split('=')[1]
        return None

    def get_user_info(self):
        url = 'https://api.bilibili.com/x/web-interface/nav'
        try:
            res = requests.get(url, headers=self.headers)
            res.raise_for_status()
            data = res.json()
            if data['code'] == 0:
                return data['data']
            logger.warning(f"获取用户信息失败: {data.get('message')}")
            return None
        except Exception as e:
            logger.error(f"请求用户信息API异常: {e}")
            return None


    
    def get_dynamic_videos(self):
        # 原 x/web-interface/dynamic/region 接口已被B站下线（返回 code=-404「啥都木有」），
        # 这里改为从「热门」视频中取投币目标，保证总能拿到可用视频。
        return self.get_popular_videos()

    def get_popular_videos(self):
        url = 'https://api.bilibili.com/x/web-interface/popular?ps=10&pn=1'
        try:
            res = requests.get(url, headers=self.headers)
            res.raise_for_status()
            data = res.json()
            if data.get('code') == 0:
                return [v['bvid'] for v in data.get('data', {}).get('list', []) if v.get('bvid')]
            logger.warning(f"热门视频接口返回: {data.get('message')}")
            return []
        except Exception as e:
            logger.error(f"请求热门视频API异常: {e}")
            return []

    def get_ranking_videos(self):
        url = 'https://api.bilibili.com/x/web-interface/ranking/v2?rid=0&type=all'
        try:
            res = requests.get(url, headers=self.headers)
            res.raise_for_status()
            data = res.json()
            if data['code'] == 0:
                return [video['bvid'] for video in data.get('data', {}).get('list', [])]
            return []
        except Exception as e:
            logger.error(f"请求排行榜视频API异常: {e}")
            return []

    def check_video_coin_status(self, bvid):
        url = f'https://api.bilibili.com/x/web-interface/archive/coins?bvid={bvid}'
        try:
            res = requests.get(url, headers=self.headers)
            res.raise_for_status()
            data = res.json()
            if data['code'] == 0:
                return data['data']['multiply'] > 0
            return False
        except Exception:
            return False

    def add_coin(self, bvid, num=1, select_like=1):
        if not self.csrf: return False, "Bili_jct(csrf) 未找到"
        url = 'https://api.bilibili.com/x/web-interface/coin/add'
        data = {'bvid': bvid, 'multiply': num, 'select_like': select_like, 'csrf': self.csrf}
        try:
            res = requests.post(url, headers=self.headers, data=data)
            data = res.json()
            if data['code'] == 0:
                return True, "投币成功"
            return False, data.get('message', '投币失败')
        except Exception as e:
            return False, str(e)
            
    def share_video(self, bvid):
        if not self.csrf: return False, "Bili_jct(csrf) 未找到"
        url = 'https://api.bilibili.com/x/web-interface/share/add'
        data = {'bvid': bvid, 'csrf': self.csrf}
        try:
            res = requests.post(url, headers=self.headers, data=data)
            data = res.json()
            if data['code'] == 0:
                return True, "分享成功"
            return False, data.get('message', '分享失败')
        except Exception as e:
            return False, str(e)

    def watch_video(self, bvid):
        url = 'https://api.bilibili.com/x/click-interface/web/heartbeat'
        data = {'bvid': bvid, 'played_time': 30, 'csrf': self.csrf}
        try:
            res = requests.post(url, headers=self.headers, data=data)
            data = res.json()
            if data['code'] == 0:
                return True, "观看成功"
            return False, data.get('message', '观看失败')
        except Exception as e:
            return False, str(e)
            
    def live_sign(self):
        url = 'https://api.live.bilibili.com/xlive/web-ucenter/v1/sign/DoSign'
        try:
            res = requests.get(url, headers=self.headers)
            data = res.json()
            if data['code'] == 0:
                return True, data.get('data', {}).get('text', '直播签到成功')
            return False, data.get('message', '直播签到失败')
        except Exception as e:
            return False, str(e)

    def manga_sign(self):
        url = 'https://manga.bilibili.com/twirp/activity.v1.Activity/ClockIn'
        try:
            res = requests.post(url, headers=self.headers, data={'platform': 'ios'})
            data = res.json()
            if data['code'] == 0:
                return True, "漫画签到成功"
            return False, data.get('message', '漫画签到失败')
        except Exception as e:
            return False, str(e)

    # ===================== 以下为「银瓜子兑换硬币」相关 =====================
    # 说明：B站已于 2026 年下线「直播签到」与「网页端心跳」产银瓜子能力，
    # 复杂双端看直播心跳（移动端需 Sypder 加密）也不可靠。这里仅保留
    # 「银瓜子 → 硬币」兑换：当账户银瓜子 ≥700 时自动兑换 1 枚硬币；
    # 银瓜子不足则安全跳过。若日后 B站恢复银瓜子来源，兑换会自动生效。

    def get_silver_status(self):
        """查询银瓜子/硬币钱包状态。"""
        try:
            r = requests.get('https://api.live.bilibili.com/xlive/revenue/v1/wallet/getStatus',
                             headers=self.headers, timeout=15).json()
            if r.get('code') == 0:
                return r.get('data', {})
        except Exception as e:
            logger.error(f"查询银瓜子状态异常: {e}")
        return None

    def silver2coin(self):
        """把银瓜子兑换成硬币（700 银瓜子 = 1 硬币）。银瓜子不足/次数用尽时安全跳过。"""
        st = self.get_silver_status()
        if not st:
            return False, '获取银瓜子状态失败'
        silver = st.get('silver', 0)
        left = st.get('silver_2_coin_left', 0)
        if left <= 0:
            return True, f'今日兑换次数已用尽(剩{left}次)'
        if silver < 700:
            return True, f'银瓜子不足({silver}<700)，暂不兑换'
        try:
            r = requests.post(
                'https://api.live.bilibili.com/xlive/revenue/v1/wallet/silver2coin',
                data={'csrf': self.csrf or '', 'csrf_token': self.csrf or ''},
                headers=self.headers, timeout=15).json()
            if r.get('code') == 0:
                return True, f"兑换成功，获得{r.get('data', {}).get('coin')}枚硬币(余银瓜子{r.get('data', {}).get('silver')})"
            return False, r.get('message', '兑换失败')
        except Exception as e:
            return False, str(e)