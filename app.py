"""Evaluador de lectura en voz alta — Español, Inglés y Guaraní."""
import html
import io
import random
import sqlite3
from datetime import datetime

import streamlit as st

from evaluador import evaluar

# ------------------------------------------------------------------
# Configuración
# ------------------------------------------------------------------
st.set_page_config(page_title="Evaluador de Lectura", page_icon="🎙️",
                   layout="centered", initial_sidebar_state="collapsed")

WHISPER_MODEL = "small"   # "base" = más rápido, "medium" = más preciso
CODIGOS = {"Español": "es", "Inglés": "en"}
DB = "ranking.db"

TEXTOS = {
    "Español": [
        "El sol brilla intensamente sobre las colinas por la mañana.",
        "La tecnología avanza rápidamente cambiando nuestra vida diaria.",
        "Aprender un nuevo idioma abre puertas a nuevas oportunidades.",
    ],
    "Inglés": [
        "The quick brown fox jumps over the lazy dog.",
        "Learning a new language opens up many global opportunities.",
        "Consistency and practice are key to achieving fluency.",
    ],
    # Conviene que un hablante de guaraní revise estas frases.
    "Guaraní": [
        "Mba'éichapa reko, vy'apavẽ ndéve guarã ko árape.",
        "Guaraní réra ha'e ñane ñe'ẽ teete ha jahayhu va'erã.",
        "Oky guasu rire, osẽ kuarahy omhesape pára tape.",
    ],
}

st.markdown("""
<style>
.block-container { max-width: 720px; padding: 1.2rem 1rem 3rem; }
h1, h2, h3 { font-weight: 600; letter-spacing: -0.01em; }
.stButton > button { width: 100%; border-radius: 10px; min-height: 3em; }
.frase { font-size: clamp(1.25rem, 4.5vw, 1.7rem); line-height: 1.7; margin: .5rem 0 1rem; }
.w { padding: 2px 6px; border-radius: 6px; margin: 0 1px; display: inline-block; }
.w.ok { background: transparent; }
.w.abrev, .w.salto { background: #ffe44d; color: #222; }
.w.mal { background: #ff5c5c; color: #fff; }
.leyenda span { margin-right: 14px; font-size: .9rem; }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# Ranking persistente (SQLite)
# ------------------------------------------------------------------
def _db():
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS ranking(nombre TEXT, idioma TEXT, "
                "puntaje REAL, fecha TEXT)")
    return con

def guardar_puntaje(nombre, idioma, puntaje):
    with _db() as con:
        con.execute("INSERT INTO ranking VALUES (?,?,?,?)",
                    (nombre, idioma, puntaje, datetime.now().isoformat()))

def top(n=5):
    with _db() as con:
        return con.execute("SELECT nombre, idioma, MAX(puntaje) p FROM ranking "
                           "GROUP BY nombre, idioma ORDER BY p DESC LIMIT ?", (n,)).fetchall()

# ------------------------------------------------------------------
# Modelos de IA (se cargan una sola vez y quedan en memoria)
# ------------------------------------------------------------------
@st.cache_resource(show_spinner="Cargando modelo de voz (solo la primera vez)…")
def cargar_whisper():
    from faster_whisper import WhisperModel
    return WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")

@st.cache_resource(show_spinner="Cargando modelo de guaraní (la primera vez tarda)…")
def cargar_mms():
    from transformers import AutoProcessor, Wav2Vec2ForCTC
    proc = AutoProcessor.from_pretrained("facebook/mms-1b-all", target_lang="grn")
    model = Wav2Vec2ForCTC.from_pretrained(
        "facebook/mms-1b-all", target_lang="grn", ignore_mismatched_sizes=True)
    model.eval()
    return proc, model

def transcribir(audio_bytes: bytes, idioma: str) -> str:
    from faster_whisper.audio import decode_audio
    audio = decode_audio(io.BytesIO(audio_bytes), sampling_rate=16000)

    if idioma == "Guaraní":          # Meta MMS: soporta guaraní (grn)
        import torch
        proc, model = cargar_mms()
        entrada = proc(audio, sampling_rate=16000, return_tensors="pt")
        with torch.no_grad():
            logits = model(**entrada).logits
        return proc.decode(torch.argmax(logits, dim=-1)[0])

    modelo = cargar_whisper()         # Whisper: español e inglés
    # Sin initial_prompt a propósito: así no "corrige" los errores del lector.
    segs, _ = modelo.transcribe(audio, language=CODIGOS[idioma], beam_size=1,
                                vad_filter=True, condition_on_previous_text=False)
    return " ".join(s.text for s in segs).strip()

# ------------------------------------------------------------------
# Utilidades de interfaz
# ------------------------------------------------------------------
def ir(vista):
    st.session_state.vista = vista
    st.rerun()

def pintar(palabras) -> str:
    return "".join(f'<span class="w {p.estado}">{html.escape(p.texto)}</span> '
                   for p in palabras)

def mensaje(p):
    if p >= 85: return st.success, "¡Excelente! 🎉 Lectura casi perfecta."
    if p >= 60: return st.warning, "¡Buen intento! 👍 Repasa las palabras marcadas."
    return st.error, "Sigue practicando 💪 Probá de nuevo despacio."

S = st.session_state
S.setdefault("vista", "menu")
S.setdefault("usuario", "")
S.setdefault("n_audio", 0)

# ------------------------------------------------------------------
# Vistas
# ------------------------------------------------------------------
if S.vista == "menu":
    st.title("🎙️ Evaluador de Lectura")
    st.caption("Proyecto escolar — Informática")
    nombre = st.text_input("Tu nombre", value=S.usuario)
    if st.button("Comenzar", type="primary"):
        if nombre.strip():
            S.usuario = nombre.strip()
            ir("practica")
        else:
            st.error("Escribe tu nombre para comenzar.")
    st.subheader("🏆 Ranking")
    filas = top()
    if not filas:
        st.caption("Todavía no hay puntajes.")
    for i, (n, idi, p) in enumerate(filas, 1):
        st.write(f"**#{i} {html.escape(n)}** — {p:.0f}% · {idi}")

elif S.vista == "practica":
    st.subheader(f"Hola, {S.usuario}")
    idioma = st.selectbox("Idioma", list(TEXTOS))
    if S.get("idioma_previo") != idioma or "frase" not in S:
        S.frase, S.idioma_previo = random.choice(TEXTOS[idioma]), idioma

    st.caption("Lee en voz alta:")
    st.markdown(f'<div class="frase">{html.escape(S.frase)}</div>', unsafe_allow_html=True)

    audio = st.audio_input("Toca el micrófono, lee y vuelve a tocar para parar",
                           key=f"audio_{S.n_audio}")
    with st.expander("¿No funciona el micrófono? Escribe lo que leíste"):
        manual = st.text_area("Texto", label_visibility="collapsed")

    c1, c2 = st.columns(2)
    if c1.button("Evaluar", type="primary"):
        if audio is None and not manual.strip():
            st.warning("Graba tu lectura primero.")
        else:
            try:
                with st.spinner("Analizando tu lectura…"):
                    dicho = manual.strip() if audio is None else transcribir(audio.getvalue(), idioma)
            except ImportError as e:
                st.error(f"Falta instalar una librería: {e}. Revisa requirements.txt.")
                st.stop()
            palabras, puntaje, extras = evaluar(S.frase, dicho)
            S.resultado = dict(palabras=palabras, puntaje=puntaje, dicho=dicho,
                               extras=extras, idioma=idioma)
            guardar_puntaje(S.usuario, idioma, puntaje)
            ir("resultado")
    if c2.button("Otra frase"):
        S.frase = random.choice(TEXTOS[idioma]); S.n_audio += 1; st.rerun()
    if st.button("← Menú"):
        ir("menu")

elif S.vista == "resultado":
    r = S.resultado
    st.title("📊 Resultado")
    st.metric("Acierto", f"{r['puntaje']}%")
    aviso, texto = mensaje(r["puntaje"])
    aviso(texto)

    st.markdown(f'<div class="frase">{pintar(r["palabras"])}</div>', unsafe_allow_html=True)
    st.markdown('<div class="leyenda"><span><span class="w salto">&nbsp;</span> salteó / abrevió</span>'
                '<span><span class="w mal">&nbsp;</span> dijo mal</span></div>',
                unsafe_allow_html=True)
    if r["extras"]:
        st.caption(f"Agregaste {r['extras']} palabra(s) que no estaban en el texto.")
    with st.expander("Lo que entendió la IA"):
        st.write(r["dicho"] or "(no se escuchó nada)")

    c1, c2 = st.columns(2)
    if c1.button("🔄 Intentar otra vez", type="primary"):
        S.n_audio += 1; ir("practica")
    if c2.button("🏠 Menú"):
        S.n_audio += 1; ir("menu")
