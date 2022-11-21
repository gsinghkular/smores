import tasks
import unittest
from unittest.mock import patch, MagicMock
from db import database, models, crud


class TestTasks(unittest.TestCase):
    def setUp(self) -> None:
        self.tearDown()
        database.Base.metadata.create_all(database.engine)

    @patch("helpers.get_web_client", autospec=True)
    def test_cache_channel_members(self, webclient):
        channel_id, team_id, enterprise_id = "test_cid", "test_tid", "test_eid"
        existing_member = "member_4"
        with database.SessionLocal() as db:
            # insert a fake channel into db
            crud.add_channel(db, channel_id, team_id, enterprise_id)
            # check that it works with existing member
            crud.add_member_if_not_exists(db, existing_member, channel_id, team_id)
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
            client_instance.conversations_members.side_effect = [cursor_resp, no_cursor_resp]
            webclient.return_value = client_instance
            
            # act
            tasks.cache_channel_members(channel_id, team_id, enterprise_id)
            
            # assert correct values are inserted
            res = db.query(models.ChannelMembers).count()
            self.assertEquals(res, 4)

    def tearDown(self) -> None:
        database.Base.metadata.drop_all(database.engine)
