from db import models, database
from slack_sdk import WebClient
from typing import List


def generate_member_model_list(member_ids, exclude_members, channel_id, team_id):
    members = []
    for member in member_ids:
        if member not in exclude_members:
            members.append(
                models.ChannelMembers(channel_id=channel_id, member_id=member, team_id=team_id)
            )

    return members


def get_slack_client(enterprise_id: str | None, team_id: str) -> WebClient:
    installation = database.installation_store.find_installation(
        enterprise_id=enterprise_id, team_id=team_id
    )

    return WebClient(token=installation.bot_token)


def round_robin_match(members: List, match_number: int) -> List[List]:
    count = len(members)
    if match_number < 1 or match_number > count - 1:
        raise ValueError("match_numer must be higher than 0 and lower than number of members")

    count = len(members)
    midpoint = count // 2
    if count % 2 != 0:
        raise ValueError("matching is supported for even number of members only")

    members_to_move = count - match_number + 1
    members_rotated_circle = members[0:1] + members[members_to_move:] + members[1:members_to_move]

    pairs = []
    for i in range(midpoint):
        if i >= midpoint:
            break

        pairs.append([members_rotated_circle[i], members_rotated_circle[count - 1 - i]])

    return pairs
