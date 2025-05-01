const { PDFDocument, StandardFonts } = require('pdf-lib');
const fs = require('fs');
const path = require('path');

async function createTestPDF() {
  // Criar um novo documento PDF
  const pdfDoc = await PDFDocument.create();
  
  // Adicionar uma página
  const page = pdfDoc.addPage();
  const { width, height } = page.getSize();
  
  // Carregar a fonte
  const font = await pdfDoc.embedFont(StandardFonts.Helvetica);
  
  // Adicionar texto
  page.drawText('Test PDF File', {
    x: 50,
    y: height - 50,
    size: 12,
    font,
  });
  
  // Salvar o PDF
  const pdfBytes = await pdfDoc.save();
  
  // Criar o diretório se não existir
  const dir = path.join(__dirname, 'data');
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  
  // Salvar o arquivo
  fs.writeFileSync(path.join(dir, '05-versions-space.pdf'), pdfBytes);
  
  console.log('PDF de teste criado com sucesso!');
}

createTestPDF().catch(console.error); 