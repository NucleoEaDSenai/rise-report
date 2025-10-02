import streamlit as st
import os
import re
import json
import base64
import unicodedata
from bs4 import BeautifulSoup
from datetime import datetime

def slugify(value):
    value = str(value)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^a-zA-Z0-9_-]+', '_', value)
    return value.strip('_').lower()

def html_to_text(s: str) -> str:
    return BeautifulSoup(s, "html.parser").get_text(" ", strip=True)

def seems_content(s: str) -> bool:
    t = (s or "").strip()
    return bool(t and re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", t) and len(t) >= 5)

def collect_texts_from_obj(obj, whitelist):
    texts = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                texts.extend(collect_texts_from_obj(v, whitelist))
            elif isinstance(v, str):
                if (k in whitelist) or ("text" in k.lower()) or ("title" in k.lower()):
                    txt = html_to_text(v)
                    if seems_content(txt):
                        texts.append(txt)
    elif isinstance(obj, list):
        for e in obj:
            texts.extend(collect_texts_from_obj(e, whitelist))
    return texts

# Configuração da página
st.set_page_config(page_title="Contador de Caracteres Rise", layout="wide")

# Barra superior com logo pequena
st.markdown(
    """
    <div style='display:flex; align-items:center; justify-content:flex-start;'>
        <img src='https://raw.githubusercontent.com/SEU-USUARIO/rise-report/main/firjan_senai_branco_horizontal.png' style='height:50px; margin-right:15px;'>
        <h1 style='color:#83c7e5; margin:0;'>Contador de Caracteres Rise</h1>
    </div>
    <hr style="border:1px solid #333;">
    """,
    unsafe_allow_html=True
)

# Estilo customizado para uploader (mais compacto e em português)
st.markdown(
    """
    <style>
    .uploadedFile {margin: 0 !important;}
    .stFileUploader {padding: 0.2rem 0 !important;}
    /* Reduz largura */
    div[data-testid="stFileUploader"] {
        max-width: 300px;
    }
    /* Botão traduzido */
    button[data-baseweb="button"]::after {
        content: "Escolher arquivo";
        color: white;
    }
    button[data-baseweb="button"] > div:first-child {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True
)

uploaded_file = st.file_uploader("📂 Selecione o arquivo `index.html` do Rise", type=["html", "htm"])

if uploaded_file:
    html = uploaded_file.read().decode("utf-8", errors="ignore")
    m = re.search(r'deserialize\("([^"]+)"\)', html)
    if not m:
        st.error("❌ Não encontrei dados de curso nesse index.html.")
    else:
        data = json.loads(base64.b64decode(m.group(1)).decode("utf-8"))
        course = data.get("course", {})
        lessons = course.get("lessons", [])
        course_title = course.get("title", "curso_rise")
        slug = slugify(course_title)
        data_geracao = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        whitelist = {"title","subtitle","body","content","heading","paragraph","text","html","label",
                     "caption","quote","description","question","answer","prompt","snippet","buttonText"}

        rows, totals_by_lesson = [], {}
        total_chars, total_words = 0, 0

        for lesson in lessons:
            lesson_title = lesson.get("title", "Sem título")
            blocks = lesson.get("items", [])
            lesson_chars = 0
            lesson_words = 0
            block_index = 0

            for block in blocks:
                texts = collect_texts_from_obj(block, whitelist)
                if not texts:
                    continue
                merged = re.sub(r"\s+", " ", " ".join(texts)).strip()
                if not merged:
                    continue
                block_index += 1
                char_count = len(merged)
                word_count = len(merged.split())
                lesson_chars += char_count
                lesson_words += word_count
                rows.append((lesson_title, f"Bloco {block_index}", char_count, word_count,
                             merged[:120] + ("..." if len(merged) > 120 else "")))

            if lesson_chars > 0:
                totals_by_lesson[lesson_title] = (lesson_chars, lesson_words)
                total_chars += lesson_chars
                total_words += lesson_words

        # Criar HTML dark mode para download
        html_out = f"""
        <!DOCTYPE html>
        <html lang="pt-br">
        <head>
        <meta charset="UTF-8">
        <title>Relatório de Caracteres - {course_title}</title>
        <style>
        body {{ font-family: Arial, sans-serif; background:#000; color:#fff; padding:20px; }}
        h1,h2,p,td,th {{ color:#fff; }}
        table {{ width:100%; border-collapse:collapse; margin-top:20px; }}
        th,td {{ border:1px solid #555; padding:8px; }}
        th {{ background:#222; }}
        tr:nth-child(even) {{ background:#111; }}
        </style>
        </head>
        <body>
        <h1>Relatório de Caracteres</h1>
        <h2>{course_title}</h2>
        <p><b>Total de caracteres:</b> {total_chars}</p>
        <p><b>Total de palavras:</b> {total_words}</p>
        <h2>Totais por módulo</h2>
        <ul>
        """
        for mod, (chars, words) in totals_by_lesson.items():
            html_out += f"<li><b>{mod}</b>: {chars} caracteres, {words} palavras</li>"
        html_out += "</ul><h2>Blocos detalhados</h2><table><tr><th>Módulo</th><th>Bloco</th><th>Caracteres</th><th>Palavras</th><th>Prévia</th></tr>"
        for row in rows:
            html_out += f"<tr><td>{row[0]}</td><td>{row[1]}</td><td>{row[2]}</td><td>{row[3]}</td><td>{row[4]}</td></tr>"
        html_out += "</table></body></html>"

        # Botão de download no topo
        st.download_button(
            label="⬇️ Baixar Relatório HTML",
            data=html_out,
            file_name=f"relatorio_{slug}.html",
            mime="text/html"
        )

        # Exibir resumo
        st.markdown(f"<h2 style='color:#83c7e5;'>{course_title}</h2>", unsafe_allow_html=True)
        st.write(f"📅 **Gerado em:** {data_geracao}")
        st.write(f"**Total de caracteres (com espaço):** {total_chars}")
        st.write(f"**Total de palavras:** {total_words}")

        st.markdown("<h3 style='color:#83c7e5;'>Totais por módulo</h3>", unsafe_allow_html=True)
        for mod, (chars, words) in totals_by_lesson.items():
            st.write(f"- **{mod}** → {chars} caracteres, {words} palavras")

        st.markdown("<h3 style='color:#83c7e5;'>Blocos detalhados</h3>", unsafe_allow_html=True)
        st.dataframe(rows, use_container_width=True)
