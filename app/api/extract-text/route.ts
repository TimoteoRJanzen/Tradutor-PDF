import { NextRequest, NextResponse } from 'next/server';
import pdfParse from 'pdf-parse';

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
    const buffer = Buffer.from(await file.arrayBuffer());
    
    // Extrair texto do PDF
    const data = await pdfParse(buffer);
    
    if (!data || !data.text) {
      throw new Error('Não foi possível extrair texto do PDF');
    }
    
    return NextResponse.json({ text: data.text });
  } catch (error) {
    console.error('Erro ao extrair texto do PDF:', error);
    return NextResponse.json(
      { error: 'Erro ao extrair texto do PDF' },
      { status: 500 }
    );
  }
} 