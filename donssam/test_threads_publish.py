import copy
import hashlib
import json
import unittest
from threads_publish import PublishError, publish_parts, validate_queue


class MemoryStore:
    def __init__(self):
        self.data = {}
        self.fail = False

    def read(self, path):
        return copy.deepcopy(self.data.get(path)), None

    def write(self, path, value):
        if self.fail:
            raise PublishError("Persistence unavailable")
        self.data[path] = copy.deepcopy(value)


class FakeAPI:
    def __init__(self, texts):
        self.texts = texts
        self.posts = []
        self.failed = False
        self.containers = {}
        self.media = {}

    def post(self, path, **values):
        self.posts.append((path, values))
        if path == "me/threads":
            key = "c" + str(len(self.containers))
            self.containers[key] = values
            return {"id": key}
        if self.failed:
            raise PublishError("Timeout after publish request")
        key = "p" + str(len(self.media))
        self.media[key] = self.containers[values["creation_id"]]["text"]
        return {"id": key}

    def get(self, path, **values):
        if path in self.containers:
            return {"status": "FINISHED"}
        return {"id": path, "text": self.media[path], "permalink": "https://www.threads.com/@test/post/" + path}


class Safeguards(unittest.TestCase):
    def setUp(self):
        self.news = {"date": "2026-11-02", "cutoff_at": "2026-11-02T07:00:00+09:00",
                     "items": [{"title": str(i)} for i in range(5)]}
        digest = hashlib.sha256(json.dumps(self.news, sort_keys=True, ensure_ascii=False,
                                         separators=(",", ":")).encode()).hexdigest()
        self.parts = ["2026-11-02 07:00 기준\n\n1. 첫째입니다.\n\n2. 둘째입니다.",
                      "3. 셋째입니다.\n\n4. 넷째입니다.", "5. 다섯째입니다."]
        self.queue = {"schema_version": 1, "date": self.news["date"],
                      "cutoff_at": self.news["cutoff_at"], "source_sha256": digest, "parts": self.parts}
        self.profile = {"id": "user"}

    def test_valid_reviewed_queue(self):
        self.assertEqual(validate_queue(self.queue, "2026-11-02", self.news), self.parts)

    def test_stale_and_modified_source_rejected(self):
        with self.assertRaises(PublishError):
            validate_queue(self.queue, "2026-11-03", self.news)
        self.news["items"][0]["title"] = "changed"
        with self.assertRaises(PublishError):
            validate_queue(self.queue, "2026-11-02", self.news)

    def test_length_and_item_split_rejected(self):
        for parts in [["a" * 501, "b", "c"], [self.parts[0], "4. 순서 오류", self.parts[2]],
                      ["1. " + "a" * 450 + "\n2. b", "3. " + "b" * 450 + "\n4. c", "5. " + "c" * 150]]:
            self.queue["parts"] = parts
            with self.assertRaises(PublishError):
                validate_queue(self.queue, "2026-11-02", self.news)

    def test_both_comments_target_root_and_rerun_does_not_post(self):
        store, api = MemoryStore(), FakeAPI(self.parts)
        publish_parts(api, store, self.queue, self.parts, self.profile)
        containers = [v for p, v in api.posts if p == "me/threads"]
        self.assertNotIn("reply_to_id", containers[0])
        self.assertEqual([x["reply_to_id"] for x in containers[1:]], ["p0", "p0"])
        count = len(api.posts)
        publish_parts(api, store, self.queue, self.parts, self.profile)
        self.assertEqual(len(api.posts), count)

    def test_uncertain_publish_blocks_blind_retry(self):
        store, api = MemoryStore(), FakeAPI(self.parts)
        api.failed = True
        with self.assertRaises(PublishError):
            publish_parts(api, store, self.queue, self.parts, self.profile)
        count = len(api.posts)
        api.failed = False
        with self.assertRaises(PublishError):
            publish_parts(api, store, self.queue, self.parts, self.profile)
        self.assertEqual(len(api.posts), count)

    def test_persistence_failure_prevents_publication(self):
        store, api = MemoryStore(), FakeAPI(self.parts)
        store.fail = True
        with self.assertRaises(PublishError):
            publish_parts(api, store, self.queue, self.parts, self.profile)
        self.assertEqual(api.posts, [])

    def test_resume_after_first_post_and_reject_changed_content(self):
        store, api = MemoryStore(), FakeAPI(self.parts)
        publish_parts(api, store, self.queue, self.parts, self.profile)
        path = "donssam/threads_state/2026-11-02.json"
        store.data[path]["posts"][1:] = [{}, {}]
        api.posts.clear()
        publish_parts(api, store, self.queue, self.parts, self.profile)
        self.assertEqual(len([p for p, v in api.posts if p == "me/threads_publish"]), 2)
        with self.assertRaises(PublishError):
            publish_parts(api, store, self.queue, self.parts[:-1] + ["5. 변경"], self.profile)


if __name__ == "__main__":
    unittest.main()
