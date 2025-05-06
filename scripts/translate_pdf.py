#!/usr/bin/env python3
import os
import argparse
import fitz  # PyMuPDF
import deepl

# Parser de argumentos
def parse_args():
    parser = argparse.ArgumentParser(description="Traduz PDF por blocos mantendo layout")
    parser.add_argument('--input', required=True, help='Caminho do PDF de entrada')
    parser.add_argument('--output', required=True, help='Caminho do PDF de saída traduzido')
    parser.add_argument('--target_lang', default='PT-BR', help='Idioma de destino, ex: PT-BR ou PT-PT')
    return parser.parse_args()

# Função principal
def main():
    args = parse_args()
    auth_key = os.getenv('DEEPL_API_KEY')
    if not auth_key:
        raise RuntimeError('DEEPL_API_KEY não está definida')
    translator = deepl.Translator(auth_key)

    # Abre o documento original e cria novo documento vazio
    doc = fitz.open(args.input)
    new_doc = fitz.open()
    for page in doc:
        # nova página com mesmas dimensões
        new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
        # extrai spans de texto e blocos de imagem
        text_dict = page.get_text('dict')
        spans = []           # lista de spans: origin, text, size, font, flags
        image_blocks = []    # lista de (bbox, img_bytes)
        for block in text_dict['blocks']:
            bbox = block['bbox']
            # imagens
            if block['type'] == 1:
                img_obj = block.get('image')
                # se 'xref', extrai bytes da imagem
                if isinstance(img_obj, dict) and 'xref' in img_obj:
                    xref = img_obj['xref']
                    if isinstance(xref, int):
                        img_info = doc.extract_image(xref)
                        img_bytes = img_info.get('image')
                        if isinstance(img_bytes, (bytes, bytearray)):
                            image_blocks.append((bbox, img_bytes))
                # se fluxo de bytes
                elif isinstance(img_obj, (bytes, bytearray)):
                    image_blocks.append((bbox, img_obj))
            # texto
            elif block['type'] == 0:
                for line in block['lines']:
                    for span in line['spans']:
                        txt = span['text']
                        if not txt.strip():
                            continue
                        spans.append({
                            'origin': span['origin'],
                            'text': txt,
                            'size': span['size'],
                            'font': span['font'],
                            'flags': span['flags'],
                        })
        # reinsere imagens no novo documento
        for bbox, img_data in image_blocks:
            new_page.insert_image(fitz.Rect(*bbox), stream=img_data)
        # reinsere spans de texto traduzidos, preservando tamanho e orientação
        for span in spans:
            translated = translator.translate_text(
                span['text'], source_lang='EN', target_lang=args.target_lang
            ).text
            x, y = span['origin']
            fontsize = span['size']
            raw_font = span['font']
            # mapeia estilo de fonte padrão
            font_out = 'Helvetica'
            if 'Bold' in raw_font:
                font_out = 'Helvetica-Bold'
            elif 'Italic' in raw_font or 'Oblique' in raw_font:
                font_out = 'Helvetica-Oblique'
            # insere texto mantendo origem, tamanho e orientação
            new_page.insert_text(
                (x, y), translated,
                fontsize=fontsize,
                fontname=font_out
            )
    # salva o PDF traduzido apenas com conteúdo reescrito
    new_doc.save(args.output)
    new_doc.close()
    doc.close()

if __name__ == '__main__':
    main() 