import express from 'express';
import { generatePDF } from './pdf-generator';

const app = express();
const PORT = process.env.PDF_SERVICE_PORT || 3001;

// Increase payload limit for large HTML files
app.use(express.json({ limit: '10mb' }));

app.post('/generate-pdf', async (req, res) => {
  try {
    const { html, output_path } = req.body;
    
    if (!html || !output_path) {
      return res.status(400).json({ error: 'Missing html or output_path' });
    }
    
    console.log(`Generating PDF -> ${output_path}`);
    await generatePDF(html, output_path);
    
    res.json({ success: true, path: output_path });
  } catch (error: any) {
    console.error('Error generating PDF:', error);
    res.status(500).json({ error: error.message });
  }
});

app.listen(PORT, () => {
  console.log(`Scout PDF Generator service listening on port ${PORT}`);
});
