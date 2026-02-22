import typer
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

if __name__ == "__main__":
    app()
