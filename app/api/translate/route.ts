import { NextRequest, NextResponse } from 'next/server';
import { PDFDocument, rgb, StandardFonts } from 'pdf-lib';
import pdfParse from 'pdf-parse';
import { translateText } from '../config';

// Função para suprimir warnings específicos
function suppressWarnings() {
  const originalConsoleWarn = console.warn;
  console.warn = function(...args) {
    // Ignorar warnings específicos do pdf-parse
    if (
      args[0]?.includes('Invalid stream') ||
      args[0]?.includes('Indexing all PDF objects') ||
      args[0]?.includes('TT: undefined function')
    ) {
      return;
    }
    originalConsoleWarn.apply(console, args);
  };
}

async function extractTextFromPDF(arrayBuffer: ArrayBuffer): Promise<TextElement[]> {
  try {
    // Suprimir warnings específicos
    suppressWarnings();

    // Converter ArrayBuffer para Buffer de forma segura
    const buffer = Buffer.from(arrayBuffer);
    
    // Extrair texto do PDF
    const data = await pdfParse(buffer);

    const textElements: TextElement[] = [];
    const lines = data.text.split('\n');
    let y = 800; // Posição inicial Y
    const font = 'Helvetica';
    const color = { r: 0, g: 0, b: 0 };
    const pageWidth = 595.28; // A4
    const margin = 50;
    const usableWidth = pageWidth - 2 * margin;
    const minFontSize = 8;
    const maxFontSize = 12;

    for (const line of lines) {
      if (line.trim()) {
        // Ajustar o tamanho da fonte para caber na largura útil
        let fontSize = maxFontSize;
        let textWidth = line.length * (fontSize * 0.6); // Aproximação
        while (textWidth > usableWidth && fontSize > minFontSize) {
          fontSize -= 0.5;
          textWidth = line.length * (fontSize * 0.6);
        }
        textElements.push({
          text: line,
          x: margin,
          y,
          fontSize,
          font,
          color
        });
        y -= fontSize * 1.5;
      }
    }

    return textElements;
  } catch (error) {
    console.error('Erro ao extrair texto do PDF:', error);
    throw error;
  }
}

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const file = formData.get('pdf') as File;
    if (!file) {
      return NextResponse.json(
        { error: 'Nenhum arquivo PDF foi enviado' },
        { status: 400 }
      );
    }
    // Extrair texto do PDF
    const arrayBuffer = await file.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);
    const data = await pdfParse(buffer);
    const originalText = data.text;

    // Traduzir todo o texto de uma vez
    const translatedText = await translateText(originalText);

    // Criar novo PDF simples com o texto traduzido
    const pdfDoc = await PDFDocument.create();
    const page = pdfDoc.addPage([595.28, 841.89]); // A4
    const font = await pdfDoc.embedFont(StandardFonts.Helvetica);
    const fontSize = 12;
    const margin = 50;
    const maxWidth = 595.28 - 2 * margin;
    let y = 841.89 - margin;

    // Quebrar o texto traduzido em linhas para caber na largura da página
    const words = translatedText.split(/\s+/);
    let line = '';
    for (const word of words) {
      const testLine = line ? line + ' ' + word : word;
      const textWidth = font.widthOfTextAtSize(testLine, fontSize);
      if (textWidth > maxWidth) {
        page.drawText(line, { x: margin, y, size: fontSize, font, color: rgb(0,0,0) });
        y -= fontSize * 1.5;
        line = word;
      } else {
        line = testLine;
      }
    }
    if (line) {
      page.drawText(line, { x: margin, y, size: fontSize, font, color: rgb(0,0,0) });
    }

    const pdfBytes = await pdfDoc.save();
    return new NextResponse(pdfBytes, {
      headers: {
        'Content-Type': 'application/pdf',
        'Content-Disposition': 'attachment; filename="traduzido.pdf"'
      }
    });
  } catch (error) {
    console.error('Erro ao processar o PDF:', error);
    return NextResponse.json(
      { error: 'Erro ao processar o PDF: ' + (error instanceof Error ? error.message : String(error)) },
      { status: 500 }
    );
  }
}

// Removendo o Edge Runtime para usar o ambiente Node.js normal
// export const runtime = 'edge'; 