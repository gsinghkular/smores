import logging
import time
import src.helpers as helpers
import src.slack_app as slack

from slack_sdk.errors import SlackApiError

from src.db import crud, models, database
from task_runner import celery


logger = logging.getLogger(__name__)


@celery.task(autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def cache_channel_members(channel_id, team_id, enterprise_id):
    sc = slack.get_slack_client(enterprise_id, team_id)
    with database.SessionLocal() as db:
        members_data = sc.conversations_members(channel=channel_id, limit=200).data
        local_members = crud.get_cached_channel_member_ids(db, channel_id, team_id)
        members = helpers.generate_member_model_list(
            members_data["members"], local_members, channel_id, team_id
        )

        next_cursor = members_data["response_metadata"]["next_cursor"]
        while next_cursor:
            members_data = sc.conversations_members(channel=channel_id, limit=200, cursor=next_cursor).data
            members += helpers.generate_member_model_list(
                members_data["members"], local_members, channel_id, team_id
            )

            next_cursor = members_data["response_metadata"]["next_cursor"]

        db.bulk_save_objects(members)
        db.commit()

        # run the task to check if any of the users were bots and remove them
        exclude_bots_from_cached_users.delay(channel_id, team_id, enterprise_id)


@celery.task
def exclude_bots_from_cached_users(channel_id: str, team_id: str, enterprise_id: str):
    with database.SessionLocal() as db:
        sc = slack.get_slack_client(enterprise_id, team_id)
        members = crud.get_cached_channel_member_ids(db, channel_id, team_id)
        for member in members:
            user_data = sc.users_info(user=member).data
            if user_data["user"]["is_bot"]:
                # TODO: handle 429 errors from slack api
                time.sleep(1.2)
                crud.delete_member(db, member, channel_id, team_id)


@celery.task(autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def add_member_to_db(member_id: str, channel_id: str, team_id: str):
    with database.SessionLocal() as db:
        channel = crud.get_channel(db, channel_id, team_id)
        if not channel:
            return
        sc = slack.get_slack_client(channel.enterprise_id, team_id)
        user_data = sc.users_info(user=member_id).data
        fields = {
            "user": member_id,
            "channel": channel_id,
            "team_id": team_id,
        }
        if user_data["user"]["is_bot"]:
            logger.warn("user is a bot", extra=fields)
            return
        result = crud.add_member_if_not_exists(db, member_id, channel)
        if result < 1:
            logger.warning("no user inserted", extra=fields)
        else:
            sc.chat_postMessage(
                channel=member_id,
                text=f"You're opted into S'mores chat since you joined the channel <#{channel_id}>. If you do not want to participate in pairings while staying the channel then you can run command `/smores opt_out` in the channel.",
            )


@celery.task
def remove_disabled_users():
    with database.SessionLocal() as db:
        channels: list[models.Channels] = db.query(models.Channels).all()
        removed_members_in_channel = {}

        for c in channels:
            time.sleep(1)
            try:
                removed_members_in_channel[c.channel_id] = get_members_drift(c.channel_id, c.team_id, c.enterprise_id)
            except SlackApiError:
                logger.exception("Error getting members drift")

        for c in channels:
            diff = removed_members_in_channel.get(c.channel_id, {})
            for removed in diff.get('removed_on_slack', []):
                crud.delete_member(db, removed, c.channel_id, c.team_id)


def get_slack_members_list(channel_id, team_id, enterprise_id, exclude_bots=True):
    sc = slack.get_slack_client(enterprise_id, team_id)
    members_data = sc.conversations_members(channel=channel_id, limit=200).data

    members = members_data["members"]
    next_cursor = members_data["response_metadata"]["next_cursor"]
    while next_cursor:
        members_data = sc.conversations_members(channel=channel_id, limit=200, cursor=next_cursor).data
        members += members_data["members"]

        next_cursor = members_data["response_metadata"]["next_cursor"]

    bots = []
    if exclude_bots:
        i = 0
        while i < len(members):
            member = members[i]
            try:
                user_data = sc.users_info(user=member).data
                if user_data["user"]["is_bot"]:
                    bots.append(member)
            except SlackApiError as e:
                if s := e.response.headers["retry-after"]:
                    time.sleep(2 * int(s))
                else:
                    time.sleep(10)
                continue
            except Exception as e:
                logger.exception(e)
                return

            i += 1

        members = set(members) - set(bots)

    return members


def get_members_drift(channel_id, team_id, enterprise_id):
    slack_members = get_slack_members_list(channel_id, team_id, enterprise_id)

    with database.SessionLocal() as db:
        cached_members = crud.get_cached_channel_member_ids(db, channel_id, team_id)

    return {
        "new_on_slack": set(slack_members) - set(cached_members),
        "removed_on_slack": set(cached_members) - set(slack_members),
    }
