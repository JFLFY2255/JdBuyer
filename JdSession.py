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
DEFAULT_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/66.0.3359.181 Safari/537.36'

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
        
        try:
            logger.info("初始化时尝试加载cookies...")
            self.loadCookies()
        except Exception as e:
            logger.error(f"初始化加载cookies失败: {e}")
            pass
        
        # 创建调试目录
        self.debug_dir = os.path.join(absPath, 'debug_html')
        if not os.path.exists(self.debug_dir):
            os.makedirs(self.debug_dir)

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
    def loadCookies(self):
        """加载Cookie并验证是否有效
        :return: 是否成功加载并验证Cookie True/False
        """
        try:
            cookiesFile = os.path.join(
                absPath, './cookies/{0}.cookies'.format(self.username))
            
            # 检查Cookie文件是否存在
            if not os.path.exists(cookiesFile):
                logger.error(f"Cookie文件不存在: {cookiesFile}")
                return False
                
            # 加载Cookie文件
            logger.info(f"正在加载Cookie文件: {cookiesFile}")
            with open(cookiesFile, 'rb') as f:
                local_cookies = pickle.load(f)
            self.sess.cookies.update(local_cookies)
            
            # 验证Cookie是否有效
            self.isLogin = self._validateCookies()
            
            if self.isLogin:
                logger.info(f"Cookie验证成功，已登录状态")
                return True
            else:
                logger.info(f"Cookie已过期，需要重新登录")
                return False
        except Exception as e:
            logger.error(f"加载Cookie时出错: {e}")
            return False

    # 验证 cookie
    def _validateCookies(self):
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
            resp = self.sess.get(url=url, params=payload,
                               allow_redirects=False)
            
            if resp.status_code == 200:
                logger.info(f"Cookie有效，成功访问订单页面")
                return True
            else:
                logger.info(f"Cookie无效，状态码: {resp.status_code}, 可能需要重新登录")
                if resp.status_code == 302:
                    logger.info(f"被重定向到: {resp.headers.get('Location', '未知页面')}")
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
                
            # 也可能是302重定向，或者其他格式的响应，检查Cookie是否有效
            if self._validateCookies():
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
        headers = {
            'User-Agent': self.userAgent,
        }
        try:
            resp = self.sess.get(url=url, headers=headers)
            if not self.respStatus(resp):
                detail = dict(venderId='0')
                self.itemDetails[skuId] = detail
                return
            
            # 保存HTML内容用于调试
            self.saveHtml(resp.text, f"item_detail_{skuId}")
                
            html = etree.HTML(resp.text)
            
            # 提取店铺ID
            shop_id = '0'
            shop_info = html.xpath('//div[contains(@class, "shopName")]/div[@class="name"]/a/@data-shopid')
            if shop_info:
                shop_id = shop_info[0]
                
            detail = dict(venderId=shop_id)
            
            # 检查是否是预售商品
            yushou_info = html.xpath('//div[contains(@class, "summary-price-wrap")]//span[contains(text(), "预售")]/text()')
            if yushou_info:
                detail['yushouUrl'] = url
                
            # 检查是否是秒杀商品
            miaosha_info = html.xpath('//div[contains(@class, "summary-price-wrap")]//span[contains(text(), "秒杀")]/text()')
            if miaosha_info:
                # 获取秒杀时间，实际时间需要从页面上解析，这里只是占位
                detail['startTime'] = int(time.time()) * 1000
                detail['endTime'] = int(time.time() + 3600) * 1000  # 默认一小时
                
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
