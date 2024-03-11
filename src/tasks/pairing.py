import logging
import random
import os
import time
import src.constants as constants
import src.helpers as helpers
import src.slack_app as slack


from sqlalchemy import and_
from datetime import datetime, timedelta

from src.db import crud, models, database
from task_runner import celery


logger = logging.getLogger(__name__)


@celery.task
def match_pairs_periodic():
    # TODO: allow configuring of which day to start conversations on per channel basis
    # TODO: If another task starts while previous one is already running that can potentially add issues, use mutex to prevent that
    # Instead of start sending messages at sunday night, this makes the day start at 9am EST. TODO: Make it configurable per channel
    today = datetime.utcnow() - timedelta(hours=14)
    if today.weekday() != int(os.environ.get("CONVERSATION_DAY", 0)):
        return

    with database.SessionLocal() as db:
        while True:
            channels = crud.get_channels_eligible_for_pairing(db, 10, today)
            if len(channels) == 0:
                break
            for channel in channels:
                generate_and_send_conversations(channel, db)


@celery.task
def force_generate_conversations(channel_id):
    with database.SessionLocal() as db:
        channel = db.query(models.Channels).where(models.Channels.channel_id == channel_id).first()
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
            enterprise_id = crud.get_enterprise_id(db, intro.team_id, intro.channel_id)
            client = slack.get_slack_client(enterprise_id, intro.team_id)

            all_convos_sent = True
            for conv in intro.conversations["pairs"]:
                if conv["status"] != "GENERATED":
                    continue
                # TODO: handle 429 errors from slack api
                time.sleep(1.2)
                try:
                    response = client.conversations_open(users=conv["pair"])
                    client.chat_postMessage(
                        text=_intro_message(intro.channel_id, conv["pair"]),
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
        midpoint_convos = (
            db.query(models.ChannelConversations)
            .where(
                and_(
                    models.ChannelConversations.conversations.op("->")("midpoint_status") == None,
                    models.ChannelConversations.sent_on == datetime.utcnow().date() - timedelta(8),
                )
            )
            .all()
        )

        for intro in midpoint_convos:
            enterprise_id = crud.get_enterprise_id(db, intro.team_id, intro.channel_id)
            client = slack.get_slack_client(enterprise_id, intro.team_id)

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
    conv_pairs = create_conversation_pairs(channel, db)
    if not conv_pairs:
        return

    client = slack.get_slack_client(channel.enterprise_id, channel.team_id)
    all_convos_sent = True
    for conv_pair in conv_pairs.conversations.get("pairs", []):
        # TODO: handle 429 errors from slack api
        time.sleep(1.2)
        try:
            response = client.conversations_open(users=conv_pair["pair"])
            client.chat_postMessage(
                text=_intro_message(channel.channel_id, conv_pair["pair"]),
                channel=response.data["channel"]["id"],
            )
            conv_pair["status"] = "INTRO_SENT"
            conv_pair["channel_id"] = response.data["channel"]["id"]
        except Exception:
            all_convos_sent = False
            logger.exception("error opening conversation")

    channel.last_sent_on = datetime.utcnow().date()
    if all_convos_sent:
        conv_pairs.conversations["status"] = "INTRO_SENT"
        conv_pairs.sent_on = datetime.utcnow().date()
    else:
        conv_pairs.conversations["status"] = "PARTIALLY_SENT"

    db.commit()


def create_conversation_pairs(channel: models.Channels, db):
    members_list = channel.members_circle
    if not members_list or len(members_list) == 0:
        members_list = crud.get_cached_channel_member_ids(
            db, channel.channel_id, channel.team_id, opted_users_only=True
        )

    installation = database.installation_store.find_installation(
        enterprise_id=channel.enterprise_id, team_id=channel.team_id
    )

    if installation.bot_user_id in members_list:
        members_list.remove(installation.bot_user_id)

    if len(members_list) < 2:
        channel.last_sent_on = datetime.utcnow().date()
        db.commit()
        return

    # For even number of people, the round robin tournament will match everyone at least once
    # by using the circle method: https://en.wikipedia.org/wiki/Round-robin_tournament#Circle_method
    # Because this works with even numbers only, for odd number ones - one member is randomly
    # removed and they are added to one of the pairs generated randomly

    count = len(members_list)
    excluded_member = ""
    if count % 2 != 0:
        random_member_to_remove = random.randrange(count)
        excluded_member = members_list[random_member_to_remove]
        del members_list[random_member_to_remove]

    pairs, members_circle = helpers.round_robin_match(members_list)

    if excluded_member:
        random_pair = random.randrange(count // 2)
        pairs[random_pair].append(excluded_member)
        members_circle.insert(1, excluded_member)

    conversations = crud.save_channel_conversations(db, channel, pairs)
    channel.members_circle = members_circle
    db.commit()
    return conversations


def _intro_message(channel_id, pair):
    organizer = random.choice(pair)
    ice_breaker = random.choice(constants.ICEBREAKERS)
    return f""":wave: You've been matched for a S'mores chat as you're a member of <#{channel_id}>, to get to know your teammates better by talking about anything you like - work, hobbies, interests, or anything else that's on your mind.
<@{organizer}>, you have been randomly chosen as the organizer for this group to schedule a meet, huddle or coffee (if you are located in the same area) for this or next week.

Here's an Ice breaker to get this conversation started: _{ice_breaker}_"""
