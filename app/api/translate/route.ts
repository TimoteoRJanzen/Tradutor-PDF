import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import { execFile } from 'child_process';
import { promisify } from 'util';
const execFileAsync = promisify(execFile);

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
    // Salvar arquivo temporário e idioma alvo
    const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'translate-'));
    const inputPath = path.join(tempDir, 'input.pdf');
    const outputPath = path.join(tempDir, 'output.pdf');
    const arrayBuffer = await file.arrayBuffer();
    await fs.writeFile(inputPath, Buffer.from(arrayBuffer));
    // idioma de destino (opcional, default PT-BR)
    const targetLang = (formData.get('target_lang') as string) || 'PT-BR';

    // Tentar executar o script Python com múltiplos comandos candidatos
    const scriptPath = path.join(process.cwd(), 'scripts', 'translate_pdf.py');
    const isWin = process.platform === 'win32';
    // Fallback de comandos Python:
    const candidates = isWin
      ? [process.env.PYTHON_PATH, 'py', 'python']
      : [process.env.PYTHON_PATH, 'python3', 'python'];
    // Remove entradas vazias e duplicadas
    const uniqueCandidates = Array.from(new Set(candidates.filter(Boolean as any))) as string[];
    let executed = false;
    for (const cmd of uniqueCandidates) {
      // Montar argumentos: 'py' usa '-3', outros não
      const baseArgs = cmd === 'py'
        ? ['-3', scriptPath]
        : [scriptPath];
      // adiciona flags de input, output e idioma
      const args = [
        ...baseArgs,
        '--input', inputPath,
        '--output', outputPath,
        '--target_lang', targetLang
      ];
      try {
        await execFileAsync(cmd, args, { env: process.env });
        executed = true;
        break;
      } catch (e: any) {
        const stderr: string = e.stderr || '';
        // Se comando não encontrado ou stub alias de Windows (Python não foi encontrado), tenta próximo
        if (
          e.code === 'ENOENT' ||
          stderr.toLowerCase().includes('não foi encontrado') ||
          stderr.toLowerCase().includes('store') ||
          stderr.toLowerCase().includes('not recognized as an internal')
        ) continue;
        // Se faltar módulo Python, informar ao usuário
        if (stderr.includes('ModuleNotFoundError')) {
          return NextResponse.json(
            { error: 'Dependência Python não instalada. Execute pip install -r requirements/python-requirements.txt para instalar pdfplumber, reportlab, deepl e PyMuPDF.' },
            { status: 500 }
          );
        }
        // Outro erro Python, repassa
        throw e;
      }
    }
    if (!executed) {
      return NextResponse.json(
        { error: 'Python não encontrado. Instale Python 3 e adicione ao PATH ou defina PYTHON_PATH.' },
        { status: 500 }
      );
    }

    // Ler PDF traduzido
    const translatedBuffer = await fs.readFile(outputPath);

    // Limpar temporários
    await fs.rm(tempDir, { recursive: true, force: true });

    return new NextResponse(translatedBuffer, {
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