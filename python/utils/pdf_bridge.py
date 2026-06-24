import os
import logging
import markdown
import subprocess
import tempfile
import re
import json
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)


def _run_ts_pdf(html_content: str, abs_output_path: str) -> tuple[int, int]:
    """Writes html_content to a temp file, calls the TS CLI, returns (page_fill, initial_fill)."""
    ts_dir = Path(__file__).resolve().parent.parent.parent / "ts"

    fd, temp_html_path = tempfile.mkstemp(suffix=".html")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(html_content)

        cmd = ["npx", "ts-node", "src/cli.ts", temp_html_path, abs_output_path]
        process = subprocess.run(
            cmd, cwd=ts_dir, capture_output=True, text=True, shell=True
        )
    finally:
        try:
            os.remove(temp_html_path)
        except OSError:
            pass

    if process.returncode != 0:
        logger.error(f"Playwright PDF generation failed: {process.stderr}")
        raise RuntimeError(f"PDF generation failed: {process.stderr}")

    page_fill = 100
    initial_fill = 100
    for line in process.stdout.splitlines():
        if "PAGE_FILL:" in line:
            try:
                page_fill = int(line.split("PAGE_FILL:")[1].strip())
            except ValueError:
                pass
        elif "INITIAL_FILL:" in line:
            try:
                initial_fill = int(line.split("INITIAL_FILL:")[1].strip())
            except ValueError:
                pass

    return page_fill, initial_fill


async def generate_pdf(
    markdown_content: str, job_id: str, line_height_override: float | None = None
) -> tuple[str, int, int]:
    """Converts markdown to HTML, injects it into the resume template, and calls TS CLI."""
    try:
        # Convert Markdown to HTML
        html_body = markdown.markdown(markdown_content)

        # Load resume template
        template_path = Path("templates/resume.html")
        if not template_path.exists():
            template_path = (
                Path(__file__).resolve().parent.parent.parent
                / "templates"
                / "resume.html"
            )

        template_html = template_path.read_text(encoding="utf-8")

        # If caller wants a temporary line-height override for this render, replace in-memory
        if line_height_override is not None:
            template_html = re.sub(
                r"(--line-height:\s*)([0-9]*\.?[0-9]+)(;)",
                lambda m: f"{m.group(1)}{line_height_override}{m.group(3)}",
                template_html,
                count=1,
            )

        full_html = template_html.replace("{{ content }}", html_body)

        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        output_path = str(output_dir / f"{job_id}.pdf")
        abs_output_path = os.path.abspath(output_path)

        logger.info("Spawning background browser to generate resume PDF...")
        page_fill, initial_fill = _run_ts_pdf(full_html, abs_output_path)

        logger.info(
            f"Resume PDF generated at {abs_output_path} (Page Fill: {page_fill}%, Initial: {initial_fill}%)"
        )
        return output_path, page_fill, initial_fill

    except Exception as ex:
        logger.error(f"Resume PDF generation failed: {ex}")
        raise ex


async def generate_cover_letter_pdf(cover_letter_text: str, job_id: str) -> str:
    """
    Renders a cover letter PDF from plain text using the cover_letter.html template.

    The template expects:
      - {{ date }}  — replaced with today's date (e.g. "May 21, 2026")
      - {{ body }}  — replaced with <p>-wrapped paragraphs of the letter body

    Returns the path to the generated PDF.
    """
    try:
        # Load cover letter template
        template_path = Path("templates/cover_letter.html")
        if not template_path.exists():
            template_path = (
                Path(__file__).resolve().parent.parent.parent
                / "templates"
                / "cover_letter.html"
            )

        template_html = template_path.read_text(encoding="utf-8")

        # Build date string — cross-platform (Windows has no %-d strftime directive)
        _d = date.today()
        today = f"{_d.strftime('%B')} {_d.day}, {_d.year}"

        # Wrap each double-newline-separated paragraph in <p> tags
        paragraphs = [
            p.strip() for p in cover_letter_text.strip().split("\n\n") if p.strip()
        ]
        body_html = "\n".join(f"<p>{p}</p>" for p in paragraphs)

        # Load resume data to get contact details
        resume_data = {}
        try:
            resume_json_path = Path("data/resume.json")
            if not resume_json_path.exists():
                resume_json_path = Path(__file__).resolve().parent.parent.parent / "data" / "resume.json"
            if resume_json_path.exists():
                with open(resume_json_path, "r", encoding="utf-8") as f:
                    resume_data = json.load(f)
        except Exception as e:
            logger.error(f"Could not load resume.json for cover letter template: {e}")

        name = resume_data.get("name", "Candidate Name")
        contact = resume_data.get("contact", {})
        phone = contact.get("phone", "")
        email = contact.get("email", "")
        linkedin = contact.get("linkedin", "")
        github = contact.get("github", "")

        full_html = (template_html
            .replace("{{ date }}", today)
            .replace("{{ body }}", body_html)
            .replace("{{ name }}", name)
            .replace("{{ phone }}", phone)
            .replace("{{ email }}", email)
            .replace("{{ linkedin }}", linkedin)
            .replace("{{ github }}", github)
        )

        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        output_path = str(output_dir / f"{job_id}_cover_letter.pdf")
        abs_output_path = os.path.abspath(output_path)

        logger.info("Spawning background browser to generate cover letter PDF...")
        _run_ts_pdf(full_html, abs_output_path)

        logger.info(f"Cover letter PDF generated at {abs_output_path}")
        return output_path

    except Exception as ex:
        logger.error(f"Cover letter PDF generation failed: {ex}")
        raise ex
