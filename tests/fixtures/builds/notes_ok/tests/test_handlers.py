"""Candidate-authored test (supplementary evidence only)."""

import unittest


class HandlersImport(unittest.TestCase):
    def test_handlers_are_callable(self) -> None:
        import notes_app.handlers as handlers

        self.assertTrue(callable(handlers.add_note))
        self.assertTrue(callable(handlers.count_notes))


if __name__ == "__main__":
    unittest.main()
