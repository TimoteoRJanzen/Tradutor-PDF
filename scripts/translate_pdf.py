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
import pikepdf
from typing import Optional
import struct
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
                reg_name = os.path.splitext(fname)[0]  # Usa o nome do arquivo sem extensão, sensível a maiúsculas/minúsculas
                path = os.path.join(local_fonts_dir, fname)
                local_fonts_map[reg_name] = path
                logger.info(f"Fonte local disponível: '{reg_name}' em '{path}'")
    else:
        local_fonts_map = {}

    # Gera PDF intermediário sem texto
    pdf_sem_texto = os.path.join(tmp_dir, "no_text.pdf")
    strip_text_from_pdf(args.input, pdf_sem_texto)
    doc = fitz.open(args.input)
    clean_doc = fitz.open(pdf_sem_texto)
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
    # Loga todas as fontes encontradas no PDF original
    logger.info("=== FONTES ENCONTRADAS NO PDF ORIGINAL ===")
    for ps_name, (xref, is_embedded) in font_info_map.items():
        logger.info(f"Fonte: '{ps_name}' | xref: {xref} | embutida: {is_embedded}")
    logger.info("=== FIM DA LISTA DE FONTES ORIGINAIS ===")

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
        # 1) Tentar extrair e registrar fonte embutida (prioridade máxima)
        try:
            info = doc.extract_font(xref)
            if isinstance(info, dict):
                font_data = info.get('fontfile') or info.get('file')
                ext = info.get('ext', 'ttf')  # PyMuPDF pode retornar 'ext' (ttf, otf, etc)
                if font_data:
                    font_path = os.path.join(tmp_dir, f"{ps_name}.{ext}")
                    with open(font_path, 'wb') as f:
                        f.write(font_data)
                    font_registry[ps_name] = ps_name  # Usa o mesmo nome do PDF
                    file_registry[ps_name] = font_path
                    fonte_registrada = True
                    logger.info(f"[EXTRAÇÃO] Fonte embutida extraída: '{ps_name}' | xref: {xref} | arquivo: {font_path}")
                else:
                    logger.warning(f"[EXTRAÇÃO] Fonte embutida '{ps_name}' encontrada mas sem dados de arquivo extraível.")
            else:
                logger.warning(f"[EXTRAÇÃO] Fonte '{ps_name}' não retornou dict ao tentar extrair.")
        except Exception as e:
            logger.warning(f"[EXTRAÇÃO] Falha ao extrair fonte embutida '{ps_name}': {e}. Será tentado fallback.")
        # 2) Se não registrado, tentar match em fontes locais (exato + fuzzy)
        if not fonte_registrada:
            # 2a) PS suffix PSMT → mapear para Regular local
            if ps_name.lower().endswith('psmt'):
                base = re.sub(r'psmt$', '', ps_name, flags=re.IGNORECASE)
                base_words = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', base)
                key = f"{base_words.strip()}Regular".replace(' ', '')  # Ex: TimesNewRomanRegular
                if key in local_fonts_map:
                    font_path = local_fonts_map[key]
                    file_registry[ps_name] = font_path
                    font_registry[ps_name] = ps_name
                    fonte_registrada = True
                    logger.info(f"Fonte local PSMT '{key}' mapeada para PS '{ps_name}' via '{font_path}'")
            if not fonte_registrada:
                normalized_ps = re.sub(r'[^A-Za-z]', '', ps_name)
                local_keys = list(local_fonts_map.keys())
                matches = [name for name in local_keys if name.lower() in normalized_ps.lower()]
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
            # Normalizar nome: remover prefixo antes do +, remover sufixos de estilo
            name_part = ps_name.split('+')[-1] if '+' in ps_name else ps_name
            # Remover sufixos de estilo
            base_part = re.sub(r'[- ]?(Bold|Italic|Regular|Oblique).*$','', name_part, flags=re.IGNORECASE)
            # Separar CamelCase e normalizar
            base_part = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', base_part)
            family_search = base_part.replace('-', ' ').strip().lower()
            logger.info(f"[font-reg] Buscando '{ps_name}' no Google Fonts (chave de busca normalizada: '{family_search}')...")
            if family_search in google_fonts_lower:
                family = google_fonts_lower[family_search]
                logger.info(f"[font-reg] Match exato no Google Fonts: '{family}' para '{ps_name}' (normalizado: '{family_search}')")
            else:
                lower_keys = list(google_fonts_lower.keys())
                similar_lower = difflib.get_close_matches(family_search, lower_keys, n=1, cutoff=0.5)
                if similar_lower:
                    family = google_fonts_lower[similar_lower[0]]
                    logger.info(f"[font-reg] Fuzzy match no Google Fonts: '{family}' para '{ps_name}' (normalizado: '{family_search}')")
                else:
                    family = None
                    logger.info(f"[font-reg] Nenhum match no Google Fonts para '{ps_name}' (chave normalizada: '{family_search}')")
            # Se obtivemos family válido, baixa e registra fonte específica para este PS-name
            if family:
                files = google_fonts.get(family, {})
                # Se ainda não baixamos variantes dessa família, faz o download agora
                if family not in family_variants_cache:
                    fam_key = family.replace(' ', '')
                    variants = {
                        'regular': files.get('regular'),
                        'bold': files.get('700') or files.get('bold'),
                        'italic': files.get('italic'),
                        'bolditalic': files.get('700italic') or files.get('bolditalic'),
                    }
                    family_variants_cache[family] = {'key': fam_key, 'variants': {}}
                    for variant, url_ttf in variants.items():
                        if not url_ttf:
                            continue
                        # Nome único e consistente para cada variante
                        variant_name = padronizar_nome_fonte(fam_key, variant)
                        font_path = os.path.join(tmp_dir, f"{variant_name}.ttf")
                        if not os.path.exists(font_path):
                            try:
                                logger.info(f"[font-reg] Baixando variante '{variant}' de '{family}' do Google Fonts: {url_ttf}")
                                resp = requests.get(url_ttf, timeout=15)
                                resp.raise_for_status()
                                with open(font_path, 'wb') as f:
                                    f.write(resp.content)
                                logger.info(f"[font-reg] Variante '{variant_name}' baixada como '{font_path}'")
                            except Exception as e:
                                logger.error(f"[font-reg] Erro ao baixar variante '{variant_name}' de '{family}': {e}")
                        file_registry[variant_name] = font_path
                        font_registry[variant_name] = variant_name
                    # Mapear o ps_name para a variante correta
                    style_variant = 'regular'
                    if 'Bold' in name_part and ('Italic' in name_part or 'Oblique' in name_part):
                        style_variant = 'bolditalic'
                    elif 'Bold' in name_part:
                        style_variant = 'bold'
                    elif 'Italic' in name_part or 'Oblique' in name_part:
                        style_variant = 'italic'
                    variant_name = padronizar_nome_fonte(fam_key, style_variant)
                    if variant_name in file_registry:
                        registrar_varios_nomes_font_registry(font_registry, ps_name, variant_name)
                        fonte_registrada = True
                        logger.info(f"[font-reg] Fonte PS '{ps_name}' mapeada para variante '{variant_name}'")
                    else:
                        logger.warning(f"[font-reg] Variante '{variant_name}' não disponível, fallback posterior")
        # 4) fallback para Roboto Condensed ou Times
        if not fonte_registrada:
            if 'Bold' in ps_name:
                font_registry[ps_name] = font_registry['default_bold']
            elif 'Italic' in ps_name or 'Oblique' in ps_name:
                font_registry[ps_name] = font_registry['default_italic']
            else:
                font_registry[ps_name] = font_registry['default']
            logger.info(f"Fallback: fonte para PS '{ps_name}' definida como '{font_registry[ps_name]}'")

    # Determinar quais fontes realmente serão usadas neste PDF
    fontes_usadas = set(file_registry.keys())  # Apenas as fontes mapeadas para algum ps_name

    # Percorrer páginas do documento original e gerar no novo
    for page_index, page in enumerate(doc, start=1):
        logger.info(f"Processando página {page_index}/{len(doc)}")
        # criar nova página com mesmas dimensões
        new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)
        # Importa fundo vetorial limpo da página intermediária
        new_page.show_pdf_page(new_page.rect, clean_doc, page_index-1)
        # Registrar apenas as fontes necessárias nesta página
        # Adicionar fontes detectadas pelo pdfminer (se houver)
        text_dict = page.get_text('dict')
        spans = []
        fontes_pdfminer = set()
        for block in page.get_text('dict')['blocks']:
            if block['type'] != 0:
                continue
            for line in block['lines']:
                for span in line['spans']:
                    txt = span['text']
                    if not txt.strip():
                        continue
                    logger.info(f"Fonte detectada pelo PyMuPDF: '{span['font']}' para texto '{txt[:30]}...' na página {page.number+1}.")
                    # Se a fonte for Unnamed-*, tenta identificar usando pdfminer
                    if span['font'].startswith('Unnamed-'):
                        logger.info(f"Fonte 'Unnamed-*' detectada na página {page.number+1}, bbox={span['bbox']}, texto='{txt[:30]}...'. Tentando identificar com pdfminer...")
                        spans_pdfminer = reconstruir_spans_pdfminer(
                            args.input,
                            page.number,
                            span['bbox'],
                            txt
                        )
                        if spans_pdfminer:
                            logger.info(f"Spans reconstruídos por pdfminer: {len(spans_pdfminer)} para texto '{txt[:30]}...' na página {page.number+1}.")
                            y_original = span['origin'][1]
                            for s in spans_pdfminer:
                                logger.info(f"Span pdfminer: fonte='{s['font']}', tamanho={s['size']}, texto='{s['text'][:30]}...'")
                                spans.append({
                                    'origin': (s['bbox'][0], y_original),
                                    'bbox': s['bbox'],
                                    'text': s['text'],
                                    'size': s['size'],
                                    'font': s['font'],
                                    'flags': s.get('flags', 0),
                                })
                                fontes_pdfminer.add(s['font'])
                            continue  # já adicionou os novos spans, não adiciona o Unnamed-*
                        else:
                            logger.warning(f"Não foi possível identificar a fonte real para texto '{txt[:30]}...' na página {page.number+1} (bbox={span['bbox']}). Mantendo 'Unnamed-*'.")
                    else:
                        spans.append({
                            'origin': span['origin'],
                            'bbox': span['bbox'],
                            'text': txt,
                            'size': span['size'],
                            'font': span['font'],
                            'flags': span.get('flags', 0),
                        })
        # Padronizar o nome da fonte de cada span para o nome registrado
        for span in spans:
            if span['font'] in font_registry:
                span['font'] = font_registry[span['font']]
        # Processar cada fonte do pdfminer pelo mesmo fluxo de registro
        for ps_name in fontes_pdfminer:
            fonte_registrada = False
            logger.info(f"[font-reg] Processando fonte '{ps_name}' detectada pelo pdfminer...")
            if ps_name in local_fonts_map:
                file_registry[ps_name] = local_fonts_map[ps_name]
                registrar_varios_nomes_font_registry(font_registry, ps_name, ps_name)
                fonte_registrada = True
                logger.info(f"[font-reg] Fonte local encontrada: '{ps_name}' → '{local_fonts_map[ps_name]}'")
            else:
                logger.info(f"[font-reg] Fonte '{ps_name}' NÃO encontrada nas fontes locais.")
            if not fonte_registrada and google_fonts_lower:
                # Normalizar nome: remover prefixo antes do +, remover sufixos de estilo
                name_part = ps_name.split('+')[-1] if '+' in ps_name else ps_name
                # Remover sufixos de estilo
                base_part = re.sub(r'[- ]?(Bold|Italic|Regular|Oblique).*$','', name_part, flags=re.IGNORECASE)
                # Separar CamelCase e normalizar
                base_part = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', base_part)
                family_search = base_part.replace('-', ' ').strip().lower()
                logger.info(f"[font-reg] Buscando '{ps_name}' no Google Fonts (chave de busca normalizada: '{family_search}')...")
                if family_search in google_fonts_lower:
                    family = google_fonts_lower[family_search]
                    logger.info(f"[font-reg] Match exato no Google Fonts: '{family}' para '{ps_name}' (normalizado: '{family_search}')")
                else:
                    lower_keys = list(google_fonts_lower.keys())
                    similar_lower = difflib.get_close_matches(family_search, lower_keys, n=1, cutoff=0.5)
                    if similar_lower:
                        family = google_fonts_lower[similar_lower[0]]
                        logger.info(f"[font-reg] Fuzzy match no Google Fonts: '{family}' para '{ps_name}' (normalizado: '{family_search}')")
                    else:
                        family = None
                        logger.info(f"[font-reg] Nenhum match no Google Fonts para '{ps_name}' (chave normalizada: '{family_search}')")
                if family:
                    files = google_fonts.get(family, {})
                    fam_key = family.replace(' ', '')
                    # Baixar e registrar variantes
                    variants = {
                        'regular': files.get('regular'),
                        'bold': files.get('700') or files.get('bold'),
                        'italic': files.get('italic'),
                        'bolditalic': files.get('700italic') or files.get('bolditalic'),
                    }
                    for variant, url_ttf in variants.items():
                        if not url_ttf:
                            continue
                        # Nome único e consistente para cada variante
                        variant_name = padronizar_nome_fonte(fam_key, variant)
                        font_path = os.path.join(tmp_dir, f"{variant_name}.ttf")
                        if not os.path.exists(font_path):
                            try:
                                logger.info(f"[font-reg] Baixando variante '{variant}' de '{family}' do Google Fonts: {url_ttf}")
                                resp = requests.get(url_ttf, timeout=15)
                                resp.raise_for_status()
                                with open(font_path, 'wb') as f:
                                    f.write(resp.content)
                                logger.info(f"[font-reg] Variante '{variant_name}' baixada como '{font_path}'")
                            except Exception as e:
                                logger.error(f"[font-reg] Erro ao baixar variante '{variant_name}' de '{family}': {e}")
                        file_registry[variant_name] = font_path
                        font_registry[variant_name] = variant_name
                    # Mapear o ps_name para a variante correta
                    style_variant = 'regular'
                    if 'Bold' in name_part and ('Italic' in name_part or 'Oblique' in name_part):
                        style_variant = 'bolditalic'
                    elif 'Bold' in name_part:
                        style_variant = 'bold'
                    elif 'Italic' in name_part or 'Oblique' in name_part:
                        style_variant = 'italic'
                    variant_name = padronizar_nome_fonte(fam_key, style_variant)
                    if variant_name in file_registry:
                        registrar_varios_nomes_font_registry(font_registry, ps_name, variant_name)
                        fonte_registrada = True
                        logger.info(f"[font-reg] Fonte PS '{ps_name}' mapeada para variante '{variant_name}'")
                    else:
                        logger.warning(f"[font-reg] Variante '{variant_name}' não disponível, fallback posterior")
            if not fonte_registrada:
                # Fallback apenas para a variante específica
                style_suffix = ''
                if 'Bold' in ps_name and ('Italic' in ps_name or 'Oblique' in ps_name):
                    style_suffix = '-BoldItalic'
                elif 'Bold' in ps_name:
                    style_suffix = '-Bold'
                elif 'Italic' in ps_name or 'Oblique' in ps_name:
                    style_suffix = '-Italic'
                fallback_name = font_registry.get('RobotoCondensed' + style_suffix) or font_registry.get('default')
                font_registry[ps_name] = fallback_name
                logger.info(f"[font-reg] Fallback: fonte para '{ps_name}' definida como '{font_registry[ps_name]}'")
        # Atualizar fontes usadas
        fontes_usadas.update(fontes_pdfminer)
        # Registrar todas as fontes presentes em file_registry (com arquivo válido)
        for name, path in file_registry.items():
            logger.info(f"[font-reg][DEBUG] Tentando registrar fonte '{name}' com arquivo '{path}' (existe: {os.path.exists(path) if path else False})")
            if path and os.path.exists(path):
                valido, header = is_valid_font_file(path)
                logger.info(f"[font-reg][DEBUG] Header do arquivo de fonte '{name}': {header}")
                if not valido:
                    logger.error(f"[font-reg][ERRO] Arquivo '{path}' não é um TTF/OTF válido! Não será registrado.")
                    continue
                try:
                    new_page.insert_font(fontfile=path, fontname=name)
                    logger.info(f"[font-reg] Fonte '{name}' registrada na página usando '{path}'")
                except Exception as e:
                    logger.error(f"Erro ao registrar fonte '{name}' na página: {e}")
        logger.info(f"[font-reg][DEBUG] font_registry: {font_registry}")
        logger.info(f"[font-reg][DEBUG] file_registry: {file_registry}")
        # Inserir spans de texto traduzido
        logger.info(f"Página {page_index}: inserindo {len(spans)} blocos de texto")
        # Agrupar spans em blocos
        def group_spans(spans, y_threshold=10, x_threshold=10):
            """
            Agrupa spans em blocos considerando uma tolerância maior para distância vertical e horizontal,
            evitando separar frases do mesmo bloco mesmo que estejam um pouco distantes.
            """
            blocks = []
            for span in spans:
                sx0, sy0, sx1, sy1 = span['bbox']
                size = span['size']
                placed = False
                for block in blocks:
                    bx0, by0, bx1, by1 = block['bbox']
                    # Permite maior tolerância na distância vertical e horizontal
                    if abs(size - block['size']) <= 0.5 and not (sx1 < bx0 - x_threshold or sx0 > bx1 + x_threshold or sy1 < by0 - y_threshold or sy0 > by1 + y_threshold):
                        block['spans'].append(span)
                        block['bbox'] = (min(bx0, sx0), min(by0, sy0), max(bx1, sx1), max(by1, sy1))
                        placed = True
                        break
                if not placed:
                    block = {'spans': [span], 'size': size, 'bbox': (sx0, sy0, sx1, sy1)}
                    blocks.append(block)
            return blocks

        def get_font_for_style(base_raw, style):
            # base_raw pode ser um ps_name (ex: 'AAAAAA+OpenSans-Regular')
            # Mapeia para o nome único registrado
            base = font_registry.get(base_raw, base_raw)
            logger = logging.getLogger('translate_pdf')
            # Tenta variantes, se não encontrar, busca por família + estilo
            if style == 'normal':
                if base in font_registry:
                    logger.info(f"[font-style] Usando fonte normal: {base}")
                    return font_registry[base]
                cleaned_raw = re.sub(r'(?i)(?:[- ]?Regular)$', '', base)
                if cleaned_raw in font_registry:
                    logger.info(f"[font-style] Usando fonte normal (cleaned): {cleaned_raw}")
                    return font_registry[cleaned_raw]
                # fallback: tenta regular da família
                fam_reg = re.sub(r'(Bold|Italic|BoldItalic)$', 'Regular', base)
                if fam_reg in font_registry:
                    logger.info(f"[font-style] Usando fonte normal (fam_reg): {fam_reg}")
                    return font_registry[fam_reg]
                # Busca variante local
                variante = buscar_variante_local(font_registry, file_registry, base, 'normal')
                if variante:
                    logger.info(f"[font-style] Usando fonte local normal: {variante}")
                    return variante
                logger.info(f"[font-style] Usando fallback normal")
                return font_registry.get('default')
            elif style == 'bold':
                if 'Bold' in base:
                    candidate = base
                else:
                    candidate = base.replace('Regular', '') + 'Bold'
                if candidate in font_registry:
                    logger.info(f"[font-style] Usando fonte bold: {candidate}")
                    return font_registry[candidate]
                # Busca variante local
                variante = buscar_variante_local(font_registry, file_registry, base, 'bold')
                if variante:
                    logger.info(f"[font-style] Usando fonte local bold: {variante}")
                    return variante
                # fallback: tenta regular da família
                fam_reg = re.sub(r'(Bold|Italic|BoldItalic)$', 'Regular', base)
                if fam_reg in font_registry:
                    logger.info(f"[font-style] Usando fonte bold (fam_reg): {fam_reg}")
                    return font_registry[fam_reg]
                logger.info(f"[font-style] Usando fallback bold")
                return font_registry.get('default_bold')
            elif style == 'italic':
                if 'Italic' in base or 'Oblique' in base:
                    candidate = base
                else:
                    candidate = base.replace('Regular', '') + 'Italic'
                if candidate in font_registry:
                    logger.info(f"[font-style] Usando fonte italic: {candidate}")
                    return font_registry[candidate]
                # Busca variante local
                variante = buscar_variante_local(font_registry, file_registry, base, 'italic')
                if variante:
                    logger.info(f"[font-style] Usando fonte local italic: {variante}")
                    return variante
                # fallback: tenta regular da família
                fam_reg = re.sub(r'(Bold|Italic|BoldItalic)$', 'Regular', base)
                if fam_reg in font_registry:
                    logger.info(f"[font-style] Usando fonte italic (fam_reg): {fam_reg}")
                    return font_registry[fam_reg]
                logger.info(f"[font-style] Usando fallback italic")
                return font_registry.get('default_italic')
            else:
                if ('Bold' in base and ('Italic' in base or 'Oblique' in base)):
                    candidate = base
                else:
                    candidate = base.replace('Regular', '') + 'BoldItalic'
                if candidate in font_registry:
                    logger.info(f"[font-style] Usando fonte bolditalic: {candidate}")
                    return font_registry[candidate]
                # Busca variante local
                variante = buscar_variante_local(font_registry, file_registry, base, 'bolditalic')
                if variante:
                    logger.info(f"[font-style] Usando fonte local bolditalic: {variante}")
                    return variante
                # fallback: tenta regular da família
                fam_reg = re.sub(r'(Bold|Italic|BoldItalic)$', 'Regular', base)
                if fam_reg in font_registry:
                    logger.info(f"[font-style] Usando fonte bolditalic (fam_reg): {fam_reg}")
                    return font_registry[fam_reg]
                if font_registry.get('default_bold'):
                    logger.info(f"[font-style] Usando fallback bolditalic (default_bold)")
                    return font_registry['default_bold']
                logger.info(f"[font-style] Usando fallback bolditalic (default_italic)")
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
            counts = {'left': 0, 'right': 0, 'center': 0}
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
            # Calcular número de linhas originais
            original_lines = len(line_clusters)
            def ajustar_titulo_para_linhas(lines, fontsize, block_width, original_lines, min_fontsize=10):
                """Reduz o tamanho da fonte até que o número de linhas não ultrapasse o original."""
                fs = fontsize
                while len(lines) > original_lines and fs > min_fontsize:
                    fs *= 0.95
                    lines = wrap_segments(fs)
                return lines, fs
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
                    # Se for título (tamanho > 14), tentar ajustar para não quebrar mais linhas que o original
                    if original_size > 14:
                        lines, fontsize = ajustar_titulo_para_linhas(lines, fontsize, block_width, original_lines)
            # centralizar verticalmente
            total_height = len(lines) * fontsize * line_spacing
            #y = by0 #+ max((block_height - total_height) / 2, 0)
            y = sorted_spans[0]['origin'][1]
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
                else:
                    x = bx0 + (block_width - line_width) / 2  # fallback para centralizado
                for seg in line:
                    logger.info(f"[font-reg][DEBUG] Inserindo texto '{seg['text'][:30]}...' com fonte '{seg['fontname']}' (arquivo: {file_registry.get(seg['fontname'])}) | estilo: {seg.get('style')}")
                    font_path = file_registry.get(seg['fontname'])
                    if font_path and os.path.exists(font_path):
                        valido, header = is_valid_font_file(font_path)
                        if not valido:
                            logger.error(f"[font-reg][ERRO] Arquivo '{font_path}' não é um TTF/OTF válido! Não será usado para inserir texto.")
                            continue
                    try:
                        new_page.insert_text((x, y), seg['text'], fontsize=fontsize, fontname=seg['fontname'])
                    except Exception as e:
                        logger.error(f"Erro ao inserir texto com fonte '{seg['fontname']}': {e}. Usando fallback.")
                        new_page.insert_text((x, y), seg['text'], fontsize=fontsize, fontname=font_registry.get('default'))
                    x += measure(seg['text'], seg['fontname'], fontsize)
                y += fontsize * line_spacing
        logger.info(f"Página {page_index} processada com sucesso: {len(blocks)} blocos de texto traduzido")
    # salva o PDF traduzido apenas com conteúdo reescrito
    new_doc.save(args.output)
    new_doc.close()
    doc.close()
    clean_doc.close()
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

def strip_text_from_pdf(input_path: str, output_path: str):
    """Remove operadores de texto (BT...ET) de todas as páginas e Form XObjects (recursivo), mantendo gráficos e imagens."""
    pdf = pikepdf.open(input_path)

    def remove_text_from_stream(obj, pdf, processed=None):
        if processed is None:
            processed = set()
        # Evita loops infinitos em XObjects recursivos
        obj_id = id(obj)
        if obj_id in processed:
            return obj.get("/Contents", None)
        processed.add(obj_id)
        cs = pikepdf.parse_content_stream(obj)
        remove_ranges = []
        stack = []
        for idx, (operands, op) in enumerate(cs):
            if op == pikepdf.Operator("BT"):
                stack.append(idx)
            elif op == pikepdf.Operator("ET") and stack:
                start = stack.pop()
                remove_ranges.append((start, idx + 1))
        for start, end in reversed(remove_ranges):
            del cs[start:end]
        # Processa recursivamente XObjects do tipo Form
        resources = obj.get("/Resources", {})
        xobjects = resources.get("/XObject", {})
        for name, xobj in xobjects.items():
            try:
                subtype = xobj.get("/Subtype", None)
                if subtype and str(subtype) == "/Form":
                    xobj["/Contents"] = remove_text_from_stream(xobj, pdf, processed)
            except Exception:
                continue
        return pdf.make_stream(pikepdf.unparse_content_stream(cs))

    for page in pdf.pages:
        # Remove texto da página e de todos os XObjects recursivamente
        page.Contents = remove_text_from_stream(page, pdf)
    pdf.save(output_path)

# Função para reconstruir spans detalhados usando pdfminer
def reconstruir_spans_pdfminer(pdf_path: str, page_number: int, bbox: tuple, texto: str):
    """
    Retorna uma lista de spans (dicts) para o trecho de texto, agrupando por fonte/estilo, como o PyMuPDF faz.
    Cada span: {'text', 'bbox', 'font', 'size', 'flags'}
    """
    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTTextContainer, LTChar
    except ImportError:
        return []
    import fitz
    doc = fitz.open(pdf_path)
    page_height = doc[page_number].rect.height
    doc.close()
    spans = []
    chars = []
    bx0, by0, bx1, by1 = bbox
    texto_alvo = texto.replace('\n', '').replace('\r', '').strip()
    import logging
    logger = logging.getLogger('translate_pdf')
    logger.info(f"[pdfminer] Iniciando busca de spans para texto '{texto[:30]}...' na página {page_number+1}, bbox={bbox}")
    def bboxes_overlap(b1, b2, tol=1.0):
        x0_1, y0_1, x1_1, y1_1 = b1
        x0_2, y0_2, x1_2, y1_2 = b2
        return not (x1_1 < x0_2 - tol or x1_2 < x0_1 - tol or y1_1 < y0_2 - tol or y1_2 < y0_1 - tol)
    for i, page_layout in enumerate(extract_pages(pdf_path)):
        if i != page_number:
            continue
        for element in page_layout:
            if isinstance(element, LTTextContainer):
                for text_line in element:
                    for char in text_line:
                        if isinstance(char, LTChar):
                            x0, y0, x1, y1 = char.bbox
                            # Converter para sistema do PyMuPDF
                            new_y0 = page_height - y1
                            new_y1 = page_height - y0
                            bbox_pymupdf = (x0, new_y0, x1, new_y1)
                            overlap = bboxes_overlap(bbox_pymupdf, bbox, tol=2.0)
                            if overlap:
                                chars.append({
                                    'char': char.get_text(),
                                    'font': char.fontname,
                                    'size': char.size,
                                    'bbox': bbox_pymupdf,
                                    'flags': 0
                                })
    # Agrupar chars consecutivos com mesma fonte e tamanho
    if not chars:
        logger.warning(f"[pdfminer] Nenhum caractere encontrado para o texto alvo '{texto[:30]}...' na página {page_number+1}.")
        return []
    grupo = {'text': '', 'font': chars[0]['font'], 'size': chars[0]['size'], 'flags': chars[0]['flags'], 'bbox': list(chars[0]['bbox'])}
    for idx, c in enumerate(chars):
        if (c['font'] == grupo['font']) and (c['size'] == grupo['size']):
            grupo['text'] += c['char']
            # Expandir bbox
            grupo['bbox'][0] = min(grupo['bbox'][0], c['bbox'][0])
            grupo['bbox'][1] = min(grupo['bbox'][1], c['bbox'][1])
            grupo['bbox'][2] = max(grupo['bbox'][2], c['bbox'][2])
            grupo['bbox'][3] = max(grupo['bbox'][3], c['bbox'][3])
        else:
            logger.info(f"[pdfminer] Novo grupo de span: fonte='{grupo['font']}', tamanho={grupo['size']}, texto='{grupo['text'][:30]}...'")
            spans.append({
                'text': grupo['text'],
                'font': grupo['font'],
                'size': grupo['size'],
                'flags': grupo['flags'],
                'bbox': tuple(grupo['bbox'])
            })
            grupo = {'text': c['char'], 'font': c['font'], 'size': c['size'], 'flags': c['flags'], 'bbox': list(c['bbox'])}
    # Adiciona o último grupo
    if grupo['text']:
        logger.info(f"[pdfminer] Último grupo de span: fonte='{grupo['font']}', tamanho={grupo['size']}, texto='{grupo['text'][:30]}...'")
        spans.append({
            'text': grupo['text'],
            'font': grupo['font'],
            'size': grupo['size'],
            'flags': grupo['flags'],
            'bbox': tuple(grupo['bbox'])
        })
    # Filtra spans vazios e ajusta texto
    spans = [s for s in spans if s['text'].strip()]
    logger.info(f"[pdfminer] Total de spans agrupados: {len(spans)} para texto '{texto[:30]}...' na página {page_number+1}.")
    return spans

# Função para padronizar nome de fonte para o PyMuPDF
def padronizar_nome_fonte(fam_key, variant):
    if variant == 'bold':
        return f"{fam_key}Bold"
    elif variant == 'italic':
        return f"{fam_key}Italic"
    elif variant == 'bolditalic':
        return f"{fam_key}BoldItalic"
    else:
        return f"{fam_key}Regular"

def is_valid_font_file(path):
    """Verifica se o arquivo é um TTF/OTF válido pelo header."""
    try:
        with open(path, 'rb') as f:
            header = f.read(4)
            # TTF: 0x00010000 ou 'true', OTF: 'OTTO'
            if header in [b'\x00\x01\x00\x00', b'true', b'OTTO']:
                return True, header
            else:
                return False, header
    except Exception as e:
        return False, str(e)

def registrar_varios_nomes_font_registry(font_registry, ps_name, variant_name):
    # Adiciona várias variações do nome ao font_registry
    font_registry[ps_name] = variant_name
    # Nome sem prefixo
    if '+' in ps_name:
        sem_prefixo = ps_name.split('+', 1)[-1]
        font_registry[sem_prefixo] = variant_name
    # Nome sem hífen
    sem_hifen = ps_name.replace('-', '')
    font_registry[sem_hifen] = variant_name
    # Nome base (ex: Roboto, BreeSerif)
    base = re.sub(r'[- ]?(Regular|Bold|Italic|Oblique|BoldItalic)$', '', ps_name, flags=re.IGNORECASE)
    font_registry[base] = variant_name

# Função auxiliar para buscar variante de fonte local por família e estilo
def buscar_variante_local(font_registry, file_registry, base, estilo):
    # Ex: base='TimesNewRomanPSMT', estilo='bold' → procura TimesNewRomanBold
    sufixos = {
        'bold': ['Bold', 'bold'],
        'italic': ['Italic', 'italic', 'Oblique', 'oblique'],
        'bolditalic': ['BoldItalic', 'bolditalic', 'BoldOblique', 'boldoblique'],
        'normal': ['Regular', 'regular', 'MT', 'PSMT', ''],
    }
    familia = re.sub(r'PSMT$', '', base, flags=re.IGNORECASE)
    familia = re.sub(r'PS-BoldMT$', '', familia, flags=re.IGNORECASE)
    familia = familia.replace('+', '').replace('-', '').replace(' ', '')
    for suf in sufixos.get(estilo, []):
        for nome in file_registry.keys():
            if familia and familia.lower() in nome.lower() and suf.lower() in nome.lower():
                return nome
    return None

if __name__ == '__main__':
    main() 