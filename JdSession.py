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
        
        # 订单提交相关参数，确保初始化
        self.eid = ''
        self.fp = ''
        self.risk_control = ''
        self.track_id = ''
        
        # 反爬参数
        self.h5st_params = {}
        self.t_params = {}
        
        # 尝试加载反爬参数
        self._load_anticrawl_params()
        
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
                    logger.info(f"配置文件中cookie长度为: {len(cookie_str)}")
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
            
            # 检查是否包含京东关键cookie
            contains_pt_key = 'pt_key=' in cookie_str
            contains_pt_pin = 'pt_pin=' in cookie_str
            
            if not (contains_pt_key and contains_pt_pin):
                logger.warning("配置文件中的cookie字符串缺少pt_key或pt_pin，可能影响登录")
            
            # 创建RequestsCookieJar并正确设置域名
            jar = requests.cookies.RequestsCookieJar()
            
            # 解析cookie字符串并添加到jar，设置正确的域名
            for cookie_item in cookie_str.split(';'):
                if '=' in cookie_item:
                    name, value = cookie_item.strip().split('=', 1)
                    # 为所有cookie设置.jd.com域名
                    jar.set(name, value, domain='.jd.com', path='/')
            
            # 将jar替换会话中的cookies
            self.sess.cookies = jar
            
            logger.info(f"从字符串更新cookies完成，session包含 {len(self.sess.cookies)} 个cookies")
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
        try:
            logger.info("正在验证Cookie有效性...")
            
            # 添加User-Agent头
            headers = {
                'User-Agent': self.userAgent,
                'Referer': 'https://www.jd.com/',
            }
            
            # 使用完整的headers
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
                        home_resp = self.sess.get('https://www.jd.com/', headers=headers)
                        if 'nickname' in home_resp.text:
                            logger.info("首页访问成功且包含用户信息，Cookie部分有效")
                            return True
                        else:
                            logger.warning("首页访问成功但未找到用户信息，Cookie可能已失效")
                            return False
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
        """获取商品信息
        :param skuId: 商品id
        """
        # 直接访问商品页面获取信息
        url = 'https://item.jd.com/{}.html'.format(skuId)
        logger.info(f"正在获取商品信息: {url}")
        
        # 使用完整的headers
        headers = {
            'User-Agent': self.userAgent,
            'Referer': 'https://www.jd.com/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Connection': 'keep-alive',
        }

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
        :param skuNum: 商品数量
        :param areaId: 地区id
        :return: 商品是否有货 True/False
        """
        # 直接访问商品页面判断库存
        url = 'https://item.jd.com/{}.html'.format(skuId)
        headers = {
            'User-Agent': self.userAgent,
            'Referer': 'https://www.jd.com/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Connection': 'keep-alive',
        }
        try:
            resp = self.sess.get(url=url, headers=headers)
            if not self.respStatus(resp):
                logger.error(f"获取商品库存状态失败: HTTP状态码 {resp.status_code}")
                return False
            
            # 保存HTML内容用于调试
            self.saveHtml(resp.text, f"item_stock_{skuId}")
            
            html = etree.HTML(resp.text)
            # 检查是否有"无货"字样
            stock_status = html.xpath('//div[@class="store-prompt"]/text()')
            if stock_status and '无货' in stock_status[0]:
                logger.info(f"商品 {skuId} 当前无货")
                return False
            # 检查是否有"现货"字样或加入购物车按钮
            has_stock = html.xpath('//div[@class="activity-message"]/span[contains(text(),"现货")]/text()') or \
                       html.xpath('//a[@id="InitCartUrl"]')
            stock_result = len(has_stock) > 0
            logger.info(f"商品 {skuId} 库存状态: {'有货' if stock_result else '无货'}")
            return stock_result
        except Exception as e:
            logger.error(f"获取商品库存状态出错: {e}")
            return False

    ############## 购物车相关 #############

    def uncheckCartAll(self, areaId):
        """ 取消所有选中商品
        
        **开发记录**：取消勾选购物车需要提供正确的h5st信息，t、user-key、area-id等字段都要一致，并且IP地址绑定国家
        
        return 购物车信息
        """
        url = 'https://api.m.jd.com/api'

        # 根据curl指令设置正确的headers
        headers = {
            'user-agent': self.userAgent,
            'origin': 'https://cart.jd.com',
            'referer': 'https://cart.jd.com/',
            'x-referer-page': 'https://cart.jd.com/cart_index',
            'x-rp-client': 'h5_1.0.0'
        }

        # 获取区域信息，如果没有则使用空字符串
        user_key = ""
        h5st = ""
        
        # 从配置的反爬参数中获取
        function_id = 'pcCart_jc_cartUnCheckAll'
        t = self.t_params.get(function_id.lower(), str(int(time.time() * 1000)))
        h5st = self.h5st_params.get(function_id.lower(), "")
        
        # 可以尝试从cookie中获取user-key
        if hasattr(self.sess, 'cookies') and self.sess.cookies.get('user-key'):
            user_key = self.sess.cookies.get('user-key')

        # 构建完整的body
        body = {
            "serInfo": {
                "area": areaId,
                "user-key": user_key
            }
        }
        
        # 转换为JSON字符串
        body_json_string = json.dumps(body, separators=(',', ':'))

        # 构建请求参数
        request_params = {
            'functionId': function_id,
            'appid': 'JDC_mall_cart',  # 根据curl，使用JDC_mall_cart而不是item-v3
            'loginType': 3,
            'client': 'pc',
            'clientVersion': '1.0.0',
            'body': body_json_string,
            'h5st': h5st,
            't': t,
        }

        logger.info("开始取消勾选购物车中所有商品")
        
        # 记录请求信息用于调试
        logger.debug("发起POST请求详情:")
        logger.debug(f"  URL: {url}")
        logger.debug(f"  Headers: {json.dumps(headers, indent=2)}")
        logger.debug(f"  Params: {json.dumps(request_params, indent=2, ensure_ascii=False)}")
        
        try:
            # 根据curl，这是一个POST请求，但所有参数都在URL中，没有请求体
            resp = self.sess.post(url=url, headers=headers, params=request_params, timeout=15)
            
            # 保存响应内容用于调试
            self.saveHtml(resp.text, "uncheck_cart_all")
            
            logger.info(f"购物车取消勾选响应状态码: {resp.status_code}")
            
            if not self.respStatus(resp):
                logger.error(f"购物车取消勾选请求失败: HTTP状态码 {resp.status_code}")
                # 返回空的响应对象
                return {
                    "success": True, 
                    "resultData": {
                        "cartInfo": {
                            "vendors": []
                        }
                    }
                }
            
            # 尝试解析响应JSON
            try:
                resp_json = resp.json()
                success = resp_json.get('success', False)
                logger.info(f"购物车取消勾选结果: {success}")
                
                if not success:
                    error_msg = resp_json.get('message', '未知错误')
                    logger.warning(f"购物车取消勾选API返回失败: {error_msg}")
                    
                    # 确保响应包含预期数据
                    if 'resultData' not in resp_json:
                        resp_json['resultData'] = {'cartInfo': {'vendors': []}}
                
                return resp_json
                
            except Exception as e:
                logger.error(f"解析购物车响应出错: {e}")
                # 返回空的响应对象
                return {
                    "success": True, 
                    "resultData": {
                        "cartInfo": {
                            "vendors": []
                        }
                    }
                }
                
        except Exception as e:
            logger.error(f"取消勾选购物车时出错: {e}")
            # 返回空的响应对象
            return {
                "success": True, 
                "resultData": {
                    "cartInfo": {
                        "vendors": []
                    }
                }
            }

    def addCartSku(self, skuId, skuNum, areaId):
        """ 加入购入车
        skuId 商品sku
        skuNum 购买数量
        retrun 是否成功
        """
        url = 'https://api.m.jd.com/api'
        function_id = 'pcCart_jc_gate'

        headers = {
            'origin': 'https://item.jd.com', # 京东加入购物车接口通常期望 origin 为 item.jd.com 或 cart.jd.com
            'referer': f'https://item.jd.com/', # Referer 指向商品详情页
            'user-agent': self.userAgent,
            'x-referer-page': f'https://item.jd.com/{skuId}.html' # 自定义头，进一步指明来源
        }


        # 1. 构建 body 内容的 Python 字典
        body_content = {
            "serInfo": {
                "area": areaId,  # 地区ID, 需要动态获取或从配置加载
                "user-key": ""  # 用户唯一标识符, 可能从cookie中提取或配置
            },
            "directOperation": {
                "source": "common",
                "theSkus": [
                    {
                        "skuId": skuId, # skuId 通常是整数
                        "num": str(skuNum), # 数量是字符串
                        "itemType": 1,
                        "extFlag": {},
                        "relationSkus": {}
                    }
                ]
            }
        }

        # 2. 将 Python 字典转换为 JSON 字符串
        body_json_string = json.dumps(body_content, separators=(',', ':'))
        
        # 从配置的反爬参数中获取
        t = self.t_params.get(function_id.lower(), str(int(time.time() * 1000)))
        h5st = self.h5st_params.get(function_id.lower(), "")

        # 3. 构建请求的查询参数 (Query Parameters)
        request_params = {
            'functionId': function_id,
            'appid': 'item-v3',
            'loginType': 3, # 假设已登录
            'client': 'pc',
            'clientVersion': '1.0.0',
            'body': body_json_string,
            'h5st': h5st,
            't': t
        }

        logger.info(f"准备添加商品到购物车: skuId={skuId}, 数量={skuNum}")
        
        # 记录完整的请求信息用于调试
        logger.debug("发起POST请求详情:")
        logger.debug(f"  URL: {url}")
        logger.debug(f"  Headers: {json.dumps(headers, indent=2)}")
        logger.debug(f"  Params (in URL query string): {json.dumps(request_params, indent=2, ensure_ascii=False)}")

        try:
            # 使用 params 参数将字典作为查询字符串附加到URL
            resp = self.sess.post(url=url, headers=headers, params=request_params)
            
            logger.info(f"添加商品到购物车响应状态码: {resp.status_code}")
            
            # 保存响应内容用于调试
            self.saveHtml(resp.text, f"add_cart_{skuId}")
            
            if not self.respStatus(resp):
                logger.error(f"添加商品到购物车请求失败: HTTP状态码 {resp.status_code}, URL: {resp.request.url}")
                return False
                
            try:
                resp_json = resp.json()
                # 检查 success 字段，有些京东API在顶层直接是 success，有些在 resultData.success
                success = resp_json.get('success', False)
                
                # 检查resultData中的success
                if not success and 'resultData' in resp_json and isinstance(resp_json['resultData'], dict):
                    success = resp_json['resultData'].get('success', False)
                
                if success:
                    logger.info(f"成功添加商品 {skuId} 到购物车")
                else:
                    message = resp_json.get('message', resp_json.get('errorMessage', '未知错误'))
                    logger.error(f"添加商品到购物车失败: {message}")
                
                return success
            except Exception as e:
                logger.error(f"处理添加购物车响应时出错: {e}")
                return False
        except Exception as e:
            logger.error(f"添加商品到购物车过程中出错: {e}")
            return False

    def changeCartSkuCount(self, skuId, skuUid, skuNum, areaId):
        """ 修改购物车商品数量
        skuId 商品sku
        skuUid 商品用户关系
        skuNum 购买数量
        retrun 是否成功
        """
        logger.info(f"开始修改购物车商品数量: skuId={skuId}, skuUuid={skuUid}, 数量={skuNum}")
        
        url = 'https://api.m.jd.com/api'
        function_id = 'pcCart_jc_changeSkuNum'

        headers = {
            'User-Agent': self.userAgent,
            'Content-Type': 'application/x-www-form-urlencoded',
            'origin': 'https://cart.jd.com',
            'referer': 'https://cart.jd.com/',
            'x-referer-page': 'https://cart.jd.com/cart_index',
            'x-rp-client': 'h5_1.0.0'
        }

        # 构建请求体JSON字符串，与curl示例保持一致
        body_content = {
            "operations": [{
                "TheSkus": [{
                    "Id": skuId,
                    "num": skuNum,
                    "skuUuid": skuUid,
                    "useUuid": False
                }]
            }],
            "serInfo": {
                "area": areaId
            }
        }
        
        # 将Python对象转换为JSON字符串，确保格式与原始请求一致
        body_json_string = json.dumps(body_content, separators=(',', ':'))
        
        # 从配置的反爬参数中获取
        t = self.t_params.get(function_id.lower(), str(int(time.time() * 1000)))
        h5st = self.h5st_params.get(function_id.lower(), "")
        
        # 构建请求参数
        params = {
            'functionId': function_id,
            'appid': 'JDC_mall_cart',
            'loginType': 3,
            'client': 'pc',
            'clientVersion': '1.0.0',
            'body': body_json_string,
            'h5st': h5st,
            't': t,
        }
        
        try:
            # 记录请求详情
            logger.debug(f"修改购物车请求URL: {url}")
            logger.debug(f"修改购物车请求头: {json.dumps(headers, ensure_ascii=False)}")
            logger.debug(f"修改购物车请求参数: {json.dumps(params, ensure_ascii=False)}")
            
            # 发送请求 - 注意使用params而不是data
            logger.info("正在发送修改购物车商品数量请求...")
            resp = self.sess.post(url=url, headers=headers, params=params)
            
            # 记录响应状态
            logger.info(f"修改购物车响应状态码: {resp.status_code}")
            
            # 保存响应内容到调试文件
            self.saveHtml(resp.text, f"change_cart_{skuId}")
            
            # 验证响应状态
            if not self.respStatus(resp):
                logger.error(f"修改购物车请求失败: HTTP状态码 {resp.status_code}")
                return False
                
            # 解析响应内容
            try:
                resp_json = resp.json()
                success = resp_json.get('success', False)
                
                if success:
                    logger.info(f"成功修改商品 {skuId} 的数量为 {skuNum}")
                else:
                    message = resp_json.get('message', resp_json.get('msg', '未知错误'))
                    logger.error(f"修改购物车商品数量API返回失败: {message}")
                    
                # 返回详细结果
                logger.debug(f"修改购物车响应内容: {json.dumps(resp_json, ensure_ascii=False)}")
                return success
                
            except json.JSONDecodeError:
                logger.error(f"解析修改购物车响应JSON出错. 内容: {resp.text[:250]}...")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"修改购物车商品数量请求时发生网络错误: {e}")
            return False
        except Exception as e:
            logger.error(f"修改购物车商品数量时出错: {e}")
            return False

    def prepareCart(self, skuId, skuNum, areaId):
        """ 下单前准备购物车
        1 取消全部勾选（返回购物车信息）
        2 已在购物车则修改商品数量
        3 不在购物车则加入购物车
        skuId 商品sku
        skuNum 商品数量
        return True/False
        """
        logger.info(f"准备购物车: 商品={skuId}, 数量={skuNum}")
        
        # 步骤1: 取消勾选所有商品
        resp = self.uncheckCartAll(areaId)
        
        # 检查响应状态
        try:
            # resp已经是一个字典对象，无需调用json()方法
            respObj = resp  # 直接使用字典对象，不需要调用json()
            logger.info(f"已获取购物车信息: {str(respObj)[:100]}...")
            
            # 即使API返回失败，我们也尝试继续
            success = respObj.get('success', False)
            if not success:
                logger.warning('购物车取消勾选返回失败，但尝试继续')
            
        except Exception as e:
            logger.error(f'解析购物车信息失败: {e}')
            # 出错时创建默认空购物车的响应对象
            respObj = {
                'success': True,
                'resultData': {'cartInfo': None}
            }
        
        # 步骤2: 检查商品是否已在购物车
        cart_info = respObj.get('resultData', {}).get('cartInfo', {})
        
        # 购物车为空或无法获取，直接添加商品
        if not cart_info:
            logger.info("购物车为空或无法获取，直接添加商品")
            add_result = self.addCartSku(skuId, skuNum, areaId)
            logger.info(f"添加商品到购物车结果: {add_result}")
            return add_result
        
        # 查找商品是否已在购物车中
        logger.info("检查商品是否已在购物车中")
        try:
            venders = cart_info.get('vendors', [])
            
            for vender in venders:
                items = vender.get('sorted', [])
                for item in items:
                    if 'item' not in item:
                        continue
                        
                    if str(item['item'].get('Id', '')) == skuId:
                        # 在购物车中，修改数量
                        current_num = item['item'].get('Num', '未知')
                        logger.info(f"商品已在购物车中，当前数量: {current_num}，将修改为: {skuNum}")
                        skuUuid = item['item'].get('skuUuid', '')
                        if not skuUuid:
                            logger.warning("购物车商品缺少skuUuid，尝试删除后重新添加")
                            # 可以考虑先移除再添加
                            add_result = self.addCartSku(skuId, skuNum, areaId)
                            return add_result
                            
                        update_result = self.changeCartSkuCount(skuId, skuUuid, skuNum, areaId)
                        logger.info(f"修改购物车商品数量结果: {update_result}")
                        return update_result
        except Exception as e:
            logger.error(f"解析购物车商品失败: {e}")
        
        # 不在购物车中或解析出错，添加商品
        logger.info("商品不在购物车中，添加商品")
        add_result = self.addCartSku(skuId, skuNum, areaId)
        logger.info(f"添加商品到购物车结果: {add_result}")
        return add_result

    ############## 订单相关 #############

    def trySubmitOrder(self, skuId, skuNum, areaId, retry=3, interval=5):
        """提交订单
        :return: 订单提交结果 True/False
        """
        logger.info(f"开始尝试提交订单: 商品={skuId}, 数量={skuNum}, 地区={areaId}")
        itemDetail = self.itemDetails[skuId]
        isYushou = False
        if 'yushouUrl' in itemDetail:
            logger.info("检测到预售商品，获取预售结算页")
            self.getPreSallCheckoutPage(skuId, skuNum)
            isYushou = True
        else:
            logger.info("普通商品，准备购物车并获取结算页")
            cart_result = self.prepareCart(skuId, skuNum, areaId)
            logger.info(f"准备购物车结果: {cart_result}")
            checkout_result = self.getCheckoutPage()
            logger.info(f"获取结算页结果: {checkout_result is not None}")

        for i in range(1, retry + 1):
            logger.info(f"第{i}次尝试提交订单...")
            ret, msg = self.submitOrder(isYushou)
            if ret:
                logger.info(f"订单提交成功，订单号: {msg}")
                return True
            else:
                logger.warning(f"订单提交失败，原因: {msg}，{interval}秒后重试")
                time.sleep(interval)
        logger.error(f"订单提交失败，已达到最大重试次数{retry}")
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
        
        payload = {
            'rid': str(int(time.time() * 1000)),
        }
        headers = {
            'User-Agent': self.userAgent,
            'Referer': 'https://cart.jd.com/cart',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Connection': 'keep-alive',
        }
        
        # 增加重试机制
        max_retries = 1
        retry_delay = 2  # 秒
        
        for retry in range(max_retries):
            try:
                current_url = url
                logger.info(f"开始获取结算页面(第{retry+1}次尝试): {current_url}")
                
                # 增加超时时间
                resp = self.sess.get(url=current_url, params=payload, headers=headers, timeout=15)
                logger.info(f"结算页面响应状态码: {resp.status_code}")
                
                if resp.status_code == 502:
                    logger.warning(f"获取结算页面遇到502错误，尝试切换URL或重试")
                    if retry < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                
                if not self.respStatus(resp):
                    logger.error(f"获取结算页面失败: HTTP状态码 {resp.status_code}")
                    if retry < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    return
                
                # 保存HTML内容用于调试
                debug_file = self.saveHtml(resp.text, f"checkout_page_attempt_{retry+1}")
                logger.info(f"已保存结算页面HTML到: {debug_file}")

                # 检查是否被重定向到登录页
                if "login" in resp.url:
                    logger.error(f"获取结算页面被重定向到登录页: {resp.url}")
                    if retry < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    return

                # 检查是否被重定向到购物车页面
                if "cart.jd.com" in resp.url and "gotoOrder" not in resp.url:
                    logger.error(f"获取结算页面被重定向到购物车: {resp.url}，可能是商品未勾选或购物车为空")
                    if retry < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    return

                html = etree.HTML(resp.text)
                # 提取页面重要信息
                page_eid = html.xpath("//input[@id='eid']/@value")
                page_fp = html.xpath("//input[@id='fp']/@value")
                page_risk_control = html.xpath("//input[@id='riskControl']/@value")
                page_track_id = html.xpath("//input[@id='TrackID']/@value")
                
                # 更新类的属性
                if page_eid:
                    self.eid = page_eid[0]
                if page_fp:
                    self.fp = page_fp[0]
                if page_risk_control:
                    self.risk_control = page_risk_control[0]
                if page_track_id:
                    self.track_id = page_track_id[0]
                
                logger.info(f"结算页面信息提取: eid={self.eid}, track_id={self.track_id}, risk_control={self.risk_control}")

                # 检查结算按钮是否存在
                submit_button = html.xpath("//a[@id='order-submit']")
                if not submit_button:
                    logger.warning("结算页面中未找到提交订单按钮")
                    # 尝试其他可能的按钮ID
                    alt_buttons = html.xpath("//a[contains(@class, 'submit-btn')]") or html.xpath("//button[contains(@class, 'submit')]")
                    if alt_buttons:
                        logger.info("找到替代的提交按钮")
                
                # 检查勾选状态
                checked_items = html.xpath("//div[contains(@class, 'item-selected')]") or html.xpath("//div[contains(@class, 'goods-item')]")
                logger.info(f"结算页面中已勾选商品数量: {len(checked_items) if checked_items else 0}")
                
                # 查找地址信息的不同方式
                address_elements = html.xpath("//span[@id='sendAddr']") or html.xpath("//div[contains(@class, 'addr-detail')]")
                receiver_elements = html.xpath("//span[@id='sendMobile']") or html.xpath("//div[contains(@class, 'addr-phone')]")
                price_elements = html.xpath("//span[@id='sumPayPriceId']") or html.xpath("//span[contains(@class, 'sumPrice')]")
                
                # 检查是否有商品信息
                product_list = html.xpath("//div[@id='product-list']/div[@class='goods-list']") or html.xpath("//div[contains(@class, 'goods-list')]")
                if not product_list and not checked_items:
                    logger.error("结算页面中未找到商品列表")
                    if retry < max_retries - 1:
                        # 再次勾选商品并重试
                        logger.info("尝试重新勾选购物车商品并重试获取结算页")
                        # TODO: 添加手动勾选购物车的逻辑
                        time.sleep(retry_delay)
                        continue
                    return
                
                # 获取商品ID列表
                product_ids = html.xpath("//div[contains(@class, 'goods-item')]/@goods-id") or html.xpath("//div[contains(@class, 'goods-item')]/@data-sku")
                if product_ids:
                    logger.info(f"结算页面中商品ID: {product_ids}")
                else:
                    logger.warning("结算页面中未找到商品ID")

                # 构建订单详情，尽可能获取信息
                address = ""
                if address_elements and address_elements[0].text:
                    address_text = address_elements[0].text
                    # 如果地址包含"寄送至："前缀，则去除
                    address = address_text[5:] if address_text.startswith("寄送至：") else address_text
                
                receiver = ""
                if receiver_elements and receiver_elements[0].text:
                    receiver_text = receiver_elements[0].text
                    # 如果收件人包含"收件人:"前缀，则去除
                    receiver = receiver_text[4:] if receiver_text.startswith("收件人:") else receiver_text
                
                total_price = "0"
                if price_elements and price_elements[0].text:
                    price_text = price_elements[0].text
                    # 如果价格包含"￥"前缀，则去除
                    total_price = price_text[1:] if price_text.startswith("￥") else price_text
                
                order_detail = {
                    'address': address,
                    'receiver': receiver,
                    'total_price': total_price,
                    'items': product_ids if product_ids else []
                }
                
                logger.info(f"结算信息: 收件人={order_detail['receiver']}, 总价={order_detail['total_price']}, 商品数={len(order_detail['items'])}")
                
                return order_detail
                
            except requests.exceptions.Timeout:
                logger.error(f"获取结算页面超时(第{retry+1}次尝试)")
                if retry < max_retries - 1:
                    time.sleep(retry_delay)
                
            except Exception as e:
                logger.error(f"获取结算页面出错: {e}")
                import traceback
                logger.error(traceback.format_exc())
                if retry < max_retries - 1:
                    time.sleep(retry_delay)
        
        # 所有重试都失败了
        logger.error(f"经过{max_retries}次尝试后仍无法获取结算页面")
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
        function_id = 'trade_submitOrder'
        # js function of submit order is included in https://trade.jd.com/shopping/misc/js/order.js?r=2018070403091

        # 确保必要参数已设置
        if not self.eid:
            logger.warning("提交订单缺少eid参数")
            self.eid = ''
            
        if not self.fp:
            logger.warning("提交订单缺少fp参数")
            self.fp = ''
            
        if not self.risk_control:
            logger.warning("提交订单缺少risk_control参数")
            self.risk_control = ''
            
        if not self.track_id:
            logger.warning("提交订单缺少track_id参数")
            self.track_id = ''

        data = {
            'overseaPurchaseCookies': '',
            'vendorRemarks': '[]',
            'submitOrderParam.sopNotPutInvoice': 'false',
            'submitOrderParam.ignorePriceChange': '0',
            'submitOrderParam.btSupport': '0',
            'riskControl': self.risk_control,
            'submitOrderParam.isBestCoupon': 1,
            'submitOrderParam.jxj': 1,
            'submitOrderParam.trackId': self.track_id if self.track_id else '',
            'submitOrderParam.eid': self.eid,
            'submitOrderParam.fp': self.fp,
         }

        if isYushou:
            data['submitOrderParam.needCheck'] = 1
            data['preSalePaymentTypeInOptional'] = 2
            data['submitOrderParam.payType4YuShou'] = 2

        # # add payment password when necessary
        # paymentPwd = self.password
        # if paymentPwd:
        #     data['submitOrderParam.payPassword'] = ''.join(
        #         ['u3' + x for x in paymentPwd])

        headers = {
            'User-Agent': self.userAgent,
            'Referer': 'https://trade.jd.com/',
        }

        logger.info(f"开始提交订单请求: {url}")
        logger.info(f"订单参数: eid={self.eid}, trackId={self.track_id}, riskControl={self.risk_control}")
        
        # 添加重试机制
        max_retries = 1
        retry_delay = 2  # 秒
        
        # 记录请求详情
        logger.debug("订单提交请求详情:")
        logger.debug(f"  URL: {url}")
        logger.debug(f"  Headers: {json.dumps(headers, indent=2)}")
        logger.debug(f"  Data: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
        for retry in range(max_retries):
            try:
                logger.info(f"第{retry+1}次尝试提交订单...")
                resp = self.sess.post(url=url, data=data, headers=headers, timeout=15)
                logger.info(f"订单提交响应状态码: {resp.status_code}")
                
                # 保存响应内容用于调试
                self.saveHtml(resp.text, f"submit_order_response_{retry+1}")
                
                # 检查响应内容
                if not resp.text.strip():
                    logger.error(f"订单提交响应为空")
                    if retry < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                
                try:
                    respJson = json.loads(resp.text)
                    logger.info(f"订单提交响应: {respJson}")

                    if respJson.get('success'):
                        orderId = respJson.get('orderId')
                        logger.info(f"订单提交成功，订单ID: {orderId}")
                        return True, orderId
                    else:
                        message, result_code = respJson.get('message', '未知错误'), respJson.get('resultCode', -1)
                        logger.warning(f"订单提交失败: 结果码={result_code}, 消息={message}")
                        
                        # 处理不同的错误码
                        if result_code == 0:
                            # 尝试解决第三方商品发票问题
                            self._saveInvoice()
                            message = message + '(下单商品可能为第三方商品，将切换为普通发票进行尝试)'
                            if retry < max_retries - 1:
                                logger.info("已切换发票，尝试重新提交订单")
                                time.sleep(retry_delay)
                                continue
                        elif result_code == 60077:
                            message = message + '(可能是购物车为空 或 未勾选购物车中商品)'
                            # 尝试重新勾选购物车
                            if retry < max_retries - 1:
                                logger.info("尝试重新勾选购物车商品并重试")
                                # TODO: 添加手动勾选购物车的逻辑
                                time.sleep(retry_delay)
                                continue
                        elif result_code == 60123:
                            message = message + '(需要在config.ini文件中配置支付密码)'
                            
                        return False, message
                except json.JSONDecodeError:
                    logger.error(f"解析订单提交响应JSON出错，响应内容: {resp.text[:200]}...")
                    
                    # 尝试从HTML响应中提取信息
                    if "订单提交成功" in resp.text or "下单成功" in resp.text:
                        # 尝试从HTML中提取订单号
                        order_id_match = re.search(r'订单号：\s*(\d+)', resp.text)
                        order_id = order_id_match.group(1) if order_id_match else "未知"
                        logger.info(f"从HTML响应中检测到订单提交成功，订单号: {order_id}")
                        return True, order_id
                    
                    if retry < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    return False, "无法解析响应"
            
            except requests.exceptions.Timeout:
                logger.error(f"订单提交请求超时(第{retry+1}次尝试)")
                if retry < max_retries - 1:
                    time.sleep(retry_delay)
                
            except Exception as e:
                logger.error(f"订单提交过程中出错: {e}")
                import traceback
                logger.error(traceback.format_exc())
                if retry < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return False, str(e)
        
        # 所有重试都失败
        logger.error(f"经过{max_retries}次尝试后仍无法成功提交订单")
        return False, f"经过{max_retries}次尝试后提交失败"

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
        """解析包含jQuery回调的JSON字符串
        :param s: 响应文本，如：jQuery123456({"code":123,"msg":"success"})
        :return: JSON对象
        """
        try:
            # 尝试直接查找第一个 { 和最后一个 }
            begin = s.find('{')
            end = s.rfind('}') + 1
            if begin >= 0 and end > 0:
                json_str = s[begin:end]
                return json.loads(json_str)
            else:
                # 如果找不到 { }, 尝试另一种格式
                logger.warning(f"无法在响应中找到JSON: {s[:100]}...")
                # 尝试提取回调参数
                match = re.search(r'\((.*)\)', s)
                if match:
                    return json.loads(match.group(1))
                else:
                    logger.error(f"无法解析响应为JSON: {s[:100]}...")
                    return {'code': -1, 'msg': '解析失败'}
        except Exception as e:
            logger.error(f"解析JSON出错: {e}, 原始内容: {s[:100]}...")
            return {'code': -1, 'msg': str(e)}

    def respStatus(self, resp):
        """
        检查响应状态是否正常
        :param resp: 响应对象
        :return: True为正常，False为异常
        """
        # 检查是否是None
        if resp is None:
            logger.error("响应对象为None")
            return False
            
        # 检查常见的成功状态码
        if resp.status_code in [200, 201, 202]:
            return True
            
        # 检查重定向状态码 - 有些接口会返回重定向但仍然是有效的
        if resp.status_code in [301, 302, 303, 307, 308]:
            logger.warning(f"请求被重定向到: {resp.headers.get('Location', '未知')}")
            return True
            
        # 特定处理403状态码 - 京东有时返回403但响应内容仍然有效
        if resp.status_code == 403:
            # 检查响应内容是否为空
            if not resp.text:
                logger.error("403响应内容为空")
                return False
                
            # 尝试解析内容，看是否包含有效数据
            try:
                if '{"success":' in resp.text or '"resultData"' in resp.text:
                    logger.warning("接收到403状态码，但响应内容看起来有效，尝试继续处理")
                    return True
            except:
                pass
                
            logger.error(f"请求被拒绝(403): {resp.text[:100]}")
            return False
            
        # 处理其他客户端错误
        if 400 <= resp.status_code < 500:
            logger.error(f"客户端请求错误: {resp.status_code}")
            return False
            
        # 处理服务器错误
        if resp.status_code >= 500:
            logger.error(f"服务器端错误: {resp.status_code}")
            return False
            
        # 默认处理其他状态码
        logger.warning(f"未知状态码: {resp.status_code}")
        return False

    def _load_anticrawl_params(self):
        """从config.ini加载反爬参数（h5st和t）"""
        try:
            from config import global_config
            
            # 检查anticrawl部分是否存在
            if not global_config.has_section('anticrawl'):
                logger.info("配置文件中没有anticrawl部分，跳过加载反爬参数")
                return
            
            # 获取所有anticrawl配置项
            for key, value in global_config.items('anticrawl'):
                # 解析h5st参数
                if key.endswith('_h5st') and value:
                    # 提取函数ID部分并统一使用小写
                    func_id = key[:-5].lower()  # 去掉_h5st后缀并转小写
                    self.h5st_params[func_id] = value
                    logger.info(f"加载h5st参数: {func_id}，值长度={len(value)}")
                
                # 解析t参数
                elif key.endswith('_t') and value:
                    func_id = key[:-2].lower()  # 去掉_t后缀并转小写
                    self.t_params[func_id] = value
                    logger.info(f"加载t参数: {func_id}，值={value}")
                else:
                    logger.debug(f"跳过不符合命名规范的配置项: {key}")
            
            # 调试信息：打印已加载的所有参数
            logger.info(f"共加载了 {len(self.h5st_params)} 个h5st参数和 {len(self.t_params)} 个t参数")
            if self.h5st_params:
                logger.debug("已加载的h5st参数:")
                for func_id, value in self.h5st_params.items():
                    logger.debug(f"  {func_id}: {value[:30]}...")
            
            if self.t_params:
                logger.debug("已加载的t参数:")
                for func_id, value in self.t_params.items():
                    logger.debug(f"  {func_id}: {value}")
                    
        except Exception as e:
            logger.error(f"加载反爬参数时出错: {e}")
