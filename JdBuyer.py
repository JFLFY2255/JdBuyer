# -*- coding: utf-8 -*-
import time
import sys

from config import global_config
from log import logger
from exception import JDException
from JdSession import Session
from timer import Timer
from utils import (
    save_image,
    open_image,
    send_wechat
)


class Buyer(object):
    """
    京东买手
    """

    # 初始化
    def __init__(self):
        self.session = Session()
        # 微信推送
        self.enableWx = global_config.getboolean('messenger', 'enable')
        self.scKey = global_config.get('messenger', 'sckey')

    ############## 登录相关 #############
    # 短信登录
    def loginBySMS(self, phone=None):
        """
        使用短信验证码登录京东
        :param phone: 手机号，为空则从配置文件获取
        :return: 登录是否成功 True/False
        """
        # 获取手机号
        if not phone:
            try:
                phone = global_config.get('account', 'phone')
                if not phone:
                    logger.error('配置文件中手机号为空')
                    return False
                logger.info(f'从配置文件获取手机号: {phone}')
            except:
                logger.error('未配置手机号，无法使用短信登录')
                return False
                
        # 获取短信登录页
        if not self.session.getLoginPageForSMS():
            logger.error('获取短信登录页失败')
            return False
        
        # 发送短信验证码
        if not self.session.getSMSCode(phone):
            logger.error('发送短信验证码失败')
            return False
        
        # 等待用户输入验证码
        sms_code = input('请输入收到的短信验证码: ')
        
        # 验证短信验证码
        if not self.session.verifySMSCode(sms_code):
            logger.error('短信验证码验证失败')
            return False
        
        logger.info('短信登录成功')
        self.session.isLogin = True
        self.session.saveCookies()
        return True

    # 二维码登录
    def loginByQrCode(self):
        """
        使用二维码登录京东
        :return: 登录是否成功 True/False
        """
        # 二维码登录流程
        # download QR code
        qrCode = self.session.getQRcode()
        if not qrCode:
            logger.error('二维码下载失败')
            return False

        fileName = 'QRcode.png'
        save_image(qrCode, fileName)
        logger.info('二维码获取成功，请打开京东APP扫描')
        open_image(fileName)

        # get QR code ticket
        ticket = None
        retryTimes = 60
        status_code = 0
        status_msg = ""
        
        # 循环检查二维码状态
        for i in range(retryTimes):
            ticket, status_code, status_msg = self.session.getQRcodeTicket()
            
            # 打印每次检查的状态
            logger.info(f'二维码状态: {status_code} - {status_msg}')
            
            if ticket:
                # 扫码成功，获取到票据
                logger.info('获取到二维码票据，正在验证...')
                break
            elif status_msg.find("二维码已取消授权") != -1 or status_msg.find("二维码已过期") != -1 or status_msg.find("二维码已失效") != -1:
                # 二维码已过期
                logger.error(f'{status_msg}，请重新获取')
                return False
            
            # 未扫描或其他状态，等待一段时间后继续检查
            time.sleep(2)
        
        # 检查是否成功获取票据
        if not ticket:
            if status_code == 201:
                logger.error('二维码未扫描，已超时')
            else:
                logger.error(f'获取二维码票据失败: {status_msg}')
            return False

        # validate QR code ticket
        if not self.session.validateQRcodeTicket(ticket):
            logger.error('二维码信息校验失败')
            return False

        logger.info('二维码登录成功')
        self.session.isLogin = True
        self.session.saveCookies()
        return True
        
    # 统一登录入口
    def login(self, login_type='qrcode', phone=None):
        """
        登录京东
        :param login_type: 登录方式，'sms'短信登录，'qrcode'二维码登录(默认)
        :param phone: 手机号，短信登录时使用
        :return: 登录是否成功 True/False
        """
        # 先检查当前登录状态
        if self.session.isLogin:
            logger.info('已处于登录状态')
            return True
            
        # 根据登录类型选择登录方式
        if login_type == 'sms':
            logger.info('使用短信验证码登录')
            return self.loginBySMS(phone)
        else:
            logger.info('使用二维码登录')
            return self.loginByQrCode()

    ############## 测试方法 #############
    def testItemInfo(self, skuId, areaId, skuNum=1):
        """测试获取商品信息和库存状态
        :param skuId: 商品ID
        :param areaId: 地区ID
        :param skuNum: 购买数量
        """
        try:
            print(f"\n===== 测试商品信息获取 =====")
            print(f"商品ID: {skuId}")
            print(f"地区ID: {areaId}")
            print(f"商品数量: {skuNum}")
            
            # 先进行登录
            if not self.session.isLogin:
                print("\n正在登录...")
                if not self.login():
                    print("登录失败，无法获取商品信息")
                    return False
                print("登录成功，继续测试")
            else:
                print("已是登录状态，继续测试")
            
            # 获取商品详情
            print("\n正在获取商品详情...")
            self.session.fetchItemDetail(skuId)
            
            # 获取库存状态
            print("\n正在检查商品库存状态...")
            stock_status = self.session.getItemStock(skuId, skuNum, areaId)
            print(f"商品库存状态: {'有货' if stock_status else '无货'}")
            
            print("\n测试完成!")
        except Exception as e:
            import traceback
            print(f"\n测试过程中发生错误: {e}")
            traceback.print_exc()
            return False
        return True

    ############## 外部方法 #############
    def buyItemInStock(self, skuId, areaId, skuNum=1, stockInterval=3, submitRetry=3, submitInterval=5, buyTime='2022-08-06 00:00:00'):
        """根据库存自动下单商品
        :skuId 商品sku
        :areaId 下单区域id
        :skuNum 购买数量
        :stockInterval 库存查询间隔（单位秒）
        :submitRetry 下单尝试次数
        :submitInterval 下单尝试间隔（单位秒）
        :buyTime 定时执行
        """
        self.session.fetchItemDetail(skuId)
        timer = Timer(buyTime)
        timer.start()

        while True:
            try:
                if not self.session.getItemStock(skuId, skuNum, areaId):
                    logger.info('不满足下单条件，{0}s后进行下一次查询'.format(stockInterval))
                else:
                    logger.info('{0} 满足下单条件，开始执行'.format(skuId))
                    if self.session.trySubmitOrder(skuId, skuNum, areaId, submitRetry, submitInterval):
                        logger.info('下单成功')
                        if self.enableWx:
                            send_wechat(
                                message='JdBuyerApp', desp='您的商品已下单成功，请及时支付订单', sckey=self.scKey)
                        return
            except Exception as e:
                logger.error(e)
            time.sleep(stockInterval)


def show_usage():
    print('用法: python JdBuyer.py [命令] [参数]')
    print('命令:')
    print('  buy  - 购买商品')
    print('  test - 测试商品信息')
    print('示例:')
    print('  python JdBuyer.py buy')
    print('  python JdBuyer.py test 100015253059 1_2901_55554_0')


if __name__ == '__main__':
    # 商品sku
    # skuId = '10118287699614'
    skuId = '10137555659077'
    # skuId = '100015253059'
    # 区域id(可根据工程 area_id 目录查找)
    # areaId = '18_1482_48942_49129'
    areaId = '1_2901_55554_0'
    # 购买数量
    skuNum = 1
    # 库存查询间隔(秒)
    stockInterval = 3
    # 监听库存后尝试下单次数
    submitRetry = 3
    # 下单尝试间隔(秒)
    submitInterval = 5
    # 程序开始执行时间(晚于当前时间立即执行，适用于定时抢购类)
    buyTime = '2022-10-10 00:00:00'

    buyer = Buyer()  # 初始化
    
    # 支持命令行参数
    if len(sys.argv) > 1:
        if sys.argv[1] == 'test':
            # 测试模式
            test_sku_id = sys.argv[2] if len(sys.argv) > 2 else skuId
            test_area_id = sys.argv[3] if len(sys.argv) > 3 else areaId
            test_sku_num = int(sys.argv[4]) if len(sys.argv) > 4 else skuNum
            
            # 检查登录状态
            if not buyer.login():
                logger.error("登录失败，无法继续测试")
                sys.exit(1)
            logger.info("登录成功，开始测试商品信息")
            
            buyer.testItemInfo(test_sku_id, test_area_id, test_sku_num)
            sys.exit(0)
        elif sys.argv[1] == 'buy':
            # 购买模式
            if not buyer.login():
                logger.error("登录失败，无法进行购买")
                sys.exit(1)
            logger.info("登录成功，开始购买商品")
            
            buyer.buyItemInStock(skuId, areaId, skuNum, stockInterval,
                             submitRetry, submitInterval, buyTime)
        else:
            show_usage()
            sys.exit(1)
    else:
        # 默认购买流程
        if not buyer.login():
            logger.error("登录失败，无法进行购买")
            sys.exit(1)
        logger.info("登录成功，开始购买商品")
        
        buyer.buyItemInStock(skuId, areaId, skuNum, stockInterval,
                         submitRetry, submitInterval, buyTime)
