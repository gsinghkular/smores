import helpers
import unittest


class TestRoundRobin(unittest.TestCase):
    def test_pairs_are_exclusive(self):
        members = [1, 2, 3, 4, 5, 6]
        pairs, circle = helpers.round_robin_match(members)
        self.assertEqual(len(pairs), 3)
        for pair in pairs:
            pair.sort()
        self.assertTrue(pairs[0] != pairs[1])
        self.assertTrue(pairs[1] != pairs[2])
        self.assertTrue(pairs[0] != pairs[2])
        self.assertTrue(circle == [1, 6, 2, 3, 4, 5])

    def test_repeated_matches(self):
        members = [1, 2, 3, 4, 5, 6]

        map = {}
        for i in range(5):
            pairs, members = helpers.round_robin_match(members)
            for pair in pairs:
                pair.sort()
                key = "".join(str(x) for x in pair)
                map[key] = True

        # there should be 15 unique pairs i.e. 3 pairs from each of the 5 times
        self.assertEqual(len(map), 15)

    def test_invalid_arguments(self):
        members = [1, 2, 3, 4, 5, 6]

        # make sure regular call passes
        pairs, _ = helpers.round_robin_match(members)
        self.assertEqual(len(pairs), 3)

        # test odd number of members
        members.append(7)
        self.assertRaises(ValueError, helpers.round_robin_match, members)
