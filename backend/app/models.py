from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (UniqueConstraint("platform", "video_id", name="uq_videos_platform_video"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(16), index=True)
    video_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text, default="")
    channel: Mapped[str] = mapped_column(String(255), default="")
    channel_id: Mapped[str | None] = mapped_column(String(64))
    followers_or_subs: Mapped[int | None] = mapped_column(Integer)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    thumbnail: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[str | None] = mapped_column(String(16))
    language: Mapped[str | None] = mapped_column(String(16))
    raw_json: Mapped[dict] = mapped_column(JSON, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    snapshots: Mapped[list["VideoSnapshot"]] = relationship(back_populates="video", cascade="all, delete-orphan")


class VideoSnapshot(Base):
    __tablename__ = "video_snapshots"
    __table_args__ = (Index("ix_snapshots_platform_captured", "platform", "captured_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(16))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    views: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[int | None] = mapped_column(Integer)
    # Position in the source chart (YouTube mostPopular order / dataset order).
    rank: Mapped[int] = mapped_column(Integer)

    video: Mapped[Video] = relationship(back_populates="snapshots")


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (Index("ix_analyses_platform_video", "platform", "video_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(16))
    video_id: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(32))
    result_json: Mapped[dict] = mapped_column(JSON)
    confidence: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (UniqueConstraint("platform", "video_id", name="uq_evidence_platform_video"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(16))
    video_id: Mapped[str] = mapped_column(String(64))
    transcript: Mapped[str | None] = mapped_column(Text)
    # "captions" | "title_description" | "dataset"
    transcript_source: Mapped[str | None] = mapped_column(String(32))
    transcript_language: Mapped[str | None] = mapped_column(String(16))
    # List of {"text": str, "likes": int}; never commenter names/ids.
    top_comments_json: Mapped[list] = mapped_column(JSON, default=list)
    comments_status: Mapped[str | None] = mapped_column(String(32))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
