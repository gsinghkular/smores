import os
import tasks
import unittest

from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from db import database, models, crud


class TestTasks(unittest.TestCase):
    def setUp(self) -> None:
        self.tearDown()
        database.Base.metadata.create_all(database.engine)

    @patch("helpers.get_slack_client", autospec=True)
    def test_cache_channel_members(self, webclient):
        channel_id, team_id, enterprise_id = "test_cid", "test_tid", "test_eid"
        existing_member = "member_4"
        with database.SessionLocal() as db:
            # insert a fake channel into db
            channel = crud.add_channel(db, channel_id, team_id, enterprise_id)
            # check that it works with existing member
            crud.add_member_if_not_exists(db, existing_member, channel)
            # return fake response data simulating slack api
            cursor_resp, no_cursor_resp = MagicMock(), MagicMock()
            cursor_resp.data = {
                "ok": True,
                "members": [
                    "member_1",
                    "member_2",
                ],
                "response_metadata": {"next_cursor": "some_cursor_value"},
            }
            no_cursor_resp.data = {
                "ok": True,
                "members": [
                    "member_3",
                    existing_member,
                ],
                "response_metadata": {"next_cursor": ""},
            }
            client_instance = MagicMock()
            client_instance.conversations_members.side_effect = [
                cursor_resp,
                no_cursor_resp,
            ]
            webclient.return_value = client_instance

            # act
            tasks.cache_channel_members(channel_id, team_id, enterprise_id)

            # assert correct values are inserted
            res = db.query(models.ChannelMembers).count()
            self.assertEquals(res, 4)

    @patch("helpers.get_slack_client", autospec=True)
    def test_generate_and_send_conversations(self, webclient):
        os.environ["CONVERSATION_DAY"] = str(datetime.now().weekday())
        self._insert_fake_channels_and_members("generate_and_send_conv_id", "test_eid")

        client_instance = MagicMock()
        client_instance.conversations_open().data = {
            "ok": True,
            "channel": {"id": "test"},
        }
        webclient.return_value = client_instance
        with database.SessionLocal() as db:
            channel = db.query(models.Channels).filter(models.Channels.channel_id == "channel_0").first()
            channel.last_sent_on = (datetime.utcnow() - timedelta(13)).date()
            channel = db.query(models.Channels).filter(models.Channels.channel_id == "channel_1").first()
            channel.last_sent_on = (datetime.utcnow() - timedelta(14)).date()
            db.commit()

            tasks.match_pairs_periodic()

            conversations = (
                db.query(models.ChannelConversations)
                .where(models.ChannelConversations.team_id == "generate_and_send_conv_id")
                .all()
            )

            self.assertEqual(2, len(conversations))

            three_members_conv = [c for c in conversations if c.channel_id == "channel_1"]
            six_members_conv = [c for c in conversations if c.channel_id == "channel_2"]

            self.assertEqual(1, len(three_members_conv[0].conversations["pairs"]))
            self.assertEqual(3, len(six_members_conv[0].conversations["pairs"]))

    def _insert_fake_channels_and_members(self, team_id, enterprise_id):

        from slack_sdk.oauth.installation_store.models import Installation

        with database.SessionLocal() as db:
            for i in range(3):
                channel_id = f"channel_{i}"
                installation = Installation(
                    user_id="test",
                    team_id=team_id,
                    bot_user_id="bot_id",
                    enterprise_id=enterprise_id,
                    app_id="app",
                )
                database.installation_store.save(installation)
                channel = crud.add_channel(db, channel_id, team_id, enterprise_id)
                for j in range(6):
                    # for ood channels, insert half records to make number of members odd
                    if i % 2 != 0 and j % 2 != 0:
                        continue
                    crud.add_member_if_not_exists(db, f"member_{j}", channel)

    def tearDown(self) -> None:
        database.Base.metadata.drop_all(database.engine)
