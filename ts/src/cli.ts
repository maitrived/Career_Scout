import { generatePDF } from './pdf-generator';
import * as fs from 'fs';

async function main() {
  const args = process.argv.slice(2);
  if (args.length < 2) {
    console.error('Usage: ts-node src/cli.ts <htmlFilePath> <outputPdfPath>');
    process.exit(1);
  }

  const htmlPath = args[0];
  const outputPath = args[1];

  try {
    const htmlContent = fs.readFileSync(htmlPath, 'utf8');
    await generatePDF(htmlContent, outputPath);
    console.log(`Successfully generated PDF: ${outputPath}`);
  } catch (err) {
    console.error('Error generating PDF:', err);
    process.exit(1);
  }
}

main();
