# -*- coding: utf-8 -*-
import time
import sys
import os

from config import global_config
from log import logger
from exception import JDException
from JdSession import Session
from timer import Timer
from utils import (
    save_image,
    open_image,
    close_image,
    send_wechat,
    is_process_running
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
    # 检查登录状态
    def checkLoginStatus(self):
        """检查当前登录状态并测试cookies有效性
        :return: 登录状态是否有效 True/False
        """
        if not self.session.isLogin:
            logger.info("当前未登录状态")
            return False
            
        # 验证登录状态和cookies
        logger.info("正在检查登录状态...")
        if self.session.validateCookies():
            logger.info("登录状态检查通过，cookies有效")
            return True
        else:
            logger.warning("登录状态检查未通过，需要重新登录")
            self.session.isLogin = False
            return False
    
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
        logger.info('开始二维码登录流程...')
        
        # 关闭二维码图片后的等待时间(秒)
        QR_CLOSE_WAIT_TIME = 3
        
        # 下载二维码
        qrCode = self.session.getQRcode()
        if not qrCode:
            logger.error('二维码下载失败')
            return False

        # 保存二维码图片
        fileName = 'QRcode.png'
        if not save_image(qrCode, fileName):
            logger.error('二维码保存失败')
            return False
            
        # 提示用户扫描
        logger.info(f'二维码已保存到: {fileName}')
        
        # 尝试自动打开图片
        qr_process = open_image(fileName)
        
        if not qr_process:
            logger.warning(f'无法自动打开二维码，请手动打开文件并使用京东APP扫描: {os.path.abspath(fileName)}')
        
        # 获取二维码票据
        ticket = None
        retryTimes = 60
        status_code = 0
        status_msg = ""
        manually_closed = False
        close_time = None
        
        # 循环检查二维码状态
        for i in range(retryTimes):
            # 检查图片是否被手动关闭
            if qr_process and not manually_closed and not is_process_running(qr_process):
                manually_closed = True
                close_time = time.time()
                logger.info(f"检测到二维码图片已被手动关闭，将继续等待{QR_CLOSE_WAIT_TIME}秒确认是否成功扫描...")
            
            # 检查是否已超过等待时间且没有票据
            if manually_closed and close_time and not ticket and (time.time() - close_time > QR_CLOSE_WAIT_TIME):
                # 如果图片被手动关闭超过指定时间，且没有获取到票据，判定为失败
                logger.error(f'二维码图片已被手动关闭，超过{QR_CLOSE_WAIT_TIME}秒未检测到成功扫描，判定为登录失败')
                return False
            
            ticket, status_code, status_msg = self.session.getQRcodeTicket()
            
            # 打印每次检查的状态
            logger.info(f'二维码状态: {status_code} - {status_msg}')
            
            if ticket:
                # 扫码成功，获取到票据
                logger.info('获取到二维码票据，正在验证...')
                break
            elif status_msg.find("二维码已取消授权") != -1 or status_msg.find("二维码已过期") != -1 or status_msg.find("二维码已失效") != -1:
                # 二维码已过期，关闭图片查看器（如果未被手动关闭）
                if not manually_closed and qr_process:
                    close_image(qr_process)
                    logger.info('已关闭二维码图片查看器')
                logger.error(f'{status_msg}，请重新获取')
                return False
            
            # 未扫描或其他状态，等待一段时间后继续检查
            time.sleep(2)
        
        # 关闭图片查看器（如果未被手动关闭）
        if not manually_closed and qr_process:
            close_image(qr_process)
            logger.info('已关闭二维码图片查看器')
        
        # 检查是否成功获取票据
        if not ticket:
            if status_code == 201:
                logger.error('二维码未扫描，已超时')
            else:
                logger.error(f'获取二维码票据失败: {status_msg}')
            return False

        # 验证二维码票据
        if not self.session.validateQRcodeTicket(ticket):
            logger.error('二维码验证失败，登录未成功')
            return False

        logger.info('二维码验证成功，登录完成')
        self.session.isLogin = True
        self.session.saveCookies()
        # 加载已保存的cookies
        self.session.updateCookies()
        logger.info('已加载保存的cookies')
             
        # 登录成功后验证cookies是否可用
        if not self.checkLoginStatus():
            logger.warning("二维码验证成功但Cookie验证失败，可能影响后续操作")

        return True
        
    # 统一登录入口
    def login(self, login_type='qrcode'):
        """
        登录京东
        :param login_type: 登录方式，'sms'短信登录，'qrcode'二维码登录(默认)
        :param phone: 手机号，短信登录时使用
        :return: 登录是否成功 True/False
        """
        # 先检查当前登录状态
        if self.session.isLogin:
            logger.info('已处于登录状态，无需重新登录')
            return True
            
        # 根据登录类型选择登录方式
        if login_type == 'sms':
            logger.info('使用短信验证码登录')
            return self.loginBySMS()
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
    # 从配置文件获取商品信息
    skuId = global_config.get('item', 'sku_id', raw=True)
    areaId = global_config.get('item', 'area_id', raw=True)
    skuNum = int(global_config.get('item', 'amount'))
    stockInterval = int(global_config.get('item', 'stock_interval'))
    submitRetry = int(global_config.get('item', 'submit_retry'))
    submitInterval = int(global_config.get('item', 'submit_interval'))
    buyTime = global_config.get('item', 'buy_time')
    
    # 参数检查
    if not skuId:
        logger.error("商品ID未设置，请检查配置文件")
        sys.exit(1)
        
    if not areaId:
        logger.error("区域ID未设置，请检查配置文件")
        sys.exit(1)

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
