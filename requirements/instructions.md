# Project overview
Use esse guia para construir um web app onde os usuários podem fazer upload de um arquivo .pdf em inglês e então esse pdf será traduzido para o português e o usuario poderá baixar esse novo pdf traduzido para o português. 

1. Visão Geral do Projeto

O usuário faz upload de um PDF em inglês pela interface Next.js (pasta app), usando componentes Shadcn UI e Tailwind CSS.

Uma API Route do Next.js (/app/api/translate/route.ts) processa o arquivo no servidor:

Recebe o PDF via multipart/form-data usando next-connect e multer.

Extrai o texto do buffer com pdf-parse.

Envia o texto extraído à Hugging Face Inference API para tradução (modelo Helsinki-NLP/opus-mt-en-pt), usando axios e variável de ambiente HF_TOKEN.

Gera um novo PDF com o texto traduzido usando pdf-lib.

A API retorna o PDF final como application/pdf para download.

Deploy automático no Vercel via GitHub Actions a cada push na main.


3. Arquitetura da Aplicação
    3.1 Front-end (Next.js + Shadcn UI + Tailwind)
     - Página /app/page.tsx com <Form> e react-dropzone para drag-and-drop;

     - Componentes Shadcn UI inicializados via npx shadcn-ui init.

    3.2 API Route (/app/api/translate/route.ts)

     - Usa next-connect + multer para ler req.file.buffer;

     - pdf-parse para extrair texto do buffer;

     - Chamada à Hugging Face Inference API com axios e token via process.env.HF_TOKEN;

     - Gera PDF final com pdf-lib e retorna como application/pdf

    3.3 Versionamento e CI/CD

     - GitHub Actions (.github/workflows/ci.yml) roda lint e testes, e aciona Vercel CLI para deploy;

     - Variáveis de ambiente (HF_TOKEN) definidas no dashboard Vercel


# Feature requirements
- Crie na página um título centralizado "Tradutor de PDF"
- abixo um caixa onde o usuário pode arrastar o arquivo .pdf para fazer upload no site. Ou se o usuario não quiser arrastar para dentro da caixa, também terá dentro dessa caixa um botão que o usuario pode apertar para abrir os arquivos do próprio computador para encontrar o arquivo pdf que ele quer fazer a tradução.
- Faça um UI e animação bonitas quanto o usuario interagir com a caixa e enquanto o site processa o pdf.
- Assim que o novo pdf estiver traduzido e pronto, mostre uma opção para baixar esse novo pdf.

# Relevant docs
## Exemplo API ROUTE /app/api/translate/route.ts
    import { NextResponse } from 'next/server';
    import nc from 'next-connect';
    import multer from 'multer';
    import pdf from 'pdf-parse';
    import { PDFDocument } from 'pdf-lib';
    import axios from 'axios';

    const upload = multer({ storage: multer.memoryStorage() });
    const handler = nc().use(upload.single('pdf'));

    handler.post(async (req: any, res: any) => {
    // extrair texto
    const data = await pdf(req.file.buffer);
    // traduzir
    const hfRes = await axios.post(
        'https://api-inference.huggingface.co/models/Helsinki-NLP/opus-mt-en-pt',
        { inputs: data.text },
        { headers: { Authorization: `Bearer ${process.env.HF_TOKEN}` } }
    );
    const translated = hfRes.data[0].translation_text;
    // gerar PDF
    const doc = await PDFDocument.create();
    const page = doc.addPage();
    page.drawText(translated, { x: 20, y: 750 });
    const pdfBytes = await doc.save();
    return new NextResponse(Buffer.from(pdfBytes), {
        headers: { 'Content-Type': 'application/pdf' },
    });
    });

    export const POST = handler;
    export const runtime = 'edge';

## Exemplo Front-end: /app/page.tsx
    'use client';
    import { useState } from 'react';
    import { useDropzone } from 'react-dropzone';

    export default function Home() {
    const [file, setFile] = useState<File | null>(null);
    const [loading, setLoading] = useState(false);
    const onDrop = (accepted: File[]) => setFile(accepted[0]);
    const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop });

    const handleUpload = async () => {
        if (!file) return;
        setLoading(true);
        const form = new FormData();
        form.append('pdf', file);
        const res = await fetch('/api/translate', { method: 'POST', body: form });
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        setLoading(false);
        window.open(url);
    };

    return (
        <div className="p-8">
        <h1 className="text-2xl font-bold text-center">Tradutor de PDF</h1>
        <div
            {...getRootProps()}
            className={`mt-4 border-2 border-dashed p-8 text-center ${
            isDragActive ? 'bg-gray-100' : ''
            }`}>
            <input {...getInputProps()} accept=".pdf" />
            {isDragActive ? 'Solte o PDF aqui' : 'Arraste ou clique para selecionar o PDF'}
        </div>
        <button
            className="mt-4 btn-primary"
            onClick={handleUpload}
            disabled={!file || loading}
        >
            {loading ? 'Traduzindo...' : 'Traduzir PDF'}
        </button>
        </div>
    );
    }



# Current File structure

Tradutor-PDF
├── .next
├── app
│   ├── favicon.ico
│   ├── globals.css
│   ├── layout.tsx
│   ├── page.tsx
│   └── components
│       └── ui
│           ├── button.tsx
│           ├── card.tsx
│           ├── form.tsx
│           ├── input.tsx
│           └── label.tsx
│   └── lib
│       └── utils.ts
├── node_modules
├── public
│   ├── file.svg
│   ├── globe.svg
│   ├── next.svg
│   ├── vercel.svg
│   └── window.svg
├── requirements
│   └── instructions.md
├── .env.local                     # Onde está armazenado HF_TOKEN
├── .gitignore
├── components.json
├── eslint.config.mjs
├── next-env.d.ts
├── next.config.ts
├── package-lock.json
├── package.json
├── postcss.config.mjs
├── README.md
└── tsconfig.json


# Regras
- Todos os novos componentes devem ir para /components e ser nomeados como example-component.tsx, a menos que especificado de outra forma.

- Todas as novas páginas devem ir para /app.