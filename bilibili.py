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
        self.liked_bvids = []   # 本次运行中点过赞(bvid)的视频，供「清理点赞列表」使用

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
                # 投币时若附加点赞，记录该视频，供后续「清理点赞列表」取消赞
                if select_like:
                    self.liked_bvids.append(bvid)
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

    # ===================== 「银瓜子」相关 =====================
    # 说明：B站自 2026 年起大幅废弃银瓜子来源。实测：
    #   - 直播签到(DoSign) 已下线
    #   - 每日礼包(receive_daily_bag) 返回空 bag_list（不再发放银瓜子）
    #   - 移动端宝箱(freeSilver*) 需 sign 签名且多数 404
    # 因此下面保留「领取礼包 + 兑换硬币」的标准实现，B站恢复发放时会自动生效；
    # 当前若无可领银瓜子，则安全跳过，不影响其它任务。

    def get_daily_bag(self):
        """领取每日银瓜子礼包（最简单来源）。礼包为空时安全跳过。"""
        try:
            r = requests.get(
                'https://api.live.bilibili.com/gift/v2/live/receive_daily_bag',
                headers=self.headers, timeout=15).json()
            if r.get('code') == 0:
                bag = r.get('data', {})
                if bag.get('bag_list'):
                    return True, f"领取每日礼包成功：{bag.get('bag_list')}"
                return True, "每日礼包为空（B站当前未发放银瓜子，已安全跳过）"
            return False, r.get('message', '领取每日礼包失败')
        except Exception as e:
            return False, str(e)

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

    # ===================== 「清理最近点赞列表」 =====================
    # 本次运行中对视频投币(select_like=1)会同时点赞，这些点赞会被记入「最近点赞」。
    # 这里统一取消这些点赞，清理痕迹。投币本身不可逆，无法撤销。

    def unlike_video(self, bvid):
        if not self.csrf: return False, "Bili_jct(csrf) 未找到"
        try:
            r = requests.post(
                'https://api.bilibili.com/x/web-interface/archive/like',
                data={'bvid': bvid, 'like': 2, 'csrf': self.csrf},
                headers=self.headers, timeout=15).json()
            if r.get('code') == 0:
                return True, "取消点赞成功"
            # 65004 取消点赞失败（本就没赞）/重复操作，视为已清理
            if r.get('code') in (65004,):
                return True, "无需取消(已无赞)"
            return False, r.get('message', '取消点赞失败')
        except Exception as e:
            return False, str(e)

    def cleanup_liked_videos(self):
        if not self.liked_bvids:
            return True, "本次未产生点赞记录，跳过"
        ok, fail = 0, 0
        for bvid in self.liked_bvids:
            success, msg = self.unlike_video(bvid)
            if success:
                ok += 1
                logger.info(f"已取消点赞 {bvid}。")
            else:
                fail += 1
                logger.warning(f"取消点赞 {bvid} 失败: {msg}")
        if fail == 0:
            return True, f"已清理 {ok} 条点赞记录"
        return False, f"清理部分失败：成功{ok}/失败{fail}"
