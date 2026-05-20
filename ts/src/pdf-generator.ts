import { chromium } from 'playwright';

export async function generatePDF(htmlContent: string, outputPath: string) {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  // Set the HTML content
  await page.setContent(htmlContent, { waitUntil: 'networkidle' });
  
  // Generate the PDF
  await page.pdf({
    path: outputPath,
    format: 'Letter',
    printBackground: true,
    margin: { top: '0.3in', bottom: '0.3in', left: '0.4in', right: '0.4in' }
  });
  
  await browser.close();
}
