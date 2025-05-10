# -*- coding: utf-8 -*-
import os

import configparser


class Config(object):

    def __init__(self, config_file='config.ini'):
        self._path = os.path.join(os.getcwd(), config_file)
        if not os.path.exists(self._path):
            raise FileNotFoundError("No such file: config.ini")
        self._config = configparser.ConfigParser()
        self._config.read(self._path, encoding='utf-8')

    def get(self, section, name, strip_blank=True, strip_quote=True, raw=False):
        s = self._config.get(section, name, raw=raw)
        if strip_blank:
            s = s.strip()
        if strip_quote:
            s = s.strip('"').strip("'")

        return s

    def getboolean(self, section, name):
        return self._config.getboolean(section, name)

    def has_option(self, section, option):
        """检查配置文件中是否存在指定的选项
        
        Args:
            section: 配置文件中的节名称
            option: 需要检查的选项名称
            
        Returns:
            bool: 如果选项存在则返回True，否则返回False
        """
        return self._config.has_option(section, option)

    def has_section(self, section):
        """检查配置文件中是否存在指定的部分
        
        Args:
            section: 配置文件中的节名称
            
        Returns:
            bool: 如果部分存在则返回True，否则返回False
        """
        return self._config.has_section(section)

    def items(self, section):
        """获取指定部分的所有配置项
        
        Args:
            section: 配置文件中的节名称
            
        Returns:
            list: 配置项的列表，每项为(option, value)的元组
        """
        return self._config.items(section)


global_config = Config()
