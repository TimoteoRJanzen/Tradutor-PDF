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
git clone https://github.com/TimoteoRJanzen/pdf-translator.git
cd pdf-translator
```

2. Instale as dependências:
```bash
npm install
```

3. Crie um arquivo `.env.local` na raiz do projeto com sua chave da API do DeepL:
```
DEEPL_API_KEY=sua-chave-api-aqui
```

4. Inicie o servidor de desenvolvimento:
```bash
npm run dev
```

5. Acesse a aplicação em `http://localhost:3000`

## Como Usar

1. Arraste e solte um arquivo PDF na área indicada ou clique para selecionar
2. Clique em "Extrair Texto" para ver o conteúdo do PDF
3. Clique em "Traduzir PDF" para traduzir o documento
4. O PDF traduzido será baixado automaticamente

## Contribuição

Contribuições são bem-vindas! Sinta-se à vontade para abrir issues ou enviar pull requests.

## Licença

Este projeto está sob a licença MIT.
