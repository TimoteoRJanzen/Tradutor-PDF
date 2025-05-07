'use client';

import { useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { motion, AnimatePresence } from 'framer-motion';

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [translatedPdfUrl, setTranslatedPdfUrl] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [targetLang, setTargetLang] = useState<string>('PT-BR');
  const [logs, setLogs] = useState<string[]>([]);

  const onDrop = (acceptedFiles: File[]) => {
    const selectedFile = acceptedFiles[0];
    if (selectedFile?.type === 'application/pdf') {
      setFile(selectedFile);
      setError(null);
      setTranslatedPdfUrl(null); // Limpa a URL do PDF anterior
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
      setProgress(0);
      setTranslatedPdfUrl(null);
      setLogs([]);
      
      const form = new FormData();
      form.append('pdf', file);
      form.append('target_lang', targetLang);
      
      const res = await fetch('/api/translate', {
        method: 'POST',
        body: form
      });
      
      if (!res.ok) {
        // Tenta obter mensagem de erro e logs do servidor
        let errorMessage = 'Erro ao traduzir o PDF';
        try {
          const errJson = await res.json();
          errorMessage = errJson.error || errorMessage;
          if (Array.isArray(errJson.logs)) {
            setLogs(errJson.logs);
          }
        } catch (e) {
          console.error('Falha ao ler resposta de erro:', e);
        }
        console.error('Erro na API:', errorMessage);
        setError(errorMessage);
        setLoading(false);
        return;
      }
      
      // Extrai logs do header
      const logsHeader = res.headers.get('X-Translation-Logs');
      if (logsHeader) {
        try {
          const decodedLogs = JSON.parse(Buffer.from(logsHeader, 'base64').toString());
          setLogs(decodedLogs);
        } catch (e) {
          console.error('Erro ao decodificar logs:', e);
        }
      }
      
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setTranslatedPdfUrl(url);
      setProgress(100);
    } catch (err) {
      setError('Ocorreu um erro ao processar o PDF. Por favor, tente novamente.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = () => {
    if (!translatedPdfUrl || !file) return;
    
    const link = document.createElement('a');
    link.href = translatedPdfUrl;
    link.download = `traduzido_${file.name}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="min-h-screen p-8 flex flex-col items-center bg-gradient-to-b from-blue-50 to-white">
      <motion.h1 
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-4xl font-bold mb-8 text-center text-blue-900"
      >
        Tradutor de PDF
      </motion.h1>
      
      <Card className="w-full max-w-2xl p-6 shadow-lg">
        <motion.div
          {...(getRootProps() as any)}
          className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-all duration-300
            ${isDragActive ? 'border-blue-500 bg-blue-50 scale-105' : 'border-gray-300 hover:border-gray-400'}
            ${error ? 'border-red-500' : ''}`}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
        >
          <input {...getInputProps()} />
          <div className="space-y-4">
            <motion.p 
              className="text-lg"
              animate={{ color: isDragActive ? '#3B82F6' : '#374151' }}
            >
              {isDragActive
                ? 'Solte o arquivo PDF aqui'
                : 'Arraste e solte um arquivo PDF aqui, ou clique para selecionar'}
            </motion.p>
            {file && (
              <motion.p 
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="text-sm text-gray-600"
              >
                Arquivo selecionado: {file.name}
              </motion.p>
            )}
          </div>
        </motion.div>

        <AnimatePresence>
          {error && (
            <motion.p 
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="mt-4 text-red-500 text-center"
            >
              {error}
            </motion.p>
          )}
        </AnimatePresence>

        <div className="mt-4 flex items-center space-x-2">
          <label htmlFor="targetLang" className="text-sm font-medium">Idioma:</label>
          <select
            id="targetLang"
            value={targetLang}
            onChange={e => setTargetLang(e.target.value)}
            className="border border-gray-300 rounded px-2 py-1 text-sm"
          >
            <option value="PT-BR">Português (Brasil)</option>
            <option value="PT-PT">Português (Portugal)</option>
          </select>
        </div>

        <div className="mt-6 flex flex-col sm:flex-row justify-center gap-4">
          <Button
            onClick={handleUpload}
            disabled={!file || loading}
            className="w-full sm:w-auto bg-blue-600 hover:bg-blue-700 transition-colors"
          >
            {loading ? (
              <div className="flex items-center space-x-2">
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                <span>Traduzindo...</span>
              </div>
            ) : (
              'Traduzir PDF'
            )}
          </Button>

          {translatedPdfUrl && (
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              className="w-full sm:w-auto"
            >
              <Button
                onClick={handleDownload}
                className="w-full bg-green-600 hover:bg-green-700 transition-colors"
              >
                <div className="flex items-center space-x-2">
                  <svg 
                    className="w-5 h-5" 
                    fill="none" 
                    stroke="currentColor" 
                    viewBox="0 0 24 24"
                  >
                    <path 
                      strokeLinecap="round" 
                      strokeLinejoin="round" 
                      strokeWidth={2} 
                      d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" 
                    />
                  </svg>
                  <span>Baixar PDF Traduzido</span>
                </div>
              </Button>
            </motion.div>
          )}
        </div>

        {loading && (
          <div className="mt-4">
            <div className="w-full bg-gray-200 rounded-full h-2.5">
              <motion.div
                className="bg-blue-600 h-2.5 rounded-full"
                initial={{ width: 0 }}
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.5 }}
              />
            </div>
          </div>
        )}

        {/* Área de logs */}
        <AnimatePresence>
          {logs.length > 0 && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="mt-6 border rounded-lg p-4 bg-gray-50"
            >
              <h3 className="text-sm font-medium mb-2 text-gray-700">Logs da Tradução:</h3>
              <div className="max-h-60 overflow-y-auto text-sm font-mono">
                {logs.map((log, index) => (
                  <div key={index} className="text-gray-600 whitespace-pre-wrap">
                    {log}
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </Card>
    </div>
  );
}
