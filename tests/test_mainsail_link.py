import unittest
from add_mainsail_link import updated_links


class SidebarTests(unittest.TestCase):
    def test_existing_links_preserved_and_repeated_setup_is_idempotent(self):
        original = [{'title': 'Nevermore', 'href': 'http://printer.local:7131', 'target': '_blank', 'position': 85}]
        updated = updated_links(original, 'http://printer.local:7132/')
        self.assertEqual(updated[0], original[0])
        self.assertEqual(len(original), 1)
        self.assertEqual(len(updated), 2)
        self.assertEqual(updated_links(updated, 'http://printer.local:7132/'), updated)
        moved = updated_links(updated, 'http://printer.local:7140/')
        self.assertEqual(len(moved), 2)
        self.assertEqual(moved[1]['href'], 'http://printer.local:7140/')

    def test_invalid_existing_file_is_not_overwritten(self):
        for invalid in ({}, [None], ['text']):
            with self.assertRaises(ValueError):
                updated_links(invalid, 'http://printer.local:7132/')
