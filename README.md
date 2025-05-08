# Tradutor de PDF

Uma aplicação para traduzir arquivos PDF do inglês para o português (ou outros idiomas) usando a API do DeepL, mantendo o layout e as fontes o mais próximo possível do original.

> **Nota**: Este é um projeto teste desenvolvido como parte do meu processo de aprendizagem em desenvolvimento de aplicações web com Inteligência Artificial. O objetivo é explorar e praticar a integração de diferentes tecnologias e APIs em um contexto real.

## Funcionalidades

- Upload e tradução de arquivos PDF via interface web (Next.js) ou linha de comando (Python)
- Extração de texto e imagens mantendo o layout
- Tradução automática usando DeepL API
- Download do PDF traduzido
- Suporte a múltiplos idiomas de destino (ex: PT-BR, PT-PT, ES, FR, etc)
- Detecção e substituição inteligente de fontes (fontes embutidas, locais, Google Fonts ou Roboto Condensed)
- Suporte a fontes customizadas: basta adicionar arquivos `.ttf`, `.otf` ou `.ttc` na pasta `fonts/`
- Fallback automático para fontes padrão se a original não estiver disponível
- Log detalhado do processo em `translate_pdf.log`

## Tecnologias Utilizadas

- Next.js 15, React 19, TypeScript (interface web)
- Python 3.8+ (backend/script)
- PyMuPDF (fitz), deepl, requests, Pillow, pdfplumber, reportlab
- DeepL API
- Google Fonts API (opcional)
- Tailwind CSS, Shadcn/ui

## Instalação

1. Clone o repositório:
```bash
git clone https://github.com/TimoteoRJanzen/Tradutor-PDF.git
cd Tradutor-PDF
```

2. Instale as dependências JavaScript (para interface web):
```bash
npm install
```

3. Instale as dependências Python (para tradução via script):

No Linux/macOS:
```bash
pip3 install -r requirements/python-requirements.txt
```
No Windows:
```powershell
py -3 -m pip install -r requirements/python-requirements.txt
```

4. (Opcional) Adicione fontes customizadas na pasta `fonts/` para melhor correspondência de layout.

5. Crie um arquivo `.env.local` na raiz do projeto e defina as variáveis:
```env
DEEPL_API_KEY=sua_chave_de_api_deepl
GOOGLE_FONTS_API_KEY=sua_chave_google_fonts # (opcional)
```

## Uso do Script Python

Traduza um PDF diretamente pela linha de comando:
```bash
python scripts/translate_pdf.py --input caminho/arquivo.pdf --output caminho/arquivo_traduzido.pdf --target_lang PT-BR
```
- `--input`: caminho do PDF original
- `--output`: caminho para salvar o PDF traduzido
- `--target_lang`: idioma de destino (ex: PT-BR, ES, FR, etc)

O script tentará manter o layout, imagens e fontes o mais próximo possível do original. Se necessário, baixe fontes do Google Fonts ou use Roboto Condensed como fallback.

## Variáveis de Ambiente
- `DEEPL_API_KEY` (**obrigatória**): chave da API DeepL para tradução
- `GOOGLE_FONTS_API_KEY` (opcional): para baixar fontes do Google Fonts automaticamente

## Observações
- Para melhor qualidade visual, adicione fontes usadas nos PDFs na pasta `fonts/`.
- O log detalhado do processo é salvo em `translate_pdf.log`.
- O projeto pode ser executado tanto via interface web quanto via linha de comando Python.

## Dependências Python
- pdfplumber
- reportlab
- deepl
- PyMuPDF
- requests
- Pillow
- python-dotenv (opcional, recomendado para uso de .env)

---

Contribuições e sugestões são bem-vindas!