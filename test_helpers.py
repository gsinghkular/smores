import helpers
import unittest


class TestRoundRobin(unittest.TestCase):
    def test_pairs_are_exclusive(self):
        members = [1, 2, 3, 4, 5, 6]
        pairs = helpers.round_robin_match(members, 1)
        self.assertEqual(len(pairs), 3)
        for pair in pairs:
            pair.sort()
        self.assertTrue(pairs[0] != pairs[1])
        self.assertTrue(pairs[1] != pairs[2])
        self.assertTrue(pairs[0] != pairs[2])

    def test_repeated_matches(self):
        members = [1, 2, 3, 4, 5, 6]

        map = {}
        for i in range(5):
            pairs = helpers.round_robin_match(members, i + 1)
            for pair in pairs:
                pair.sort()
                key = "".join(str(x) for x in pair)
                map[key] = True

        # there should be 5 unique pairs
        assert (len(map), 5)

    def test_invalid_arguments(self):
        members = [1, 2, 3, 4, 5, 6]
        # test for invalid match numer
        self.assertRaises(ValueError, helpers.round_robin_match, members, 0)
        self.assertRaises(ValueError, helpers.round_robin_match, members, 6)

        # make sure regular call passes
        pairs = helpers.round_robin_match(members, 5)
        self.assertEqual(len(pairs), 3)

        # test odd number of members
        members.append(7)
        self.assertRaises(ValueError, helpers.round_robin_match, members, 5)
