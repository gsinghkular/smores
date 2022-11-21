from db import models, database
from slack_sdk import WebClient

def generate_member_model_list(member_ids, exclude_members, channel_id, team_id):
    members = []
    for member in member_ids:
        if member not in exclude_members:
            members.append(
                models.ChannelMembers(
                    channel_id=channel_id, member_id=member, team_id=team_id
                )
            )

    return members


def get_web_client(enterprise_id: str | None, team_id: str)-> WebClient:
    installation = database.installation_store.find_installation(
        enterprise_id=enterprise_id, team_id=team_id
    )

    return WebClient(token=installation.bot_token)