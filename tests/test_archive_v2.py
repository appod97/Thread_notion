import unittest
from unittest.mock import patch
from src.archive_v2 import canonical_url, sample_records, classify, run

class ArchiveV2Tests(unittest.TestCase):
    def test_canonical(self):
        self.assertEqual(canonical_url('https://example.org/x/?utm_source=y'), 'https://example.org/x')
    def test_dedup(self):
        records=sample_records()
        self.assertEqual(records[0]['id'],records[1]['id'])
    def test_classify(self):
        self.assertEqual(classify('AI assistant','new LLM'), 'AI · 생성형 AI')
    def test_safe_run(self):
        with patch.dict('os.environ',{'ARCHIVE_V2_MODE':'sample','DRY_RUN':'true','ENABLE_ARCHIVE_WRITES':'false'}):
            self.assertEqual(run(),0)
