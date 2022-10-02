import logging
import random
import os
import time

from sqlalchemy import or_, and_
from datetime import datetime, timedelta

from db import crud, models, database
from task_runner import celery
from slack_sdk import WebClient


logger = logging.getLogger(__name__)


@celery.task
def cache_channel_members(channel_id, team_id, enterprise_id):
    installation = database.installation_store.find_installation(
        enterprise_id=enterprise_id, team_id=team_id
    )

    client = WebClient(token=installation.bot_token)

    with database.SessionLocal() as db:
        members_data = client.conversations_members(channel=channel_id, limit=200).data
        next_cursor = members_data["response_metadata"]["next_cursor"]
        local_members = (
            db.query(models.ChannelMembers.member_id)
            .where(models.ChannelMembers.channel_id == channel_id)
            .all()
        )
        local_members_list = [m for (m,) in local_members]

        members = _generate_members_list(
            members_data["members"], local_members_list, channel_id, team_id
        )
        db.bulk_save_objects(members)
        while next_cursor:
            members_data = client.conversations_members(
                channel=channel_id, limit=1, cursor=next_cursor
            ).data
            members = _generate_members_list(
                members_data["members"], local_members_list, channel_id, team_id
            )
            db.bulk_save_objects(members)
            next_cursor = members_data["response_metadata"]["next_cursor"]

        db.commit()


@celery.task
def match_pairs_periodic():
    # TODO: allow configuring of which day to start conversations on per channel basis
    if datetime.now().weekday() != int(os.environ.get("CONVERSATION_DAY", 1)):
        return

    with database.SessionLocal() as db:
        skip = 0
        limit = 10
        while True:
            two_weeks_ago_date = datetime.utcnow() - timedelta(14)
            channels = (
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
                .offset(skip)
                .limit(limit)
                .all()
            )
            if len(channels) == 0:
                break
            for channel in channels:
                generate_and_send_conversations(channel, db)


@celery.task
def force_generate_conversations(channel_id):
    with database.SessionLocal() as db:
        channel = (
            db.query(models.Channels)
            .where(models.Channels.channel_id == channel_id)
            .first()
        )
        if channel is None:
            return

        generate_and_send_conversations(channel, db)


@celery.task
def send_failed_intros():
    with database.SessionLocal() as db:
        pending_intros = (
            db.query(models.ChannelConversations)
            .where(
                and_(
                    models.ChannelConversations.sent_on == None,
                    models.ChannelConversations.conversations["status"].astext == "PARTIALLY_SENT",
                )
            )
            .all()
        )
        for intro in pending_intros:
            enterprise_id = db.query(models.Channels.enterprise_id).where(
                and_(
                    models.Channels.team_id == intro.team_id,
                    models.Channels.channel_id == intro.channel_id
                )
            ).first()

            installation = database.installation_store.find_installation(
                enterprise_id=enterprise_id[0], team_id=intro.team_id
            )

            client = WebClient(token=installation.bot_token)

            all_convos_sent = True
            for conv in intro.conversations["pairs"]:
                if conv["status"] != "GENERATED":
                    continue
                # TODO: handle 429 errors from slack api
                time.sleep(1.2)
                try:
                    response = client.conversations_open(users=conv["pair"])
                    client.chat_postMessage(
                        text="hello :wave:! You've been matched for a S'mores chat. Find some time on your calendar and make it happen!",
                        channel=response.data["channel"]["id"],
                    )
                    conv["status"] = "INTRO_SENT"
                    conv["channel_id"] = response.data["channel"]["id"]
                except Exception:
                    all_convos_sent = False
                    logger.exception("error opening conversation")

            if all_convos_sent:
                intro.conversations["status"] = "INTRO_SENT"
                intro.sent_on = datetime.utcnow().date()
            else:
                intro.conversations["status"] = "PARTIALLY_SENT"

            db.commit()


@celery.task
def send_midpoint_reminder():
    with database.SessionLocal() as db:
        midpoint_convos = db.query(models.ChannelConversations).where(
                and_(
                    models.ChannelConversations.conversations.op("->")("midpoint_status") == None,
                    models.ChannelConversations.sent_on == datetime.utcnow().date() - timedelta(8),
                )
            ).all()

        for intro in midpoint_convos:
            client = _get_web_client(db, intro.team_id, intro.channel_id)

            all_convos_sent = True
            for conv in intro.conversations["pairs"]:
                if conv["status"] != "INTRO_SENT" or "midpoint_sent_on" in conv:
                    continue
                time.sleep(1.2)
                try:
                    client.chat_postMessage(
                        text=":wave: Mid point reminder - if you haven't met yet, make it happen!",
                        channel=conv["channel_id"],
                    )
                    conv["midpoint_sent_on"] = datetime.utcnow().date().isoformat()
                except Exception:
                    all_convos_sent = False
                    logger.exception("error sending midpoint")

            
            intro.conversations["midpoint_status"] = "SENT" if all_convos_sent else "PARTIALLY_SENT"
            db.commit()

def generate_and_send_conversations(channel, db):
    members = (
        db.query(models.ChannelMembers.member_id)
        .where(models.ChannelMembers.channel_id == channel.channel_id)
        .all()
    )
    members_list = [m for (m,) in members]

    installation = database.installation_store.find_installation(
        enterprise_id=channel.enterprise_id, team_id=channel.team_id
    )
    if installation.bot_user_id in members_list:
        members_list.remove(installation.bot_user_id)
    if len(members_list) < 2:
        return []

    random.shuffle(members_list)

    count = len(members_list)
    pairs = []
    for i in range(count // 2):
        pairs.append([members_list[i], members_list[count - i - 1]])

    if count % 2 != 0:
        last_pair = pairs[len(pairs) - 1]
        last_pair.append(members_list[count // 2])
        pairs[len(pairs) - 1] = last_pair

    convos = _save_new_conversations(pairs, channel, db)
    client = WebClient(token=installation.bot_token)

    all_convos_sent = True
    for conv in convos.conversations["pairs"]:
        # TODO: handle 429 errors from slack api
        time.sleep(1.2)
        try:
            response = client.conversations_open(users=conv["pair"])
            client.chat_postMessage(
                text="hello :wave:! You've been matched for a S'mores chat. Find some time on your calendar and make it happen!",
                channel=response.data["channel"]["id"],
            )
            conv["status"] = "INTRO_SENT"
            conv["channel_id"] = response.data["channel"]["id"]
        except Exception:
            all_convos_sent = False
            logger.exception("error opening conversation")

    channel.last_sent_on = datetime.utcnow().date()
    if all_convos_sent:
        convos.conversations["status"] = "INTRO_SENT"
        convos.sent_on = datetime.utcnow().date()
    else:
        convos.conversations["status"] = "PARTIALLY_SENT"

    db.commit()


def _save_new_conversations(pairs, channel, db):
    conversations = []
    for pair in pairs:
        conversation = {"status": "GENERATED", "pair": pair}
        conversations.append(conversation)

    conversations_data = {"status": "GENERATED", "pairs": conversations}
    return crud.add_conversation(
        db, channel.channel_id, channel.team_id, conversations_data
    )


def _generate_members_list(member_ids, exclude_members, channel_id, team_id):
    members = []
    for member in member_ids:
        if member not in exclude_members:
            members.append(
                models.ChannelMembers(
                    channel_id=channel_id, member_id=member, team_id=team_id
                )
            )

    return members


def _get_web_client(db, team_id, channel_id):
    enterprise_id = (
        db.query(models.Channels.enterprise_id)
        .where(
            and_(
                models.Channels.team_id == team_id,
                models.Channels.channel_id == channel_id,
            )
        )
        .first()
    )

    installation = database.installation_store.find_installation(
        enterprise_id=enterprise_id[0], team_id=team_id
    )

    return WebClient(token=installation.bot_token)