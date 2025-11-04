
import streamlit as st
import os
import re
import json
import base64
import unicodedata
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Any, Optional, Tuple, Union, List, Dict

# ------------------- Utils -------------------
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

# -------- Payload extraction helpers --------
def _try_b64_decode(s: str) -> Optional[bytes]:
    # Try standard b64
    for urlsafe in (False, True):
        t = s.strip()
        if urlsafe:
            t = t.replace('-', '+').replace('_', '/')
        # Fix padding if needed
        pad = len(t) % 4
        if pad:
            t = t + ('=' * (4 - pad))
        try:
            return base64.b64decode(t, validate=False)
        except Exception:
            pass
    return None

def extract_rise_payload(html: str) -> Optional[bytes]:
    """
    Attempts multiple strategies to find the Rise base64 payload.
    Returns raw decoded bytes if successful.
    """
    candidates: List[str] = []

    # Strategy 1: deserialize("...") or deserialize('...')
    pat1 = re.compile(r'deserialize\(\s*([\'"])(.*?)\1\s*\)', re.DOTALL | re.IGNORECASE)
    for m in pat1.finditer(html):
        candidates.append(m.group(2))

    # Strategy 2: atob("...") or atob('...')
    pat2 = re.compile(r'atob\(\s*([\'"])(.*?)\1\s*\)', re.DOTALL | re.IGNORECASE)
    for m in pat2.finditer(html):
        candidates.append(m.group(2))

    # Strategy 3: any very long base64-like quoted string
    pat3 = re.compile(r'([\'"])([A-Za-z0-9+/=_-]{500,})\1', re.DOTALL)
    for m in pat3.finditer(html):
        candidates.append(m.group(2))

    # Deduplicate while preserving order
    seen = set()
    uniq_candidates = []
    for c in candidates:
        if c not in seen:
            uniq_candidates.append(c)
            seen.add(c)

    for c in uniq_candidates:
        raw = _try_b64_decode(c)
        if not raw:
            continue
        # Heuristic: decoded bytes should look like JSON
        # Try json loads; if it fails, skip
        try:
            data = json.loads(raw.decode('utf-8', errors='ignore'))
        except Exception:
            # Sometimes there is a second layer of base64 or stringified JSON
            try:
                inner_try = raw.decode('utf-8', errors='ignore')
                inner_b = _try_b64_decode(inner_try)
                if inner_b:
                    data = json.loads(inner_b.decode('utf-8', errors='ignore'))
                else:
                    continue
            except Exception:
                continue
        # If JSON loaded, return original decoded bytes (of the JSON)
        return json.dumps(data).encode('utf-8')
    return None

def find_course_root(obj: Any) -> Tuple[Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
    """
    Finds a dict that contains lessons (list of dicts). Returns (course_root, lessons_list).
    Tries standard paths and a BFS over nested dicts.
    """
    # Common cases
    if isinstance(obj, dict):
        if 'course' in obj and isinstance(obj['course'], dict):
            c = obj['course']
            if 'lessons' in c and isinstance(c['lessons'], list):
                return c, c['lessons']
        if 'lessons' in obj and isinstance(obj['lessons'], list):
            return obj, obj['lessons']

    # BFS over dicts/lists
    queue = [obj]
    while queue:
        cur = queue.pop(0)
        if isinstance(cur, dict):
            if 'lessons' in cur and isinstance(cur['lessons'], list):
                return cur, cur['lessons']
            for v in cur.values():
                if isinstance(v, (dict, list)):
                    queue.append(v)
        elif isinstance(cur, list):
            for v in cur:
                if isinstance(v, (dict, list)):
                    queue.append(v)
    return None, None

# ------------------- UI / ESTILO -------------------
st.set_page_config(page_title="Contador de Palavras Rise", layout="wide")

if os.path.exists("firjan_senai_branco_horizontal.png"):
    st.image("firjan_senai_branco_horizontal.png", width=180)

st.markdown("<h1 style='color:#83c7e5; text-align:center;'>Contador de Palavras Rise</h1>", unsafe_allow_html=True)

st.markdown(
    """
    <style>
    body { background-color: #000; color: #fff; }
    h1, h2, h3, p, td, th { color: #fff !important; }
    div[data-testid="stFileUploader"] { max-width: 600px; margin: auto; }
    div.stDownloadButton > button {
        background-color: #333 !important; color: #83c7e5 !important; font-weight: bold;
        border-radius: 6px; border: none !important; padding: 0.6rem 1.2rem;
    }
    </style>
    """,
    unsafe_allow_html=True
)

uploaded_file = st.file_uploader("📂 Selecione o arquivo `index.html` do Rise", type=["html", "htm"])

if uploaded_file:
    html = uploaded_file.read().decode("utf-8", errors="ignore")

    raw_payload = extract_rise_payload(html)
    if not raw_payload:
        st.error("❌ Não encontrei dados de curso nesse index.html. Tente garantir que é o `index.html` exportado do Rise (não zip recompactado) e que o arquivo não foi minificado/alterado.")
    else:
        try:
            data = json.loads(raw_payload.decode('utf-8', errors='ignore'))
        except Exception as e:
            st.error("❌ Encontrei um payload, mas não consegui ler o JSON interno.")
            st.exception(e)
            st.stop()

        course_root, lessons = find_course_root(data)
        if not lessons:
            st.error("❌ Encontrei JSON, mas não localizei a estrutura de `lessons`. Pode ser um formato diferente do Rise.")
            st.stop()

        course_title = course_root.get("title", "curso_rise")
        data_geracao = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        slug = slugify(course_title)

        whitelist = {
            "title","subtitle","body","content","heading","paragraph","text","html","label",
            "caption","quote","description","question","answer","prompt","snippet","buttonText"
        }

        # -------- Contagem por MÓDULO (sessão) e detalhado por blocos --------
        block_rows = []         # tabela detalhada (por bloco) - SÓ PALAVRAS (original)
        module_rows = []        # resumo por módulo - SÓ PALAVRAS (original)
        total_words = 0         # total de palavras (original)

        # --- NOVO (caracteres) ---
        block_rows_chars = []   # detalhado por bloco (palavras + caracteres)
        module_rows_chars = []  # resumo por módulo (palavras + caracteres)
        total_chars_ws = 0      # caracteres com espaços (curso)
        total_chars_ns = 0      # caracteres sem espaços (curso)

        for lesson in lessons:
            if not isinstance(lesson, dict):
                continue
            lesson_title = lesson.get("title", "Sem título")
            blocks = lesson.get("items", []) or lesson.get("blocks", []) or []
            lesson_words = 0
            lesson_chars_ws = 0
            lesson_chars_ns = 0
            block_index = 0

            for block in blocks:
                texts = collect_texts_from_obj(block, whitelist)
                if not texts:
                    continue

                merged = re.sub(r"\s+", " ", " ".join(texts)).strip()
                if not merged:
                    continue

                block_index += 1
                word_count = len(merged.split())
                char_count_ws = len(merged)
                char_count_ns = len(re.sub(r"\s+", "", merged))

                lesson_words += word_count
                lesson_chars_ws += char_count_ws
                lesson_chars_ns += char_count_ns

                preview = merged[:120] + ("..." if len(merged) > 120 else "")

                block_rows.append({
                    "Módulo": lesson_title,
                    "Bloco": f"Bloco {block_index}",
                    "Palavras": word_count,
                    "Prévia": preview
                })

                block_rows_chars.append({
                    "Módulo": lesson_title,
                    "Bloco": f"Bloco {block_index}",
                    "Palavras": word_count,
                    "Caracteres (c/ espaços)": char_count_ws,
                    "Caracteres (s/ espaços)": char_count_ns,
                    "Prévia": preview
                })

            module_rows.append({
                "Módulo": lesson_title,
                "Palavras": lesson_words
            })
            total_words += lesson_words

            module_rows_chars.append({
                "Módulo": lesson_title,
                "Palavras": lesson_words,
                "Caracteres (c/ espaços)": lesson_chars_ws,
                "Caracteres (s/ espaços)": lesson_chars_ns
            })
            total_chars_ws += lesson_chars_ws
            total_chars_ns += lesson_chars_ns

        # ----------------- RELATÓRIO HTML DETALHADO (ORIGINAL) -----------------
        parts = []
        parts.append(f"""
        <!DOCTYPE html>
        <html lang="pt-br">
        <head>
        <meta charset="UTF-8">
        <title>Relatório de Palavras - {course_title}</title>
        <style>
        body {{ font-family: Arial, sans-serif; background:#000; color:#fff; padding:20px; }}
        h1,h2,p,td,th {{ color:#fff; }}
        table {{ width:100%; border-collapse:collapse; margin-top:20px; }}
        th,td {{ border:1px solid #555; padding:8px; }}
        th {{ background:#222; }}
        tr:nth-child(even) {{ background:#111; }}
        .tot {{ font-weight:bold; }}
        </style>
        </head>
        <body>
        <h1>Relatório de Palavras</h1>
        <h2>{course_title}</h2>
        <p><b>Gerado em:</b> {data_geracao}</p>

        <h2>Totais por módulo</h2>
        <table>
            <tr><th>Módulo</th><th>Palavras</th></tr>
        """)
        for row in module_rows:
            parts.append(f"<tr><td>{row['Módulo']}</td><td>{row['Palavras']}</td></tr>")
        parts.append(f"<tr class='tot'><td>Total do curso</td><td>{total_words}</td></tr></table>")

        parts.append("""
        <h2>Blocos detalhados</h2>
        <table>
            <tr><th>Módulo</th><th>Bloco</th><th>Palavras</th><th>Prévia</th></tr>
        """)
        for row in block_rows:
            parts.append(
                f"<tr><td>{row['Módulo']}</td><td>{row['Bloco']}</td><td>{row['Palavras']}</td><td>{row['Prévia']}</td></tr>"
            )
        parts.append(f"</table><p class='tot'>Total do curso: {total_words} palavras</p></body></html>")
        html_out = "".join(parts)

        # ----------------- NOVO: RELATÓRIO HTML (PALAVRAS + CARACTERES) -----------------
        parts_chars = []
        parts_chars.append(f"""
        <!DOCTYPE html>
        <html lang="pt-br">
        <head>
        <meta charset="UTF-8">
        <title>Relatório de Palavras e Caracteres - {course_title}</title>
        <style>
        body {{ font-family: Arial, sans-serif; background:#000; color:#fff; padding:20px; }}
        h1,h2,p,td,th {{ color:#fff; }}
        table {{ width:100%; border-collapse:collapse; margin-top:20px; }}
        th,td {{ border:1px solid #555; padding:8px; }}
        th {{ background:#222; }}
        tr:nth-child(even) {{ background:#111; }}
        .tot {{ font-weight:bold; }}
        </style>
        </head>
        <body>
        <h1>Relatório de Palavras e Caracteres</h1>
        <h2>{course_title}</h2>
        <p><b>Gerado em:</b> {data_geracao}</p>

        <h2>Totais por módulo</h2>
        <table>
            <tr>
              <th>Módulo</th>
              <th>Palavras</th>
              <th>Caracteres (c/ espaços)</th>
              <th>Caracteres (s/ espaços)</th>
            </tr>
        """)
        for row in module_rows_chars:
            parts_chars.append(
                f"<tr><td>{row['Módulo']}</td><td>{row['Palavras']}</td>"
                f"<td>{row['Caracteres (c/ espaços)']}</td><td>{row['Caracteres (s/ espaços)']}</td></tr>"
            )
        parts_chars.append(
            f"<tr class='tot'><td>Total do curso</td><td>{total_words}</td>"
            f"<td>{total_chars_ws}</td><td>{total_chars_ns}</td></tr></table>"
        )

        parts_chars.append("""
        <h2>Blocos detalhados</h2>
        <table>
            <tr>
              <th>Módulo</th><th>Bloco</th><th>Palavras</th>
              <th>Caracteres (c/ espaços)</th><th>Caracteres (s/ espaços)</th><th>Prévia</th>
            </tr>
        """)
        for row in block_rows_chars:
            parts_chars.append(
                f"<tr><td>{row['Módulo']}</td><td>{row['Bloco']}</td>"
                f"<td>{row['Palavras']}</td>"
                f"<td>{row['Caracteres (c/ espaços)']}</td>"
                f"<td>{row['Caracteres (s/ espaços)']}</td>"
                f"<td>{row['Prévia']}</td></tr>"
            )
        parts_chars.append(
            f"</table><p class='tot'>Total do curso: {total_words} palavras | "
            f"{total_chars_ws} caracteres (c/ espaços) | {total_chars_ns} caracteres (s/ espaços)</p>"
            f"</body></html>"
        )
        html_out_chars = "".join(parts_chars)

        # ----------------- CSV RESUMO POR MÓDULO (ORIGINAL) -----------------
        csv_lines = ["Modulo,Palavras"]
        for row in module_rows:
            modulo = row["Módulo"].replace('"', '""')
            csv_lines.append(f"\"{modulo}\",{row['Palavras']}")
        csv_lines.append(f"\"Total do curso\",{total_words}")
        csv_bytes = ("\n".join(csv_lines)).encode("utf-8")

        # ----------------- NOVO: CSV RESUMO (PALAVRAS + CARACTERES) -----------------
        csv_lines_chars = ["Modulo,Palavras,CaracteresComEspacos,CaracteresSemEspacos"]
        for row in module_rows_chars:
            modulo = row["Módulo"].replace('"', '""')
            csv_lines_chars.append(
                f"\"{modulo}\",{row['Palavras']},{row['Caracteres (c/ espaços)']},{row['Caracteres (s/ espaços)']}"
            )
        csv_lines_chars.append(f"\"Total do curso\",{total_words},{total_chars_ws},{total_chars_ns}")
        csv_bytes_chars = ("\n".join(csv_lines_chars)).encode("utf-8")

        # ----------------- DOWNLOADS -----------------
        st.download_button(
            label="⬇️ Baixar Relatório HTML (detalhado)",
            data=html_out,
            file_name=f"relatorio_palavras_{slug}.html",
            mime="text/html"
        )
        st.download_button(
            label="⬇️ Baixar CSV (resumo por módulo)",
            data=csv_bytes,
            file_name=f"resumo_palavras_{slug}.csv",
            mime="text/csv"
        )

        st.download_button(
            label="⬇️ Baixar Relatório HTML (palavras + caracteres)",
            data=html_out_chars,
            file_name=f"relatorio_palavras_e_caracteres_{slug}.html",
            mime="text/html"
        )
        st.download_button(
            label="⬇️ Baixar CSV (módulos: palavras + caracteres)",
            data=csv_bytes_chars,
            file_name=f"resumo_palavras_e_caracteres_{slug}.csv",
            mime="text/csv"
        )

        # ----------------- RESUMO NA TELA -----------------
        st.markdown(f"<h2 style='color:#83c7e5;'>{course_title}</h2>", unsafe_allow_html=True)
        st.write(f"📅 **Gerado em:** {data_geracao}")

        st.markdown("<h3 style='color:#83c7e5;'>Totais por módulo</h3>", unsafe_allow_html=True)
        st.dataframe(module_rows, use_container_width=True)
        st.markdown(
            f"<p style='font-size:1.1rem;'><b>Total do curso:</b> {total_words} palavras</p>",
            unsafe_allow_html=True
        )

        st.markdown("<h3 style='color:#83c7e5;'>Blocos detalhados (preview)</h3>", unsafe_allow_html=True)
        max_preview = 100
        preview_rows = block_rows[:max_preview]
        st.dataframe(preview_rows, use_container_width=True)

        if len(block_rows) > max_preview:
            st.info(
                f"⚠️ Mostrando apenas os primeiros {max_preview} blocos no app. "
                f"O relatório HTML baixado contém todos os {len(block_rows)} blocos."
            )

        st.markdown("<hr/>", unsafe_allow_html=True)
        st.markdown("<h3 style='color:#83c7e5;'>Totais por módulo (palavras + caracteres)</h3>", unsafe_allow_html=True)
        st.dataframe(module_rows_chars, use_container_width=True)
        st.markdown(
            f"<p style='font-size:1.1rem;'><b>Total do curso:</b> {total_words} palavras | "
            f"{total_chars_ws} caracteres (c/ espaços) | {total_chars_ns} caracteres (s/ espaços)</p>",
            unsafe_allow_html=True
        )

        st.markdown("<h3 style='color:#83c7e5;'>Blocos detalhados com caracteres (preview)</h3>", unsafe_allow_html=True)
        preview_rows_chars = block_rows_chars[:max_preview]
        st.dataframe(preview_rows_chars, use_container_width=True)

        if len(block_rows_chars) > max_preview:
            st.info(
                f"⚠️ Mostrando apenas os primeiros {max_preview} blocos na visualização com caracteres. "
                f"O relatório HTML (palavras + caracteres) contém todos os {len(block_rows_chars)} blocos."
            )
