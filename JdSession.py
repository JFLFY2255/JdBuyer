# -*- coding:utf-8 -*-
import json
import os
import sys
import pickle
import random
import time
import re
import requests

from lxml import etree
from log import logger

DEFAULT_TIMEOUT = 10
# DEFAULT_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/66.0.3359.181 Safari/537.36'
DEFAULT_USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36'

if getattr(sys, 'frozen', False):
    absPath = os.path.dirname(os.path.abspath(sys.executable))
elif __file__:
    absPath = os.path.dirname(os.path.abspath(__file__))


class Session(object):
    """
    京东买手
    """

    # 初始化
    def __init__(self):
        self.userAgent = DEFAULT_USER_AGENT
        self.headers = {'User-Agent': self.userAgent}
        self.timeout = DEFAULT_TIMEOUT
        self.itemDetails = dict()  # 商品信息：分类id、商家id
        self.username = 'jd'
        self.isLogin = False
        self.password = None
        self.sess = requests.session()
        # 短信登录相关参数
        self.s_token = None
        self.guid = None
        self.lsid = None
        self.phone = None
        
        # 创建调试目录
        self.debug_dir = os.path.join(absPath, 'debug_html')
        if not os.path.exists(self.debug_dir):
            os.makedirs(self.debug_dir)
            
        # 尝试加载cookies
        logger.info("初始化时尝试加载cookies...")
        cookies_loaded = False
        try:
            # 先尝试从配置文件加载cookie字符串
            try:
                from config import global_config
                cookie_str = global_config.get('account', 'cookie', raw=True)
                if cookie_str and len(cookie_str) > 10:
                    logger.info('尝试从配置文件加载Cookie...')
                    cookies_loaded, error_msg = self.updateCookies(cookie_str)
                    if cookies_loaded:
                        logger.info("配置文件中的cookie加载成功")
                    else:
                        logger.warning(f"配置文件中的cookie加载失败: {error_msg}")
            except Exception as e:
                logger.warning(f"从配置文件加载Cookie出错: {e}")
                
            # 如果配置文件加载失败，尝试从文件加载cookies
            if not cookies_loaded:
                logger.info("尝试从文件加载cookies...")
                cookies_loaded, error_msg = self.updateCookies()
                if cookies_loaded:
                    logger.info("文件中的cookies加载成功")
                else:
                    logger.info(f"文件中的cookies加载失败: {error_msg}")
                    
            # 无论从哪里加载的cookie，统一进行验证
            if cookies_loaded:
                if self.validateCookies():
                    logger.info("Cookie验证成功，已处于登录状态")
                    self.isLogin = True
                    # 如果是从配置文件加载的cookie，保存到文件以便下次使用
                    self.saveCookies()
                else:
                    logger.warning("Cookie已过期或无效，请手动删除")
                    self.isLogin = False
        except Exception as e:
            logger.error(f"初始化加载cookies失败: {e}")
        
        if not self.isLogin:
            logger.info("未能成功加载有效cookies，需要重新登录")

    # 保存HTML内容到文件
    def saveHtml(self, html_content, filename_prefix):
        """保存HTML内容到文件，用于调试
        :param html_content: HTML内容
        :param filename_prefix: 文件名前缀
        """
        filename = f"{filename_prefix}.html"
        filepath = os.path.join(self.debug_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"已保存HTML到文件: {filepath}")
        return filepath

    ############## 登录相关 #############
    # 保存 cookie
    def saveCookies(self):
        """保存Cookie到文件
        """
        cookiesFile = os.path.join(
            absPath, './cookies/{0}.cookies'.format(self.username))
        directory = os.path.dirname(cookiesFile)
        if not os.path.exists(directory):
            os.makedirs(directory)
        with open(cookiesFile, 'wb') as f:
            pickle.dump(self.sess.cookies, f)
        logger.info("已保存Cookie到文件")

    # 加载 cookie
    def _loadCookies(self, cookiesFile=None):
        """加载Cookie并验证是否有效
        :param cookiesFile: 指定cookie文件路径，为空则使用默认路径
        :return: 是否成功加载并验证Cookie True/False
        """
        try:
            # 如果没有指定cookie文件路径，则使用默认路径
            if not cookiesFile:
                cookiesFile = os.path.join(
                    absPath, './cookies/{0}.cookies'.format(self.username))
            
            # 检查Cookie文件是否存在
            if not os.path.exists(cookiesFile):
                return False, "Cookie文件不存在"
                
            # 检查文件大小
            if os.path.getsize(cookiesFile) == 0:
                return False, "Cookie文件为空"
                
            # 加载Cookie文件
            try:
                with open(cookiesFile, 'rb') as f:
                    local_cookies = pickle.load(f)
                self.sess.cookies.update(local_cookies)
            except (pickle.UnpicklingError, EOFError) as e:
                return False, f"Cookie文件格式错误: {e}"
            
            # 不再这里验证Cookie有效性，由调用者决定何时验证
            return True, None
        except Exception as e:
            return False, f"加载Cookie时出错: {e}"
    
    def updateCookies(self, cookie_str = None):
        """更新Cookies，可以从文件或字符串更新
        :param cookie_str: Cookie字符串，为None时从文件加载
        :return: (是否成功加载 True/False, 错误信息)
        """
        if cookie_str is None:
            # 从文件加载
            result, error_msg = self._loadCookies()
            return result, error_msg
        else:
            # 从字符串加载
            if len(cookie_str) < 10:
                return False, '配置文件中Cookie为空或过短，更新失败'
            
            # 将cookie字符串转换为字典
            cookie_dict = {}
            for item in cookie_str.split(';'):
                if '=' in item:
                    name, value = item.strip().split('=', 1)
                    cookie_dict[name] = value
            
            # 更新session的cookies
            self.sess.cookies.update(cookie_dict)
            return True, None

    # 验证 cookie
    def validateCookies(self):
        """
        通过访问用户订单列表页进行判断：若未登录，将会重定向到登陆页面。
        :return: cookies是否有效 True/False
        """
        url = 'https://order.jd.com/center/list.action'
        payload = {
            'rid': str(int(time.time() * 1000)),
        }
        headers = {
            'User-Agent': self.userAgent,
            'cookie': 'shshshfpa=df34eb0a-2763-b0f3-b511-f2c069527728-1746123670; shshshfpx=df34eb0a-2763-b0f3-b511-f2c069527728-1746123670; __jdv=94967808|www.popmart.com.cn|-|referral|-|1746123672002; __jdu=17461236720021421729451; user-key=4d8730bf-8f59-468e-8914-886a49fb743a; PCSYCityID=CN_110000_110100_0; areaId=18; ipLoc-djd=1-2901-55565-0.9504675402; ipLocation=%u5317%u4eac; umc_count=1; jsavif=1; jsavif=1; o2State=; TrackID=13VktL_GIhCvEeKRSK9MSW6aYHoMDx-pEnzcb6gkhk_4c_yoboAxyNZQDXzNETegqQce9lWRPMtNxFkKYfpBlTtG8Qu9w1o67eUw2M3RacT1DrRkQu_VMy51i9FGQpbZ-; thor=442A1477C204DB7E5DA32115556DA7388E98EBF52DE77AAE1DD0FB55873F6B5915D98B6A12BC1ABA65C034DEC0CF31550250B09F7689D91504AB506A1D0696EEF00594E44C899792EA8549CD04E7ED0C45537F4F880CA28DA34EA53394D727E06DCB9FAFBF870DC06AC644B9B814ECAEC33C47EE4312926FB6DED7417140A9F1FEDEE347BC5B2B997184198E77B76786; light_key=AASBKE7rOxgWQziEhC_QY6ya-ON8QiPjWlvS75DDHhhNctqzLSInsNA2muIOFuqu5286Tw4G; pinId=mceLUjN9-aN4LF7FK8COGg; pin=JFLFY2255; unick=n1c2yrutn99v5l; ceshi3.com=000; _tp=NObGvZOrUmvIDNZgnBTkJA%3D%3D; _pst=JFLFY2255; cn=27; 3AB9D23F7A4B3C9B=BS5AXYPPARGL5ELOL4CVTT2ZKW33FKUNJJVCMFOI5FYOZVKVWYXFMRCRAJRXEEUMZRWDYNL4ARN5OWB44JR77IGG7Q; flash=3_MftHLZPBhgtC8y3uEN1mJJUJ9kmLPCGIdb4UMO5VlMrCnJ9iKEEqUWo33Ce3EugYEY49zFEBXKhRWGpnZfiy_2kV_pOsXA7puAOR6cJRoTdvSlZnLbRkfaJVmMYBgLU4ccp3pkrHXWQiSwu5JKoiMPaMWyPd7cMPCwkQmxwDqsbF; 3AB9D23F7A4B3CSS=jdd03BS5AXYPPARGL5ELOL4CVTT2ZKW33FKUNJJVCMFOI5FYOZVKVWYXFMRCRAJRXEEUMZRWDYNL4ARN5OWB44JR77IGG7QAAAAMWT5NJK6AAAAAADM66W7ZBUDISOIX; _gia_d=1; token=2225647c427355c3439744597229896c,3,970239; __jda=181111935.17461236720021421729451.1746123672.1746412013.1746423518.7; __jdc=181111935; mt_xid=V2_52007VwMUV1pYUVgYTxpdBGQDF1FdXlFSGk0ZbARlAxQCXAsGRhcZTF4ZYlZGUEEIV18eVUlaA25XQAYICFFTHHkaXQZjHxNWQVlWSx9NEl4FbAIRYl9oUmoWQRlaBGcHFldaXFdTG0EeXQJnMxdTVF4%3D; shshshfpb=BApXSFJJTnPNAwkUa1SReRwfYm7fSlMbyBgRTMV9p9xJ1MiSADo62; __jdb=181111935.56.17461236720021421729451|7.1746423518; sdtoken=AAbEsBpEIOVjqTAKCQtvQu17_YJ0StieaDcBLBamrqqvx9ozkWiCevaEIqlKNTBHLqW7g3_6u796RhhDu-rvxbkBeVSbYFWzW_4MTCr84fokZkmRCKZWYxVkXA7YfV8RuQTuERp-whlit7f3KU91tG7hIIyS74bfmA',
        }
        try:
            logger.info("正在验证Cookie有效性...")
            resp = self.sess.get(url=url, params=payload, headers=headers, allow_redirects=False)
            
            if resp.status_code == 200:
                logger.info(f"Cookie有效，成功访问订单页面: {resp.url}")
                return True
            else:
                logger.info(f"Cookie无效，状态码: {resp.status_code}, 可能需要重新登录")
                if resp.status_code == 302:
                    logger.info(f"被重定向到: {resp.headers.get('Location', '未知页面')}")
                    
                    # 添加额外的尝试，访问京东首页检查登录状态
                    try:
                        logger.info("尝试访问京东首页检查登录状态...")
                        home_resp = self.sess.get('https://www.jd.com/')
                        if 'nickname' in home_resp.text:
                            logger.info("首页访问成功且包含用户信息")
                            return True
                    except Exception as e:
                        logger.error(f"访问首页时出错: {e}")
        except Exception as e:
            logger.error(f"验证Cookie时发生错误: {e}")
            return False

        # 连接失败时，创建新会话
        self.sess = requests.session()
        return False

    # 获取登录页
    def getLoginPage(self):
        url = "https://passport.jd.com/new/login.aspx"
        page = self.sess.get(url, headers=self.headers)
        return page

    # 获取登录二维码
    def getQRcode(self):
        url = 'https://qr.m.jd.com/show'
        payload = {
            'appid': 133,
            'size': 147,
            't': str(int(time.time() * 1000)),
        }
        headers = {
            'User-Agent': self.userAgent,
            'Referer': 'https://passport.jd.com/new/login.aspx',
        }
        resp = self.sess.get(url=url, headers=headers, params=payload)

        if not self.respStatus(resp):
            logger.error("获取二维码失败")
            return None

        return resp.content

    # 检查二维码状态
    def checkQRcodeStatus(self):
        """
        检查二维码状态
        :return: 扫描状态 200-已扫描，201-未扫描，202-过期, 203-确认登录中
        """
        url = 'https://qr.m.jd.com/check'
        payload = {
            'appid': '133',
            'callback': 'jQuery{}'.format(random.randint(1000000, 9999999)),
            'token': self.sess.cookies.get('wlfstk_smdl'),
            '_': str(int(time.time() * 1000)),
        }
        headers = {
            'User-Agent': self.userAgent,
            'Referer': 'https://passport.jd.com/new/login.aspx',
        }
        resp = self.sess.get(url=url, headers=headers, params=payload)

        if not self.respStatus(resp):
            return None, -1, "请求失败"

        respJson = self.parseJson(resp.text)
        
        # 提取状态码
        code = respJson.get('code', -1)
        msg = respJson.get('msg', '未知状态')
        
        # 根据状态码返回对应信息
        if code == 200:
            # 已完成扫码
            ticket = respJson.get('ticket')
            return ticket, code, msg
        else:
            # 其他状态
            return None, code, msg

    # 获取Ticket
    def getQRcodeTicket(self):
        """获取二维码票据
        :return: (ticket, status_code, status_msg)
                 ticket: 成功返回票据字符串，失败返回None
                 status_code: 状态码，200-已扫描，201-未扫描，202-过期，203-确认登录中，其他-未知状态
                 status_msg: 状态说明
        """
        url = 'https://qr.m.jd.com/check'
        payload = {
            'appid': '133',
            'callback': 'jQuery{}'.format(random.randint(1000000, 9999999)),
            'token': self.sess.cookies.get('wlfstk_smdl'),
            '_': str(int(time.time() * 1000)),
        }
        headers = {
            'User-Agent': self.userAgent,
            'Referer': 'https://passport.jd.com/new/login.aspx',
        }
        resp = self.sess.get(url=url, headers=headers, params=payload)

        if not self.respStatus(resp):
            return None, -1, "请求失败"

        respJson = self.parseJson(resp.text)
        
        # 提取状态码
        code = respJson.get('code', -1)
        msg = respJson.get('msg', '未知状态')
        
        # 根据状态码返回对应信息
        if code == 200:
            # 已完成扫码
            ticket = respJson.get('ticket')
            return ticket, code, msg
        else:
            # 其他状态
            return None, code, msg

    # 验证Ticket
    def validateQRcodeTicket(self, ticket):
        url = 'https://passport.jd.com/uc/qrCodeTicketValidation'
        headers = {
            'User-Agent': self.userAgent,
            'Referer': 'https://passport.jd.com/uc/login?ltype=logout',
        }
        resp = self.sess.get(url=url, headers=headers, params={'t': ticket})

        if not self.respStatus(resp):
            logger.error("验证二维码票据失败")
            return False

        respJson = json.loads(resp.text)
        if respJson['returnCode'] == 0:
            logger.info("二维码登录成功")
            return True
        else:
            logger.error(f"二维码登录失败: {respJson.get('message')}")
            return False
            
    ############## 短信登录相关 #############
    def getLoginPageForSMS(self):
        """获取短信登录页所需的token等信息
        :return: 是否成功获取信息 True/False
        """
        # 使用PC版登录页面代替移动版，可能更稳定
        url = "https://passport.jd.com/new/login.aspx"
        headers = {
            'User-Agent': self.userAgent,
            'Connection': 'Keep-Alive',
            'Referer': 'https://www.jd.com/'
        }
        
        try:
            logger.info("正在获取登录页...")
            resp = self.sess.get(url=url, headers=headers)
            if not self.respStatus(resp):
                logger.error("获取登录页失败")
                return False
                
            # 保存页面用于调试
            self.saveHtml(resp.text, "login_page_sms")
            
            # 检查是否已有必要的cookies
            if self.sess.cookies.get('guid') and self.sess.cookies.get('lsid'):
                self.guid = self.sess.cookies.get('guid')
                self.lsid = self.sess.cookies.get('lsid')
                logger.info(f"成功获取登录所需cookies: guid={self.guid}, lsid={self.lsid}")
                return True
                
            # 如果没有通过cookies获取到token，尝试其他方式
            logger.info("尝试直接初始化登录参数...")
            self.guid = ''.join([str(random.randint(0, 9)) for _ in range(16)])
            self.lsid = '{}-{}-{}-{}'.format(
                ''.join([hex(random.randint(0, 15))[2:] for _ in range(8)]),
                ''.join([hex(random.randint(0, 15))[2:] for _ in range(4)]),
                ''.join([hex(random.randint(0, 15))[2:] for _ in range(4)]),
                ''.join([hex(random.randint(0, 15))[2:] for _ in range(12)])
            )
            logger.info(f"成功初始化登录参数: guid={self.guid}, lsid={self.lsid}")
            return True
        
        except Exception as e:
            logger.error(f"获取短信登录页时出错: {e}")
            return False
            
    def getSMSCode(self, phone):
        """获取短信验证码
        :param phone: 手机号
        :return: 是否成功发送短信 True/False
        """
        self.phone = phone
        
        # 确保已初始化必要的参数
        if not hasattr(self, 'guid') or not self.guid:
            self.guid = ''.join([str(random.randint(0, 9)) for _ in range(16)])
            logger.info(f"自动生成guid: {self.guid}")
            
        # 请求发送验证码
        url = "https://passport.jd.com/uc/login/sendMCode"
        data = {
            'phone': phone,
            'guid': self.guid,
            'appid': 133,
            'returnurl': 'https://www.jd.com/',
            'serviceCode': 'jd',
            'smsType': 'sms'
        }
        headers = {
            'User-Agent': self.userAgent,
            'Referer': 'https://passport.jd.com/new/login.aspx',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://passport.jd.com'
        }
        
        try:
            logger.info(f"正在向手机 {phone} 发送验证码...")
            resp = self.sess.post(url=url, headers=headers, data=data)
            # 保存响应内容用于调试
            self.saveHtml(resp.text, f"sms_code_response_{phone}")
            
            if not self.respStatus(resp):
                logger.error("发送短信验证码请求失败")
                return False
                
            # 尝试解析JSON响应
            try:
                resp_json = json.loads(resp.text)
                if resp_json.get('success', False) or resp_json.get('code', -1) == 200:
                    logger.info("短信验证码已发送，请注意查收")
                    return True
                else:
                    logger.error(f"发送短信验证码失败: {resp_json.get('message', resp_json.get('msg', '未知错误'))}")
                    return False
            except:
                # 如果无法解析JSON，检查是否包含成功标识
                if "发送成功" in resp.text or "已发送" in resp.text:
                    logger.info("短信验证码已发送，请注意查收")
                    return True
                    
                logger.error(f"无法解析短信验证码响应: {resp.text[:100]}...")
                return False
                
        except Exception as e:
            logger.error(f"发送短信验证码时出错: {e}")
            return False
    
    def verifySMSCode(self, sms_code):
        """验证短信验证码
        :param sms_code: 收到的短信验证码
        :return: 是否成功登录 True/False
        """
        if not self.phone:
            logger.error("手机号未设置，无法验证短信")
            return False
            
        # PC版登录接口
        url = "https://passport.jd.com/uc/loginService"
        data = {
            'uuid': self.guid if hasattr(self, 'guid') else '',
            'phone': self.phone,
            'authcode': sms_code,
            'authCodeMethod': 4,  # 4表示短信验证码登录
            'loginType': 3,
            'returnurl': 'https://www.jd.com/',
            'isVirtualKey': '1',
            'isVerify': 'true',
            'isOauth': 'false',
            'isResetName': 'false',
            'slideAppId': '',
            'slideToken': '',
        }
        headers = {
            'User-Agent': self.userAgent,
            'Referer': 'https://passport.jd.com/new/login.aspx',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://passport.jd.com'
        }
        
        try:
            logger.info(f"正在验证短信验证码...")
            resp = self.sess.post(url=url, headers=headers, data=data)
            
            # 保存响应内容用于调试
            self.saveHtml(resp.text, "verify_sms_result")
            
            if not self.respStatus(resp):
                logger.error("验证短信验证码请求失败")
                return False
            
            # 首先尝试解析JSON响应
            try:
                resp_json = json.loads(resp.text)
                if resp_json.get('success', False) or "成功" in resp.text:
                    logger.info("短信验证码登录成功")
                    self.isLogin = True
                    self.saveCookies()
                    return True
                else:
                    logger.error(f"短信验证码登录失败: {resp_json.get('message', resp_json.get('msg', '未知错误'))}")
                    return False
            except:
                pass
                
            # 检查响应内容中是否包含成功标识
            if "success" in resp.text.lower() or "成功" in resp.text:
                logger.info("短信验证码登录成功")
                self.isLogin = True
                self.saveCookies()
                return True
            else:
                logger.error("短信验证码登录失败，检查验证码是否正确")
                return False
                
        except Exception as e:
            logger.error(f"验证短信验证码时出错: {e}")
            return False

    ############## 商品方法 #############
    def fetchItemDetail(self, skuId):
        """ 解析商品信息
        :param skuId
        """
        # 直接访问商品页面获取信息
        url = 'https://item.jd.com/{}.html'.format(skuId)
        logger.info(f"正在获取商品信息: {url}")
        
        # 使用提供的完整请求头信息
        headers = {
            'User-Agent': self.userAgent,
            'cookie': 'shshshfpa=df34eb0a-2763-b0f3-b511-f2c069527728-1746123670; shshshfpx=df34eb0a-2763-b0f3-b511-f2c069527728-1746123670; __jdv=94967808|www.popmart.com.cn|-|referral|-|1746123672002; __jdu=17461236720021421729451; user-key=4d8730bf-8f59-468e-8914-886a49fb743a; PCSYCityID=CN_110000_110100_0; areaId=18; ipLoc-djd=1-2901-55565-0.9504675402; ipLocation=%u5317%u4eac; umc_count=1; jsavif=1; jsavif=1; o2State=; TrackID=13VktL_GIhCvEeKRSK9MSW6aYHoMDx-pEnzcb6gkhk_4c_yoboAxyNZQDXzNETegqQce9lWRPMtNxFkKYfpBlTtG8Qu9w1o67eUw2M3RacT1DrRkQu_VMy51i9FGQpbZ-; thor=442A1477C204DB7E5DA32115556DA7388E98EBF52DE77AAE1DD0FB55873F6B5915D98B6A12BC1ABA65C034DEC0CF31550250B09F7689D91504AB506A1D0696EEF00594E44C899792EA8549CD04E7ED0C45537F4F880CA28DA34EA53394D727E06DCB9FAFBF870DC06AC644B9B814ECAEC33C47EE4312926FB6DED7417140A9F1FEDEE347BC5B2B997184198E77B76786; light_key=AASBKE7rOxgWQziEhC_QY6ya-ON8QiPjWlvS75DDHhhNctqzLSInsNA2muIOFuqu5286Tw4G; pinId=mceLUjN9-aN4LF7FK8COGg; pin=JFLFY2255; unick=n1c2yrutn99v5l; ceshi3.com=000; _tp=NObGvZOrUmvIDNZgnBTkJA%3D%3D; _pst=JFLFY2255; cn=27; 3AB9D23F7A4B3C9B=BS5AXYPPARGL5ELOL4CVTT2ZKW33FKUNJJVCMFOI5FYOZVKVWYXFMRCRAJRXEEUMZRWDYNL4ARN5OWB44JR77IGG7Q; flash=3_MftHLZPBhgtC8y3uEN1mJJUJ9kmLPCGIdb4UMO5VlMrCnJ9iKEEqUWo33Ce3EugYEY49zFEBXKhRWGpnZfiy_2kV_pOsXA7puAOR6cJRoTdvSlZnLbRkfaJVmMYBgLU4ccp3pkrHXWQiSwu5JKoiMPaMWyPd7cMPCwkQmxwDqsbF; 3AB9D23F7A4B3CSS=jdd03BS5AXYPPARGL5ELOL4CVTT2ZKW33FKUNJJVCMFOI5FYOZVKVWYXFMRCRAJRXEEUMZRWDYNL4ARN5OWB44JR77IGG7QAAAAMWT5NJK6AAAAAADM66W7ZBUDISOIX; _gia_d=1; token=2225647c427355c3439744597229896c,3,970239; __jda=181111935.17461236720021421729451.1746123672.1746412013.1746423518.7; __jdc=181111935; mt_xid=V2_52007VwMUV1pYUVgYTxpdBGQDF1FdXlFSGk0ZbARlAxQCXAsGRhcZTF4ZYlZGUEEIV18eVUlaA25XQAYICFFTHHkaXQZjHxNWQVlWSx9NEl4FbAIRYl9oUmoWQRlaBGcHFldaXFdTG0EeXQJnMxdTVF4%3D; shshshfpb=BApXSFJJTnPNAwkUa1SReRwfYm7fSlMbyBgRTMV9p9xJ1MiSADo62; __jdb=181111935.56.17461236720021421729451|7.1746423518; sdtoken=AAbEsBpEIOVjqTAKCQtvQu17_YJ0StieaDcBLBamrqqvx9ozkWiCevaEIqlKNTBHLqW7g3_6u796RhhDu-rvxbkBeVSbYFWzW_4MTCr84fokZkmRCKZWYxVkXA7YfV8RuQTuERp-whlit7f3KU91tG7hIIyS74bfmA',
        }

        logger.info(f"使用 User-Agent: {headers.get('user-agent', self.userAgent)}") # 获取实际使用的UA

        try:
            logger.info(f"开始请求商品页面: {url}")
            resp = self.sess.get(url=url, headers=headers, timeout=self.timeout)

            # 记录响应状态
            logger.info(f"商品页面响应状态码: {resp.status_code}")

            # 检查是否发生了重定向
            if url != resp.url:
                logger.warning(f"请求被重定向: {url} -> {resp.url}")
            
            if not self.respStatus(resp):
                logger.error(f"获取商品页面失败: HTTP状态码 {resp.status_code}")
                detail = dict(venderId='0')
                self.itemDetails[skuId] = detail
                return

            # 保存HTML内容用于调试
            debug_file = self.saveHtml(resp.text, f"item_detail_{skuId}")

            # 检查响应内容
            if len(resp.text) < 1000:
                logger.warning(f"商品页面内容过短，可能被重定向或限制: {len(resp.text)} 字符")
                if "location.href" in resp.text:
                    logger.warning("检测到页面包含重定向脚本")

            html = etree.HTML(resp.text)

            # 提取店铺ID
            shop_id = '0'
            shop_info = html.xpath('//div[contains(@class, "shopName")]/div[@class="name"]/a/@data-shopid')
            if shop_info:
                shop_id = shop_info[0]
                logger.info(f"成功提取到店铺ID: {shop_id}")
            else:
                logger.warning("未能提取到店铺ID，使用默认值'0'")
                
            detail = dict(venderId=shop_id)
            
            # 检查是否是预售商品
            yushou_info = html.xpath('//div[contains(@class, "summary-price-wrap")]//span[contains(text(), "预售")]/text()')
            if yushou_info:
                detail['yushouUrl'] = url
                logger.info("检测到预售商品")
                
            # 检查是否是秒杀商品
            miaosha_info = html.xpath('//div[contains(@class, "summary-price-wrap")]//span[contains(text(), "秒杀")]/text()')
            if miaosha_info:
                # 获取秒杀时间，实际时间需要从页面上解析，这里只是占位
                detail['startTime'] = int(time.time()) * 1000
                detail['endTime'] = int(time.time() + 3600) * 1000  # 默认一小时
                logger.info("检测到秒杀商品")
                
            logger.info(f"商品信息获取完成: {detail}")
            self.itemDetails[skuId] = detail
            
        except Exception as e:
            # 出错时设置默认值
            detail = dict(venderId='0')
            self.itemDetails[skuId] = detail
            logger.error(f"获取商品信息出错: {e}")

    ############## 库存方法 #############
    def getItemStock(self, skuId, skuNum, areaId):
        """获取单个商品库存状态
        :param skuId: 商品id
        :param num: 商品数量
        :param areadId: 地区id
        :return: 商品是否有货 True/False
        """
        # 直接访问商品页面判断库存
        url = 'https://item.jd.com/{}.html'.format(skuId)
        headers = {
            'User-Agent': self.userAgent,
            'Referer': 'https://www.jd.com/',
        }
        try:
            resp = self.sess.get(url=url, headers=headers)
            if not self.respStatus(resp):
                return False
            
            # 保存HTML内容用于调试
            self.saveHtml(resp.text, f"item_stock_{skuId}")
            
            html = etree.HTML(resp.text)
            # 检查是否有"无货"字样
            stock_status = html.xpath('//div[@class="store-prompt"]/text()')
            if stock_status and '无货' in stock_status[0]:
                return False
            # 检查是否有"现货"字样或加入购物车按钮
            has_stock = html.xpath('//div[@class="activity-message"]/span[contains(text(),"现货")]/text()') or \
                       html.xpath('//a[@id="InitCartUrl"]')
            return len(has_stock) > 0
        except Exception as e:
            logger.error(f"获取商品库存状态出错: {e}")
            return False

    ############## 购物车相关 #############

    def uncheckCartAll(self):
        """ 取消所有选中商品
        return 购物车信息
        """
        url = 'https://api.m.jd.com/api'

        headers = {
            'User-Agent': self.userAgent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'origin': 'https://cart.jd.com',
            'referer': 'https://cart.jd.com'
        }

        data = {
            'functionId': 'pcCart_jc_cartUnCheckAll',
            'appid': 'JDC_mall_cart',
            'body': '{"serInfo":{"area":"","user-key":""}}',
            'loginType': 3
        }

        resp = self.sess.post(url=url, headers=headers, data=data)

        # return self.respStatus(resp) and resp.json()['success']
        return resp

    def addCartSku(self, skuId, skuNum):
        """ 加入购入车
        skuId 商品sku
        skuNum 购买数量
        retrun 是否成功
        """
        url = 'https://api.m.jd.com/api'

        headers = {
            'User-Agent': self.userAgent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'origin': 'https://cart.jd.com',
            'referer': 'https://cart.jd.com'
        }

        data = {
            'functionId': 'pcCart_jc_cartAdd',
            'appid': 'JDC_mall_cart',
            'body': '{\"operations\":[{\"carttype\":1,\"TheSkus\":[{\"Id\":\"' + skuId + '\",\"num\":' + str(skuNum) + '}]}]}',
            'loginType': 3
        }

        resp = self.sess.post(url=url, headers=headers, data=data)

        return self.respStatus(resp) and resp.json()['success']

    def changeCartSkuCount(self, skuId, skuUid, skuNum, areaId):
        """ 修改购物车商品数量
        skuId 商品sku
        skuUid 商品用户关系
        skuNum 购买数量
        retrun 是否成功
        """
        url = 'https://api.m.jd.com/api'

        headers = {
            'User-Agent': self.userAgent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'origin': 'https://cart.jd.com',
            'referer': 'https://cart.jd.com'
        }

        body = '{\"operations\":[{\"TheSkus\":[{\"Id\":\"'+skuId+'\",\"num\":'+str(
            skuNum)+',\"skuUuid\":\"'+skuUid+'\",\"useUuid\":false}]}],\"serInfo\":{\"area\":\"'+areaId+'\"}}'
        data = {
            'functionId': 'pcCart_jc_changeSkuNum',
            'appid': 'JDC_mall_cart',
            'body': body,
            'loginType': 3
        }

        resp = self.sess.post(url=url, headers=headers, data=data)

        return self.respStatus(resp) and resp.json()['success']

    def prepareCart(self, skuId, skuNum, areaId):
        """ 下单前准备购物车
        1 取消全部勾选（返回购物车信息）
        2 已在购物车则修改商品数量
        3 不在购物车则加入购物车
        skuId 商品sku
        skuNum 商品数量
        return True/False
        """
        resp = self.uncheckCartAll()
        respObj = resp.json()
        if not self.respStatus(resp) or not respObj['success']:
            raise Exception('购物车取消勾选失败')

        # 检查商品是否已在购物车
        cartInfo = respObj['resultData']['cartInfo']
        if not cartInfo:
            # 购物车为空 直接加入
            return self.addCartSku(skuId, skuNum)

        venders = cartInfo['vendors']

        for vender in venders:
            # if str(vender['vendorId']) != self.itemDetails[skuId]['vender_id']:
            #     continue
            items = vender['sorted']
            for item in items:
                if str(item['item']['Id']) == skuId:
                    # 在购物车中 修改数量
                    return self.changeCartSkuCount(skuId, item['item']['skuUuid'], skuNum, areaId)
        # 不在购物车中
        return self.addCartSku(skuId, skuNum)

    ############## 订单相关 #############

    def trySubmitOrder(self, skuId, skuNum, areaId, retry=3, interval=5):
        """提交订单
        :return: 订单提交结果 True/False
        """
        itemDetail = self.itemDetails[skuId]
        isYushou = False
        if 'yushouUrl' in itemDetail:
            self.getPreSallCheckoutPage(skuId, skuNum)
            isYushou = True
        else:
            self.prepareCart(skuId, skuNum, areaId)
            self.getCheckoutPage()

        for i in range(1, retry + 1):
            ret, msg = self.submitOrder(isYushou)
            if ret:
                return True
            else:
                time.sleep(interval)
        return False

    def submitOrderWitchTry(self, retry=3, interval=4):
        """提交订单，并且带有重试功能
        :param retry: 重试次数
        :param interval: 重试间隔
        :return: 订单提交结果 True/False
        """
        for i in range(1, retry + 1):
            self.getCheckoutPage()
            sumbmitSuccess, msg = self.submitOrder()
            if sumbmitSuccess:
                return True
            else:
                if i < retry:
                    time.sleep(interval)
        return False

    def getCheckoutPage(self):
        """获取订单结算页面信息
        :return: 结算信息 dict
        """
        url = 'http://trade.jd.com/shopping/order/getOrderInfo.action'
        # url = 'https://cart.jd.com/gotoOrder.action'
        payload = {
            'rid': str(int(time.time() * 1000)),
        }
        headers = {
            'User-Agent': self.userAgent,
            'Referer': 'https://cart.jd.com/cart',
        }
        try:
            resp = self.sess.get(url=url, params=payload, headers=headers)
            if not self.respStatus(resp):
                return
            
            # 保存HTML内容用于调试
            self.saveHtml(resp.text, "checkout_page")

            html = etree.HTML(resp.text)
            self.eid = html.xpath("//input[@id='eid']/@value")
            self.fp = html.xpath("//input[@id='fp']/@value")
            self.risk_control = html.xpath("//input[@id='riskControl']/@value")
            self.track_id = html.xpath("//input[@id='TrackID']/@value")

            order_detail = {
                # remove '寄送至： ' from the begin
                'address': html.xpath("//span[@id='sendAddr']")[0].text[5:],
                # remove '收件人:' from the begin
                'receiver':  html.xpath("//span[@id='sendMobile']")[0].text[4:],
                # remove '￥' from the begin
                'total_price':  html.xpath("//span[@id='sumPayPriceId']")[0].text[1:],
                'items': []
            }
            return order_detail
        except Exception as e:
            logger.error(f"获取结算页面出错: {e}")
            return

    def getPreSallCheckoutPage(self, skuId, skuNum=1):
        """获取预售商品结算页面信息
        :return: 结算信息 dict
        """
        url = 'https://item.jd.com/{}.html'.format(skuId)
        headers = {
            'User-Agent': self.userAgent,
            'Referer': 'https://www.jd.com/',
        }
        try:
            resp = self.sess.get(url=url, headers=headers)
            if not self.respStatus(resp):
                return
            
            # 保存HTML内容用于调试
            self.saveHtml(resp.text, f"presale_checkout_{skuId}")

            html = etree.HTML(resp.text)
            # 提取商品页面信息
            self.eid = self.eid or ''
            self.fp = self.fp or ''
            self.risk_control = self.risk_control or ''
            self.track_id = self.track_id or ''
            
            # 从商品页面获取地址信息
            order_detail = {}
            
            # 如果商品页面中无法获取收货信息，使用用户账号的默认信息
            try:
                order_detail['address'] = html.xpath("//div[@id='J-deliver']//div[@class='ui-area-text']")[0].text.strip()
                order_detail['receiver'] = self.sess.cookies.get('pin', '')
            except:
                order_detail['address'] = '默认地址'
                order_detail['receiver'] = '默认收件人'
                
            return order_detail
        except Exception as e:
            logger.error(f"获取预售商品结算页面出错: {e}")
            return

    def submitOrder(self, isYushou=False):
        """提交订单
        :return: True/False 订单提交结果
        """
        url = 'https://trade.jd.com/shopping/order/submitOrder.action'
        # js function of submit order is included in https://trade.jd.com/shopping/misc/js/order.js?r=2018070403091

        data = {
            'overseaPurchaseCookies': '',
            'vendorRemarks': '[]',
            'submitOrderParam.sopNotPutInvoice': 'false',
            'submitOrderParam.trackID': 'TestTrackId',
            'submitOrderParam.ignorePriceChange': '0',
            'submitOrderParam.btSupport': '0',
            'riskControl': self.risk_control,
            'submitOrderParam.isBestCoupon': 1,
            'submitOrderParam.jxj': 1,
            'submitOrderParam.trackId': self.track_id,
            'submitOrderParam.eid': self.eid,
            'submitOrderParam.fp': self.fp,
            'submitOrderParam.needCheck': 1,
        }

        if isYushou:
            data['submitOrderParam.needCheck'] = 1
            data['preSalePaymentTypeInOptional'] = 2
            data['submitOrderParam.payType4YuShou'] = 2

        # add payment password when necessary
        paymentPwd = self.password
        if paymentPwd:
            data['submitOrderParam.payPassword'] = ''.join(
                ['u3' + x for x in paymentPwd])

        headers = {
            'User-Agent': self.userAgent,
            'Host': 'trade.jd.com',
            'Referer': 'http://trade.jd.com/shopping/order/getOrderInfo.action',
        }

        try:
            resp = self.sess.post(url=url, data=data, headers=headers)
            respJson = json.loads(resp.text)

            if respJson.get('success'):
                orderId = respJson.get('orderId')
                return True, orderId
            else:
                message, result_code = respJson.get(
                    'message'), respJson.get('resultCode')
                if result_code == 0:
                    self._saveInvoice()
                    message = message + '(下单商品可能为第三方商品，将切换为普通发票进行尝试)'
                elif result_code == 60077:
                    message = message + '(可能是购物车为空 或 未勾选购物车中商品)'
                elif result_code == 60123:
                    message = message + '(需要在config.ini文件中配置支付密码)'
                return False, message
        except Exception as e:
            return False, e

    def _saveInvoice(self):
        """下单第三方商品时如果未设置发票，将从电子发票切换为普通发票
        http://jos.jd.com/api/complexTemplate.htm?webPamer=invoice&groupName=%E5%BC%80%E6%99%AE%E5%8B%92%E5%85%A5%E9%A9%BB%E6%A8%A1%E5%BC%8FAPI&id=566&restName=jd.kepler.trade.submit&isMulti=true
        :return:
        """
        url = 'https://trade.jd.com/shopping/dynamic/invoice/saveInvoice.action'
        data = {
            "invoiceParam.selectedInvoiceType": 1,
            "invoiceParam.companyName": "个人",
            "invoiceParam.invoicePutType": 0,
            "invoiceParam.selectInvoiceTitle": 4,
            "invoiceParam.selectBookInvoiceContent": "",
            "invoiceParam.selectNormalInvoiceContent": 1,
            "invoiceParam.vatCompanyName": "",
            "invoiceParam.code": "",
            "invoiceParam.regAddr": "",
            "invoiceParam.regPhone": "",
            "invoiceParam.regBank": "",
            "invoiceParam.regBankAccount": "",
            "invoiceParam.hasCommon": "true",
            "invoiceParam.hasBook": "false",
            "invoiceParam.consigneeName": "",
            "invoiceParam.consigneePhone": "",
            "invoiceParam.consigneeAddress": "",
            "invoiceParam.consigneeProvince": "请选择：",
            "invoiceParam.consigneeProvinceId": "NaN",
            "invoiceParam.consigneeCity": "请选择",
            "invoiceParam.consigneeCityId": "NaN",
            "invoiceParam.consigneeCounty": "请选择",
            "invoiceParam.consigneeCountyId": "NaN",
            "invoiceParam.consigneeTown": "请选择",
            "invoiceParam.consigneeTownId": 0,
            "invoiceParam.sendSeparate": "false",
            "invoiceParam.usualInvoiceId": "",
            "invoiceParam.selectElectroTitle": 4,
            "invoiceParam.electroCompanyName": "undefined",
            "invoiceParam.electroInvoiceEmail": "",
            "invoiceParam.electroInvoicePhone": "",
            "invokeInvoiceBasicService": "true",
            "invoice_ceshi1": "",
            "invoiceParam.showInvoiceSeparate": "false",
            "invoiceParam.invoiceSeparateSwitch": 1,
            "invoiceParam.invoiceCode": "",
            "invoiceParam.saveInvoiceFlag": 1
        }
        headers = {
            'User-Agent': self.userAgent,
            'Referer': 'https://trade.jd.com/shopping/dynamic/invoice/saveInvoice.action',
        }
        self.sess.post(url=url, data=data, headers=headers)

    def parseJson(self, s):
        begin = s.find('{')
        end = s.rfind('}') + 1
        return json.loads(s[begin:end])

    def respStatus(self, resp):
        if resp.status_code != requests.codes.OK:
            return False
        return True
