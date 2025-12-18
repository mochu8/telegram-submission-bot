#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库模型定义
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, 
    ForeignKey, create_engine
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker as async_sessionmaker

Base = declarative_base()


class User(Base):
    """用户表"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)  # Telegram 用户ID
    username = Column(String(100), nullable=True)
    full_name = Column(String(200), nullable=True)
    level = Column(Integer, default=0)  # 用户等级 0-10
    role = Column(String(20), default='user')  # user / reviewer / admin
    is_banned = Column(Boolean, default=False)
    ban_reason = Column(Text, nullable=True)
    banned_at = Column(DateTime, nullable=True)
    banned_by = Column(Integer, nullable=True)
    total_submissions = Column(Integer, default=0)
    approved_count = Column(Integer, default=0)
    rejected_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    
    # 关联
    submissions = relationship("Submission", back_populates="user")
    
    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, role={self.role})>"
    
    @property
    def approval_rate(self):
        """计算通过率"""
        if self.total_submissions == 0:
            return 0
        return round(self.approved_count / self.total_submissions * 100, 1)


class Submission(Base):
    """投稿表"""
    __tablename__ = 'submissions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    status = Column(String(20), default='pending')  # pending / approved / rejected
    is_anonymous = Column(Boolean, default=False)
    content_type = Column(String(50), nullable=True)  # text / photo / video / audio / media_group
    text_content = Column(Text, nullable=True)
    text_html = Column(Text, nullable=True)  # HTML格式的文本（保留富文本格式）
    media_ids = Column(Text, nullable=True)  # JSON数组存储media file_id
    media_types = Column(Text, nullable=True)  # JSON数组存储media类型
    tags = Column(Text, nullable=True)  # JSON数组存储标签
    reject_reason = Column(Text, nullable=True)
    reviewer_id = Column(Integer, nullable=True)
    published_msg_id = Column(Integer, nullable=True)
    original_msg_ids = Column(Text, nullable=True)  # 原始消息ID（用于多图）
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)
    
    # 关联
    user = relationship("User", back_populates="submissions")
    
    def __repr__(self):
        return f"<Submission(id={self.id}, user_id={self.user_id}, status={self.status})>"


class Tag(Base):
    """标签表"""
    __tablename__ = 'tags'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False)
    emoji = Column(String(10), nullable=True)
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<Tag(id={self.id}, name={self.name})>"
    
    @property
    def display_name(self):
        if self.emoji:
            return f"{self.emoji} {self.name}"
        return self.name


class RejectReason(Base):
    """拒绝理由表"""
    __tablename__ = 'reject_reasons'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(Text, nullable=False)
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<RejectReason(id={self.id}, text={self.text[:20]}...)>"


class BanRecord(Base):
    """封禁记录表"""
    __tablename__ = 'ban_records'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    action = Column(String(20), nullable=False)  # ban / unban
    reason = Column(Text, nullable=True)
    admin_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<BanRecord(id={self.id}, user_id={self.user_id}, action={self.action})>"
