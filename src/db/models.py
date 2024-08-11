from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    ForeignKeyConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.ext.mutable import MutableDict, MutableList

from datetime import datetime

from .database import Base


class Channels(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(String, index=True)
    enterprise_id = Column(String, nullable=True)
    channel_id = Column(String, index=True)
    is_active = Column(Boolean)
    last_sent_on = Column(Date, nullable=True)
    conversation_day = Column(Integer, default=2)
    conversation_frequency_weeks = Column(Integer, nullable=False, server_default="2", default=2)
    send_midpoint_reminder = Column(Boolean, nullable=False, server_default="t", default=True)
    added_on = Column(DateTime, default=datetime.utcnow)
    members_circle = Column(MutableList.as_mutable(ARRAY(String)))

    __table_args__ = (UniqueConstraint("channel_id", "team_id", name="channel_uc"),)


class ChannelMembers(Base):
    __tablename__ = "channel_members"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(String, index=True)
    team_id = Column(String, index=True)
    member_id = Column(String)
    is_opted = Column(Boolean, nullable=False, server_default="t", default=True)
    added_on = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "channel_id", "member_id", "team_id", name="channel_member_uc"
        ),
        ForeignKeyConstraint(
            [channel_id, team_id], [Channels.channel_id, Channels.team_id]
        ),
    )


class ChannelConversations(Base):
    __tablename__ = "channel_conversations"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(String, index=True)
    team_id = Column(String, index=True)
    conversations = Column(MutableDict.as_mutable(JSONB))
    created_on = Column(Date, default=datetime.utcnow)
    sent_on = Column(Date, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            [channel_id, team_id], [Channels.channel_id, Channels.team_id]
        ),
    )
