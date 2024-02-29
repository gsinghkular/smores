
from fastapi import FastAPI, Request
from slack_bolt.adapter.fastapi import SlackRequestHandler

from src.slack_app import app


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

