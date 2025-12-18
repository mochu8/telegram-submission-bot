#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块
"""

import json
from pathlib import Path
from typing import Dict, List, Any


class Config:
    """配置类"""
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent / "config.json"
        self.config_path = Path(config_path)
        self._config = self._load_config()
    
    def _load_config(self) -> dict:
        """加载配置文件"""
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def reload(self):
        """重新加载配置"""
        self._config = self._load_config()
    
    @property
    def bot_token(self) -> str:
        return self._config.get('bot_token', '')
    
    @property
    def admin_ids(self) -> List[int]:
        return self._config.get('admin_ids', [])
    
    @property
    def channel_id(self) -> str:
        return self._config.get('channel_id', '')
    
    @property
    def channel_name(self) -> str:
        return self._config.get('channel_name', '')
    
    @property
    def bot_info(self) -> dict:
        return self._config.get('bot_info', {})
    
    @property
    def navigation_links(self) -> List[dict]:
        return self._config.get('navigation_links', [])
    
    @property
    def customer_service(self) -> dict:
        return self._config.get('customer_service', {})
    
    @property
    def submission_rules(self) -> str:
        return self._config.get('submission_rules', '')
    
    @property
    def default_tags(self) -> List[dict]:
        return self._config.get('default_tags', [])
    
    @property
    def default_reject_reasons(self) -> List[str]:
        return self._config.get('default_reject_reasons', [])
    
    def is_config_admin(self, user_id: int) -> bool:
        """检查是否是配置文件中的管理员"""
        return user_id in self.admin_ids
    
    def get_footer_text(self) -> str:
        """获取尾部信息文本"""
        footer_config = self._config.get('footer', {})
        if not footer_config.get('enabled', False):
            return ""
        
        parts = []
        for item in footer_config.get('links', []):
            if item.get('enabled', True) and item.get('username'):
                name = item.get('name', '')
                username = item['username']
                parts.append(f"{name} @{username}")
        
        return " ".join(parts)


# 全局配置实例
config = Config()
