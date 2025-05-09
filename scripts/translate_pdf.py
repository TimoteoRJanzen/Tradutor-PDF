#!/usr/bin/env python3
import os
import argparse
import fitz  # PyMuPDF
import deepl
import tempfile
import shutil
import requests
import logging
import sys
import difflib
import re
import html
try:
    from dotenv import load_dotenv
    # Carrega .env e .env.local para fazer override de variáveis
    load_dotenv()  # carrega .env
    local_env = os.path.join(os.getcwd(), '.env.local')
    if os.path.exists(local_env):
        load_dotenv(local_env, override=True)
except ImportError:
    pass

# Configuração do logging
def setup_logging():
    logger = logging.getLogger('translate_pdf')
    logger.setLevel(logging.DEBUG)
    
    # Handler para arquivo
    fh = logging.FileHandler('translate_pdf.log')
    fh.setLevel(logging.DEBUG)
    
    # Handler para console
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    
    # Formato do log
    formatter = logging.Formatter('%(asctime)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger

# Parser de argumentos
def parse_args():
    parser = argparse.ArgumentParser(description="Traduz PDF por blocos mantendo layout")
    parser.add_argument('--input', required=True, help='Caminho do PDF de entrada')
    parser.add_argument('--output', required=True, help='Caminho do PDF de saída traduzido')
    parser.add_argument('--target_lang', default='PT-BR', help='Idioma de destino, ex: PT-BR ou PT-PT')
    return parser.parse_args()

# Função principal
def main():
    logger = setup_logging()
    logger.info("Carregando variáveis de ambiente (.env, .env.local e variáveis de sistema)")
    args = parse_args()
    auth_key = os.getenv('DEEPL_API_KEY')
    logger.info(f"DeepL API key presente: {bool(auth_key)}")
    if not auth_key:
        raise RuntimeError('DEEPL_API_KEY não está definida')
    translator = deepl.Translator(auth_key)

    # Diretório temporário para baixar fontes
    tmp_dir = tempfile.mkdtemp(prefix="fonts_")
    font_registry = {}
    # Mapear nomes de fontes customizadas para seus arquivos
    file_registry = {}
    # Mapear fontes locais em ./fonts
    local_fonts_dir = os.path.join(os.getcwd(), 'fonts')
    local_fonts_map = {}
    if os.path.isdir(local_fonts_dir):
        for fname in os.listdir(local_fonts_dir):
            if fname.lower().endswith(('.ttf', '.otf', '.ttc')):
                reg_name = os.path.splitext(fname)[0].lower()
                path = os.path.join(local_fonts_dir, fname)
                local_fonts_map[reg_name] = path
                file_registry[reg_name] = path
                logger.info(f"Fonte local disponível: '{reg_name}' em '{path}'")
    else:
        local_fonts_map = {}

    # Abre o documento original e cria novo documento vazio
    doc = fitz.open(args.input)
    new_doc = fitz.open()
    # Extrai e registra fontes do documento
    font_info_map = {}
    for page_font in doc:
        for font in page_font.get_fonts(full=True):
            xref = font[0]
            ps_name = font[3]
            is_embedded = font[4] if len(font) > 4 else False
            if ps_name not in font_info_map:
                font_info_map[ps_name] = (xref, is_embedded)

    # Baixar e preparar Roboto Condensed como fonte fallback
    roboto_font_paths = download_and_prepare_roboto_condensed_fonts(tmp_dir, logger)
    # Mapear Roboto Condensed como fonte fallback
    for style, path in roboto_font_paths.items():
        if path and os.path.exists(path):
            font_registry[style] = style
            file_registry[style] = path
            logger.info(f"Fallback Roboto Condensed '{style}' mapeado para uso por página")

    # Definir fontes padrão para fallback
    font_registry['default'] = font_registry.get('RobotoCondensed', 'Times-Roman')
    font_registry['default_bold'] = font_registry.get('RobotoCondensed-Bold', 'Times-Bold')
    font_registry['default_italic'] = font_registry.get('RobotoCondensed-Italic', 'Times-Italic')
    # Carrega catálogo do Google Fonts
    google_fonts = {}
    api_key = os.getenv("GOOGLE_FONTS_API_KEY")
    logger.info(f"Google Fonts API key presente: {bool(api_key)}")
    if api_key:
        url = "https://www.googleapis.com/webfonts/v1/webfonts"
        params = {"key": api_key, "subset": "latin"}
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            fonts = resp.json().get("items", [])
            for f in fonts:
                google_fonts[f["family"]] = f["files"]
        except Exception as e:
            logger.error(f"Erro ao carregar catálogo do Google Fonts: {e}")
    # Mapear families case-insensitive para matching
    google_fonts_lower = {family.lower(): family for family in google_fonts.keys()}
    logger.info(f"Famílias do Google Fonts carregadas: {len(google_fonts)}")
    logger.info(f"Famílias do Google Fonts para matching (case-insensitive): {len(google_fonts_lower)}")

    # Registrar fontes originais ou semelhantes para cada fonte do PDF
    # Cache para variantes por família (download único)
    family_variants_cache = {}
    for ps_name, (xref, is_embedded) in font_info_map.items():
        logger.info(f"Processando fonte PS '{ps_name}', embutida={is_embedded}")
        fonte_registrada = False
        # 1) Tentar extrair e registrar fonte embutida (se existir)
        try:
            info = doc.extract_font(xref)
            if isinstance(info, dict):
                font_data = info.get('fontfile') or info.get('file')
                if font_data:
                    font_path = os.path.join(tmp_dir, f"{ps_name}.ttf")
                    with open(font_path, 'wb') as f:
                        f.write(font_data)
                    font_registry[ps_name] = ps_name
                    file_registry[ps_name] = font_path
                    fonte_registrada = True
                    logger.info(f"Fonte embutida '{ps_name}' mapeada para uso por página")
        except Exception as e:
            logger.debug(f"Não é fonte embutida ou falhou extração de '{ps_name}': {e}")
        # 2) Se não registrado, tentar match em fontes locais (exato + fuzzy)
        if not fonte_registrada:
            # 2a) PS suffix PSMT → mapear para Regular local
            if ps_name.lower().endswith('psmt'):
                base = re.sub(r'psmt$', '', ps_name, flags=re.IGNORECASE)
                base_words = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', base)
                key = f"{base_words.strip().lower()} regular"
                if key in local_fonts_map:
                    font_path = local_fonts_map[key]
                    file_registry[ps_name] = font_path
                    font_registry[ps_name] = ps_name
                    fonte_registrada = True
                    logger.info(f"Fonte local PSMT '{key}' mapeada para PS '{ps_name}' via '{font_path}'")
            if not fonte_registrada:
                normalized_ps = re.sub(r'[^A-Za-z]', '', ps_name).lower()
                local_keys = list(local_fonts_map.keys())
                # Match exato por substring
                matches = [name for name in local_keys if name in normalized_ps]
                if matches:
                    chosen = max(matches, key=len)
                    font_path = local_fonts_map[chosen]
                    file_registry[ps_name] = font_path
                    font_registry[ps_name] = ps_name
                    fonte_registrada = True
                    logger.info(f"Fonte local exata '{chosen}' mapeada para PS '{ps_name}' via '{font_path}'")
                else:
                    similar = difflib.get_close_matches(normalized_ps, local_keys, n=1, cutoff=0.8)
                    if similar:
                        chosen = similar[0]
                        font_path = local_fonts_map[chosen]
                        file_registry[ps_name] = font_path
                        font_registry[ps_name] = ps_name
                        fonte_registrada = True
                        logger.info(f"Fonte local fuzzy '{chosen}' mapeada para PS '{ps_name}' via '{font_path}'")
        # 3) Se não registrado, tentar match exato ou fuzzy no Google Fonts
        if not fonte_registrada and google_fonts_lower:
            # Extrair a parte após '+' no PS name (ex: 'OpenSans-Bold')
            name_part = ps_name.split('+')[-1]
            # Remover sufixos de estilo (Bold, Italic, Regular, Oblique)
            base_part = re.sub(r'[- ]?(Bold|Italic|Regular|Oblique).*$', '', name_part, flags=re.IGNORECASE)
            # Separar CamelCase e normalizar
            base_part = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', base_part)
            family_search = base_part.replace('-', ' ').strip().lower()
            logger.info(f"Buscando similar para '{family_search}' no Google Fonts (PS '{ps_name}')")
            # Tentar match exato (case-insensitive)
            if family_search in google_fonts_lower:
                family = google_fonts_lower[family_search]
                logger.info(f"Match exato encontrado: '{family}' para PS '{ps_name}'")
            else:
                # Fuzzy match
                lower_keys = list(google_fonts_lower.keys())
                similar_lower = difflib.get_close_matches(family_search, lower_keys, n=1, cutoff=0.5)
                if similar_lower:
                    family = google_fonts_lower[similar_lower[0]]
                    logger.info(f"Fuzzy match encontrado: '{family}' para PS '{ps_name}'")
                else:
                    logger.warning(f"Nenhum match encontrado para '{family_search}', usando fallback")
                    family = None
            # Se obtivemos family válido, baixa e registra fonte específica para este PS-name
            if family:
                files = google_fonts.get(family, {})
                # Se ainda não baixamos variantes dessa família, faz o download agora
                if family not in family_variants_cache:
                    fam_key = family.replace(' ', '')
                    variants = {
                        '': files.get('regular'),
                        '-Bold': files.get('700') or files.get('bold'),
                        '-Italic': files.get('italic'),
                    }
                    family_variants_cache[family] = {'key': fam_key, 'variants': {}}
                    for suffix, url_ttf in variants.items():
                        if not url_ttf:
                            continue
                        variant_name = f"{fam_key}{suffix}"
                        font_path = os.path.join(tmp_dir, f"{variant_name}.ttf")
                        try:
                            if not os.path.exists(font_path):
                                resp = requests.get(url_ttf, timeout=15)
                                resp.raise_for_status()
                                with open(font_path, 'wb') as f:
                                    f.write(resp.content)
                            family_variants_cache[family]['variants'][suffix] = font_path
                            # registrar fonte customizada para uso posterior
                            font_registry[variant_name] = variant_name
                            file_registry[variant_name] = font_path
                            logger.info(f"Baixada variante '{suffix or 'Regular'}' da família '{family}' como '{variant_name}'")
                        except Exception as e:
                            logger.error(f"Erro ao baixar variante '{suffix or 'Regular'}' de '{family}': {e}")
                # determinar sufixo baseado no PS name
                style_suffix = ''
                if 'Bold' in name_part:
                    style_suffix = '-Bold'
                elif 'Italic' in name_part or 'Oblique' in name_part:
                    style_suffix = '-Italic'
                fam_key = family_variants_cache[family]['key']
                variant_name = f"{fam_key}{style_suffix}"
                if variant_name in file_registry:
                    font_registry[ps_name] = variant_name
                    fonte_registrada = True
                    logger.info(f"Fonte PS '{ps_name}' mapeada para variante '{variant_name}'")
                else:
                    logger.warning(f"Variante '{variant_name}' não disponível, fallback posterior")
        # 4) fallback para Roboto Condensed ou Times
        if not fonte_registrada:
            if 'Bold' in ps_name:
                font_registry[ps_name] = font_registry['default_bold']
            elif 'Italic' in ps_name or 'Oblique' in ps_name:
                font_registry[ps_name] = font_registry['default_italic']
            else:
                font_registry[ps_name] = font_registry['default']
            logger.info(f"Fallback: fonte para PS '{ps_name}' definida como '{font_registry[ps_name]}'")

    # Percorrer páginas do documento original e gerar no novo
    for page_index, page in enumerate(doc, start=1):
        logger.info(f"Processando página {page_index}/{len(doc)}")
        # criar nova página com mesmas dimensões
        new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
        # Registrar fontes customizadas nesta página
        for name, path in file_registry.items():
            if path and os.path.exists(path):
                try:
                    new_page.insert_font(fontfile=path, fontname=name)
                except Exception:
                    pass
        # Extrair blocos da página (texto e imagem)
        page_dict = page.get_text('dict')
        inserted = 0
        # Inserir imagens diretamente a partir de blocos de imagem
        for block in page_dict.get('blocks', []):
            if block.get('type') == 1 and 'image' in block:
                bbox = block['bbox']
                img_val = block['image']
                img_data = None
                # o bloco pode fornecer bytes diretamente ou um dict com dados
                if isinstance(img_val, (bytes, bytearray)):
                    img_data = img_val
                elif isinstance(img_val, dict):
                    img_data = img_val.get('image') or img_val.get('image_bytes')
                if img_data:
                    try:
                        new_page.insert_image(fitz.Rect(*bbox), stream=img_data)
                        inserted += 1
                        logger.info(f"Página {page_index}: inseriu imagem block bbox={bbox}")
                    except Exception as e:
                        logger.error(f"Página {page_index}: falha ao inserir imagem stream block bbox={bbox}: {e}")
                else:
                    logger.error(f"Página {page_index}: bloco de imagem sem dados stream bbox={bbox}")
        # Fallback full-page se nenhuma imagem inserida
        if True:
            try:
                # Fallback full-page em alta resolução para melhor qualidade
                matrix = fitz.Matrix(2.0, 2.0)
                page_pix = page.get_pixmap(matrix=matrix, alpha=False)
                new_page.insert_image(
                    fitz.Rect(0, 0, page.rect.width, page.rect.height),
                    pixmap=page_pix
                )
                logger.info(f"Página {page_index}: fallback full-page como imagem")
                # cobrir texto original para evitar mistura
                for block in page_dict.get('blocks', []):
                    if block.get('type') == 0:
                        rect = fitz.Rect(block['bbox'])
                        new_page.draw_rect(rect, color=(1,1,1), fill=(1,1,1))
            except Exception as e:
                logger.error(f"Página {page_index}: falha no fallback full-page: {e}")
        # Extrair spans de texto
        text_dict = page.get_text('dict')
        spans = []
        for block in text_dict['blocks']:
            if block['type'] != 0:
                continue
            for line in block['lines']:
                for span in line['spans']:
                    txt = span['text']
                    if not txt.strip():
                        continue
                    spans.append({
                        'origin': span['origin'],
                        'bbox': span['bbox'],
                        'text': txt,
                        'size': span['size'],
                        'font': span['font'],
                        'flags': span.get('flags', 0),
                    })
        # Inserir spans de texto traduzido
        logger.info(f"Página {page_index}: inserindo {len(spans)} blocos de texto")
        # Agrupar spans em blocos
        def group_spans(spans):
            blocks = []
            for span in spans:
                sx0, sy0, sx1, sy1 = span['bbox']
                size = span['size']
                placed = False
                for block in blocks:
                    bx0, by0, bx1, by1 = block['bbox']
                    # span overlaps or is adjacent within 5px
                    if abs(size - block['size']) <= 0.5 and not (sx1 < bx0 - 5 or sx0 > bx1 + 5 or sy1 < by0 - 5 or sy0 > by1 + 5):
                        block['spans'].append(span)
                        block['bbox'] = (min(bx0, sx0), min(by0, sy0), max(bx1, sx1), max(by1, sy1))
                        placed = True
                        break
                if not placed:
                    block = {'spans': [span], 'size': size, 'bbox': (sx0, sy0, sx1, sy1)}
                    blocks.append(block)
            return blocks

        def get_font_for_style(base_raw, style):
            if style == 'normal':
                # Tentar usar mapeamento direto; se base_raw não encontrado, remover sufixo 'Regular'
                if base_raw in font_registry:
                    return font_registry[base_raw]
                # remover sufixos '-Regular' ou ' Regular' e tentar novamente
                cleaned_raw = re.sub(r'(?i)(?:[- ]?Regular)$', '', base_raw)
                if cleaned_raw in font_registry:
                    return font_registry[cleaned_raw]
                return font_registry.get('default')
            elif style == 'bold':
                candidate = base_raw.replace('Regular', '').rstrip('-') + '-Bold'
                return font_registry.get(candidate, font_registry.get('default_bold'))
            elif style == 'italic':
                candidate = base_raw.replace('Regular', '').rstrip('-') + '-Italic'
                return font_registry.get(candidate, font_registry.get('default_italic'))
            else:
                candidate = base_raw.replace('Regular', '').rstrip('-') + '-BoldItalic'
                if candidate in font_registry:
                    return font_registry[candidate]
                if font_registry.get('default_bold'):
                    return font_registry['default_bold']
                return font_registry.get('default_italic')

        blocks = group_spans(spans)
        for block in blocks:
            # Detectar alinhamento original do bloco
            bx0, by0, bx1, by1 = block['bbox']
            # Agrupar spans em linhas com base na coordenada Y
            line_clusters = []
            for span in block['spans']:
                y = span['origin'][1]
                placed = False
                for lc in line_clusters:
                    if abs(y - lc['y']) <= 1.0:
                        lc['spans'].append(span)
                        placed = True
                        break
                if not placed:
                    line_clusters.append({'y': y, 'spans': [span]})
            # Contar alinhamentos por linha
            counts = {'left': 0, 'right': 0, 'center': 0, 'justify': 0}
            threshold = 5.0
            for lc in line_clusters:
                x0_line = min(s['origin'][0] for s in lc['spans'])
                x1_line = max(s['origin'][0] + (s['bbox'][2] - s['bbox'][0]) for s in lc['spans'])
                offset_left = x0_line - bx0
                offset_right = bx1 - x1_line
                if offset_left <= threshold and offset_right > threshold:
                    counts['left'] += 1
                elif offset_left > threshold and offset_right <= threshold:
                    counts['right'] += 1
                elif offset_left <= threshold and offset_right <= threshold:
                    counts['justify'] += 1
                elif abs(offset_left - offset_right) <= threshold:
                    counts['center'] += 1
                else:
                    counts['left'] += 1
            block['alignment'] = max(counts, key=lambda k: counts[k])
            # Ordenar spans por posição na página: primeiro Y (topo), depois X (esquerda)
            sorted_spans = sorted(block['spans'], key=lambda s: (s['origin'][1], s['origin'][0]))
            marked_text = ''
            for span in sorted_spans:
                text = span['text'].strip()
                raw_font = span['font']
                # marcar XML para estilos: <b><i>, <b>, <i>
                if 'Bold' in raw_font and ('Italic' in raw_font or 'Oblique' in raw_font):
                    piece = f'<b><i>{html.escape(text)}</i></b>'
                elif 'Bold' in raw_font:
                    piece = f'<b>{html.escape(text)}</b>'
                elif 'Italic' in raw_font or 'Oblique' in raw_font:
                    piece = f'<i>{html.escape(text)}</i>'
                else:
                    piece = html.escape(text)
                # garantir espaço entre spans se não houver espaço
                if marked_text and not marked_text.endswith(' ') and not piece.startswith(' '):
                    marked_text += ' '
                marked_text += piece
            # Traduzir texto preservando tags XML, mas sem ignorar conteúdo de <b> e <i>
            result = translator.translate_text(
                marked_text,
                source_lang='EN',
                target_lang=args.target_lang,
                tag_handling='xml',
                preserve_formatting=True
            )
            translated_xml = result.text
            # Extrair segmentos preservando tags XML <b> e <i>
            pattern = r'(<b><i>.*?</i></b>|<b>.*?</b>|<i>.*?</i>)'
            segments = []
            last_end = 0
            for m in re.finditer(pattern, translated_xml):
                # texto antes da tag
                pre = translated_xml[last_end:m.start()]
                if pre:
                    segments.append({'text': html.unescape(pre), 'style': 'normal'})
                grp = m.group(0)
                if grp.startswith('<b><i>'):
                    content = grp[7:-7]; style = 'bolditalic'
                elif grp.startswith('<b>'):
                    content = grp[3:-4]; style = 'bold'
                else:
                    content = grp[3:-4]; style = 'italic'
                segments.append({'text': content, 'style': style})
                last_end = m.end()
            # texto após última tag
            if last_end < len(translated_xml):
                tail = translated_xml[last_end:]
                if tail:
                    segments.append({'text': html.unescape(tail), 'style': 'normal'})
            bx0, by0, bx1, by1 = block['bbox']
            block_width = bx1 - bx0
            block_height = by1 - by0
            # Ajuste de tamanho de fonte por prioridade: manter original, reduzir até 20% ou quebrar linhas
            # cache de objetos Font para medição de texto customizado
            font_cache = {}
            def measure(txt, fontname, fs):
                if fontname not in font_cache:
                    path = file_registry.get(fontname)
                    try:
                        if path and os.path.exists(path):
                            font_cache[fontname] = fitz.Font(fontfile=path)
                        else:
                            font_cache[fontname] = fitz.Font(fontname)
                    except Exception:
                        font_cache[fontname] = fitz.Font()
                return font_cache[fontname].text_length(txt, fs)

            original_size = block['size']
            fontsize = original_size
            line_spacing = 1.2
            # 1) testar sem quebra: medir largura total
            full_width = sum(measure(seg['text'], get_font_for_style(sorted_spans[0]['font'], seg['style']), fontsize)
                              for seg in segments)
            if full_width <= block_width:
                # sem quebra; usar segmentos originais com fontname
                base_font = sorted_spans[0]['font']
                lines = [[
                    {'text': seg['text'], 'style': seg['style'], 'fontname': get_font_for_style(base_font, seg['style'])}
                    for seg in segments
                ]]
            else:
                # 2) tentar reduzir fonte até 20%
                min_size = original_size * 0.9
                size_shrink = fontsize
                while size_shrink > min_size:
                    size_shrink *= 0.95
                    full_width = sum(measure(seg['text'], get_font_for_style(sorted_spans[0]['font'], seg['style']), size_shrink)
                                      for seg in segments)
                    if full_width <= block_width:
                        break
                if full_width <= block_width:
                    fontsize = size_shrink
                    # sem quebra após shrink; manter spans originais com novo tamanho
                    base_font = sorted_spans[0]['font']
                    lines = [[
                        {'text': seg['text'], 'style': seg['style'], 'fontname': get_font_for_style(base_font, seg['style'])}
                        for seg in segments
                    ]]
                else:
                    # 3) fallback: voltar ao tamanho original e quebrar linhas
                    fontsize = original_size
                    def wrap_segments(fs):
                        lines_tmp = []
                        current_line = []
                        current_width = 0
                        for seg in segments:
                            words = seg['text'].split(' ')
                            for i, word in enumerate(words):
                                txt = word + (' ' if i < len(words)-1 else '')
                                style = seg['style']
                                fontname = get_font_for_style(sorted_spans[0]['font'], style)
                                w = measure(txt, fontname, fs)
                                if current_width + w <= block_width or not current_line:
                                    current_line.append({'text': txt, 'style': style, 'fontname': fontname})
                                    current_width += w
                                else:
                                    lines_tmp.append(current_line)
                                    current_line = [{'text': txt, 'style': style, 'fontname': fontname}]
                                    current_width = w
                        if current_line:
                            lines_tmp.append(current_line)
                        return lines_tmp
                    lines = wrap_segments(fontsize)
            # centralizar verticalmente
            total_height = len(lines) * fontsize * line_spacing
            y = by0 + max((block_height - total_height) / 2, 0)
            for line in lines:
                line_width = sum(measure(seg['text'], seg['fontname'], fontsize) for seg in line)
                # Ajustar posição X de acordo com alinhamento original
                align = block.get('alignment', 'left')
                if align == 'left':
                    x = bx0
                elif align == 'right':
                    x = bx0 + block_width - line_width
                elif align == 'center':
                    x = bx0 + (block_width - line_width) / 2
                elif align == 'justify' and line != lines[-1]:
                    # Distribuir espaço extra entre espaços
                    num_spaces = sum(1 for seg in line if seg['text'].endswith(' '))
                    extra_total = block_width - line_width
                    extra_per = extra_total / num_spaces if num_spaces > 0 else 0
                    x = bx0
                    for seg in line:
                        try:
                            new_page.insert_text((x, y), seg['text'], fontsize=fontsize, fontname=seg['fontname'])
                        except Exception:
                            new_page.insert_text((x, y), seg['text'], fontsize=fontsize, fontname=font_registry.get('default'))
                        w = measure(seg['text'], seg['fontname'], fontsize)
                        x += w + (extra_per if seg['text'].endswith(' ') else 0)
                    y += fontsize * line_spacing
                    continue
                else:
                    x = bx0 + (block_width - line_width) / 2
                for seg in line:
                    try:
                        new_page.insert_text((x, y), seg['text'], fontsize=fontsize, fontname=seg['fontname'])
                    except Exception:
                        new_page.insert_text((x, y), seg['text'], fontsize=fontsize, fontname=font_registry.get('default'))
                    x += measure(seg['text'], seg['fontname'], fontsize)
                y += fontsize * line_spacing
        logger.info(f"Página {page_index} processada com sucesso: {len(blocks)} blocos de texto traduzido")
    # salva o PDF traduzido apenas com conteúdo reescrito
    new_doc.save(args.output)
    new_doc.close()
    doc.close()
    # Limpa diretório temporário de fontes
    shutil.rmtree(tmp_dir)

def download_and_prepare_roboto_condensed_fonts(tmp_dir, logger=None):
    logger = logger or logging.getLogger('translate_pdf')
    # URLs estáticas para Roboto Condensed no GitHub
    static_urls = {
        'RobotoCondensed': 'https://github.com/google/fonts/raw/main/apache/robotocondensed/RobotoCondensed-Regular.ttf',
        'RobotoCondensed-Bold': 'https://github.com/google/fonts/raw/main/apache/robotocondensed/RobotoCondensed-Bold.ttf',
        'RobotoCondensed-Italic': 'https://github.com/google/fonts/raw/main/apache/robotocondensed/RobotoCondensed-Italic.ttf',
    }
    # Preparar lista de URLs a baixar (inicialmente estáticas)
    urls_to_download = static_urls.copy()
    API_KEY = os.getenv("GOOGLE_FONTS_API_KEY")
    if API_KEY:
        try:
            # Tentar obter via API para usar possíveis variantes mais recentes
            api_url = "https://www.googleapis.com/webfonts/v1/webfonts"
            params = {"key": API_KEY, "subset": "latin"}
            resp = requests.get(api_url, params=params, timeout=15)
            resp.raise_for_status()
            fonts = resp.json().get("items", [])
            rc = next((f for f in fonts if f["family"] == "Roboto Condensed"), None)
            if rc and "files" in rc:
                files = rc["files"]
                urls_to_download = {
                    'RobotoCondensed': files.get('regular'),
                    'RobotoCondensed-Bold': files.get('700') or files.get('bold'),
                    'RobotoCondensed-Italic': files.get('italic'),
                }
                logger.info("Usando API do Google Fonts para Roboto Condensed")
            else:
                logger.warning("Roboto Condensed não encontrado via API, usando URLs estáticas")
        except Exception as e:
            logger.error(f"Erro ao obter Roboto Condensed via API: {e}, usando URLs estáticas")
    # Download e preparação dos arquivos de fonte
    font_paths = {}
    for style, url_ttf in urls_to_download.items():
        if not url_ttf:
            font_paths[style] = None
            continue
        local_path = os.path.join(tmp_dir, f"{style}.ttf")
        try:
            if not os.path.exists(local_path):
                r = requests.get(url_ttf, timeout=15)
                r.raise_for_status()
                with open(local_path, 'wb') as f:
                    f.write(r.content)
            font_paths[style] = local_path
            logger.info(f"Roboto Condensed estilo '{style}' disponível em '{local_path}'")
        except Exception as e:
            logger.error(f"Falha ao baixar Roboto Condensed {style}: {e}")
            font_paths[style] = None
    return font_paths

if __name__ == '__main__':
    main() 