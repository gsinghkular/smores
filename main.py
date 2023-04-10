import tasks
import logging

from db import crud, database
from slack_app import app

from fastapi import FastAPI, Request
from slack_bolt.adapter.fastapi import SlackRequestHandler
from slack_sdk.errors import SlackApiError


api = FastAPI()

app_handler = SlackRequestHandler(app)


@api.post("/slack/events")
async def endpoint(req: Request):
    return await app_handler.handle(req)


@api.get("/slack/install")
async def install(req: Request):
    return await app_handler.handle(req)


@api.get("/slack/oauth_redirect")
async def oauth_redirect(req: Request):
    return await app_handler.handle(req)


@app.event("member_joined_channel")
def handle_member_joined(body, context):
    event = body["event"]
    tasks.add_member_to_db.delay(event["user"], context.channel_id, context.team_id)


@app.event("member_left_channel")
def handle_member_left(body, context, logger: logging.Logger):
    event = body["event"]
    with database.SessionLocal() as db:
        result = crud.delete_member(
            db, event["user"], context.channel_id, context.team_id
        )
        if result < 1:
            fields = {
                "user": event["user"],
                "channel": context.channel_id,
                "team_id": context.team_id,
            }
            logger.warning("no user deleted", extra=fields)


@app.command("/smores")
def handle_smores_command(
    ack, command, respond, client, context, logger: logging.Logger
):
    try:
        ack()

        action = command["text"].strip().split(" ")[0].lower()
        channel_id = command["channel_id"]

        if action in ["enable", "disable"]:
            _handle_activation(client, respond, action, context, channel_id, logger)
        elif action in ["force_chat"]:
            tasks.force_generate_conversations.delay(channel_id)
            respond("conversations queued to be sent.")
        elif action in ["opt_in", "opt_out"]:
            _handle_member_inclusion(respond, action, context, context.user_id)
        elif action in ["exclude"]:
            member_id = command["text"].strip().split(" ")[-1]
            if _remove_from_channel(member_id, context.channel_id, context.team_id):
                respond(f"User <@{member_id}> as been removed from pairings.")
            else:
                respond(f"User <@{member_id}> not found in the channel pairings.")
        else:
            respond(
                f"Action `{action}` not recognized. Supported actions are `enable | disable | force_chat | exclude | opt_out | opt_in`"
            )
            return

    # TODO: handle exceptions better individually
    except Exception:
        logger.exception("failed to handle command", command)


def _handle_activation(client, respond, action, context, channel_id, logger):
    try:
        client.conversations_info(channel=channel_id)
    except SlackApiError as e:
        if e.response.data["error"] == "channel_not_found":
            respond(
                "For private channels, please add the bot user to the channel first"
            )
        else:
            logger.exception("got error getting channel info")
        return

    # while this works for now, eventually move it to background task
    # as slack requires to respond in under 3 seconds
    with database.SessionLocal() as db:
        channel = crud.get_channel(db, channel_id, context.team_id)

        if channel is None and action == "enable":
            crud.add_channel(db, channel_id, context.team_id, context.enterprise_id)
            tasks.cache_channel_members.delay(
                channel_id, context.team_id, context.enterprise_id
            )
        else:
            channel.is_active = True if action == "enable" else False
            db.commit()

        respond(f"S'mores fireside chats {action}d")


def _handle_member_inclusion(respond, action, context, member_id):
    if action == "opt_out":
        _remove_from_channel(member_id, context.channel_id, context.team_id)
        respond(
            "You are now opted out from pairings in this channel. Use `opt_in` command to rejoin."
        )
    else:
        tasks.add_member_to_db.delay(member_id, context.channel_id, context.team_id)
        respond("You are now opted in for pairings in this channel.")


def _remove_from_channel(member_id, channel_id, team_id):
    with database.SessionLocal() as db:
        member = crud.get_member(db, member_id, channel_id, team_id)
        if not member:
            return False
        crud.delete_member(db, member_id, channel_id, team_id)
        return True
