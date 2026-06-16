import argparse
import asyncio
import logging
import sys
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

from python.orchestrator import (
    scrape_pipeline,
    score_pipeline,
    tailor_pipeline,
    package_pipeline,
    master_pipeline,
    process_single_job,
    validate_pipeline,
    process_contact,
    prep_outreach,
)
from python.db.client import (
    get_pipeline_status,
    get_ready_applications,
    mark_applied,
    get_jobs_needing_tailor,
    get_jobs_needing_package,
)

# Initialize Rich console
console = Console()

# Configure logging to write to console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
# Quiet down third party libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.WARNING)


def cmd_score(args):
    """Executes the job scoring stage."""
    job_id = args.job
    within_days = args.within_days
    dry_run = args.dry_run
    company = getattr(args, "company", None)

    console.print(
        Panel(
            f"[bold blue]Scout Pipeline: Scoring Stage[/bold blue]\n"
            f"Company: [cyan]{company or 'All Companies'}[/cyan]\n"
            f"Job ID: [cyan]{job_id or 'All Unscored'}[/cyan]\n"
            f"Within Days: [cyan]{within_days or 'All'}[/cyan]\n"
            f"Dry Run: [cyan]{dry_run}[/cyan]",
            title="[bold]Scoring[/bold]",
            expand=False,
        )
    )

    with console.status(
        "[bold green]Evaluating jobs against candidate profile..."
    ) as status:
        metrics = asyncio.run(
            score_pipeline(job_id=job_id, within_days=within_days, company_slug=company, dry_run=dry_run)
        )

    console.print("\n[bold green]Scoring Stage Complete![/bold green]")
    console.print(f"Total Evaluated: [bold]{metrics['jobs_evaluated']}[/bold]")
    if not dry_run:
        console.print(
            f"Advanced (Score >= 3.5): [bold green]{metrics['jobs_advanced']}[/bold green]"
        )
        console.print(
            f"Skipped/Low Match: [bold red]{metrics['jobs_skipped']}[/bold red]"
        )

    if metrics["details"]:
        console.print("\n[bold]Details:[/bold]")
        for item in metrics["details"]:
            if dry_run:
                console.print(
                    f"  - {item['company']} | {item['title']} (ID: {item['id']}, Posted: {item['posted_at']})"
                )
            else:
                color = "green" if item["advanced"] else "red"
                symbol = "[PASS]" if item["advanced"] else "[FAIL]"
                console.print(
                    f"  [{color}]{symbol} {item['company']} - {item['title']} (Score: {item['score']})[/{color}]"
                )
                if (
                    item["red_flags"]
                    and item["red_flags"] != ["None"]
                    and item["red_flags"] != ["none"]
                ):
                    console.print(
                        f"    [bold red]Red Flags:[/bold red] {', '.join(item['red_flags'])}"
                    )
                console.print(f"    [dim]{item['rationale']}[/dim]\n")


def cmd_tailor(args):
    """Executes the resume and cover letter tailoring stage — single job or bulk."""
    job_id = args.job

    # --- Single job mode ---
    if job_id:
        console.print(
            Panel(
                f"[bold blue]Scout Pipeline: Tailoring Stage[/bold blue]\n"
                f"Job ID: [cyan]{job_id}[/cyan]",
                title="[bold]Tailoring[/bold]",
                expand=False,
            )
        )
        with console.status(
            "[bold green]Tailoring resume & generating cover letter..."
        ) as status:
            metrics = asyncio.run(tailor_pipeline(job_id=job_id))
        if metrics["success"]:
            console.print(f"\n[bold green][PASS] Tailoring Complete![/bold green]")
            console.print(f"Company: [bold]{metrics['company']}[/bold]")
            console.print(f"Role: [bold]{metrics['title']}[/bold]")
        else:
            console.print(f"\n[bold red][FAIL] Tailoring failed![/bold red]")
            console.print(f"Error: [red]{metrics['error']}[/red]")
        return

    # --- Bulk mode: tailor all jobs scoring >= 3.5 without a resume yet ---
    jobs = get_jobs_needing_tailor()
    if not jobs:
        console.print(
            Panel(
                "[bold yellow]No jobs found needing tailoring.[/bold yellow]\nAll scored jobs (>= 3.5) already have tailored resumes, or none have been scored yet."
            )
        )
        return

    console.print(
        Panel(
            f"[bold blue]Scout Pipeline: Bulk Tailoring Stage[/bold blue]\n"
            f"Jobs to tailor: [cyan]{len(jobs)}[/cyan]",
            title="[bold]Tailoring (Bulk)[/bold]",
            expand=False,
        )
    )

    passed = 0
    failed = 0
    for job in jobs:
        jid = job["id"]
        company = job["company"]
        title = job["title"]
        score = job["overall_score"]
        with console.status(
            f"[bold green]Tailoring: {company} — {title} (Score: {score})..."
        ):
            metrics = asyncio.run(tailor_pipeline(job_id=jid))
        if metrics["success"]:
            console.print(f"  [green][PASS][/green] {company} — {title}")
            passed += 1
        else:
            console.print(
                f"  [red][FAIL][/red] {company} — {title}: {metrics['error']}"
            )
            failed += 1

    console.print(
        f"\n[bold]Bulk Tailoring Complete:[/bold] [green]{passed} succeeded[/green], [red]{failed} failed[/red]"
    )


def cmd_package(args):
    """Executes the PDF generation packaging stage — single job or bulk."""
    job_id = args.job

    def _print_page_fit(metrics):
        page_fill = metrics.get("page_fill", 100)
        initial_fill = metrics.get("initial_fill", page_fill)
        if initial_fill > 105:
            console.print(
                f"  [red]  Warning: Heavily squished (Initial: {initial_fill}%, Final: {page_fill}%)[/red]"
            )
        elif page_fill < 88:
            console.print(f"  [yellow]  Warning: Underfilled ({page_fill}%)[/yellow]")
        elif page_fill > 100:
            console.print(f"  [red]  Warning: Overflowed ({page_fill}%)[/red]")
        else:
            console.print(
                f"  [green]  [PASS] Page Fit: optimal (Initial: {initial_fill}%, Final: {page_fill}%)[/green]"
            )

    # --- Single job mode ---
    if job_id:
        console.print(
            Panel(
                f"[bold blue]Scout Pipeline: Packaging Stage[/bold blue]\n"
                f"Job ID: [cyan]{job_id}[/cyan]",
                title="[bold]PDF Generation[/bold]",
                expand=False,
            )
        )
        with console.status(
            "[bold green]Generating PDF via Playwright service..."
        ) as status:
            metrics = asyncio.run(package_pipeline(job_id=job_id))
        if metrics["success"]:
            console.print(f"\n[bold green][PASS] Packaging Complete![/bold green]")
            console.print(f"PDF saved to: [bold]{metrics['pdf_path']}[/bold]")
            _print_page_fit(metrics)
        else:
            console.print(f"\n[bold red][FAIL] Packaging failed![/bold red]")
            console.print(f"Error: [red]{metrics['error']}[/red]")
        return

    # --- Bulk mode: package all tailored jobs without a PDF ---
    jobs = get_jobs_needing_package()
    if not jobs:
        console.print(
            Panel(
                "[bold yellow]No jobs found needing packaging.[/bold yellow]\nAll tailored resumes already have PDFs, or no resumes have been tailored yet."
            )
        )
        return

    console.print(
        Panel(
            f"[bold blue]Scout Pipeline: Bulk Packaging Stage[/bold blue]\n"
            f"Jobs to package: [cyan]{len(jobs)}[/cyan]",
            title="[bold]PDF Generation (Bulk)[/bold]",
            expand=False,
        )
    )

    passed = 0
    failed = 0
    for job in jobs:
        jid = job["id"]
        company = job["company"]
        title = job["title"]
        with console.status(f"[bold green]Packaging: {company} — {title}..."):
            metrics = asyncio.run(package_pipeline(job_id=jid))
        if metrics["success"]:
            console.print(
                f"  [green][PASS][/green] {company} — {title} -> {metrics['pdf_path']}"
            )
            _print_page_fit(metrics)
            passed += 1
        else:
            console.print(
                f"  [red][FAIL][/red] {company} — {title}: {metrics['error']}"
            )
            failed += 1

    console.print(
        f"\n[bold]Bulk Packaging Complete:[/bold] [green]{passed} succeeded[/green], [red]{failed} failed[/red]"
    )


def cmd_validate(args):
    """Validates the PDF generation layout scaling and A4 page fit.

    Modes:
    - No args: lists all jobs that have a tailored resume and prints their job ID and page_fill.
    - --job <ID> with no adjust flags: validates that single job and prints detailed metrics.
    - --job <ID> --increaseline X: iteratively re-renders the job increasing line-height by X until page_fill in [95,100] or attempts exhausted.
    - --job <ID> --decreaseline X: iteratively re-renders the job decreasing line-height by X until page_fill in [95,100] or attempts exhausted.
    """

    job_id = args.job
    inc = getattr(args, "increaseline", None)
    dec = getattr(args, "decreaseline", None)

    # Validate flag usage
    if inc is not None and dec is not None:
        console.print(
            "[bold red]Error: specify only one of --increaseline or --decreaseline.[/bold red]"
        )
        return

    # 1) No job: list all jobs with resumes out of bounds
    if not job_id and inc is None and dec is None:
        console.print(
            Panel("[bold blue]Resume Page-Fill Summary (Out of Bounds)[/bold blue]", expand=False)
        )
        from python.db.client import get_connection

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT j.id, rv.page_fill FROM jobs j JOIN applications a ON j.id = a.job_id JOIN resume_versions rv ON a.resume_version_id = rv.id WHERE rv.page_fill < 95 OR rv.page_fill > 100"
        )
        rows = cur.fetchall()
        conn.close()

        if not rows:
            console.print("[green]All tailored resumes are perfectly fitted (95-100%) or no resumes found![/green]")
            return

        for r in rows:
            jid = r["id"]
            pf = r["page_fill"]
            if pf is None:
                continue
            if pf > 100:
                console.print(f"[red]{jid} — page_fill: {pf}% (OVERFLOW)[/red]")
            else:
                console.print(f"[yellow]{jid} — page_fill: {pf}% (UNDERFILL)[/yellow]")
        return

    # 2) Single-job adjustments
    if job_id and (inc is not None or dec is not None):
        # Fetch current template line-height
        from pathlib import Path
        import re

        tpl_path = Path("templates/resume.html")
        if not tpl_path.exists():
            tpl_path = (
                Path(__file__).resolve().parent.parent / "templates" / "resume.html"
            )
        txt = tpl_path.read_text(encoding="utf-8")
        m = re.search(r"--line-height:\s*([0-9]*\.?[0-9]+);", txt)
        if not m:
            console.print(
                "[yellow]Could not find --line-height in template; aborting adjustment.[/yellow]"
            )
            return
        cur_val = float(m.group(1))

        step = inc if inc is not None else dec
        direction = "increase" if inc is not None else "decrease"

        # Prepare resume markdown
        from python.db.client import get_connection as _get_conn

        conn2 = _get_conn()
        cur2 = conn2.cursor()
        cur2.execute(
            "SELECT rv.resume_md FROM resume_versions rv JOIN applications a ON rv.id = a.resume_version_id WHERE a.job_id = ?",
            (str(job_id),),
        )
        rr = cur2.fetchone()
        conn2.close()
        if not (rr and rr[0]):
            console.print(
                f"[yellow]No resume markdown found for {job_id}; cannot re-render.[/yellow]"
            )
            return

        # Single per-render adjustment (only one iteration)
        from python.utils.pdf_bridge import generate_pdf

        if direction == "increase":
            current_val = cur_val + float(step)
        else:
            current_val = max(0.1, cur_val - float(step))

        try:
            out_path, pf, init = asyncio.run(
                generate_pdf(rr[0], job_id, line_height_override=current_val)
            )
        except Exception as e:
            console.print(f"[red]Failed to generate PDF for {job_id}: {e}[/red]")
            console.print(
                f"[yellow]No changes applied. Original line-height: {cur_val}[/yellow]"
            )
            return

        console.print(
            f"[dim]Rendered page_fill={pf}%, initial={init}%, line-height={current_val}[/dim]"
        )
        
        # Save to database
        stored_pf = pf if 95 <= pf <= 100 else init
        conn3 = _get_conn()
        cur3 = conn3.cursor()
        cur3.execute(
            "UPDATE resume_versions SET page_fill = ? WHERE id = (SELECT resume_version_id FROM applications WHERE job_id = ?)",
            (stored_pf, str(job_id))
        )
        conn3.commit()
        conn3.close()
        
        if 95 <= pf <= 100:
            console.print(
                f"[green]Success: page_fill {pf}% with line-height {current_val} (Saved to DB: {stored_pf}%)[/green]"
            )
        else:
            console.print(
                f"[yellow]Single adjustment finished; page_fill={pf}% (line-height {current_val}). (Saved to DB: {stored_pf}%)[/yellow]"
            )
        console.print(
            f"[green]Per-render adjustment attempted: {cur_val} -> {current_val}[/green]"
        )
        return

    # 3) Single-job validation (no adjustments): unchanged behavior
    if job_id:
        console.print(
            Panel(
                f"[bold blue]Scout Pipeline: Layout & A4 Page Fit Validation[/bold blue]\n"
                f"Job ID: [cyan]{job_id}[/cyan]",
                title="[bold]PDF Layout Consistency[/bold]",
                expand=False,
            )
        )
        with console.status("[bold green]Validating page scaling metrics...") as status:
            metrics = asyncio.run(validate_pipeline(job_id=job_id))

        if metrics["success"]:
            pdf_path = metrics["pdf_path"]
            page_fill = metrics["page_fill"]
            initial_fill = metrics.get("initial_fill", page_fill)
            page_count = metrics.get("page_count")

            console.print(f"\n[bold green][PASS] Validation Complete![/bold green]")
            console.print(f"PDF Output Path: [bold]{pdf_path}[/bold]")

            # --- Page fill metric ---
            if initial_fill > 105:
                console.print(
                    f"[bold red][FAIL] [OVERFLOW] Initial content length was {initial_fill}%! Playwright squished it to {page_fill}%.[/bold red]"
                )
                console.print(
                    "[red]The resume content is too long. The font size has been drastically reduced, making it hard to read. Shorten the experience bullets.[/red]"
                )
            elif page_fill < 88:
                console.print(
                    f"[bold yellow]⚠️  [UNDERFILL] Page fill is {page_fill}% (below target 88%).[/bold yellow]"
                )
                console.print(
                    "[yellow]The content is too short for a single A4 page. Consider adding more detail to bullets.[/yellow]"
                )
            elif page_fill > 100:
                console.print(
                    f"[bold red]⚠️  [OVERFLOW] Page fill is {page_fill}% (exceeds 100%).[/bold red]"
                )
                console.print(
                    "[red]The content is too long. Shorten experience bullets or reduce font size.[/red]"
                )
            else:
                console.print(
                    f"[bold green][PASS] Page fill is optimal (Initial: {initial_fill}%, Final: {page_fill}%).[/bold green]"
                )

            # --- Actual page count from PDF ---
            if page_count is not None:
                if page_count == 1:
                    console.print(
                        f"[bold green][PASS] Page count: {page_count} — Resume fits on exactly one page![/bold green]"
                    )
                else:
                    console.print(
                        f"[bold red][FAIL] Page count: {page_count} — Resume is overflowing to {page_count} pages![/bold red]"
                    )
                    console.print(
                        "[red]The 'page fill' metric is based on scrollHeight and may underestimate the true PDF length.[/red]"
                    )
                    console.print(
                        "[yellow]Fix: Reduce font size, line-height, or bullet count in templates/resume.html[/yellow]"
                    )
            else:
                console.print(
                    "[yellow]⚠️  Could not determine page count from PDF.[/yellow]"
                )
        else:
            console.print(f"\n[bold red][FAIL] Validation failed![/bold red]")
            console.print(f"Error: [red]{metrics['error']}[/red]")
        return

    # End of validate


def cmd_scrape(args):
    """Executes the job scraper stage."""
    company = args.company
    query = args.query
    source = args.source
    run_all = args.all

    console.print(
        Panel(
            f"[bold blue]Scout Pipeline: Scraping Stage[/bold blue]\n"
            f"Company: [cyan]{company or 'All TARGET_COMPANIES'}[/cyan]\n"
            f"Search Query: [cyan]{query or 'None'}[/cyan]\n"
            f"Source: [cyan]{source or 'All'}[/cyan]\n"
            f"Run All: [cyan]{run_all}[/cyan]",
            title="[bold]Scraping[/bold]",
            expand=False,
        )
    )

    # Run the async orchestrator
    with console.status("[bold green]Running scraper drivers...") as status:
        metrics = asyncio.run(scrape_pipeline(company_slug=company, search_query=query, source=source, run_all=run_all))

    console.print("\n[bold green]Scraping Stage Complete![/bold green]")
    console.print(f"Companies Attempted: [bold]{metrics['companies_attempted']}[/bold]")
    console.print(
        f"Companies Successful: [bold]{metrics['companies_successful']}[/bold]"
    )
    console.print(
        f"Total Jobs Scraped: [bold cyan]{metrics['jobs_scraped']}[/bold cyan]"
    )
    console.print(
        f"New/Updated Jobs Saved: [bold green]{metrics['jobs_saved']}[/bold green]"
    )

    if metrics["errors"]:
        console.print(
            f"\n[bold red]Encountered {len(metrics['errors'])} errors during execution:[/bold red]"
        )
        for err in metrics["errors"][:5]:
            console.print(f"  - [red]{err}[/red]")
        if len(metrics["errors"]) > 5:
            console.print(
                f"  - [red]... and {len(metrics['errors']) - 5} more errors.[/red]"
            )

    if metrics.get("zero_job_companies"):
        import os
        os.makedirs("data", exist_ok=True)
        with open("data/failed_companies.log", "w", encoding="utf-8") as f:
            for c in sorted(list(set(metrics["zero_job_companies"]))):
                f.write(f"{c}\n")
        console.print(f"\n[bold yellow]Logged {len(set(metrics['zero_job_companies']))} companies with 0 jobs found to data/failed_companies.log[/bold yellow]")


def cmd_pipeline(args):
    """Executes the full end-to-end pipeline."""
    company = getattr(args, "company", None)

    console.print(
        Panel(
            f"[bold blue]Scout Master Pipeline[/bold blue]\n"
            f"Target: [cyan]{company or 'All TARGET_COMPANIES'}[/cyan]",
            title="[bold]Orchestrator Pipeline[/bold]",
            expand=False,
        )
    )

    with console.status("[bold green]Running full end-to-end pipeline...") as status:
        metrics = asyncio.run(master_pipeline(company_slug=company))

    console.print(f"\n[bold green][PASS] Pipeline Complete![/bold green]")
    console.print(f"Jobs Scraped: [bold]{metrics['scraped']}[/bold]")
    console.print(f"Jobs Scored: [bold]{metrics['scored']}[/bold]")
    console.print(f"Packages Generated: [bold cyan]{metrics['packaged']}[/bold cyan]")

    if metrics["packaged"] > 0:
        console.print(
            "\n[bold]Run '.\\scout.bat review' to see your new application packages![/bold]"
        )


def cmd_process(args):
    """Executes the pipeline for a single job ID (score -> tailor -> package)."""
    job_id = args.job

    console.print(
        Panel(
            f"[bold blue]Scout Single-Job Pipeline[/bold blue]\n"
            f"Job ID: [cyan]{job_id}[/cyan]",
            title="[bold]Single Job Process[/bold]",
            expand=False,
        )
    )

    with console.status(f"[bold green]Processing job {job_id}...") as status:
        metrics = asyncio.run(process_single_job(job_id=job_id))

    if metrics["success"]:
        console.print(f"\n[bold green][PASS] Processing Complete![/bold green]")
        if metrics.get("advanced"):
            console.print(
                "[bold]Job scored >= 3.5 and was successfully tailored and packaged![/bold]"
            )
            console.print(
                "\n[bold]Run '.\\scout.bat review' to see the new application package![/bold]"
            )
        else:
            console.print(
                "[yellow]Job processed but scored < 3.5. It was not tailored or packaged.[/yellow]"
            )
    else:
        console.print(f"\n[bold red][FAIL] Processing failed![/bold red]")
        console.print(f"Error: [red]{metrics.get('error')}[/red]")


def cmd_review(args):
    """Lists all packages that are ready to apply."""
    apps = get_ready_applications()

    if not apps:
        console.print(
            Panel(
                "[bold yellow]No ready applications found.[/bold yellow]\nRun the pipeline to generate some!"
            )
        )
        return

    console.print(f"\n[bold green]Ready to Apply ({len(apps)} packages):[/bold green]")
    for i, app in enumerate(apps, 1):
        score_color = "green" if app["overall_score"] >= 4.0 else "yellow"
        console.print(
            f"  {i}. [bold]{app['company']}[/bold] — {app['title']} (score: [{score_color}]{app['overall_score']}[/{score_color}])"
        )
        console.print(f"     [cyan]Job ID:[/cyan] {app['job_id']}")
        console.print(f"     [cyan]PDF Path:[/cyan] {app['pdf_path']}\n")


def cmd_mark(args):
    """Updates the status of an application."""
    job_id = args.job
    status = args.status

    success = mark_applied(job_id=job_id, status=status)
    if success:
        console.print(
            f"[bold green][SUCCESS][/bold green] Marked job {job_id} as '{status}'!"
        )
    else:
        console.print(
            f"[bold red][ERROR][/bold red] Failed to update job {job_id}. Does it exist in the applications table?"
        )


def cmd_status(args):
    """Executes status dashboard output."""
    status = get_pipeline_status()

    table = Table(
        title="Scout Pipeline Tracker Dashboard",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Pipeline Metric / Status", style="cyan")
    table.add_column("Count", justify="right", style="green")

    table.add_row("Total Scraped Jobs", str(status.get("scraped", 0)))
    table.add_row("Total Scored Jobs", str(status.get("scored", 0)))
    table.add_row(
        "Advanced (Score >= 3.5)",
        f"[bold green]{status.get('advanced', 0)}[/bold green]",
    )
    table.add_row("Ready packages", str(status.get("ready", 0)))
    table.add_row("Applied applications", str(status.get("applied", 0)))
    table.add_row("Followed Up", str(status.get("followed_up", 0)))
    table.add_row("Responded", str(status.get("responded", 0)))
    table.add_row("Rejected", str(status.get("rejected", 0)))
    table.add_row("Offer", f"[bold gold1]{status.get('offer', 0)}[/bold gold1]")

    console.print(Panel(table, expand=False))


def cmd_apply(args):
    """Executes the Playwright autofiller."""
    job_id = args.job

    if job_id:
        job_ids = [job_id]
        console.print(
            Panel(
                f"[bold blue]Scout Auto-Filler: Single Job[/bold blue]\n"
                f"Job ID: [cyan]{job_id}[/cyan]",
                title="[bold]Auto-Filler[/bold]",
                expand=False,
            )
        )
    else:
        # Get all ready applications
        apps = get_ready_applications()
        if not apps:
            console.print(
                Panel(
                    "[bold yellow]No ready applications found in DB.[/bold yellow]\nRun the pipeline to tailor and package some jobs first!"
                )
            )
            return
        job_ids = [app["job_id"] for app in apps]
        console.print(
            Panel(
                f"[bold blue]Scout Auto-Filler: Multi-Tab[/bold blue]\n"
                f"Ready Applications to Fill: [cyan]{len(job_ids)}[/cyan]",
                title="[bold]Auto-Filler[/bold]",
                expand=False,
            )
        )

    from python.utils.autofill import run_multi_tab_autofill

    try:
        asyncio.run(run_multi_tab_autofill(job_ids))
        console.print("[bold green]Auto-Filler execution complete![/bold green]")
    except Exception as ex:
        console.print(f"[bold red]Error running auto-filler:[/bold red] {ex}")


def cmd_qa(args):
    """Manages the custom QA bank."""
    from python.utils.question_handler import QuestionHandler
    from rich.table import Table

    qh = QuestionHandler()

    if args.list:
        table = Table(
            title="Custom QA Bank (Demographics & Standards)",
            header_style="bold magenta",
        )
        table.add_column("Key / ID", style="cyan", no_wrap=True)
        table.add_column("Type", style="green", no_wrap=True)
        table.add_column("Answer", style="white")
        table.add_column("Keywords", style="yellow")

        for key, val in qh.qa_bank.items():
            keywords_str = ", ".join(val.get("keywords", []))
            table.add_row(
                key, val.get("type", "text"), str(val.get("answer", "")), keywords_str
            )

        console.print(table)

        star_table = Table(
            title="STAR Answer Bank (Dynamic & Open-ended)", header_style="bold cyan"
        )
        star_table.add_column("Key / ID", style="cyan", no_wrap=True)
        star_table.add_column("Type", style="green", no_wrap=True)
        star_table.add_column("Answer / Template", style="white")
        star_table.add_column("Keywords", style="yellow")

        for key, val in qh.star_bank.items():
            keywords_str = ", ".join(val.get("keywords", []))
            ans_temp = val.get("answer") or val.get("template", "")
            star_table.add_row(key, val.get("type", "static"), ans_temp, keywords_str)

        console.print(star_table)

    elif args.add:
        console.print("[bold green]Add a New Q&A Entry[/bold green]")
        key = input("Enter Key (e.g. preferred_pronoun): ").strip()
        if not key:
            console.print("[bold red]Key cannot be empty.[/bold red]")
            return
        if key in qh.qa_bank:
            console.print(
                f"[bold yellow]Key '{key}' already exists in QA bank.[/bold yellow]"
            )
            return

        ans_type = (
            input("Enter Type (dropdown / text / checkbox) [text]: ").strip() or "text"
        )
        answer = input("Enter Answer: ").strip()
        keywords_input = input("Enter Keywords (comma-separated): ").strip()
        keywords = [kw.strip() for kw in keywords_input.split(",") if kw.strip()]

        qh.qa_bank[key] = {"answer": answer, "type": ans_type, "keywords": keywords}
        qh._save_bank(qh.qa_bank, qh.qa_bank_path)
        console.print(
            f"[bold green]✓ Successfully added '{key}' to QA bank.[/bold green]"
        )

    elif args.edit:
        key = args.edit
        if key not in qh.qa_bank and key not in qh.star_bank:
            console.print(
                f"[bold red]Key '{key}' not found in QA or STAR banks.[/bold red]"
            )
            return

        target_bank = qh.qa_bank if key in qh.qa_bank else qh.star_bank
        entry = target_bank[key]

        console.print(f"[bold green]Editing Entry: {key}[/bold green]")
        console.print(
            f"Current Value: [yellow]{entry.get('answer') or entry.get('template')}[/yellow]"
        )
        new_val = input(
            "Enter New Answer/Template (press Enter to keep current): "
        ).strip()

        keywords_str = ", ".join(entry.get("keywords", []))
        console.print(f"Current Keywords: [yellow]{keywords_str}[/yellow]")
        new_kw = input(
            "Enter New Keywords (comma-separated, press Enter to keep current): "
        ).strip()

        if new_val:
            if "template" in entry:
                entry["template"] = new_val
            else:
                entry["answer"] = new_val

        if new_kw:
            entry["keywords"] = [kw.strip() for kw in new_kw.split(",") if kw.strip()]

        target_path = qh.qa_bank_path if key in qh.qa_bank else qh.star_bank_path
        qh._save_bank(target_bank, target_path)
        console.print(f"[bold green]✓ Successfully updated entry '{key}'.[/bold green]")

    else:
        console.print(
            "[bold yellow]Please specify an action: --list, --add, or --edit <key>[/bold yellow]"
        )


def cmd_outreach(args):
    """Outreach command: generate a draft email for a manually-found contact."""

    # ── outreach --job <job_id> --linkedin <url> --email <addr> ────────
    if args.job and args.linkedin and args.email:
        console.print(
            Panel(
                f"[bold blue]Scout Outreach: Compose + Save Gmail Draft[/bold blue]\n"
                f"Job ID:  [cyan]{args.job}[/cyan]\n"
                f"LinkedIn: [cyan]{args.linkedin}[/cyan]\n"
                f"Email:    [cyan]{args.email}[/cyan]",
                title="[bold]Outreach[/bold]",
                expand=False,
            )
        )

        with console.status("[bold green]Scraping profile, composing email, saving Gmail draft...[/bold green]"):
            result = asyncio.run(process_contact(
                job_id=args.job,
                linkedin_url=args.linkedin,
                email=args.email,
            ))

        if result["success"]:
            console.print(f"\n[bold green][PASS] Done![/bold green]")
            console.print(f"Contact: [bold]{result['contact_name']}[/bold] <{args.email}>")
            console.print(f"Gmail Draft ID: [cyan]{result['gmail_draft_id']}[/cyan]")
            console.print("\n[dim]Open Gmail Drafts -> review -> hit Send.[/dim]")
        else:
            console.print(f"\n[bold red][FAIL] Outreach failed![/bold red]")
            console.print(f"Error: [red]{result['error']}[/red]")
        return

    # ── outreach --review ──────────────────────────────────────────────────
    if args.review:
        from python.db.client import get_outreach_drafts
        drafts = get_outreach_drafts()
        if not drafts:
            console.print("[yellow]No outreach drafts found.[/yellow]")
            return

        from rich.table import Table
        table = Table(title="Outreach Drafts (review in Gmail -> Send)")
        table.add_column("Job ID (short)", style="dim")
        table.add_column("Company")
        table.add_column("Contact")
        table.add_column("Email")
        table.add_column("Gmail Draft ID", style="cyan")
        table.add_column("Status")

        for d in drafts:
            table.add_row(
                str(d["job_id"])[-8:],
                d["company"],
                d["contact_name"] or "-",
                d["contact_email"] or "-",
                d["gmail_draft_id"] or "-",
                d["status"],
            )
        console.print(table)
        return

    # ── outreach --mark <job_id> --status <status> ─────────────────────────
    if args.mark:
        from python.db.client import get_connection
        from datetime import datetime
        conn = get_connection()
        cur = conn.cursor()
        now = datetime.utcnow().isoformat()
        cur.execute(
            "UPDATE outreach SET status = ?, sent_at = ? WHERE job_id LIKE ?",
            (args.status, now if args.status == "sent" else None, f"%{args.mark}%"),
        )
        updated = cur.rowcount
        conn.commit()
        conn.close()
        if updated:
            console.print(f"[green]Marked outreach for job {args.mark} as '{args.status}'.[/green]")
        else:
            console.print(f"[red]No outreach record found for job ID {args.mark}.[/red]")
        return

    # ── Default: prep scored jobs (all, or specific --job) ──
    from rich.table import Table as RichTable
    job_arg = getattr(args, 'job', None)
    
    # If the user passed --linkedin or --email but not ALL THREE required for processing
    if args.linkedin or args.email:
        console.print("[bold red]Error: To process a contact, you must provide --job, --linkedin, AND --email together.[/bold red]")
        return
        
    panel_msg = (
        f"[bold blue]Scout Outreach Prep[/bold blue]\n"
        f"{'Single job: ' + job_arg if job_arg else 'All scored jobs (>= 3.5) without an outreach record'}"
    )
    console.print(Panel(panel_msg, expand=False))

    with console.status("[bold green]Extracting JD signals...[/bold green]"):
        metrics = asyncio.run(prep_outreach(job_id=job_arg))

    if not metrics["jobs"]:
        console.print("[yellow]No jobs found needing outreach prep.[/yellow]")
        console.print("[dim]All scored jobs may already have an outreach record. Run 'scout outreach --review' to see them.[/dim]")
        return

    table = RichTable(title=f"Outreach Prep Complete — {metrics['prepped']}/{metrics['attempted']} jobs prepped")
    table.add_column("Job ID (short)", style="dim")
    table.add_column("Company", style="bold")
    table.add_column("Role")
    table.add_column("Team")
    table.add_column("Find someone like...", style="cyan")
    table.add_column("Domain", style="dim")

    for j in metrics["jobs"]:
        table.add_row(
            j["job_id"][-8:],
            j["company"],
            j["title"],
            j["team_name"],
            ", ".join(j["find_someone_like"]),
            j["domain"],
        )
    console.print(table)
    console.print("\n[bold]Next step:[/bold] Go to LinkedIn, find the right person, get their email via ContactOut.")
    console.print("[bold]Then run:[/bold] scout outreach --job <job_id> --linkedin <url> --email <addr>")

    if metrics["errors"]:
        console.print(f"\n[red]{len(metrics['errors'])} errors:[/red]")
        for err in metrics["errors"]:
            console.print(f"  [red]- {err}[/red]")





def main():
    parser = argparse.ArgumentParser(description="Scout: Auto-Applier CLI Orchestrator")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # 1. Scrape subcommand
    parser_scrape = subparsers.add_parser(
        "scrape", help="Scrape job postings from Greenhouse, Lever, Ashby, or LinkedIn"
    )
    parser_scrape.add_argument(
        "--company",
        type=str,
        default=None,
        help="Specific company slug to scrape (e.g. 'retool')",
    )
    parser_scrape.add_argument(
        "--query",
        type=str,
        default=None,
        help="LinkedIn jobs search query (triggers Apify actor)",
    )
    parser_scrape.add_argument(
        "--source",
        type=str,
        default=None,
        help="Specific scraper source to run (e.g. 'yc', 'wellfound', 'direct')",
    )
    parser_scrape.add_argument(
        "--all",
        action="store_true",
        help="Run all target companies AND aggregator sources (yc, wellfound)",
    )

    # 2. Status subcommand
    subparsers.add_parser("status", help="Print pipeline dashboard status counts")

    # 3. Score subcommand
    parser_score = subparsers.add_parser(
        "score", help="Score unscored jobs in the database"
    )
    parser_score.add_argument(
        "--job", type=str, default=None, help="Specific job ID to score"
    )
    parser_score.add_argument(
        "--company",
        type=str,
        default=None,
        help="Specific company slug to score (e.g. 'retool')",
    )
    parser_score.add_argument(
        "--within-days",
        type=int,
        default=None,
        help="Only score jobs posted within the last N days",
    )
    parser_score.add_argument(
        "--dry-run",
        action="store_true",
        help="Print matching jobs without invoking Gemini or saving scores",
    )

    # 4. Tailor subcommand
    parser_tailor = subparsers.add_parser(
        "tailor",
        help="Tailor resume & cover letter. Omit --job to tailor ALL scored (>=3.5) jobs.",
    )
    parser_tailor.add_argument(
        "--job",
        type=str,
        default=None,
        help="Specific job ID to tailor (omit to run bulk tailor)",
    )

    # 5. Package subcommand
    parser_package = subparsers.add_parser(
        "package",
        help="Generate PDF. Omit --job to package ALL tailored jobs without a PDF.",
    )
    parser_package.add_argument(
        "--job",
        type=str,
        default=None,
        help="Specific job ID to package (omit to run bulk packaging)",
    )

    # 6. Pipeline subcommand
    parser_pipeline = subparsers.add_parser(
        "pipeline",
        help="Run the full end-to-end pipeline (scrape -> score -> tailor -> package)",
    )
    parser_pipeline.add_argument(
        "--company",
        type=str,
        default=None,
        help="Specific company slug to run the pipeline for",
    )

    # 7. Process subcommand
    parser_process = subparsers.add_parser(
        "process", help="Run score -> tailor -> package on a single job ID"
    )
    parser_process.add_argument(
        "--job", type=str, required=True, help="Specific job ID to process"
    )

    # 8. Review subcommand
    subparsers.add_parser(
        "review", help="List all 'ready' applications with their generated PDFs"
    )

    # 9. Mark subcommand
    parser_mark = subparsers.add_parser(
        "mark", help="Update the status of a job application"
    )
    parser_mark.add_argument("--job", type=str, required=True, help="Job ID to update")
    parser_mark.add_argument(
        "--status",
        type=str,
        required=True,
        choices=["ready", "applied", "followed_up", "responded", "rejected", "offer"],
        help="New status for the application",
    )

    # 10. Apply subcommand
    parser_apply = subparsers.add_parser(
        "apply", help="Autofill job applications in browser using Playwright"
    )
    parser_apply.add_argument(
        "--job",
        type=str,
        default=None,
        help="Specific job ID to autofill (otherwise fills all 'ready' jobs)",
    )

    # 11. QA subcommand
    parser_qa = subparsers.add_parser(
        "qa", help="Manage custom Q&A bank (list, add, edit)"
    )
    parser_qa.add_argument(
        "--list", action="store_true", help="List all Q&A entries in the bank"
    )
    parser_qa.add_argument(
        "--add", action="store_true", help="Interactively add a new Q&A entry"
    )
    parser_qa.add_argument(
        "--edit", type=str, default=None, help="Edit an existing Q&A entry by its key"
    )

    # 12. Validate subcommand
    parser_validate = subparsers.add_parser(
        "validate", help="Validate PDF layout and A4 page fill percentage"
    )
    parser_validate.add_argument(
        "--job", type=str, default=None, help="Specific job ID to validate layout for"
    )
    parser_validate.add_argument(
        "--increaseline",
        type=float,
        default=None,
        help="Increase line-height by this amount for the specified job (per-render)",
    )
    parser_validate.add_argument(
        "--decreaseline",
        type=float,
        default=None,
        help="Decrease line-height by this amount for the specified job (per-render)",
    )

    # 13. Outreach subcommand
    parser_outreach = subparsers.add_parser(
        "outreach", help="Draft personalized outreach emails via Gmail"
    )
    parser_outreach.add_argument(
        "--job",
        type=str,
        default=None,
        metavar="JOB_ID",
        help="Job ID. Used alone to prep a job, or with --linkedin and --email to process a contact.",
    )
    parser_outreach.add_argument(
        "--linkedin",
        type=str,
        default=None,
        metavar="URL",
        help="Contact's LinkedIn profile URL (e.g. https://linkedin.com/in/sarahchen)",
    )
    parser_outreach.add_argument(
        "--email",
        type=str,
        default=None,
        metavar="ADDR",
        help="Contact's email address (from ContactOut or similar)",
    )
    parser_outreach.add_argument(
        "--review",
        action="store_true",
        help="List all saved outreach drafts",
    )
    parser_outreach.add_argument(
        "--mark",
        type=str,
        default=None,
        metavar="JOB_ID",
        help="Job ID to update outreach status for",
    )
    parser_outreach.add_argument(
        "--status",
        type=str,
        default="sent",
        choices=["sent", "replied", "pending"],
        help="Status to set when using --mark (default: sent)",
    )

    # Parse arguments
    args = parser.parse_args()

    if args.command == "scrape":
        cmd_scrape(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "score":
        cmd_score(args)
    elif args.command == "tailor":
        cmd_tailor(args)
    elif args.command == "package":
        cmd_package(args)
    elif args.command == "validate":
        cmd_validate(args)
    elif args.command == "pipeline":
        cmd_pipeline(args)
    elif args.command == "process":
        cmd_process(args)
    elif args.command == "review":
        cmd_review(args)
    elif args.command == "mark":
        cmd_mark(args)
    elif args.command == "apply":
        cmd_apply(args)
    elif args.command == "qa":
        cmd_qa(args)
    elif args.command == "outreach":
        cmd_outreach(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
