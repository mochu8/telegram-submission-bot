#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据库操作模块"""

import json
import logging
from pathlib import Path

from sqlalchemy import create_engine, delete, event, func, select, text, update
from sqlalchemy.orm import sessionmaker

from config import config
from database.models import (
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_PUBLISHING,
    STATUS_REJECTED,
    BanRecord,
    Base,
    RejectReason,
    ReviewNotice,
    Submission,
    Tag,
    User,
)
from utils.timeutil import utcnow

logger = logging.getLogger(__name__)


class SubmissionNotAllowed(Exception):
    """The user is missing or banned, so the submission must not be stored."""


class Database:
    """数据库操作类"""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path: str | None = None
        self.engine = None
        self.SessionLocal = None
        if db_path is not None:
            self.configure(db_path)

    def configure(self, db_path: str | Path) -> None:
        """Point this instance at a SQLite file and create its parent directory."""
        path = Path(db_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        if self.engine is not None:
            self.engine.dispose()
        self.db_path = str(path)
        self.engine = create_engine(
            f"sqlite:///{path.as_posix()}",
            echo=False,
            connect_args={"check_same_thread": False, "timeout": 30},
        )

        @event.listens_for(self.engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def init_db(self):
        """初始化数据库表"""
        if self.engine is None:
            raise RuntimeError("数据库尚未配置，请先调用 configure()")
        Base.metadata.create_all(self.engine)

    def get_session(self):
        """获取数据库会话"""
        if self.SessionLocal is None:
            raise RuntimeError("数据库尚未配置，请先调用 configure()")
        return self.SessionLocal()

    def _detach(self, session, obj):
        if obj is not None:
            session.expunge(obj)
        return obj

    # ==================== 用户操作 ====================

    def get_or_create_user(self, user_id: int, username: str = None, full_name: str = None) -> User:
        """获取或创建用户。不会改动封禁状态。"""
        with self.get_session() as session:
            user = session.get(User, user_id)
            now = utcnow()
            if user is None:
                user = User(
                    id=user_id,
                    username=username,
                    full_name=full_name,
                    last_active=now,
                )
                session.add(user)
                session.commit()
                session.refresh(user)
                return self._detach(session, user)

            profile_changed = user.username != username or user.full_name != full_name
            last_active = user.last_active
            stale = last_active is None or (now - last_active).total_seconds() >= 300
            if not profile_changed and not stale:
                return self._detach(session, user)

            if profile_changed:
                user.username = username
                user.full_name = full_name
            user.last_active = now
            session.commit()
            session.refresh(user)
            return self._detach(session, user)

    def get_user(self, user_id: int):
        """获取用户"""
        with self.get_session() as session:
            return self._detach(session, session.get(User, user_id))

    def update_user_role(self, user_id: int, role: str) -> bool:
        """更新用户角色"""
        with self.get_session() as session:
            user = session.get(User, user_id)
            if user is None:
                return False
            user.role = role
            session.commit()
            return True

    def ban_user(self, user_id: int, admin_id: int, reason: str = None) -> bool:
        """封禁用户。用户还不存在时会先建档，因此未 /start 的用户也能被封禁。"""
        if config.is_config_admin(user_id):
            logger.warning("Refused to ban configured admin %s", user_id)
            return False
        with self.get_session() as session:
            user = session.get(User, user_id)
            if user is not None and user.role in ("admin", "reviewer"):
                logger.warning("Refused to ban user %s with role %s", user_id, user.role)
                return False
            if user is None:
                user = User(id=user_id)
                session.add(user)
                session.flush()
            user.is_banned = True
            user.ban_reason = reason
            user.banned_at = utcnow()
            user.banned_by = admin_id
            session.add(
                BanRecord(
                    user_id=user_id,
                    action="ban",
                    reason=reason,
                    admin_id=admin_id,
                )
            )
            session.commit()
            return True

    def unban_user(self, user_id: int, admin_id: int) -> bool:
        """解封用户"""
        with self.get_session() as session:
            user = session.get(User, user_id)
            if user is None:
                return False
            user.is_banned = False
            user.ban_reason = None
            user.banned_at = None
            user.banned_by = None
            session.add(
                BanRecord(
                    user_id=user_id,
                    action="unban",
                    admin_id=admin_id,
                )
            )
            session.commit()
            return True

    def is_user_banned(self, user_id: int) -> bool:
        """检查用户是否被封禁"""
        with self.get_session() as session:
            user = session.get(User, user_id)
            return bool(user and user.is_banned)

    def is_admin(self, user_id: int) -> bool:
        """检查数据库角色是否是管理员或审核员"""
        with self.get_session() as session:
            user = session.get(User, user_id)
            return bool(user and user.role in ("admin", "reviewer"))

    def has_admin_role(self, user_id: int) -> bool:
        """True only for role=admin, not for reviewers."""
        with self.get_session() as session:
            user = session.get(User, user_id)
            return bool(user and user.role == "admin")

    def list_user_ids_by_roles(self, roles: tuple[str, ...]) -> list[int]:
        with self.get_session() as session:
            stmt = select(User.id).where(User.role.in_(roles))
            return [int(item) for item in session.execute(stmt).scalars().all()]

    def set_user_role(self, user_id: int, role: str) -> bool:
        if role not in {"user", "reviewer", "admin"}:
            return False
        with self.get_session() as session:
            user = session.get(User, user_id)
            if user is None:
                user = User(id=user_id, role=role)
                session.add(user)
            else:
                user.role = role
            session.commit()
            return True

    def get_user_stats(self, user_id: int):
        """获取用户统计"""
        with self.get_session() as session:
            user = session.get(User, user_id)
            if user is None:
                return None
            return {
                "total": user.total_submissions,
                "approved": user.approved_count,
                "rejected": user.rejected_count,
                "pending": user.total_submissions - user.approved_count - user.rejected_count,
                "approval_rate": user.approval_rate,
                "level": user.level,
            }

    # ==================== 投稿操作 ====================

    def create_submission(
        self,
        user_id: int,
        content_type: str,
        text_content: str = None,
        text_html: str = None,
        media_ids: list = None,
        media_types: list = None,
        is_anonymous: bool = False,
        original_msg_ids: list = None,
    ) -> Submission:
        """创建投稿。封禁或未注册用户会被拒绝，且不会写入投稿。"""
        with self.get_session() as session:
            user = session.get(User, user_id)
            if user is None or user.is_banned:
                raise SubmissionNotAllowed(f"user {user_id} cannot submit")
            limited = self._submission_limit_reason(session, user_id)
            if limited:
                raise SubmissionNotAllowed(limited)
            submission = Submission(
                user_id=user_id,
                content_type=content_type,
                text_content=text_content,
                text_html=text_html,
                media_ids=json.dumps(media_ids) if media_ids else None,
                media_types=json.dumps(media_types) if media_types else None,
                is_anonymous=is_anonymous,
                original_msg_ids=json.dumps(original_msg_ids) if original_msg_ids else None,
            )
            session.add(submission)
            user.total_submissions = (user.total_submissions or 0) + 1
            session.commit()
            session.refresh(submission)
            return self._detach(session, submission)

    def _submission_limit_reason(self, session, user_id: int) -> str | None:
        cap = config.max_pending_submissions
        if cap > 0:
            pending = session.execute(
                select(func.count(Submission.id)).where(
                    Submission.user_id == user_id,
                    Submission.status == STATUS_PENDING,
                )
            ).scalar() or 0
            if pending >= cap:
                return (
                    f"你还有 {pending} 篇投稿正在审核，最多同时 {cap} 篇。"
                    "请等待审核后再提交。"
                )
        cooldown = config.submission_cooldown_seconds
        if cooldown > 0:
            last = session.execute(
                select(func.max(Submission.created_at)).where(Submission.user_id == user_id)
            ).scalar()
            if last is not None:
                remaining = cooldown - (utcnow() - last).total_seconds()
                if remaining > 0:
                    return f"投稿过于频繁，请在 {max(1, int(remaining))} 秒后再试。"
        return None

    def get_user_submissions(self, user_id: int, limit: int = 10) -> list:
        with self.get_session() as session:
            stmt = (
                select(Submission)
                .where(Submission.user_id == user_id)
                .order_by(Submission.created_at.desc())
                .limit(limit)
            )
            rows = list(session.execute(stmt).scalars().all())
            for row in rows:
                session.expunge(row)
            return rows

    def get_submission(self, submission_id: int):
        """获取投稿"""
        with self.get_session() as session:
            return self._detach(session, session.get(Submission, submission_id))

    def get_pending_submissions(self, limit: int = 10) -> list:
        """获取待审核投稿"""
        with self.get_session() as session:
            stmt = (
                select(Submission)
                .where(Submission.status == STATUS_PENDING)
                .order_by(Submission.created_at.asc())
                .limit(limit)
            )
            rows = list(session.execute(stmt).scalars().all())
            for row in rows:
                session.expunge(row)
            return rows

    def get_pending_count(self) -> int:
        """获取待审核数量"""
        with self.get_session() as session:
            stmt = select(func.count(Submission.id)).where(Submission.status == STATUS_PENDING)
            return session.execute(stmt).scalar() or 0

    def _execute_conditional(self, session, statement) -> bool:
        """Apply one conditional UPDATE and report whether this connection changed a row.

        ``changes()`` works on SQLite older than 3.35. The WHERE clause keeps the
        claim atomic: two callers cannot both update the same pending row.
        """
        session.execute(statement, execution_options={"synchronize_session": False})
        changed = session.execute(text("SELECT changes()")).scalar()
        return int(changed or 0) == 1

    def claim_submission(self, submission_id: int, reviewer_id: int) -> bool:
        """原子地把 pending 改为 publishing。同时通过时只有一个调用会成功。"""
        with self.get_session() as session:
            changed = self._execute_conditional(
                session,
                update(Submission)
                .where(Submission.id == submission_id, Submission.status == STATUS_PENDING)
                .values(
                    status=STATUS_PUBLISHING,
                    reviewer_id=reviewer_id,
                    reviewed_at=utcnow(),
                ),
            )
            if not changed:
                session.rollback()
                return False
            session.commit()
            return True

    def release_submission_claim(self, submission_id: int) -> bool:
        """发布失败时把 publishing 退回 pending，避免卡死或重复发布。"""
        with self.get_session() as session:
            changed = self._execute_conditional(
                session,
                update(Submission)
                .where(Submission.id == submission_id, Submission.status == STATUS_PUBLISHING)
                .values(status=STATUS_PENDING, reviewer_id=None, reviewed_at=None),
            )
            if not changed:
                session.rollback()
                return False
            session.commit()
            return True

    def list_publishing_submissions(self, limit: int = 20) -> list:
        """列出卡在发布中的投稿。"""
        with self.get_session() as session:
            stmt = (
                select(Submission)
                .where(Submission.status == STATUS_PUBLISHING)
                .order_by(Submission.reviewed_at.asc())
                .limit(limit)
            )
            rows = list(session.execute(stmt).scalars().all())
            for row in rows:
                session.expunge(row)
            return rows

    def finalize_approval(
        self,
        submission_id: int,
        reviewer_id: int,
        tags: list = None,
        published_msg_id: int = None,
    ) -> bool:
        """在发布成功后把 publishing 改为 approved，并只增加一次通过计数。"""
        with self.get_session() as session:
            changed = self._execute_conditional(
                session,
                update(Submission)
                .where(Submission.id == submission_id, Submission.status == STATUS_PUBLISHING)
                .values(
                    status=STATUS_APPROVED,
                    reviewer_id=reviewer_id,
                    reviewed_at=utcnow(),
                    tags=json.dumps(tags) if tags else None,
                    published_msg_id=published_msg_id,
                ),
            )
            if not changed:
                session.rollback()
                return False
            submission = session.get(Submission, submission_id)
            user = session.get(User, submission.user_id) if submission is not None else None
            if user is not None:
                user.approved_count = (user.approved_count or 0) + 1
                self._update_user_level(user)
            session.commit()
            return True

    def reject_submission(self, submission_id: int, reviewer_id: int, reason: str = None) -> bool:
        """拒绝投稿。只有当前仍是 pending 时才会成功。"""
        with self.get_session() as session:
            changed = self._execute_conditional(
                session,
                update(Submission)
                .where(Submission.id == submission_id, Submission.status == STATUS_PENDING)
                .values(
                    status=STATUS_REJECTED,
                    reviewer_id=reviewer_id,
                    reviewed_at=utcnow(),
                    reject_reason=reason,
                ),
            )
            if not changed:
                session.rollback()
                return False
            submission = session.get(Submission, submission_id)
            user = session.get(User, submission.user_id) if submission is not None else None
            if user is not None:
                user.rejected_count = (user.rejected_count or 0) + 1
            session.commit()
            return True

    def _update_user_level(self, user: User):
        """更新用户等级（根据通过数量）"""
        levels = [0, 5, 15, 30, 50, 100, 200, 500, 1000, 2000, 5000]
        for level, threshold in enumerate(levels):
            if user.approved_count >= threshold:
                user.level = level

    # ==================== 标签操作 ====================

    def get_all_tags(self) -> list:
        """获取所有标签"""
        with self.get_session() as session:
            stmt = select(Tag).order_by(Tag.usage_count.desc(), Tag.id.asc())
            tags = list(session.execute(stmt).scalars().all())
            for tag in tags:
                session.expunge(tag)
            return tags

    def get_tag(self, tag_id: int):
        """按数据库 id 获取标签"""
        with self.get_session() as session:
            return self._detach(session, session.get(Tag, tag_id))

    def get_tags_by_ids(self, tag_ids: list[int]) -> list:
        """按调用方给出的 id 顺序返回标签。"""
        if not tag_ids:
            return []
        with self.get_session() as session:
            tags = list(session.execute(select(Tag).where(Tag.id.in_(tag_ids))).scalars().all())
            for tag in tags:
                session.expunge(tag)
        order = {tag_id: index for index, tag_id in enumerate(tag_ids)}
        return sorted(tags, key=lambda tag: order.get(tag.id, len(order)))

    def add_tag(self, name: str, emoji: str = None):
        """添加标签"""
        with self.get_session() as session:
            existing = session.execute(select(Tag).where(Tag.name == name)).scalar_one_or_none()
            if existing is not None:
                return None
            tag = Tag(name=name, emoji=emoji)
            session.add(tag)
            session.commit()
            session.refresh(tag)
            return self._detach(session, tag)

    def increment_tag_usage(self, tag_names: list[str]):
        """增加标签使用次数"""
        with self.get_session() as session:
            for name in tag_names:
                tag = session.execute(select(Tag).where(Tag.name == name)).scalar_one_or_none()
                if tag is not None:
                    tag.usage_count = (tag.usage_count or 0) + 1
            session.commit()

    # ==================== 拒绝理由操作 ====================

    def get_all_reject_reasons(self) -> list:
        """获取所有拒绝理由"""
        with self.get_session() as session:
            stmt = select(RejectReason).order_by(RejectReason.usage_count.desc(), RejectReason.id.asc())
            reasons = list(session.execute(stmt).scalars().all())
            for reason in reasons:
                session.expunge(reason)
            return reasons

    def get_reject_reason(self, reason_id: int):
        """按数据库 id 获取拒绝理由"""
        with self.get_session() as session:
            return self._detach(session, session.get(RejectReason, reason_id))

    def add_reject_reason(self, text: str) -> RejectReason:
        """添加拒绝理由"""
        with self.get_session() as session:
            reason = RejectReason(text=text)
            session.add(reason)
            session.commit()
            session.refresh(reason)
            return self._detach(session, reason)

    def increment_reason_usage(self, reason_id: int):
        """增加理由使用次数"""
        with self.get_session() as session:
            reason = session.get(RejectReason, reason_id)
            if reason is not None:
                reason.usage_count = (reason.usage_count or 0) + 1
                session.commit()

    # ==================== 统计操作 ====================

    def get_overall_stats(self) -> dict:
        """获取总体统计"""
        with self.get_session() as session:
            def _count(status=None) -> int:
                stmt = select(func.count(Submission.id))
                if status is not None:
                    stmt = stmt.where(Submission.status == status)
                return session.execute(stmt).scalar() or 0

            return {
                "total_users": session.execute(select(func.count(User.id))).scalar() or 0,
                "total_submissions": _count(),
                "pending": _count(STATUS_PENDING),
                "publishing": _count(STATUS_PUBLISHING),
                "approved": _count(STATUS_APPROVED),
                "rejected": _count(STATUS_REJECTED),
            }

    def add_review_notice(self, submission_id: int, chat_id: int, message_id: int) -> None:
        with self.get_session() as session:
            session.add(
                ReviewNotice(
                    submission_id=submission_id,
                    chat_id=chat_id,
                    message_id=message_id,
                )
            )
            session.commit()

    def get_review_notices(self, submission_id: int) -> list:
        with self.get_session() as session:
            stmt = select(ReviewNotice).where(ReviewNotice.submission_id == submission_id)
            rows = list(session.execute(stmt).scalars().all())
            for row in rows:
                session.expunge(row)
            return rows

    def clear_review_notices(self, submission_id: int) -> None:
        with self.get_session() as session:
            session.execute(delete(ReviewNotice).where(ReviewNotice.submission_id == submission_id))
            session.commit()

    def backup_database(self, directory: str | Path, keep: int = 7) -> Path:
        """Copy the live database with SQLite's backup API and keep the newest files."""
        if not self.db_path:
            raise RuntimeError("数据库尚未配置")
        import sqlite3

        target_dir = Path(directory)
        target_dir.mkdir(parents=True, exist_ok=True)
        dest = target_dir / f"bot-{utcnow().strftime('%Y%m%d-%H%M%S-%f')}.db"
        source = sqlite3.connect(self.db_path)
        try:
            copied = sqlite3.connect(dest)
            try:
                source.backup(copied)
            finally:
                copied.close()
        finally:
            source.close()
        files = sorted(target_dir.glob("bot-*.db"), key=lambda path: path.name, reverse=True)
        for old in files[max(1, keep):]:
            old.unlink(missing_ok=True)
        return dest

    def init_default_data(self, tags: list, reject_reasons: list):
        """初始化默认数据"""
        with self.get_session() as session:
            for tag_data in tags:
                if not isinstance(tag_data, dict) or not tag_data.get("name"):
                    continue
                existing = session.execute(
                    select(Tag).where(Tag.name == tag_data["name"])
                ).scalar_one_or_none()
                if existing is None:
                    session.add(Tag(name=tag_data["name"], emoji=tag_data.get("emoji")))

            for reason_text in reject_reasons:
                if not reason_text:
                    continue
                existing = session.execute(
                    select(RejectReason).where(RejectReason.text == reason_text)
                ).scalar_one_or_none()
                if existing is None:
                    session.add(RejectReason(text=reason_text))

            session.commit()


db = Database()
