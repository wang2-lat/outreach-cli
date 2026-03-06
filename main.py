import os
import typer
from typing import List
from rich.console import Console
from rich.table import Table
from database import Database
from reports import generate_weekly_report, suggest_template

app = typer.Typer(help="Track and optimize your community outreach efforts")
console = Console()
db = Database()

@app.command()
def add(
    url: str = typer.Argument(..., help="Post URL with UTM parameters"),
    platform: str = typer.Option(..., "--platform", "-p", help="Platform name (reddit, twitter, etc)"),
    title: str = typer.Option(..., "--title", "-t", help="Post title or description"),
):
    """Add a new outreach post to track"""
    post_id = db.add_post(url, platform, title)
    console.print(f"[green]✓[/green] Added post #{post_id}: {title}")
    console.print(f"[dim]Track clicks with: python main.py update {post_id} --clicks N[/dim]")

@app.command()
def update(
    post_id: int = typer.Argument(..., help="Post ID to update"),
    clicks: int = typer.Option(None, "--clicks", "-c", help="Number of clicks"),
    conversions: int = typer.Option(None, "--conversions", "-v", help="Number of conversions"),
):
    """Update click and conversion metrics for a post"""
    if clicks is None and conversions is None:
        console.print("[red]Error:[/red] Provide at least --clicks or --conversions")
        raise typer.Exit(1)
    
    db.update_metrics(post_id, clicks, conversions)
    console.print(f"[green]✓[/green] Updated post #{post_id}")

@app.command()
def list(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of posts to show"),
):
    """List recent outreach posts"""
    posts = db.get_recent_posts(limit)
    
    if not posts:
        console.print("[yellow]No posts tracked yet. Add one with 'add' command.[/yellow]")
        return
    
    table = Table(title="Recent Outreach Posts")
    table.add_column("ID", style="cyan")
    table.add_column("Platform", style="magenta")
    table.add_column("Title", style="white")
    table.add_column("Clicks", justify="right", style="green")
    table.add_column("Conversions", justify="right", style="yellow")
    table.add_column("CTR", justify="right", style="blue")
    table.add_column("Date", style="dim")
    
    for post in posts:
        ctr = f"{post['ctr']:.1f}%" if post['ctr'] else "N/A"
        table.add_row(
            str(post['id']),
            post['platform'],
            post['title'][:40] + "..." if len(post['title']) > 40 else post['title'],
            str(post['clicks']),
            str(post['conversions']),
            ctr,
            post['created_at'][:10]
        )
    
    console.print(table)

@app.command()
def report(
    days: int = typer.Option(7, "--days", "-d", help="Number of days to analyze"),
):
    """Generate performance report for recent outreach"""
    report_data = generate_weekly_report(db, days)
    
    console.print(f"\n[bold]Outreach Report - Last {days} Days[/bold]\n")
    
    console.print(f"Total Posts: {report_data['total_posts']}")
    console.print(f"Total Clicks: {report_data['total_clicks']}")
    console.print(f"Total Conversions: {report_data['total_conversions']}")
    console.print(f"Average CTR: {report_data['avg_ctr']:.1f}%\n")
    
    if report_data['by_platform']:
        table = Table(title="Performance by Platform")
        table.add_column("Platform", style="magenta")
        table.add_column("Posts", justify="right")
        table.add_column("Clicks", justify="right", style="green")
        table.add_column("Conversions", justify="right", style="yellow")
        table.add_column("Avg CTR", justify="right", style="blue")
        
        for platform_data in report_data['by_platform']:
            table.add_row(
                platform_data['platform'],
                str(platform_data['posts']),
                str(platform_data['clicks']),
                str(platform_data['conversions']),
                f"{platform_data['avg_ctr']:.1f}%"
            )
        
        console.print(table)
    
    if report_data['top_posts']:
        console.print("\n[bold]Top Performing Posts:[/bold]")
        for i, post in enumerate(report_data['top_posts'][:3], 1):
            console.print(f"{i}. [{post['platform']}] {post['title']}")
            console.print(f"   {post['clicks']} clicks, {post['conversions']} conversions, {post['ctr']:.1f}% CTR\n")

@app.command()
def template(
    platform: str = typer.Option(None, "--platform", "-p", help="Filter by platform"),
):
    """Get data-driven sharing template based on successful posts"""
    template = suggest_template(db, platform)
    
    if not template:
        console.print("[yellow]Not enough data yet. Track more posts to get insights.[/yellow]")
        return
    
    console.print("\n[bold]Recommended Sharing Template:[/bold]\n")
    console.print(f"[cyan]Best Platform:[/cyan] {template['best_platform']}")
    console.print(f"[cyan]Success Pattern:[/cyan] {template['pattern']}")
    console.print(f"\n[bold]Example from your top post:[/bold]")
    console.print(f"Title: {template['example_title']}")
    console.print(f"Performance: {template['example_clicks']} clicks, {template['example_ctr']:.1f}% CTR\n")
    console.print("[dim]Tip: Posts with clear value propositions and specific use cases tend to perform better.[/dim]")

# ---------------------------------------------------------------------------
# Auto-reply commands
# ---------------------------------------------------------------------------

def _get_orchestrator(provider: str, style: str, exclude: List[str], dry_run: bool = False):
    """Create a ReplyOrchestrator with proper env-var checks."""
    from github_reply import ReplyOrchestrator, AIProviderError

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        console.print("[red]Error:[/red] GITHUB_TOKEN environment variable is not set")
        console.print("[dim]Create a token at https://github.com/settings/tokens with 'notifications' and 'repo' scopes[/dim]")
        raise typer.Exit(1)

    try:
        orch = ReplyOrchestrator(
            db=db,
            github_token=token,
            ai_provider=provider,
            style=style,
            excluded_repos=exclude,
            dry_run=dry_run,
        )
    except AIProviderError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)

    return orch


@app.command()
def reply(
    provider: str = typer.Option("deepseek", "--provider", "-ai", help="AI provider: deepseek or anthropic"),
    style: str = typer.Option("helpful", "--style", "-s", help="Reply style: helpful, concise, technical"),
    exclude: List[str] = typer.Option([], "--exclude", "-x", help="Repos to exclude (owner/repo)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview replies without posting"),
):
    """Check GitHub notifications and auto-reply with AI"""
    orch = _get_orchestrator(provider, style, exclude, dry_run)

    with console.status("[bold green]Checking notifications..."):
        results = orch.process_notifications()

    if not results:
        console.print("[yellow]No actionable notifications found.[/yellow]")
        return

    table = Table(title="Auto-Reply Results")
    table.add_column("Repo", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Status", style="magenta")

    for r in results:
        status = r["status"]
        status_style = {
            "replied": "[green]replied[/green]",
            "dry_run": "[blue]dry-run[/blue]",
            "skipped": "[yellow]skipped[/yellow]",
            "already_replied": "[dim]already replied[/dim]",
            "self_skip": "[dim]self-skip[/dim]",
            "ai_skip": "[dim]ai-skip[/dim]",
            "excluded": "[dim]excluded[/dim]",
            "error": f"[red]error: {r.get('error', '')[:40]}[/red]",
        }.get(status, status)

        table.add_row(
            r.get("repo", ""),
            (r.get("title", "")[:50] + "...") if len(r.get("title", "")) > 50 else r.get("title", ""),
            status_style,
        )

    console.print(table)

    # Show dry-run previews
    if dry_run:
        for r in results:
            if r["status"] == "dry_run" and r.get("reply"):
                console.print(f"\n[bold cyan]{r['repo']}[/bold cyan] — {r['title']}")
                console.print(r["reply"])
                console.print("---")


@app.command("reply-watch")
def reply_watch(
    interval: int = typer.Option(5, "--interval", "-i", help="Minutes between checks"),
    provider: str = typer.Option("deepseek", "--provider", "-ai", help="AI provider"),
    style: str = typer.Option("helpful", "--style", "-s", help="Reply style"),
    exclude: List[str] = typer.Option([], "--exclude", "-x", help="Repos to exclude"),
):
    """Continuously monitor GitHub notifications and auto-reply"""
    orch = _get_orchestrator(provider, style, exclude)

    console.print(f"[bold green]Watching notifications every {interval} min[/bold green] (Ctrl+C to stop)")

    def on_cycle(results):
        replied = [r for r in results if r.get("status") == "replied"]
        if replied:
            for r in replied:
                console.print(f"  [green]Replied[/green] {r['repo']} — {r['title']}")
        elif results:
            console.print(f"  [dim]{len(results)} notifications processed, none needed a reply[/dim]")
        else:
            console.print("  [dim]No new notifications[/dim]")

    try:
        orch.watch(interval_minutes=interval, on_cycle=on_cycle)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped watching.[/yellow]")


@app.command("reply-history")
def reply_history(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of replies to show"),
):
    """Show recent auto-reply history"""
    replies = db.get_recent_replies(limit)

    if not replies:
        console.print("[yellow]No replies yet. Run 'reply' to get started.[/yellow]")
        return

    table = Table(title="Recent Auto-Replies")
    table.add_column("ID", style="cyan")
    table.add_column("Repo", style="magenta")
    table.add_column("Type", style="blue")
    table.add_column("Summary", style="white")
    table.add_column("AI", style="dim")
    table.add_column("Date", style="dim")

    for r in replies:
        summary = r["context_summary"] or ""
        table.add_row(
            str(r["id"]),
            r["repo"],
            r["event_type"],
            (summary[:40] + "...") if len(summary) > 40 else summary,
            r["ai_provider"],
            r["created_at"][:16],
        )

    console.print(table)


@app.command("reply-stats")
def reply_stats(
    days: int = typer.Option(7, "--days", "-d", help="Number of days to analyze"),
):
    """Show auto-reply statistics"""
    stats = db.get_reply_stats(days)

    console.print(f"\n[bold]Auto-Reply Stats — Last {days} Days[/bold]\n")
    console.print(f"Total Replies: {stats['total']}")
    console.print(f"Repos Interacted: {stats['repos']}")

    if stats["by_type"]:
        console.print("\n[bold]By Event Type:[/bold]")
        for t in stats["by_type"]:
            console.print(f"  {t['event_type']}: {t['count']}")

    if stats["by_repo"]:
        table = Table(title="Top Repos by Replies")
        table.add_column("Repo", style="cyan")
        table.add_column("Replies", justify="right", style="green")
        for r in stats["by_repo"]:
            table.add_row(r["repo"], str(r["count"]))
        console.print(table)


# ---------------------------------------------------------------------------
# Scout commands — proactive outreach
# ---------------------------------------------------------------------------

def _get_scanner(provider: str, style: str, queries: List[str],
                 max_replies_hour: int, max_replies_day: int,
                 max_comments: int, max_age: int,
                 max_per_repo: int, cooldown: int, dry_run: bool = False):
    """Create an OutreachScanner with proper env-var checks."""
    from github_reply import OutreachScanner, AIProviderError

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        console.print("[red]Error:[/red] GITHUB_TOKEN environment variable is not set")
        raise typer.Exit(1)

    try:
        scanner = OutreachScanner(
            db=db,
            github_token=token,
            ai_provider=provider,
            style=style,
            search_queries=queries or None,
            max_replies_per_hour=max_replies_hour,
            max_replies_per_day=max_replies_day,
            max_comments_on_issue=max_comments,
            max_issue_age_hours=max_age,
            max_per_repo_per_day=max_per_repo,
            cooldown_seconds=cooldown,
            dry_run=dry_run,
        )
    except AIProviderError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)

    return scanner


@app.command()
def scout(
    provider: str = typer.Option("deepseek", "--provider", "-ai", help="AI provider: deepseek or anthropic"),
    style: str = typer.Option("helpful", "--style", "-s", help="Reply style"),
    query: List[str] = typer.Option([], "--query", "-q", help="Custom search query (can repeat)"),
    max_replies_hour: int = typer.Option(5, "--max-replies-hour", help="Max replies per hour"),
    max_replies_day: int = typer.Option(20, "--max-replies-day", help="Max replies per day"),
    max_comments: int = typer.Option(5, "--max-comments", help="Skip issues with more comments"),
    max_age: int = typer.Option(48, "--max-age", help="Max issue age in hours"),
    max_per_repo: int = typer.Option(2, "--max-per-repo", help="Max replies per repo per day"),
    cooldown: int = typer.Option(30, "--cooldown", help="Seconds between posts"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without posting"),
):
    """Search GitHub for issues and offer helpful suggestions"""
    scanner = _get_scanner(provider, style, query, max_replies_hour,
                           max_replies_day, max_comments, max_age,
                           max_per_repo, cooldown, dry_run)

    with console.status("[bold green]Scanning GitHub for issues to help with..."):
        results = scanner.scan_once()

    if not results:
        console.print("[yellow]No issues found to help with.[/yellow]")
        return

    table = Table(title="Scout Results")
    table.add_column("Repo", style="cyan")
    table.add_column("Issue", style="white")
    table.add_column("Status", style="magenta")

    for r in results:
        status = r.get("status", "")
        status_style = {
            "replied": "[green]replied[/green]",
            "dry_run": "[blue]dry-run[/blue]",
            "skipped": "[yellow]skipped[/yellow]",
            "hourly_limit": "[red]hourly limit[/red]",
            "daily_limit": "[red]daily limit[/red]",
            "error": f"[red]error: {r.get('error', '')[:30]}[/red]",
        }.get(status, status)

        table.add_row(
            r.get("repo", ""),
            (r.get("title", "")[:50] + "...") if len(r.get("title", "")) > 50 else r.get("title", ""),
            status_style,
        )

    console.print(table)

    # Show dry-run previews
    if dry_run:
        for r in results:
            if r.get("status") == "dry_run" and r.get("reply"):
                console.print(f"\n[bold cyan]{r['repo']}[/bold cyan] — {r['title']}")
                console.print(f"[dim]{r.get('html_url', '')}[/dim]")
                console.print(r["reply"])
                console.print("---")


@app.command("scout-watch")
def scout_watch(
    interval: int = typer.Option(10, "--interval", "-i", help="Minutes between scans"),
    provider: str = typer.Option("deepseek", "--provider", "-ai", help="AI provider"),
    style: str = typer.Option("helpful", "--style", "-s", help="Reply style"),
    query: List[str] = typer.Option([], "--query", "-q", help="Custom search query"),
    max_replies_hour: int = typer.Option(5, "--max-replies-hour", help="Max replies per hour"),
    max_replies_day: int = typer.Option(20, "--max-replies-day", help="Max replies per day"),
    max_comments: int = typer.Option(5, "--max-comments", help="Skip issues with more comments"),
    max_age: int = typer.Option(48, "--max-age", help="Max issue age in hours"),
    max_per_repo: int = typer.Option(2, "--max-per-repo", help="Max replies per repo per day"),
    cooldown: int = typer.Option(30, "--cooldown", help="Seconds between posts"),
):
    """Continuously scan GitHub and help people (runs forever)"""
    scanner = _get_scanner(provider, style, query, max_replies_hour,
                           max_replies_day, max_comments, max_age,
                           max_per_repo, cooldown)

    console.print(f"[bold green]Scouting every {interval} min[/bold green] (Ctrl+C to stop)")

    def on_cycle(results):
        replied = [r for r in results if r.get("status") == "replied"]
        if replied:
            for r in replied:
                console.print(f"  [green]Helped[/green] {r['repo']} — {r['title']}")
        elif results:
            skipped = len([r for r in results if r.get("status") == "skipped"])
            console.print(f"  [dim]{len(results)} issues checked, {skipped} skipped[/dim]")
        else:
            console.print("  [dim]No new issues found[/dim]")

    try:
        scanner.watch(interval_minutes=interval, on_cycle=on_cycle)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped scouting.[/yellow]")


@app.command("scout-history")
def scout_history(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of records to show"),
):
    """Show recent scout activity"""
    rows = db.get_recent_scout_issues(limit)

    if not rows:
        console.print("[yellow]No scout activity yet. Run 'scout' to get started.[/yellow]")
        return

    table = Table(title="Recent Scout Activity")
    table.add_column("ID", style="cyan")
    table.add_column("Repo", style="magenta")
    table.add_column("#", style="blue")
    table.add_column("Title", style="white")
    table.add_column("Status", style="green")
    table.add_column("Date", style="dim")

    for r in rows:
        title = r["title"] or ""
        table.add_row(
            str(r["id"]),
            r["repo"],
            str(r["issue_number"]),
            (title[:35] + "...") if len(title) > 35 else title,
            r["status"],
            r["created_at"][:16],
        )

    console.print(table)


@app.command("scout-stats")
def scout_stats(
    days: int = typer.Option(7, "--days", "-d", help="Number of days to analyze"),
):
    """Show scout statistics"""
    stats = db.get_scout_stats(days)

    console.print(f"\n[bold]Scout Stats — Last {days} Days[/bold]\n")
    console.print(f"Total Scanned: {stats['total']}")
    console.print(f"Replied: {stats['replied'] or 0}")
    console.print(f"Skipped: {stats['skipped'] or 0}")
    console.print(f"Repos Helped: {stats['repos']}")

    if stats.get("by_repo"):
        table = Table(title="Top Repos Helped")
        table.add_column("Repo", style="cyan")
        table.add_column("Replies", justify="right", style="green")
        for r in stats["by_repo"]:
            table.add_row(r["repo"], str(r["count"]))
        console.print(table)


if __name__ == "__main__":
    app()
