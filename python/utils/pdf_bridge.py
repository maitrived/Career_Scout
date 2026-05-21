import os
import logging
import markdown
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

async def generate_pdf(markdown_content: str, job_id: str) -> tuple[str, int]:
    """Converts markdown to HTML, injects it into template, and calls TS CLI."""
    try:
        # Convert Markdown to HTML
        html_body = markdown.markdown(markdown_content)
        
        # Load template
        template_path = Path("templates/resume.html")
        if not template_path.exists():
            template_path = Path(__file__).resolve().parent.parent.parent / "templates" / "resume.html"
            
        template_html = template_path.read_text(encoding="utf-8")
        full_html = template_html.replace("{{ content }}", html_body)
        
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        output_path = str(output_dir / f"{job_id}.pdf")
        abs_output_path = os.path.abspath(output_path)
        
        # Write HTML to a temporary file
        fd, temp_html_path = tempfile.mkstemp(suffix=".html")
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(full_html)
            
        # Call TS CLI directly via subprocess
        ts_dir = Path(__file__).resolve().parent.parent.parent / "ts"
        
        logger.info("Spawning background browser to generate PDF...")
        
        # Use npx ts-node to run the CLI
        cmd = ["npx", "ts-node", "src/cli.ts", temp_html_path, abs_output_path]
        
        process = subprocess.run(
            cmd,
            cwd=ts_dir,
            capture_output=True,
            text=True,
            shell=True
        )
        
        # Clean up temp file
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
            
        logger.info(f"PDF generated successfully at {abs_output_path} (Page Fill: {page_fill}%, Initial: {initial_fill}%)")
        return output_path, page_fill, initial_fill
        
    except Exception as ex:
        logger.error(f"PDF generation failed: {ex}")
        raise ex
