"""Compile and apply ordered rules to outgoing text segments."""

from dataclasses import dataclass
from fnmatch import fnmatchcase
import re
from typing import Callable
from urllib.parse import urlsplit

URL = r"(?:https?://[^\s<>\"'\x60\[\]）】。，！？；、]+|(?:[\w-]+\.)+[a-z]{2,}(?::\d+)?(?:/[^\s<>\"'\x60\[\]）】。，！？；、]*)?)"
LINK = re.compile(
    rf"\[(?P<label>[^\]\n]+)\]\((?P<markdown>{URL})\)|(?<![\w@.])(?P<plain>{URL})",
    re.IGNORECASE,
)


def host_of(url: str) -> str:
    try:
        host = urlsplit(url if "://" in url else "//" + url).hostname
        return (host or "").rstrip(".").encode("idna").decode("ascii").lower()
    except (ValueError, UnicodeError):
        return ""


@dataclass(frozen=True)
class Rule:
    allow: tuple[str, ...]
    deny: tuple[str, ...]
    stop: bool
    replace: Callable[[str], tuple[str, int]]

    def applies(self, umo: str) -> bool:
        return not any(fnmatchcase(umo, p) for p in self.deny) and (
            not self.allow or any(fnmatchcase(umo, p) for p in self.allow)
        )


def link_replacer(raw: dict, replacement: str):
    domains = frozenset(host_of(domain.strip()) for domain in raw.get("domains", []))
    if not domains or "" in domains:
        raise ValueError("请填写有效的域名列表")
    subdomains = raw.get("subdomains", True)
    whitelist = raw.get("domain_mode") == "allow"
    keep_label = raw.get("keep_label", True)

    def replace(text: str) -> tuple[str, int]:
        count = 0

        def handle(match: re.Match) -> str:
            nonlocal count
            plain = match.group("plain")
            url = plain or match.group("markdown")
            clean = url.rstrip(".,;:!?")
            while clean.endswith(")") and clean.count(")") > clean.count("("):
                clean = clean[:-1]
            host = host_of(clean)
            parts = host.split(".")
            listed = host in domains or (
                subdomains and any(".".join(parts[i:]) in domains for i in range(1, len(parts)))
            )
            if not host or listed == whitelist:
                return match.group()
            count += 1
            if plain:
                return replacement + url[len(clean):]
            return match.group("label") if keep_label else replacement

        return LINK.sub(handle, text), count

    return replace


def compile_rule(raw: dict) -> Rule:
    kind = raw["__template_key"]
    replacement = raw.get("replacement", "")
    if kind == "link":
        replace = link_replacer(raw, replacement)
    else:
        if kind == "text":
            words = sorted(set(filter(None, raw.get("words", []))), key=lambda w: (-len(w), w))
            expression = "|".join(map(re.escape, words))
        elif kind == "regex":
            expression = raw.get("pattern", "")
        else:
            raise ValueError("未知规则类型")
        if not expression:
            raise ValueError("请填写待匹配内容")
        try:
            pattern = re.compile(expression, 0 if raw.get("case_sensitive") else re.IGNORECASE)
        except re.error as exc:
            raise ValueError("正则表达式无效") from exc

        def replace(text: str) -> tuple[str, int]:
            count = 0

            def handle(match: re.Match) -> str:
                nonlocal count
                if not match.group():
                    return ""
                count += 1
                return replacement

            return pattern.sub(handle, text), count

    return Rule(
        tuple(p.strip() for p in raw.get("umo_allow", []) if p.strip()),
        tuple(p.strip() for p in raw.get("umo_deny", []) if p.strip()),
        raw.get("stop_on_match", False),
        replace,
    )
