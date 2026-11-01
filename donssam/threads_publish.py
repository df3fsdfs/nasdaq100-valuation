"""Publish a reviewed daily queue, with durable progress before every publish.

Credentials come only from Actions secrets. Never log provider response bodies.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BASE = "https://graph.threads.net/v1.0/"
KST = ZoneInfo("Asia/Seoul")


class PublishError(RuntimeError):
    pass


def request_json(method, url, token, values=None):
    headers = {"Authorization": "Bearer " + token, "User-Agent": "Donssaem-Threads/1"}
    body = None
    if values:
        encoded = urlencode(values)
        if method == "GET":
            url += ("&" if "?" in url else "?") + encoded
        else:
            body = encoded.encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        with urlopen(Request(url, data=body, headers=headers, method=method), timeout=35) as response:
            return json.load(response)
    except HTTPError as error:
        # Only numeric codes and the endpoint path are safe to log.
        codes = {}
        safe_message = ""
        try:
            failure = json.loads(error.read()).get("error", {})
            safe_message = str(failure.get("message", "")).replace(token, "[redacted]")
            safe_message = re.sub(r"[A-Za-z0-9_\\-]{16,}", "[redacted]", safe_message)[:300]
            codes = {key: failure[key] for key in ("code", "error_subcode")
                     if isinstance(failure.get(key), int)}
        except (ValueError, OSError):
            pass
        endpoint = urlsplit(url).path
        raise PublishError("Provider HTTP " + str(error.code) + " at " + endpoint
                           + " codes=" + json.dumps(codes) + " reason=" + safe_message) from None
    except (URLError, TimeoutError, ValueError, OSError):
        raise PublishError("Provider network/response error; no automatic publish retry") from None


class Threads:
    def __init__(self, token):
        self.token = token

    def get(self, path, **values):
        return request_json("GET", BASE + path, self.token, values)

    def post(self, path, **values):
        return request_json("POST", BASE + path, self.token, values)

    def verify(self):
        print("Verifying Threads profile")
        profile = self.get("me", fields="id,username")
        print("Verifying Threads token scopes")
        details = self.get("debug_token", input_token=self.token).get("data", {})
        required = {"threads_basic", "threads_content_publish"}
        if not details.get("is_valid") or not required.issubset(set(details.get("scopes", []))):
            raise PublishError("Threads token invalid or missing threads_basic/threads_content_publish")
        expected_app = os.environ.get("THREADS_APP_ID", "").strip()
        # The Threads debugger may omit app_id. An absent optional field is not a mismatch.
        if expected_app and details.get("app_id") and str(details["app_id"]).strip() != expected_app:
            raise PublishError("Threads token belongs to a different app")
        if details.get("user_id") and str(details["user_id"]) != str(profile.get("id")):
            raise PublishError("Token/profile account mismatch")
        expiry = details.get("expires_at", 0)
        if expiry and expiry < time.time() + 86400:
            raise PublishError("Threads token expires within 24h; replace THREADS_ACCESS_TOKEN")
        return {"id": str(profile["id"]), "username": profile["username"], "expires_at": expiry}


class StateStore:
    def __init__(self):
        self.repo = os.environ["GITHUB_REPOSITORY"]
        self.token = os.environ["GITHUB_TOKEN"]

    def read(self, path):
        url = "https://api.github.com/repos/" + self.repo + "/contents/" + path + "?ref=main"
        req = Request(url, headers={"Authorization": "Bearer " + self.token, "User-Agent": "Donssaem-Threads/1"})
        try:
            with urlopen(req, timeout=30) as response:
                obj = json.load(response)
        except HTTPError as error:
            if error.code == 404:
                return None, None
            raise PublishError("State read HTTP " + str(error.code)) from None
        except (URLError, TimeoutError, OSError):
            raise PublishError("State read failed") from None
        return json.loads(base64.b64decode(obj["content"])), obj["sha"]

    def write(self, path, data):
        # Single publisher workflow + fresh content SHA; never overwrite concurrent state.
        _, sha = self.read(path)
        content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        payload = {"message": "Record Threads publishing progress", "branch": "main",
                   "content": base64.b64encode(content.encode()).decode()}
        if sha:
            payload["sha"] = sha
        url = "https://api.github.com/repos/" + self.repo + "/contents/" + path
        req = Request(url, data=json.dumps(payload).encode(), method="PUT", headers={
            "Authorization": "Bearer " + self.token, "User-Agent": "Donssaem-Threads/1",
            "Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=30) as response:
                json.load(response)
        except (HTTPError, URLError, TimeoutError, OSError):
            raise PublishError("Progress persistence failed; stop to prevent duplicate publication") from None


def validate_queue(queue, today, news):
    if queue.get("schema_version") != 1 or queue.get("date") != today:
        raise PublishError("Queue date/schema mismatch")
    if queue.get("cutoff_at") != today + "T07:00:00+09:00":
        raise PublishError("Queue cutoff mismatch")
    if news.get("date") != today or news.get("cutoff_at") != queue["cutoff_at"]:
        raise PublishError("Source news date/cutoff mismatch")
    source_hash = hashlib.sha256(json.dumps(news, sort_keys=True, ensure_ascii=False,
                                          separators=(",", ":")).encode()).hexdigest()
    if queue.get("source_sha256") != source_hash:
        raise PublishError("Queue does not match the reviewed source news")
    parts = queue.get("parts", [])
    if len(parts) != 3 or any(not isinstance(p, str) or not p.strip() or len(p) > 500 for p in parts):
        raise PublishError("Need exactly 3 nonempty parts, at most 500 characters each")
    if sum(map(len, parts)) > 1000 or any("**" in p or "\ue200" in p for p in parts):
        raise PublishError("Threads text exceeds 1000 characters or contains internal markup")
    if len(set(parts)) != 3:
        raise PublishError("Duplicate text parts")
    if len(news.get("items", [])) != 5:
        raise PublishError("Three-part 2/2/1 layout requires five verified items")
    for part, numbers in zip(parts, ([1, 2], [3, 4], [5])):
        found = [int(n) for n in re.findall(r"(?m)^([1-5])\.\s", part)]
        if found != numbers:
            raise PublishError("Expected item split: body 1-2, reply1 3-4, reply2 5")
    if today not in parts[0] or "07:00" not in parts[0]:
        raise PublishError("Body must show date and 07:00 cutoff")
    return parts


def publish_parts(api, store, queue, parts, profile):
    path = "donssam/threads_state/" + queue["date"] + ".json"
    digest = hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()
    state, _ = store.read(path)
    if state is None:
        state = {"date": queue["date"], "account_id": profile["id"], "parts_sha256": digest,
                 "posts": [{}, {}, {}]}
        store.write(path, state)
    if state["account_id"] != profile["id"] or state["parts_sha256"] != digest:
        raise PublishError("Existing publication differs; do not replace or repost")
    for index, text in enumerate(parts):
        post = state["posts"][index]
        if post.get("id"):
            continue
        if post.get("publish_started"):
            raise PublishError("Previous publish outcome uncertain; reconcile existing post before retry")
        if not post.get("container_id"):
            values = {"media_type": "TEXT", "text": text}
            if index:
                # Both comments belong directly to the same root post.
                values["reply_to_id"] = state["posts"][0]["id"]
            container = api.post("me/threads", **values)
            post["container_id"] = str(container["id"])
            store.write(path, state)
        ready = False
        for attempt in range(6):
            status = api.get(post["container_id"], fields="status").get("status")
            if status == "FINISHED":
                ready = True
                break
            if status != "IN_PROGRESS":
                raise PublishError("Container not publishable: " + str(status))
            if attempt < 5:
                time.sleep(30)
        if not ready:
            raise PublishError("Container still processing; saved progress for next run")
        post["publish_started"] = True
        store.write(path, state)  # Must succeed before public mutation.
        result = api.post("me/threads_publish", creation_id=post["container_id"])
        post["id"] = str(result["id"])
        store.write(path, state)
        # Read back; saved ID prevents duplicate publication if this request fails.
        confirmed = api.get(post["id"], fields="id,text,permalink")
        if str(confirmed.get("id")) != post["id"] or confirmed.get("text") != text:
            raise PublishError("Published text readback mismatch")
        post["permalink"] = confirmed.get("permalink")
        post["verified"] = True
        store.write(path, state)
        print("Verified published part", index + 1)
    # Re-check all saved posts, including posts recovered from interrupted runs.
    for post, text in zip(state["posts"], parts):
        confirmed = api.get(post["id"], fields="id,text,permalink")
        if confirmed.get("text") != text:
            raise PublishError("Published text readback mismatch")
        post["verified"] = True
        post["permalink"] = confirmed.get("permalink")
    state["completed"] = True
    state["root_url"] = state["posts"][0].get("permalink")
    store.write(path, state)
    print("Threads publication complete:", state["root_url"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    token = os.environ.get("THREADS_ACCESS_TOKEN", "")
    if not token:
        raise PublishError("Missing GitHub secret THREADS_ACCESS_TOKEN")
    api = Threads(token)
    profile = api.verify()
    print("Authenticated Threads account: @" + profile["username"])
    if profile["expires_at"]:
        print("Token expiry:", datetime.fromtimestamp(profile["expires_at"], KST).isoformat())
    store = StateStore()
    binding_path = "donssam/threads_state/account.json"
    binding, _ = store.read(binding_path)
    if binding and binding["id"] != profile["id"]:
        raise PublishError("Account changed; update account binding deliberately before posting")
    if not binding:
        store.write(binding_path, profile)
    if args.check_only:
        print("Authentication and publishing scopes verified; no public post created")
        return
    today = datetime.now(KST).date().isoformat()
    queue_path = Path("donssam/threads_queue") / (today + ".json")
    if not queue_path.exists():
        print("No reviewed queue for today; no public post created")
        return
    if datetime.now(KST).hour < 7:
        raise PublishError("Before today's 07:00 cutoff")
    queue = json.loads(queue_path.read_text())
    news = json.loads((Path("donssam/news") / (today + ".json")).read_text())
    parts = validate_queue(queue, today, news)
    publish_parts(api, store, queue, parts, profile)


if __name__ == "__main__":
    try:
        main()
    except PublishError as error:
        print("ERROR:", error, file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("ERROR: unexpected failure; stop and inspect saved progress before retry", file=sys.stderr)
        sys.exit(1)
