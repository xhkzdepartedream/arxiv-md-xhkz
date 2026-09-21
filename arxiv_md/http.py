"""Shared HTTP layer: browser-like request headers + retry with exponential backoff.

arXiv 的 ``e-print`` 口会偶发返回 ``406 Not Acceptable``：同一个请求原样重试通常
就能成功，与 URL、参数、UA 都无关（本机复现：同一个 UA 连续请求 38/40 次返回 200，
失败的那两次连接被直接中断）。Fastly 边缘在连接被中断时也会抛 ``URLError``。
两类都属瞬时错误，适合重试；而 404 之类是确定性错误，必须原样上抛给调用方处理。

因此这里集中两件事：

1. 请求头按浏览器补齐（``Accept`` / ``Accept-Language`` / ``Upgrade-Insecure-Requests``），
   不设 ``Accept-Encoding`` —— 保留 urllib 默认的 ``identity``，否则 e-print 返回的
   gzip 字节流会被再套一层编码。
2. 可重试错误按指数退避重试，重试时轮换一批真实浏览器 UA，并遵循响应里的
   ``Retry-After``。
"""

from __future__ import annotations

import http.client
import random
import sys
import time
from pathlib import Path
from typing import Callable, Mapping
from urllib import error, request

__all__ = [
    "BROWSER_HEADERS",
    "RETRY_STATUSES",
    "USER_AGENT",
    "USER_AGENTS",
    "fetch_bytes",
    "fetch_to_file",
]

# 一批当前常见的浏览器 UA：重试时轮换，避免边缘节点按 UA 把请求归到机器人一侧。
USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
)

# 第一个保持与原实现一致，其它模块仍可用 `USER_AGENT`。
USER_AGENT = USER_AGENTS[0]

BROWSER_HEADERS: Mapping[str, str] = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
}

# 406: arXiv 边缘对部分请求返回；408/425/429: 节流；5xx: 边缘错误。
RETRY_STATUSES: frozenset[int] = frozenset({406, 408, 425, 429, 500, 502, 503, 504})

MAX_ATTEMPTS = 4
BASE_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 8.0

_RETRYABLE_EXCEPTIONS = (
    error.URLError,
    ConnectionError,
    TimeoutError,
    http.client.HTTPException,
)


def _headers(attempt: int, accept: str | None, referer: str | None) -> dict[str, str]:
    headers = dict(BROWSER_HEADERS)
    headers["User-Agent"] = USER_AGENTS[attempt % len(USER_AGENTS)]
    if accept:
        headers["Accept"] = accept
    if referer:
        headers["Referer"] = referer
    return headers


def _retry_after_seconds(exc: BaseException) -> float | None:
    if not isinstance(exc, error.HTTPError):
        return None
    raw = None
    headers = getattr(exc, "headers", None)
    if headers is not None:
        raw = headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(str(raw).strip()))
    except ValueError:
        return None


def _delay_for(attempt: int, exc: BaseException) -> float:
    hinted = _retry_after_seconds(exc)
    if hinted is not None:
        return min(hinted, MAX_DELAY_SECONDS * 2)
    backoff = min(MAX_DELAY_SECONDS, BASE_DELAY_SECONDS * (2 ** attempt))
    return backoff * (0.75 + random.random() * 0.5)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, error.HTTPError):
        return exc.code in RETRY_STATUSES
    return isinstance(exc, _RETRYABLE_EXCEPTIONS)


def _notify(
    url: str, exc: BaseException, attempt: int, delay: float, attempts: int
) -> None:
    if isinstance(exc, error.HTTPError):
        why = f"HTTP {exc.code}"
    else:
        why = f"{type(exc).__name__}: {exc}"
    print(
        f"{url}: {why}；{delay:.1f}s 后重试（第 {attempt + 1}/{attempts} 次尝试）",
        file=sys.stderr,
        flush=True,
    )


def _run(
    url: str,
    consume: Callable[[object], object],
    *,
    timeout: float,
    attempts: int,
    accept: str | None,
    referer: str | None,
    sleep: Callable[[float], None],
) -> object:
    last: BaseException | None = None
    for attempt in range(max(1, attempts)):
        req = request.Request(url, headers=_headers(attempt, accept, referer))
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                return consume(resp)
        except error.HTTPError as exc:
            last = exc
            if not _is_retryable(exc):
                raise
        except Exception as exc:  # noqa: BLE001 - 分类后原样上抛
            last = exc
            if not _is_retryable(exc):
                raise
        if attempt + 1 < max(1, attempts):
            delay = _delay_for(attempt, last)
            _notify(url, last, attempt, delay, max(1, attempts))
            sleep(delay)
    assert last is not None
    raise last


def fetch_bytes(
    url: str,
    *,
    timeout: float = 120,
    accept: str | None = None,
    referer: str | None = None,
    attempts: int = MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    """GET ``url`` 并返回响应体；瞬时错误按退避重试，耗尽后上抛最后一次异常。"""

    def consume(resp) -> bytes:
        return resp.read()

    return _run(
        url,
        consume,
        timeout=timeout,
        attempts=attempts,
        accept=accept,
        referer=referer,
        sleep=sleep,
    )  # type: ignore[return-value]


def fetch_to_file(
    url: str,
    destination: Path,
    *,
    timeout: float = 120,
    accept: str | None = None,
    referer: str | None = None,
    attempts: int = MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """GET ``url`` 流式写入 ``destination``；每次尝试都重新截断文件，避免留下半截内容。"""

    def consume(resp) -> None:
        with destination.open("wb") as handle:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                handle.write(chunk)

    _run(
        url,
        consume,
        timeout=timeout,
        attempts=attempts,
        accept=accept,
        referer=referer,
        sleep=sleep,
    )
