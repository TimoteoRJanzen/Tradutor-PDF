# Tradutor de PDF

Uma aplicação web para traduzir arquivos PDF do inglês para o português usando a API do DeepL.

> **Nota**: Este é um projeto teste desenvolvido como parte do meu processo de aprendizagem em desenvolvimento de aplicações web com Inteligência Artificial. O objetivo é explorar e praticar a integração de diferentes tecnologias e APIs em um contexto real.

## Funcionalidades

- Upload de arquivos PDF
- Extração de texto do PDF
- Tradução automática usando DeepL API
- Download do PDF traduzido
- Interface amigável com drag-and-drop

## Tecnologias Utilizadas

- Next.js 15
- React 19
- TypeScript
- DeepL API
- PDF.js
- Tailwind CSS
- Shadcn/ui

## Configuração

1. Clone o repositório:
```bash
git clone https://github.com/TimoteoRJanzen/Tradutor-PDF.git
cd Tradutor-PDF
```

2. Instale as dependências JavaScript:
```bash
npm install
```

3. Instale as dependências Python:

   No Linux/macOS:
   ```bash
   pip3 install -r requirements/python-requirements.txt
   ```

   No Windows:
   ```powershell
   py -3 -m pip install -r requirements/python-requirements.txt
   ```

4. Crie um arquivo `.env.local`