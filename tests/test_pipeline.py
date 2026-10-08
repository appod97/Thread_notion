import json
import unittest
from dataclasses import replace
from pathlib import Path

from src.main import (
    Config,
    classify_post,
    classify_rules,
    normalize_and_deduplicate,
    notion_existing_ids,
    post_uid,
    report_path,
    run,
)

ROOT = Path(__file__).resolve().parent.parent


class FakeResponse:
    def __init__(self, data, status=200):
        self.data = data
        self.status_code = status

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, notion_pages=None):
        self.notion_pages = list(notion_pages or [{"results": [], "has_more": False}])
        self.saved_pages = []
        self.telegram_messages = []

    def post(self, url, **kwargs):
        if "/data_sources/" in url and url.endswith("/query"):
            return FakeResponse(self.notion_pages.pop(0))
        if url == "https://api.notion.com/v1/pages":
            self.saved_pages.append(kwargs["json"])
            return FakeResponse({"url": "https://notion.so/example"})
        if "api.telegram.org" in url:
            self.telegram_messages.append(kwargs["json"]["text"])
            return FakeResponse({"ok": True})
        raise AssertionError(f"Unexpected POST {url}")

    def get(self, url, **kwargs):
        raise AssertionError(f"Unexpected GET {url}")


class FakeOpenAISession(FakeSession):
    def post(self, url, **kwargs):
        if url == "https://api.openai.com/v1/chat/completions":
            content = json.dumps(
                {"category": "AI · 생성형 AI", "summary": "생성형 AI 동향입니다.", "relevant": True},
                ensure_ascii=False,
            )
            return FakeResponse({"choices": [{"message": {"content": content}}]})
        return super().post(url, **kwargs)


def config(**changes):
    base = Config(
        source_mode="sample",
        dry_run=True,
        sample_path=ROOT / "sample_data" / "posts.json",
        openai_api_key="",
        openai_model="gpt-4.1-mini",
        notion_token="",
        notion_data_source_id="",
        notion_title_property="Name",
        notion_version="2026-03-11",
        telegram_bot_token="",
        telegram_chat_id="",
        archive_url="",
    )
    return replace(base, **changes)


class PipelineTests(unittest.TestCase):
    def test_topic_uses_highest_keyword_score(self):
        self.assertEqual(classify_rules("대학 AI 교육과정 수업"), "교육 · 대학")

    def test_irrelevant(self):
        self.assertIsNone(classify_rules("오늘 날씨가 좋아요"))

    def test_stable_uid_is_16_hex_chars(self):
        post = {"id": "x1"}
        self.assertEqual(post_uid(post), post_uid(post))
        self.assertRegex(post_uid(post), r"^[0-9a-f]{16}$")

    def test_normalize_deduplicates_and_rejects_invalid(self):
        posts = [
            {"id": "1", "text": " AI  뉴스 "},
            {"id": "1", "text": "AI 뉴스"},
            {"id": "2", "text": ""},
            "not-a-post",
        ]
        cleaned, duplicates, invalid = normalize_and_deduplicate(posts)
        self.assertEqual(cleaned, [{"id": "1", "text": "AI 뉴스"}])
        self.assertEqual(duplicates, 1)
        self.assertEqual(invalid, 2)

    def test_openai_classification_contract(self):
        topic, summary, method = classify_post(
            "생성형 AI 소식", config(openai_api_key="test-key"), FakeOpenAISession()
        )
        self.assertEqual(topic, "AI · 생성형 AI")
        self.assertEqual(summary, "생성형 AI 동향입니다.")
        self.assertEqual(method, "openai")

    def test_dry_run_full_pipeline(self):
        self.assertEqual(run(config(), FakeSession()), 0)
        report = json.loads(report_path().read_text(encoding="utf-8"))
        self.assertEqual(report["fetched"], 5)
        self.assertEqual(report["duplicate_batch"], 1)
        self.assertEqual(report["unique"], 4)
        self.assertEqual(report["relevant"], 3)
        self.assertEqual(report["irrelevant"], 1)
        self.assertEqual(report["saved"], 3)
        self.assertEqual(len(report["preview"]), 3)

    def test_notion_existing_ids_follows_pagination(self):
        identifier = "0123456789abcdef"
        pages = [
            {
                "results": [{"properties": {"Name": {"type": "title", "title": [{"plain_text": f"a [ID:{identifier}]"}]}}}],
                "has_more": True,
                "next_cursor": "next",
            },
            {"results": [], "has_more": False},
        ]
        cfg = config(notion_token="token", notion_data_source_id="source")
        self.assertEqual(notion_existing_ids(cfg, FakeSession(pages)), {identifier})

    def test_real_mode_saves_to_notion_and_sends_one_terminal_message(self):
        cfg = config(
            dry_run=False,
            notion_token="token",
            notion_data_source_id="source",
            telegram_bot_token="bot",
            telegram_chat_id="chat",
        )
        session = FakeSession()
        self.assertEqual(run(cfg, session), 0)
        self.assertEqual(len(session.saved_pages), 3)
        self.assertEqual(len(session.telegram_messages), 1)
        self.assertIn("[작업 완료]", session.telegram_messages[0])
        for page in session.saved_pages:
            title = page["properties"]["Name"]["title"][0]["text"]["content"]
            self.assertRegex(title, r"\[ID:[0-9a-f]{16}\]$")


if __name__ == "__main__":
    unittest.main()
