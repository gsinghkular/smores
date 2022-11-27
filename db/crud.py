from typing import List
from sqlalchemy import delete, and_, or_
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from datetime import datetime, timedelta

from . import models


def get_channel(db: Session, channel_id: str, team_id: str):
    return (
        db.query(models.Channels)
        .filter(
            and_(
                models.Channels.channel_id == channel_id,
                models.Channels.team_id == team_id,
            )
        )
        .first()
    )


def get_channels_eligible_for_pairing(db: Session, limit: int = 10):
    # TODO: instead of being default of 2 weeks, allow per channel configuration of frequency of pairing
    two_weeks_ago_date = datetime.utcnow() - timedelta(14)
    return (
        db.query(models.Channels)
        .where(
            and_(
                models.Channels.is_active == True,
                or_(
                    models.Channels.last_sent_on == None,
                    models.Channels.last_sent_on <= two_weeks_ago_date.date(),
                ),
            )
        )
        .limit(limit)
        .all()
    )


def add_channel(db: Session, channel_id: str, team_id: str, enterprise_id: str):
    channel = models.Channels(
        channel_id=channel_id,
        team_id=team_id,
        enterprise_id=enterprise_id,
        is_active=True,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def get_member(
    db: Session, member_id: str, channel_id: str, team_id: str
) -> models.ChannelMembers:
    condition = [
        models.ChannelMembers.member_id == member_id,
        models.ChannelMembers.channel_id == channel_id,
        models.ChannelMembers.team_id == team_id,
    ]
    return db.query(models.ChannelMembers).where(and_(*condition)).first()


def add_member_if_not_exists(
    db: Session, member_id: str, channel_id: str, team_id: str
):
    insert_query = (
        insert(models.ChannelMembers)
        .values(member_id=member_id, channel_id=channel_id, team_id=team_id)
        .on_conflict_do_nothing(index_elements=["member_id", "channel_id", "team_id"])
    )
    result = db.execute(insert_query)
    db.commit()

    return result.rowcount


def delete_member(db: Session, member_id: str, channel_id: str, team_id: str):
    condition = [
        models.ChannelMembers.member_id == member_id,
        models.ChannelMembers.channel_id == channel_id,
        models.ChannelMembers.team_id == team_id,
    ]
    delete_query = delete(models.ChannelMembers).where(and_(*condition))
    result = db.execute(delete_query)
    db.commit()

    return result.rowcount


def get_cached_channel_member_ids(
    db: Session, channel_id: str, team_id: str, opted_users_only: bool = False
) -> List[str]:
    condition = [
        models.ChannelMembers.channel_id == channel_id,
        models.ChannelMembers.team_id == team_id,
    ]
    if opted_users_only:
        condition.append(models.ChannelMembers.is_opted == True)
    local_members = (
        db.query(models.ChannelMembers.member_id).where(and_(*condition)).all()
    )
    return [m for (m,) in local_members]


def save_channel_conversations(db: Session, channel, pairs):
    conversation_pairs = []
    for pair in pairs:
        conversation_pair = {"status": "GENERATED", "pair": pair}
        conversation_pairs.append(conversation_pair)

    conversations = {"status": "GENERATED", "pairs": conversation_pairs}
    conversation = models.ChannelConversations(
        channel_id=channel.channel_id,
        team_id=channel.team_id,
        conversations=conversations,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def get_enterprise_id(db, team_id, channel_id):
    return (
        db.query(models.Channels.enterprise_id)
        .where(
            and_(
                models.Channels.team_id == team_id,
                models.Channels.channel_id == channel_id,
            )
        )
        .first()
    )[0]
