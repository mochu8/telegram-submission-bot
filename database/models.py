#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据库模型定义"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship

from utils.timeutil import utcnow

Base = declarative_base()

STATUS_PENDING = "pending"
STATUS_PUBLISHING = "publishing"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"


class User(Base):
    """用户表"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)  # Telegram 用户ID
    username = Column(String(100), nullable=True)
    full_name = Column(String(200), nullable=True)
    level = Column(Integer, default=0)  # 用户等级 0-10
    role = Column(String(20), default="user")  # user / reviewer / admin
    is_banned = Column(Boolean, default=False)
    ban_reason = Column(Text, nullable=True)
    banned_at = Column(DateTime, nullable=True)
    banned_by = Column(Integer, nullable=True)
    total_submissions = Column(Integer, default=0)
    approved_count = Column(Integer, default=0)
    rejected_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)
    last_active = Column(DateTime, default=utcnow)

    submissions = relationship("Submission", back_populates="user")

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, role={self.role})>"

    @property
    def approval_rate(self):
        """计算通过率"""
        if not self.total_submissions:
            return 0
        return round(self.approved_count / self.total_submissions * 100, 1)


class Submission(Base):
    """投稿表"""

    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # pending / publishing / approved / rejected
    status = Column(String(20), default=STATUS_PENDING)
    is_anonymous = Column(Boolean, default=False)
    content_type = Column(String(50), nullable=True)
    text_content = Column(Text, nullable=True)
    text_html = Column(Text, nullable=True)
    media_ids = Column(Text, nullable=True)
    media_types = Column(Text, nullable=True)
    tags = Column(Text, nullable=True)
    reject_reason = Column(Text, nullable=True)
    reviewer_id = Column(Integer, nullable=True)
    published_msg_id = Column(Integer, nullable=True)
    original_msg_ids = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    reviewed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="submissions")

    def __repr__(self):
        return f"<Submission(id={self.id}, user_id={self.user_id}, status={self.status})>"


class Tag(Base):
    """标签表"""

    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False)
    emoji = Column(String(10), nullable=True)
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)

    def __repr__(self):
        return f"<Tag(id={self.id}, name={self.name})>"

    @property
    def display_name(self):
        if self.emoji:
            return f"{self.emoji} {self.name}"
        return self.name


class RejectReason(Base):
    """拒绝理由表"""

    __tablename__ = "reject_reasons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(Text, nullable=False)
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)

    def __repr__(self):
        return f"<RejectReason(id={self.id}, text={self.text[:20]}...)>"


class ReviewNotice(Base):
    """发给管理员的审核消息，处理后用来改掉其他人的按钮。"""

    __tablename__ = "review_notices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=False, index=True)
    chat_id = Column(Integer, nullable=False)
    message_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    def __repr__(self):
        return (
            f"<ReviewNotice(submission_id={self.submission_id}, "
            f"chat_id={self.chat_id}, message_id={self.message_id})>"
        )


class BanRecord(Base):
    """封禁记录表"""

    __tablename__ = "ban_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(20), nullable=False)  # ban / unban
    reason = Column(Text, nullable=True)
    admin_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    def __repr__(self):
        return f"<BanRecord(id={self.id}, user_id={self.user_id}, action={self.action})>"
