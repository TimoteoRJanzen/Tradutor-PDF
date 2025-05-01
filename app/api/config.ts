import * as deepl from 'deepl-node';

// Verificar se a chave da API está definida
const apiKey = process.env.DEEPL_API_KEY;
if (!apiKey) {
  throw new Error('A chave da API do DeepL não está configurada. Por favor, crie um arquivo .env.local com DEEPL_API_KEY=sua-chave-api-aqui');
}

// Inicializa o cliente DeepL com sua chave de API
export const translator = new deepl.Translator(apiKey);

// Configurações padrão para tradução
export const DEFAULT_TRANSLATION_OPTIONS = {
    sourceLang: 'EN' as deepl.SourceLanguageCode,
    targetLang: 'PT-BR' as deepl.TargetLanguageCode,
    preserveFormatting: true,
};

// Função auxiliar para traduzir texto
export async function translateText(text: string, options = DEFAULT_TRANSLATION_OPTIONS) {
    try {
        const result = await translator.translateText(text, options.sourceLang, options.targetLang, {
            preserveFormatting: options.preserveFormatting,
        });
        return result.text;
    } catch (error) {
        console.error('Erro na tradução:', error);
        throw new Error('Falha ao traduzir o texto');
    }
} 