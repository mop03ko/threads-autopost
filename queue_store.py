"""Durable queue updates with GitHub SHA compare-and-swap.

Live publishers must share this store. Never retry a Threads publish request
because a GitHub write failed; leave the durable claim for manual reconciliation.
"""
from __future__ import annotations

import base64
import copy
import json
import os
from urllib.parse import quote

import requests


class QueueConflict(RuntimeError):
    pass


class GitHubQueue:
    def __init__(self, repository, token, branch="main", path="queue.json", session=None):
        if not repository or not token:
            raise RuntimeError("Live ажиллагаанд GITHUB_REPOSITORY, GITHUB_TOKEN шаардлагатай.")
        self.base = "https://api.github.com/repos/" + "/".join(quote(p, safe="") for p in repository.split("/"))
        self.branch, self.path = branch, path
        self.session = session or requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def request(self, method, path, **kwargs):
        try:
            response = self.session.request(method, self.base + path, timeout=45, **kwargs)
        except requests.RequestException as exc:
            # Do not include request URLs, headers, or credentials in logs.
            raise RuntimeError("GitHub queue сүлжээний алдаа; нийтлэл дахин бүү явуул.") from exc
        if response.status_code in (409, 422) and method == "PUT":
            raise QueueConflict("Queue өөрчлөгдсөн; шинэ хувилбарыг дахин уншина.")
        if response.status_code >= 400:
            raise RuntimeError(f"GitHub queue HTTP {response.status_code}")
        return response.json()

    def read(self):
        path = "/contents/" + quote(self.path, safe="/")
        metadata = self.request("GET", path, params={"ref": self.branch})
        sha = metadata.get("sha")
        if metadata.get("type") != "file" or not sha:
            raise RuntimeError("Queue metadata дутуу байна.")
        content = metadata
        if not content.get("content") or content.get("encoding") != "base64":
            # Contents omits inline data above 1 MB. Read the exact immutable blob,
            # not the branch again, so content and CAS SHA are always consistent.
            content = self.request("GET", f"/git/blobs/{sha}")
        if content.get("encoding") != "base64":
            raise RuntimeError("Queue encoding буруу байна.")
        queue = json.loads(base64.b64decode(content["content"]).decode("utf-8"))
        if not isinstance(queue, list):
            raise RuntimeError("Queue нь жагсаалт байх ёстой.")
        ids = [p.get("id") for p in queue if isinstance(p, dict)]
        if len(ids) != len(queue) or any(type(i) is not int or i <= 0 for i in ids) or len(set(ids)) != len(ids):
            raise RuntimeError("Queue ID давхардсан эсвэл буруу байна.")
        return queue, sha

    def update(self, mutate, message):
        for _ in range(3):
            queue, sha = self.read()
            before = copy.deepcopy(queue)
            result = mutate(queue)
            if queue == before:
                return result, queue
            encoded = base64.b64encode((json.dumps(queue, ensure_ascii=False, indent=2) + "\n").encode()).decode()
            try:
                self.request("PUT", "/contents/" + quote(self.path, safe="/"), json={
                    "message": message, "content": encoded, "sha": sha, "branch": self.branch,
                })
                return result, queue
            except QueueConflict:
                continue
        raise QueueConflict("Queue-г 3 оролдлогоор хадгалж чадсангүй.")


def remote_store():
    return GitHubQueue(
        os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GITHUB_TOKEN", ""),
        os.environ.get("THREADS_QUEUE_BRANCH", "main"),
    )
