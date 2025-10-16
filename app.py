import streamlit as st
import os
import re
import json
import base64
import unicodedata
from bs4 import BeautifulSoup
from datetime import datetime

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

    # Detecta o payload base64 do Rise (Articulate) dentro do index.html
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

        whitelist = {
            "title","subtitle","body","content","heading","paragraph","text","html","label",
            "caption","quote","description","question","answer","prompt","snippet","buttonText"
        }

        # -------- Contagem por MÓDULO (sessão) e detalhado por blocos --------
        block_rows = []         # tabela detalhada (por bloco)
        module_rows = []        # resumo por módulo (mantém a ordem de aparição)
        total_words = 0

        for lesson in lessons:
            lesson_title = lesson.get("title", "Sem título")
            blocks = lesson.get("items", [])
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
                word_count = len(merged.split())

                lesson_words += word_count

                preview = merged[:120] + ("..." if len(merged) > 120 else "")
                block_rows.append({
                    "Módulo": lesson_title,
                    "Bloco": f"Bloco {block_index}",
                    "Palavras": word_count,
                    "Prévia": preview
                })

            # Guarda o total do módulo, mesmo que 0 (opcionalmente você pode ocultar zeros)
            module_rows.append({
                "Módulo": lesson_title,
                "Palavras": lesson_words
            })
            total_words += lesson_words

        # ----------------- RELATÓRIO HTML DETALHADO -----------------
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

        # ----------------- CSV RESUMO POR MÓDULO -----------------
        csv_lines = ["Modulo,Palavras"]
        for row in module_rows:
            # Escapa vírgulas no título com aspas
            modulo = row["Módulo"].replace('"', '""')
            csv_lines.append(f"\"{modulo}\",{row['Palavras']}")
        csv_lines.append(f"\"Total do curso\",{total_words}")
        csv_bytes = ("\n".join(csv_lines)).encode("utf-8")

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
