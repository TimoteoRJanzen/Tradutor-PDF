'use client';

import { useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [extractedText, setExtractedText] = useState<string>('');

  const onDrop = (acceptedFiles: File[]) => {
    const selectedFile = acceptedFiles[0];
    if (selectedFile?.type === 'application/pdf') {
      setFile(selectedFile);
      setError(null);
      setExtractedText(''); // Limpa o texto extraído anterior
    } else {
      setError('Por favor, selecione apenas arquivos PDF.');
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf']
    },
    maxFiles: 1
  });

  const handleUpload = async () => {
    if (!file) return;
    
    try {
      setLoading(true);
      setError(null);
      
      const form = new FormData();
      form.append('pdf', file);
      
      const res = await fetch('/api/translate', {
        method: 'POST',
        body: form
      });
      
      if (!res.ok) {
        throw new Error('Erro ao traduzir o PDF');
      }
      
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      
      // Criar link para download
      const link = document.createElement('a');
      link.href = url;
      link.download = `traduzido_${file.name}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      
    } catch (err) {
      setError('Ocorreu um erro ao processar o PDF. Por favor, tente novamente.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleExtractText = async () => {
    if (!file) return;
    
    try {
      setLoading(true);
      setError(null);
      
      const form = new FormData();
      form.append('pdf', file);
      
      const res = await fetch('/api/extract-text', {
        method: 'POST',
        body: form
      });
      
      if (!res.ok) {
        throw new Error('Erro ao extrair texto do PDF');
      }
      
      const data = await res.json();
      setExtractedText(data.text);
      
    } catch (err) {
      setError('Ocorreu um erro ao extrair o texto do PDF. Por favor, tente novamente.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen p-8 flex flex-col items-center">
      <h1 className="text-4xl font-bold mb-8 text-center">Tradutor de PDF</h1>
      
      <Card className="w-full max-w-2xl p-6">
        <div
          {...getRootProps()}
          className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors
            ${isDragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400'}
            ${error ? 'border-red-500' : ''}`}
        >
          <input {...getInputProps()} />
          <div className="space-y-4">
            <p className="text-lg">
              {isDragActive
                ? 'Solte o arquivo PDF aqui'
                : 'Arraste e solte um arquivo PDF aqui, ou clique para selecionar'}
            </p>
            {file && (
              <p className="text-sm text-gray-600">
                Arquivo selecionado: {file.name}
              </p>
            )}
          </div>
        </div>

        {error && (
          <p className="mt-4 text-red-500 text-center">{error}</p>
        )}

        <div className="mt-6 flex justify-center space-x-4">
          <Button
            onClick={handleExtractText}
            disabled={!file || loading}
            className="w-full sm:w-auto"
          >
            {loading ? 'Extraindo...' : 'Extrair Texto'}
          </Button>
          <Button
            onClick={handleUpload}
            disabled={!file || loading}
            className="w-full sm:w-auto"
          >
            {loading ? 'Traduzindo...' : 'Traduzir PDF'}
          </Button>
        </div>

        {extractedText && (
          <div className="mt-6">
            <h2 className="text-lg font-semibold mb-2">Texto Extraído do PDF:</h2>
            <div className="border rounded-lg p-4 bg-gray-50 max-h-96 overflow-y-auto">
              <pre className="whitespace-pre-wrap text-sm">{extractedText}</pre>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
