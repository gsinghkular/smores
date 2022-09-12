import settings
import logging

from slack_bolt.oauth.oauth_settings import OAuthSettings
from slack_bolt.app import App
from db import database


# set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# slack app with OAuth store
app = App(
    logger=logger,
    signing_secret=settings.SLACK_SIGNING_SECRET,
    installation_store=database.installation_store,
    oauth_settings=OAuthSettings(
        client_id=settings.SLACK_CLIENT_ID,
        client_secret=settings.SLACK_CLIENT_SECRET,
        state_store=database.oauth_state_store,
    ),
)
