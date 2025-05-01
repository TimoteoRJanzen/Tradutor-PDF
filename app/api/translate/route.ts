import { NextRequest, NextResponse } from 'next/server';
import { PDFDocument, rgb, StandardFonts } from 'pdf-lib';
import pdfParse from 'pdf-parse';
import { translateText as translateWithDeepL } from '../config';

interface TextElement {
  text: string;
  x: number;
  y: number;
  fontSize: number;
  font: string;
  color: { r: number; g: number; b: number };
}

async function extractTextWithFormatting(buffer: Buffer): Promise<TextElement[]> {
  try {
    // Carregar o PDF original
    const pdfDoc = await PDFDocument.load(buffer);
    const pages = pdfDoc.getPages();
    const textElements: TextElement[] = [];

    // Processar cada página
    for (let i = 0; i < pages.length; i++) {
      const page = pages[i];
      const { width, height } = page.getSize();
      
      // Extrair texto com pdf-parse
      const data = await pdfParse(buffer);
      
      if (data && data.text) {
        const lines = data.text.split('\n');
        let y = height - 50; // Posição inicial Y

        for (const line of lines) {
          if (line.trim()) {
            // Calcular a largura do texto para centralizar
            const textWidth = line.length * 7; // Aproximação grosseira
            const x = (width - textWidth) / 2;

            textElements.push({
              text: line,
              x: Math.max(50, x), // Mínimo de 50px da margem
              y,
              fontSize: 12,
              font: 'Helvetica',
              color: { r: 0, g: 0, b: 0 }
            });
            y -= 20; // Espaçamento entre linhas
          }
        }
      }
    }

    return textElements;
  } catch (error) {
    console.error('Erro ao extrair texto com formatação:', error);
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

    // Converter o arquivo para Buffer
    const arrayBuffer = await file.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);
    
    // Extrair texto com formatação
    const textElements = await extractTextWithFormatting(buffer);
    console.log('Elementos de texto extraídos:', textElements.length);
    
    // Traduzir cada elemento de texto
    const translatedElements = await Promise.all(
      textElements.map(async (element) => ({
        ...element,
        text: await translateWithDeepL(element.text)
      }))
    );
    
    // Criar um novo PDF com o texto traduzido
    const newPdf = await PDFDocument.create();
    const newPage = newPdf.addPage();
    const { width, height } = newPage.getSize();
    
    // Carregar a fonte
    const font = await newPdf.embedFont(StandardFonts.Helvetica);
    
    // Desenhar cada elemento traduzido
    for (const element of translatedElements) {
      newPage.drawText(element.text, {
        x: element.x,
        y: element.y,
        size: element.fontSize,
        font,
        color: rgb(element.color.r, element.color.g, element.color.b)
      });
    }

    // Salvar o PDF
    const pdfBytes = await newPdf.save();
    
    // Retornar o PDF traduzido
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