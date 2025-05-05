#!/usr/bin/env python
# -*- encoding=utf8 -*-
import logging
import logging.handlers
import os
from time import strftime

from config import global_config

# 日志文件路径
LOG_FILENAME = strftime("logs/jd-buyer_%Y_%m_%d_%H.log")

def set_logger():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    # 判断日志文件父目录是否存在，不存在则创建
    log_dir = os.path.dirname(LOG_FILENAME)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir)
    # 定义handler的输出格式
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    
    # 设置级别，使用默认值处理异常
    try:
        loglevel = global_config.get('config', 'log_level').upper()
        if loglevel in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            logger.setLevel(loglevel)
    except:
        # 默认INFO级别
        logger.setLevel("INFO")
    
    # 添加handler
    logger.addHandler(console)

    # 输出到文件
    try:
        save_log = global_config.getboolean('config', 'save_log')
    except:
        save_log = True  # 默认保存日志
        
    if save_log:
        # 每天生成新文件
        file_handler = logging.handlers.TimedRotatingFileHandler(
            LOG_FILENAME, when='midnight', interval=1, backupCount=7)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    # 返回
    return logger


# 导出
logger = set_logger()
