import { chromium } from 'playwright';

export async function generatePDF(htmlContent: string, outputPath: string) {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  // A4 standard dimensions at 96 DPI: 794 x 1123 px
  // PDF Margin: 12mm top/bottom/left/right = 12 * (96 / 25.4) = ~45.35 px
  // Total margins width/height = ~90.7 px
  // Actual printable width = 794 - 90.7 = ~703 px
  // Actual printable height = 1123 - 90.7 = ~1032 px
  const PRINTABLE_WIDTH = 703;
  const PRINTABLE_HEIGHT = 1032;

  // Set viewport to exactly match the printable area so there is zero reflow/wrapping mismatch
  await page.setViewportSize({ width: PRINTABLE_WIDTH, height: PRINTABLE_HEIGHT });

  // Pass 1: Render and measure scroll height
  await page.setContent(htmlContent, { waitUntil: 'networkidle' });
  let contentHeight = await page.evaluate(() => document.body.scrollHeight);

  // Do NOT rescale when initial page fill is within 95% - 100%.
  // Only adjust if content is noticeably short (<95%) or overflowing (>100%).
  const TARGET_MIN = 0.95;  // scale up if too short (fills less than 95% of page)
  const TARGET_MAX = 1.00;  // scale down if too tall (exceeds page height)

  let initialRatio = contentHeight / PRINTABLE_HEIGHT;
  let ratio = initialRatio;

  // Pass 2: Inject corrected CSS variables if scaling is required to fit perfectly on 1 page
  if (ratio < TARGET_MIN || ratio > TARGET_MAX) {
    // Original base font size is 10pt. Scale based on the ratio.
    const scaledFontSize = Math.min(11.0, Math.max(8.2, 10.0 / ratio));
    const scaledLineHeight = ratio > 1 ? 1.00 : 1.10;
    const scaledSectionGap = ratio > 1 ? 5 : 10;
    const scaledBulletGap = ratio > 1 ? 0 : 2;
    const scaledMarginTop = ratio > 1 ? 2 : 5;

    await page.evaluate(({ fs, lh, sg, bg, mt }: { fs: number, lh: number, sg: number, bg: number, mt: number }) => {
      const root = document.documentElement;
      root.style.setProperty('--font-size', `${fs}pt`);
      root.style.setProperty('--line-height', `${lh}`);
      root.style.setProperty('--section-gap', `${sg}px`);
      root.style.setProperty('--bullet-gap', `${bg}px`);
      root.style.setProperty('--margin-top', `${mt}px`);
    }, { fs: scaledFontSize, lh: scaledLineHeight, sg: scaledSectionGap, bg: scaledBulletGap, mt: scaledMarginTop });

    // Let Playwright reflow the page and re-measure
    await page.waitForTimeout(150);
    contentHeight = await page.evaluate(() => document.body.scrollHeight);
    ratio = contentHeight / PRINTABLE_HEIGHT;
  }

  // Generate the PDF
  await page.pdf({
    path: outputPath,
    format: 'A4',
    printBackground: true,
    margin: { top: '12mm', bottom: '12mm', left: '12mm', right: '12mm' }
  });

  await browser.close();

  const finalRatio = Math.round(ratio * 100);
  const initialFill = Math.round(initialRatio * 100);
  console.log(`📄 PDF generated: ${finalRatio}% page fill (Initial: ${initialFill}%) -> ${outputPath}`);
  return { initialFill, finalRatio };
}
