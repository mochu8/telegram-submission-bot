#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库操作模块
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from sqlalchemy import create_engine, select, update, func
from sqlalchemy.orm import sessionmaker, Session
from .models import Base, User, Submission, Tag, RejectReason, BanRecord


class Database:
    """数据库操作类"""
    
    def __init__(self, db_path: str = "bot.db"):
        self.db_path = db_path
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
        
    def init_db(self):
        """初始化数据库表"""
        Base.metadata.create_all(self.engine)
        
    def get_session(self) -> Session:
        """获取数据库会话"""
        return self.SessionLocal()
    
    # ==================== 用户操作 ====================
    
    def get_or_create_user(self, user_id: int, username: str = None, 
                           full_name: str = None) -> User:
        """获取或创建用户"""
        with self.get_session() as session:
            user = session.get(User, user_id)
            if not user:
                user = User(
                    id=user_id,
                    username=username,
                    full_name=full_name
                )
                session.add(user)
                session.commit()
                session.refresh(user)
            else:
                # 更新用户信息
                user.username = username
                user.full_name = full_name
                user.last_active = datetime.utcnow()
                session.commit()
            return user
    
    def get_user(self, user_id: int) -> Optional[User]:
        """获取用户"""
        with self.get_session() as session:
            return session.get(User, user_id)
    
    def update_user_role(self, user_id: int, role: str) -> bool:
        """更新用户角色"""
        with self.get_session() as session:
            user = session.get(User, user_id)
            if user:
                user.role = role
                session.commit()
                return True
            return False
    
    def ban_user(self, user_id: int, admin_id: int, reason: str = None) -> bool:
        """封禁用户"""
        with self.get_session() as session:
            user = session.get(User, user_id)
            if user:
                user.is_banned = True
                user.ban_reason = reason
                user.banned_at = datetime.utcnow()
                user.banned_by = admin_id
                
                # 记录封禁
                record = BanRecord(
                    user_id=user_id,
                    action='ban',
                    reason=reason,
                    admin_id=admin_id
                )
                session.add(record)
                session.commit()
                return True
            return False
    
    def unban_user(self, user_id: int, admin_id: int) -> bool:
        """解封用户"""
        with self.get_session() as session:
            user = session.get(User, user_id)
            if user:
                user.is_banned = False
                user.ban_reason = None
                user.banned_at = None
                user.banned_by = None
                
                # 记录解封
                record = BanRecord(
                    user_id=user_id,
                    action='unban',
                    admin_id=admin_id
                )
                session.add(record)
                session.commit()
                return True
            return False
    
    def is_user_banned(self, user_id: int) -> bool:
        """检查用户是否被封禁"""
        with self.get_session() as session:
            user = session.get(User, user_id)
            return user.is_banned if user else False
    
    def is_admin(self, user_id: int) -> bool:
        """检查是否是管理员"""
        with self.get_session() as session:
            user = session.get(User, user_id)
            return user.role in ['admin', 'reviewer'] if user else False
    
    def get_user_stats(self, user_id: int) -> dict:
        """获取用户统计"""
        with self.get_session() as session:
            user = session.get(User, user_id)
            if user:
                return {
                    'total': user.total_submissions,
                    'approved': user.approved_count,
                    'rejected': user.rejected_count,
                    'pending': user.total_submissions - user.approved_count - user.rejected_count,
                    'approval_rate': user.approval_rate,
                    'level': user.level
                }
            return None
    
    # ==================== 投稿操作 ====================
    
    def create_submission(self, user_id: int, content_type: str, 
                          text_content: str = None, text_html: str = None,
                          media_ids: list = None, media_types: list = None, 
                          is_anonymous: bool = False,
                          original_msg_ids: list = None) -> Submission:
        """创建投稿"""
        with self.get_session() as session:
            submission = Submission(
                user_id=user_id,
                content_type=content_type,
                text_content=text_content,
                text_html=text_html,
                media_ids=json.dumps(media_ids) if media_ids else None,
                media_types=json.dumps(media_types) if media_types else None,
                is_anonymous=is_anonymous,
                original_msg_ids=json.dumps(original_msg_ids) if original_msg_ids else None
            )
            session.add(submission)
            
            # 更新用户投稿计数
            user = session.get(User, user_id)
            if user:
                user.total_submissions += 1
            
            session.commit()
            session.refresh(submission)
            return submission
    
    def get_submission(self, submission_id: int) -> Optional[Submission]:
        """获取投稿"""
        with self.get_session() as session:
            return session.get(Submission, submission_id)
    
    def get_pending_submissions(self, limit: int = 10) -> List[Submission]:
        """获取待审核投稿"""
        with self.get_session() as session:
            stmt = select(Submission).where(
                Submission.status == 'pending'
            ).order_by(Submission.created_at.asc()).limit(limit)
            result = session.execute(stmt)
            return result.scalars().all()
    
    def get_pending_count(self) -> int:
        """获取待审核数量"""
        with self.get_session() as session:
            stmt = select(func.count(Submission.id)).where(
                Submission.status == 'pending'
            )
            result = session.execute(stmt)
            return result.scalar()
    
    def approve_submission(self, submission_id: int, reviewer_id: int, 
                           tags: list = None, published_msg_id: int = None) -> bool:
        """通过投稿"""
        with self.get_session() as session:
            submission = session.get(Submission, submission_id)
            if submission:
                submission.status = 'approved'
                submission.reviewer_id = reviewer_id
                submission.reviewed_at = datetime.utcnow()
                submission.tags = json.dumps(tags) if tags else None
                submission.published_msg_id = published_msg_id
                
                # 更新用户统计
                user = session.get(User, submission.user_id)
                if user:
                    user.approved_count += 1
                    # 更新用户等级
                    self._update_user_level(user)
                
                session.commit()
                return True
            return False
    
    def reject_submission(self, submission_id: int, reviewer_id: int, 
                          reason: str = None) -> bool:
        """拒绝投稿"""
        with self.get_session() as session:
            submission = session.get(Submission, submission_id)
            if submission:
                submission.status = 'rejected'
                submission.reviewer_id = reviewer_id
                submission.reviewed_at = datetime.utcnow()
                submission.reject_reason = reason
                
                # 更新用户统计
                user = session.get(User, submission.user_id)
                if user:
                    user.rejected_count += 1
                
                session.commit()
                return True
            return False
    
    def _update_user_level(self, user: User):
        """更新用户等级（根据通过数量）"""
        levels = [0, 5, 15, 30, 50, 100, 200, 500, 1000, 2000, 5000]
        for i, threshold in enumerate(levels):
            if user.approved_count >= threshold:
                user.level = i
    
    # ==================== 标签操作 ====================
    
    def get_all_tags(self) -> List[Tag]:
        """获取所有标签"""
        with self.get_session() as session:
            stmt = select(Tag).order_by(Tag.usage_count.desc())
            result = session.execute(stmt)
            return result.scalars().all()
    
    def add_tag(self, name: str, emoji: str = None) -> Optional[Tag]:
        """添加标签"""
        with self.get_session() as session:
            existing = session.execute(
                select(Tag).where(Tag.name == name)
            ).scalar_one_or_none()
            
            if existing:
                return None
            
            tag = Tag(name=name, emoji=emoji)
            session.add(tag)
            session.commit()
            session.refresh(tag)
            return tag
    
    def increment_tag_usage(self, tag_names: List[str]):
        """增加标签使用次数"""
        with self.get_session() as session:
            for name in tag_names:
                tag = session.execute(
                    select(Tag).where(Tag.name == name)
                ).scalar_one_or_none()
                if tag:
                    tag.usage_count += 1
            session.commit()
    
    # ==================== 拒绝理由操作 ====================
    
    def get_all_reject_reasons(self) -> List[RejectReason]:
        """获取所有拒绝理由"""
        with self.get_session() as session:
            stmt = select(RejectReason).order_by(RejectReason.usage_count.desc())
            result = session.execute(stmt)
            return result.scalars().all()
    
    def add_reject_reason(self, text: str) -> RejectReason:
        """添加拒绝理由"""
        with self.get_session() as session:
            reason = RejectReason(text=text)
            session.add(reason)
            session.commit()
            session.refresh(reason)
            return reason
    
    def increment_reason_usage(self, reason_id: int):
        """增加理由使用次数"""
        with self.get_session() as session:
            reason = session.get(RejectReason, reason_id)
            if reason:
                reason.usage_count += 1
                session.commit()
    
    # ==================== 统计操作 ====================
    
    def get_overall_stats(self) -> dict:
        """获取总体统计"""
        with self.get_session() as session:
            total_users = session.execute(
                select(func.count(User.id))
            ).scalar()
            
            total_submissions = session.execute(
                select(func.count(Submission.id))
            ).scalar()
            
            pending = session.execute(
                select(func.count(Submission.id)).where(Submission.status == 'pending')
            ).scalar()
            
            approved = session.execute(
                select(func.count(Submission.id)).where(Submission.status == 'approved')
            ).scalar()
            
            rejected = session.execute(
                select(func.count(Submission.id)).where(Submission.status == 'rejected')
            ).scalar()
            
            return {
                'total_users': total_users,
                'total_submissions': total_submissions,
                'pending': pending,
                'approved': approved,
                'rejected': rejected
            }
    
    def init_default_data(self, tags: list, reject_reasons: list):
        """初始化默认数据"""
        with self.get_session() as session:
            # 添加默认标签
            for tag_data in tags:
                existing = session.execute(
                    select(Tag).where(Tag.name == tag_data['name'])
                ).scalar_one_or_none()
                if not existing:
                    tag = Tag(name=tag_data['name'], emoji=tag_data.get('emoji'))
                    session.add(tag)
            
            # 添加默认拒绝理由
            for reason_text in reject_reasons:
                existing = session.execute(
                    select(RejectReason).where(RejectReason.text == reason_text)
                ).scalar_one_or_none()
                if not existing:
                    reason = RejectReason(text=reason_text)
                    session.add(reason)
            
            session.commit()


# 全局数据库实例
db = Database()
