#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量翻译脚本 - 处理所有模板文件中的常见翻译
"""
import os
import re
import glob

# 翻译映射
TRANSLATIONS = {
    "{% trans 'Learning management system' %}": "学习管理系统",
    "{% trans 'Home' %}": "首页",
    "{% trans 'Dashboard' %}": "仪表板",
    "{% trans 'Profile' %}": "个人资料",
    "{% trans 'Students' %}": "学生",
    "{% trans 'Lecturers' %}": "讲师",
    "{% trans 'Add' %}": "添加",
    "{% trans 'Update' %}": "更新",
    "{% trans 'Delete' %}": "删除",
    "{% trans 'Edit' %}": "编辑",
    "{% trans 'Save' %}": "保存",
    "{% trans 'Cancel' %}": "取消",
    "{% trans 'Action' %}": "操作",
    "{% trans 'Actions' %}": "操作",
    "{% trans 'Email' %}": "邮箱",
    "{% trans 'Password' %}": "密码",
    "{% trans 'Course' %}": "课程",
    "{% trans 'Courses' %}": "课程",
    "{% trans 'Program' %}": "项目",
    "{% trans 'Programs' %}": "项目",
    "{% trans 'Quiz' %}": "测验",
    "{% trans 'Quizzes' %}": "测验",
    "{% trans 'Result' %}": "结果",
    "{% trans 'Results' %}": "结果",
    "{% trans 'Semester' %}": "学期",
    "{% trans 'Session' %}": "学期",
    "{% trans 'My Courses' %}": "我的课程",
    "{% trans 'Admin Panel' %}": "管理面板",
    "{% trans 'Setting' %}": "设置",
    "{% trans 'Signout' %}": "退出",
    "{% trans 'Change Password' %}": "修改密码",
    "{% trans 'Account Setting' %}": "账户设置",
}

def translate_file(file_path):
    """翻译单个文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # 应用所有翻译
        for en, zh in TRANSLATIONS.items():
            content = content.replace(en, zh)
        
        # 如果内容有变化，保存文件
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"已处理: {file_path}")
            return True
        return False
    except Exception as e:
        print(f"处理 {file_path} 时出错: {e}")
        return False

def main():
    """主函数"""
    templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
    
    # 获取所有HTML文件
    html_files = []
    for root, dirs, files in os.walk(templates_dir):
        for file in files:
            if file.endswith('.html'):
                html_files.append(os.path.join(root, file))
    
    print(f"找到 {len(html_files)} 个HTML文件")
    
    translated_count = 0
    for file_path in html_files:
        if translate_file(file_path):
            translated_count += 1
    
    print(f"\n处理完成！共处理 {translated_count} 个文件")

if __name__ == '__main__':
    main()
