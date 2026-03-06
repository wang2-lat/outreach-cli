"""
GitHub intelligent auto-reply module.

Monitors GitHub notifications and generates AI-powered replies using
DeepSeek or Anthropic Claude APIs.  Uses only the standard library
(urllib / json) so no extra dependencies are needed.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class RateLimitError(Exception):
    """Raised when the GitHub API rate limit is exhausted."""

    def __init__(self, reset_timestamp: int):
        self.reset_timestamp = reset_timestamp
        super().__init__(f"Rate limit exceeded. Resets at {reset_timestamp}")


class GitHubAPIError(Exception):
    """Generic GitHub API error."""


class AIProviderError(Exception):
    """Error when calling the AI provider API."""


# ---------------------------------------------------------------------------
# GitHub API client
# ---------------------------------------------------------------------------

class GitHubClient:
    """Thin wrapper around the GitHub REST API."""

    BASE = "https://api.github.com"

    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._username: Optional[str] = None

    # -- helpers ----------------------------------------------------------

    def _request(self, method: str, url: str, body: dict = None,
                 extra_headers: dict = None) -> dict | str | list:
        if not url.startswith("http"):
            url = f"{self.BASE}{url}"

        headers = {**self.headers, **(extra_headers or {})}
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req) as resp:
                remaining = resp.headers.get("X-RateLimit-Remaining")
                if remaining is not None and int(remaining) == 0:
                    reset = int(resp.headers.get("X-RateLimit-Reset", 0))
                    raise RateLimitError(reset)

                raw = resp.read().decode()
                if not raw:
                    return {}
                content_type = resp.headers.get("Content-Type", "")
                if "json" in content_type:
                    return json.loads(raw)
                return raw
        except urllib.error.HTTPError as exc:
            remaining = exc.headers.get("X-RateLimit-Remaining") if exc.headers else None
            if exc.code == 403 and remaining is not None and int(remaining) == 0:
                reset = int(exc.headers.get("X-RateLimit-Reset", 0))
                raise RateLimitError(reset) from exc
            err_body = exc.read().decode() if exc.fp else str(exc)
            raise GitHubAPIError(f"HTTP {exc.code}: {err_body}") from exc

    @property
    def username(self) -> str:
        if self._username is None:
            user = self._request("GET", "/user")
            self._username = user["login"]
        return self._username

    # -- public API -------------------------------------------------------

    def get_notifications(self, participating: bool = True) -> list[dict]:
        params = f"?participating={'true' if participating else 'false'}"
        return self._request("GET", f"/notifications{params}")

    def get_thread_context(self, notification: dict) -> dict:
        """Gather full context for a notification thread."""
        subject = notification["subject"]
        subject_type = subject["type"]           # Issue, PullRequest, Commit …
        subject_url = subject["url"]             # API url
        repo_full = notification["repository"]["full_name"]

        result = {
            "repo": repo_full,
            "subject_type": subject_type,
            "title": subject["title"],
            "body": "",
            "comments": [],
            "diff": None,
            "readme_snippet": None,
            "url": subject_url,
            "html_url": "",
            "comments_url": "",
        }

        # Fetch the subject itself (issue / PR)
        try:
            item = self._request("GET", subject_url)
            result["body"] = item.get("body") or ""
            result["html_url"] = item.get("html_url", "")
            comments_url = item.get("comments_url", "")
            result["comments_url"] = comments_url
        except GitHubAPIError:
            return result

        # Fetch recent comments (last 10)
        if result["comments_url"]:
            try:
                comments = self._request(
                    "GET", f"{result['comments_url']}?per_page=10&sort=created&direction=desc"
                )
                result["comments"] = [
                    {"user": c["user"]["login"], "body": c["body"]}
                    for c in (comments if isinstance(comments, list) else [])
                ]
            except GitHubAPIError:
                pass

        # Fetch PR diff
        if subject_type == "PullRequest":
            try:
                diff = self._request(
                    "GET", subject_url,
                    extra_headers={"Accept": "application/vnd.github.v3.diff"},
                )
                if isinstance(diff, str):
                    result["diff"] = diff[:4000]
            except GitHubAPIError:
                pass

        # Fetch repo README snippet
        try:
            readme = self._request(
                "GET", f"/repos/{repo_full}/readme",
                extra_headers={"Accept": "application/vnd.github.raw"},
            )
            if isinstance(readme, str):
                result["readme_snippet"] = readme[:2000]
        except GitHubAPIError:
            pass

        return result

    def search_issues(self, query: str, per_page: int = 30,
                      sort: str = "created", order: str = "desc") -> list[dict]:
        """Search GitHub issues via the Search API."""
        encoded_q = urllib.parse.quote(query)
        url = f"/search/issues?q={encoded_q}&sort={sort}&order={order}&per_page={per_page}"
        resp = self._request("GET", url)
        return resp.get("items", []) if isinstance(resp, dict) else []

    def get_issue_context(self, issue_item: dict) -> dict:
        """Build a context dict from a search-result issue item.

        Output format matches get_thread_context() so AIProvider can consume it.
        """
        repo_full = issue_item.get("repository", {}).get("full_name", "")
        if not repo_full and "/" in (issue_item.get("repository_url") or ""):
            # Extract from repository_url like https://api.github.com/repos/owner/repo
            repo_full = "/".join(issue_item["repository_url"].rsplit("/", 2)[-2:])

        result = {
            "repo": repo_full,
            "subject_type": "Issue",
            "title": issue_item.get("title", ""),
            "body": issue_item.get("body") or "",
            "comments": [],
            "diff": None,
            "readme_snippet": None,
            "url": issue_item.get("url", ""),
            "html_url": issue_item.get("html_url", ""),
            "comments_url": issue_item.get("comments_url", ""),
        }

        # Fetch recent comments
        if result["comments_url"]:
            try:
                comments = self._request(
                    "GET", f"{result['comments_url']}?per_page=10&sort=created&direction=desc"
                )
                result["comments"] = [
                    {"user": c["user"]["login"], "body": c["body"]}
                    for c in (comments if isinstance(comments, list) else [])
                ]
            except GitHubAPIError:
                pass

        # Fetch repo README snippet
        if repo_full:
            try:
                readme = self._request(
                    "GET", f"/repos/{repo_full}/readme",
                    extra_headers={"Accept": "application/vnd.github.raw"},
                )
                if isinstance(readme, str):
                    result["readme_snippet"] = readme[:2000]
            except GitHubAPIError:
                pass

        return result

    def post_comment(self, comments_url: str, body: str):
        self._request("POST", comments_url, body={"body": body})

    def mark_notification_read(self, thread_id: str):
        self._request("PATCH", f"/notifications/threads/{thread_id}")


# ---------------------------------------------------------------------------
# AI provider
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a thoughtful software developer replying to a GitHub notification.
Repo: {repo}
{readme_context}

Rules:
- Be concise but substantive. No filler.
- If it's an issue: acknowledge the problem, suggest concrete next steps or ask clarifying questions.
- If it's a PR: review the diff, note specific things that look good or need attention.
- If it's a comment thread: read all prior comments to understand the conversation before replying.
- Match the language of the conversation (English, Chinese, etc.).
- Never claim to be a human. End your reply with:
  > 🤖 This reply was generated by an AI assistant.
- If you truly cannot add value (e.g. the thread is already resolved), reply with exactly "SKIP" and nothing else.
"""


class AIProvider:
    """Call DeepSeek or Anthropic to generate a reply."""

    def __init__(self, provider: str = "deepseek", api_key: str = None):
        self.provider = provider.lower()
        if self.provider == "anthropic":
            self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            self.api_url = "https://api.anthropic.com/v1/messages"
        else:
            self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
            self.api_url = "https://api.deepseek.com/chat/completions"

        if not self.api_key:
            env_name = "ANTHROPIC_API_KEY" if self.provider == "anthropic" else "DEEPSEEK_API_KEY"
            raise AIProviderError(f"{env_name} environment variable is not set")

    def generate_reply(self, context: dict, style: str = "helpful",
                       system_prompt_template: str = None) -> str:
        readme_context = ""
        if context.get("readme_snippet"):
            readme_context = f"Repo description (README excerpt):\n{context['readme_snippet'][:300]}"

        template = system_prompt_template or SYSTEM_PROMPT
        system = template.format(repo=context["repo"], readme_context=readme_context)
        system += f"\nReply style: {style}"

        user_msg = self._build_user_message(context)

        if self.provider == "anthropic":
            return self._call_anthropic(system, user_msg)
        return self._call_deepseek(system, user_msg)

    # -- message builder --------------------------------------------------

    @staticmethod
    def _build_user_message(ctx: dict) -> str:
        parts = [
            f"[{ctx['subject_type']}] {ctx['title']}",
            f"\nBody:\n{ctx['body'][:3000]}" if ctx["body"] else "",
        ]

        if ctx.get("comments"):
            parts.append("\n--- Recent comments (newest first) ---")
            for c in ctx["comments"][:8]:
                parts.append(f"@{c['user']}: {c['body'][:500]}")

        if ctx.get("diff"):
            parts.append(f"\n--- Code diff (truncated) ---\n{ctx['diff']}")

        return "\n".join(parts)

    # -- provider calls ---------------------------------------------------

    def _call_deepseek(self, system: str, user_msg: str) -> str:
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            "max_tokens": 1024,
            "temperature": 0.7,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        return self._http_post(self.api_url, payload, headers,
                               extract=lambda d: d["choices"][0]["message"]["content"])

    def _call_anthropic(self, system: str, user_msg: str) -> str:
        payload = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "system": system,
            "messages": [{"role": "user", "content": user_msg}],
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        return self._http_post(self.api_url, payload, headers,
                               extract=lambda d: d["content"][0]["text"])

    @staticmethod
    def _http_post(url: str, payload: dict, headers: dict, extract) -> str:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                body = json.loads(resp.read().decode())
                return extract(body).strip()
        except urllib.error.HTTPError as exc:
            err = exc.read().decode() if exc.fp else str(exc)
            raise AIProviderError(f"AI API error {exc.code}: {err}") from exc


# ---------------------------------------------------------------------------
# Reply orchestrator
# ---------------------------------------------------------------------------

AI_FOOTER = "This reply was generated by an AI assistant"


class ReplyOrchestrator:
    """Fetch notifications, generate AI replies, and post them."""

    def __init__(self, db, github_token: str, ai_provider: str = "deepseek",
                 ai_api_key: str = None, style: str = "helpful",
                 excluded_repos: list[str] = None, dry_run: bool = False):
        self.db = db
        self.github = GitHubClient(github_token)
        self.ai = AIProvider(ai_provider, ai_api_key)
        self.ai_provider_name = ai_provider
        self.style = style
        self.excluded_repos = set(excluded_repos or [])
        self.dry_run = dry_run

    def process_notifications(self) -> list[dict]:
        """Process all pending notifications. Returns a list of result dicts."""
        notifications = self.github.get_notifications(participating=True)
        results = []

        for notif in notifications:
            repo = notif["repository"]["full_name"]
            subject_type = notif["subject"]["type"]

            # Only handle Issues, PRs, and Commits
            if subject_type not in ("Issue", "PullRequest", "Commit"):
                continue

            # Excluded repos
            if repo in self.excluded_repos:
                results.append({"repo": repo, "status": "excluded"})
                continue

            try:
                result = self._process_single(notif)
                results.append(result)
            except RateLimitError:
                raise  # propagate so watch loop can handle it
            except Exception as exc:
                results.append({
                    "repo": repo,
                    "title": notif["subject"]["title"],
                    "status": "error",
                    "error": str(exc),
                })

        return results

    def _process_single(self, notif: dict) -> dict:
        subject_url = notif["subject"]["url"]
        repo = notif["repository"]["full_name"]
        title = notif["subject"]["title"]
        thread_id = notif["id"]

        # Deduplication
        if self.db.has_replied(subject_url):
            self.github.mark_notification_read(thread_id)
            return {"repo": repo, "title": title, "status": "already_replied"}

        # Fetch context
        ctx = self.github.get_thread_context(notif)

        # Bot loop prevention: skip if last comment is ours
        if ctx["comments"]:
            latest_user = ctx["comments"][0]["user"]
            if latest_user == self.github.username:
                self.github.mark_notification_read(thread_id)
                return {"repo": repo, "title": title, "status": "self_skip"}

            # Skip if last comment has AI footer
            if AI_FOOTER in (ctx["comments"][0].get("body") or ""):
                self.github.mark_notification_read(thread_id)
                return {"repo": repo, "title": title, "status": "ai_skip"}

        # Generate reply
        reply_text = self.ai.generate_reply(ctx, self.style)

        if reply_text.strip() == "SKIP":
            self.github.mark_notification_read(thread_id)
            return {"repo": repo, "title": title, "status": "skipped"}

        if self.dry_run:
            return {
                "repo": repo, "title": title,
                "status": "dry_run", "reply": reply_text,
            }

        # Post comment
        comments_url = ctx.get("comments_url")
        if not comments_url:
            # Construct from subject URL
            comments_url = subject_url + "/comments"
        self.github.post_comment(comments_url, reply_text)

        # Mark as read
        self.github.mark_notification_read(thread_id)

        # Save to database
        summary = title[:100]
        self.db.add_reply(
            github_url=subject_url,
            repo=repo,
            event_type=notif["subject"]["type"],
            context_summary=summary,
            reply_text=reply_text,
            ai_provider=self.ai_provider_name,
        )

        return {"repo": repo, "title": title, "status": "replied", "reply": reply_text}

    def watch(self, interval_minutes: int = 5, on_cycle=None):
        """Continuously check notifications. Call on_cycle(results) after each round."""
        while True:
            try:
                results = self.process_notifications()
                if on_cycle:
                    on_cycle(results)
            except RateLimitError as exc:
                wait = max(exc.reset_timestamp - int(time.time()) + 5, 10)
                if on_cycle:
                    on_cycle([{"status": "rate_limited", "wait_seconds": wait}])
                time.sleep(wait)
                continue
            except KeyboardInterrupt:
                break

            time.sleep(interval_minutes * 60)


# ---------------------------------------------------------------------------
# Scout: proactive issue search and reply
# ---------------------------------------------------------------------------

SCOUT_SYSTEM_PROMPT = """\
You are a helpful and knowledgeable developer who enjoys helping others solve \
problems on GitHub — a "热心群众" (enthusiastic community helper).

You are reviewing an open issue in the repo: {repo}
{readme_context}

Rules:
- Only reply if you can provide genuinely useful, actionable help.
- Suggest concrete solutions, code snippets, debugging steps, or relevant docs.
- If it's a question, answer it clearly and directly.
- If it's a bug report, suggest possible causes and workarounds.
- Be respectful and encouraging. People are volunteering their time.
- Keep your reply concise: aim for 3-10 sentences.
- Match the language of the issue (English, Chinese, etc.).
- DO NOT give generic advice. Be specific to the problem.
- DO NOT advertise, self-promote, or link to unrelated projects.
- If you cannot add value (unclear issue, already resolved, needs domain \
  knowledge you lack, or already has good answers), reply with exactly \
  "SKIP" and nothing else.
- End your reply with:
  > 🤖 This suggestion was generated by an AI assistant. Please verify before applying.
"""

DEFAULT_SCOUT_QUERIES = [
    'is:issue is:open label:"help wanted" created:>{date}',
    'is:issue is:open label:question created:>{date}',
    'is:issue is:open label:bug created:>{date}',
    'is:issue is:open label:"good first issue" created:>{date}',
]


class OutreachScanner:
    """Proactively search GitHub for issues and offer helpful replies."""

    def __init__(self, db, github_token: str, ai_provider: str = "deepseek",
                 ai_api_key: str = None, style: str = "helpful",
                 search_queries: list[str] = None,
                 max_replies_per_hour: int = 5,
                 max_replies_per_day: int = 20,
                 max_comments_on_issue: int = 5,
                 max_issue_age_hours: int = 48,
                 max_per_repo_per_day: int = 2,
                 cooldown_seconds: int = 30,
                 dry_run: bool = False):
        self.db = db
        self.github = GitHubClient(github_token)
        self.ai = AIProvider(ai_provider, ai_api_key)
        self.ai_provider_name = ai_provider
        self.style = style
        self.search_queries = search_queries or DEFAULT_SCOUT_QUERIES
        self.max_replies_per_hour = max_replies_per_hour
        self.max_replies_per_day = max_replies_per_day
        self.max_comments_on_issue = max_comments_on_issue
        self.max_issue_age_hours = max_issue_age_hours
        self.max_per_repo_per_day = max_per_repo_per_day
        self.cooldown_seconds = cooldown_seconds
        self.dry_run = dry_run

    def _date_cutoff(self) -> str:
        """ISO date string for max_issue_age_hours ago."""
        dt = datetime.now(timezone.utc) - timedelta(hours=self.max_issue_age_hours)
        return dt.strftime("%Y-%m-%d")

    def scan_once(self) -> list[dict]:
        """Run one scan cycle across all queries. Returns result dicts."""
        # Check daily cap
        daily = self.db.get_scout_replies_in_window(hours=24)
        if daily >= self.max_replies_per_day:
            return [{"status": "daily_limit", "count": daily}]

        date_str = self._date_cutoff()
        results = []

        for raw_query in self.search_queries:
            query = raw_query.replace("{date}", date_str)

            try:
                issues = self.github.search_issues(query, per_page=20)
            except RateLimitError:
                raise
            except GitHubAPIError as exc:
                results.append({"status": "search_error", "query": query, "error": str(exc)})
                continue

            for issue in issues:
                try:
                    r = self._process_issue(issue, query)
                    if r:
                        results.append(r)
                except RateLimitError:
                    raise
                except Exception as exc:
                    results.append({
                        "repo": issue.get("repository", {}).get("full_name", "?"),
                        "title": issue.get("title", ""),
                        "status": "error",
                        "error": str(exc),
                    })

        return results

    def _process_issue(self, issue: dict, query: str) -> Optional[dict]:
        api_url = issue.get("url", "")
        html_url = issue.get("html_url", "")
        title = issue.get("title", "")
        number = issue.get("number", 0)
        repo_data = issue.get("repository", {})
        repo = repo_data.get("full_name", "")
        if not repo and "repository_url" in issue:
            repo = "/".join(issue["repository_url"].rsplit("/", 2)[-2:])

        # --- filters ---

        # Deduplication
        if self.db.has_scouted(api_url):
            return None

        # Comment count filter
        if issue.get("comments", 0) > self.max_comments_on_issue:
            return None

        # Hourly cap
        hourly = self.db.get_scout_replies_in_window(hours=1)
        if hourly >= self.max_replies_per_hour:
            return {"repo": repo, "title": title, "status": "hourly_limit"}

        # Per-repo cap
        if repo and self.db.get_scout_repo_replies_in_window(repo, hours=24) >= self.max_per_repo_per_day:
            return None

        # --- fetch context & generate reply ---

        ctx = self.github.get_issue_context(issue)

        # Self-comment check
        for c in ctx.get("comments", []):
            if c["user"] == self.github.username:
                self.db.add_scout_issue(
                    api_url, html_url, repo, number, title,
                    None, "skipped", self.ai_provider_name, query)
                return None

        reply_text = self.ai.generate_reply(
            ctx, self.style, system_prompt_template=SCOUT_SYSTEM_PROMPT)

        if reply_text.strip() == "SKIP":
            self.db.add_scout_issue(
                api_url, html_url, repo, number, title,
                None, "skipped", self.ai_provider_name, query)
            return {"repo": repo, "title": title, "status": "skipped", "html_url": html_url}

        if self.dry_run:
            self.db.add_scout_issue(
                api_url, html_url, repo, number, title,
                reply_text, "dry_run", self.ai_provider_name, query)
            return {
                "repo": repo, "title": title, "html_url": html_url,
                "status": "dry_run", "reply": reply_text,
            }

        # Post comment
        comments_url = ctx.get("comments_url") or (api_url + "/comments")
        self.github.post_comment(comments_url, reply_text)

        # Record
        self.db.add_scout_issue(
            api_url, html_url, repo, number, title,
            reply_text, "replied", self.ai_provider_name, query)

        # Cooldown
        time.sleep(self.cooldown_seconds)

        return {
            "repo": repo, "title": title, "html_url": html_url,
            "status": "replied", "reply": reply_text,
        }

    def watch(self, interval_minutes: int = 10, on_cycle=None):
        """Continuously scan for issues to help with."""
        while True:
            try:
                results = self.scan_once()
                if on_cycle:
                    on_cycle(results)
            except RateLimitError as exc:
                wait = max(exc.reset_timestamp - int(time.time()) + 5, 10)
                if on_cycle:
                    on_cycle([{"status": "rate_limited", "wait_seconds": wait}])
                time.sleep(wait)
                continue
            except KeyboardInterrupt:
                break

            time.sleep(interval_minutes * 60)
