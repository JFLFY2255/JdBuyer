#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import configparser
import os
import html

def extract_curl_commands(content):
    """提取完整的curl命令"""
    # 匹配完整的curl命令，包括所有参数和引号
    curl_pattern = r"curl '(.*?)' \\(?:\r?\n(?:.*?\\)*.*?-H '.*?')*"
    curl_matches = re.finditer(curl_pattern, content, re.DOTALL)
    
    commands = []
    for match in curl_matches:
        # 提取URL部分
        url = match.group(1)
        commands.append(url)
    
    return commands

def extract_params_from_curl(curl_url):
    """从curl URL中提取functionId, h5st和t参数"""
    # 提取functionId
    function_id_match = re.search(r'functionId=([^&]+)', curl_url)
    function_id = function_id_match.group(1) if function_id_match else None
    
    # 提取h5st，需要处理URL编码
    h5st_match = re.search(r'h5st=([^&]+)', curl_url)
    h5st = h5st_match.group(1) if h5st_match else None
    if h5st:
        h5st = html.unescape(h5st)  # 处理HTML转义
    
    # 提取t - 修复提取逻辑，确保获取正确的t值
    t_match = re.search(r'[?&]t=(\d+)', curl_url)
    t = t_match.group(1) if t_match else None
    
    return function_id, h5st, t

def update_config_ini(function_id, h5st, t):
    """更新config.ini文件中的h5st和t参数"""
    if not function_id or (not h5st and not t):
        return False
    
    config = configparser.ConfigParser()
    config.read('config.ini', encoding='utf-8')
    
    # 如果没有anticrawl部分，则创建
    if 'anticrawl' not in config:
        config['anticrawl'] = {}
    
    # 更新h5st
    if h5st:
        h5st_key = f"{function_id}_h5st"
        config['anticrawl'][h5st_key] = h5st
        print(f"已更新 {h5st_key} = {h5st[:30]}...")
    
    # 更新t
    if t:
        t_key = f"{function_id}_t"
        config['anticrawl'][t_key] = t
        print(f"已更新 {t_key} = {t}")
    
    # 保存配置
    with open('config.ini', 'w', encoding='utf-8') as f:
        config.write(f)
    
    return True

def main():
    print("开始从realrequests.txt提取参数...")
    
    if not os.path.exists('realrequests.txt'):
        print("错误: realrequests.txt文件不存在")
        return
    
    if not os.path.exists('config.ini'):
        print("错误: config.ini文件不存在")
        return
    
    with open('realrequests.txt', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 先尝试直接使用简单方式提取curl命令的URL部分
    curl_commands = re.findall(r"curl '([^']+)'", content)
    
    if not curl_commands:
        print("未找到curl命令，尝试其他匹配方式...")
        curl_commands = extract_curl_commands(content)
    
    if not curl_commands:
        print("无法提取curl命令，请检查realrequests.txt格式")
        return
    
    print(f"找到 {len(curl_commands)} 个curl命令")
    
    # 记录更新数量
    updated_count = 0
    
    # 为每个命令提取参数并更新配置
    for i, cmd in enumerate(curl_commands):
        print(f"\n处理第 {i+1} 个curl命令:")
        function_id, h5st, t = extract_params_from_curl(cmd)
        if function_id:
            print(f"发现functionId: {function_id}")
            if update_config_ini(function_id, h5st, t):
                updated_count += 1
        else:
            print("未找到functionId，跳过")
    
    print(f"\n完成! 共更新了 {updated_count} 个参数配置")

if __name__ == "__main__":
    main() 