import time
import logging
import helpers

from db import database, crud
from slack_sdk.errors import SlackApiError


logger = logging.getLogger(__name__)


def get_slack_members_list(channel_id, team_id, enterprise_id, exclude_bots=True):
    sc = helpers.get_slack_client(enterprise_id, team_id)
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
                if s := e.response.headers['retry-after']:
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
        "removed_on_slack": set(cached_members) - set(slack_members)
    }