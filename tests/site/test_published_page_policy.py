from __future__ import annotations

import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

from web.web_security import CONTENT_SECURITY_POLICY

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
PAGES = sorted(DOCS.glob("*.html"))


HEAD_TAGS = {"base", "link", "meta", "noscript", "script", "style", "template", "title"}
INERT_TAGS = {"noscript", "template"}


class _Head(HTMLParser):

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_head = False
        self.head_closed = False
        self.inert_depth = 0
        self.policies: list[str] = []
        self.before_policy: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "head" and not self.head_closed:
            self.in_head = True
            return
        if self.in_head and self.inert_depth == 0 and tag not in HEAD_TAGS:
            self.in_head, self.head_closed = False, True
        if not self.in_head:
            return
        if tag in INERT_TAGS:
            self.inert_depth += 1
            return
        if self.inert_depth:
            return
        values = {name.lower(): value or "" for name, value in attrs}
        if tag == "meta" and values.get("http-equiv", "").lower() == "content-security-policy":
            self.policies.append(values.get("content", ""))
        elif tag in ("script", "link", "style") and not self.policies:
            self.before_policy.append(tag)

    handle_startendtag = handle_starttag

    def handle_endtag(self, tag):
        if tag in INERT_TAGS and self.inert_depth:
            self.inert_depth -= 1
        elif tag == "head" and self.in_head and self.inert_depth == 0:
            self.in_head, self.head_closed = False, True


def lxml_head_policies(html: str) -> list[str]:
    import lxml.html

    head = lxml.html.fromstring(html).find("head")
    if head is None:
        return []
    return [node.get("content", "") for node in head
            if node.tag == "meta" and (node.get("http-equiv") or "").lower() == "content-security-policy"]


CONNECT_SOURCES = {"live.html": "'self' https://raw.githubusercontent.com https://*.workers.dev https://*.deno.dev"}


def policy_problems(html: str, connect: str = "'self'") -> list[str]:
    head = _Head()
    head.feed(html)
    if len(head.policies) != 1:
        return [f"{len(head.policies)} thẻ CSP trong <head>, cần đúng 1"]
    problems = []
    if head.before_policy:
        problems.append(f"thẻ CSP đứng sau {head.before_policy}: phần ấy không được bảo vệ")
    expected = CONTENT_SECURITY_POLICY.replace("connect-src 'self'", f"connect-src {connect}")
    if head.policies[0] != expected:
        problems.append(f"chính sách khác bản chung: {head.policies[0]!r}")
    return problems


def test_there_are_pages_to_check():
    assert len(PAGES) >= 40, "docs/ gần như rỗng: phép kiểm tham số hoá sẽ không chạy lần nào"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_published_page_declares_the_shared_content_security_policy(page: Path):
    html = page.read_text(encoding="utf-8")
    assert policy_problems(html, CONNECT_SOURCES.get(page.name, "'self'")) == []
    head = _Head()
    head.feed(html)
    assert lxml_head_policies(html) == head.policies


def test_the_policy_rule_itself_catches_a_missing_late_or_loosened_policy():
    ok = f'<meta content="{CONTENT_SECURITY_POLICY}" http-equiv="Content-Security-Policy"/>'
    page = "<html><head>{}</head><body><script>x()</script></body></html>".format
    assert policy_problems(page(ok + '<script src="a.js"></script>')) == []
    worker = "'self' https://w.example"
    live = CONTENT_SECURITY_POLICY.replace("connect-src 'self'", f"connect-src {worker}")
    assert policy_problems(page(f'<meta http-equiv="Content-Security-Policy" content="{live}">'), worker) == []
    assert policy_problems(page(f'<meta http-equiv="Content-Security-Policy" content="{live}">')) != []
    wide = CONTENT_SECURITY_POLICY.replace("connect-src 'self'", "connect-src *")
    assert policy_problems(page(f'<meta http-equiv="Content-Security-Policy" content="{wide}">')) != []
    assert policy_problems(page('<script src="a.js"></script>')) != []
    assert policy_problems(page('<script src="a.js"></script>' + ok)) != []
    loose = CONTENT_SECURITY_POLICY.replace("object-src 'none'", "object-src *")
    assert policy_problems(page(f'<meta http-equiv="Content-Security-Policy" content="{loose}">')) != []
    assert policy_problems(page(ok + ok)) != []
    assert policy_problems(f"<html><head></head><body>{ok}</body></html>") != []
    assert policy_problems(f"<html><head><title>t</title><body>{ok}</body></html>") != []
    assert policy_problems(f"<html><head><div></div>{ok}</head><body></body></html>") != []
    assert policy_problems(f"<html><head><title>t</title>{ok}</head><body></body></html>") == []
    assert policy_problems(f"<html><head><template>{ok}</template></head><body></body></html>") != []
    assert policy_problems(f"<html><head><noscript>{ok}</noscript></head><body></body></html>") != []
    assert policy_problems(f"<html><head><template><div></div></template>{ok}</head><body></body></html>") == []


def test_github_pages_keeps_files_that_start_with_an_underscore():
    marker = DOCS / ".nojekyll"
    assert marker.is_file()
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "docs/.nojekyll"], cwd=ROOT,
                             capture_output=True, text=True, check=False)
    if tracked.returncode != 0 and "not a git repository" in tracked.stderr:
        pytest.skip("không phải bản checkout git")
    assert tracked.returncode == 0, tracked.stderr
