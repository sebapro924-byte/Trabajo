"""Lectura en voz alta con IA — Español, Inglés y Guaraní."""
import html
import io
import random
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher

import streamlit as st
import streamlit.components.v1 as components

# ------------------------------------------------------------------
# Configuración
# ------------------------------------------------------------------
st.set_page_config(page_title="Lectura", page_icon="🎙️",
                   layout="centered", initial_sidebar_state="collapsed")

WHISPER_MODEL = "small"          # "base" = más rápido, "medium" = más preciso
CODIGOS = {"Español": "es", "Inglés": "en"}
IDIOMAS = ["Español", "Inglés", "Guaraní"]
NIVELES = ["Normal", "Difícil", "Profesional"]
DESCRIPCION = {
    "Normal": "Frases cortas y sencillas. Corrección flexible.",
    "Difícil": "Frases largas. Corrección más exigente.",
    "Profesional": "Trabalenguas y vocabulario técnico. Corrección estricta.",
}
UMBRALES = {"Normal": 0.78, "Difícil": 0.85, "Profesional": 0.92}  # parecido para dar OK
UMBRAL_MAL = 0.50
DB = "ranking.db"

# ------------------------------------------------------------------
# Banco de frases: TEXTOS[idioma][nivel]
# (Las de guaraní conviene que las revise un hablante.)
# ------------------------------------------------------------------
TEXTOS = {
    "Español": {
        "Normal": [
            "El sol brilla sobre las colinas.",
            "Mi abuela prepara el almuerzo los domingos.",
            "Los niños juegan en el patio.",
            "Leer un buen libro es divertido.",
            "El perro corre feliz por el parque.",
            "Mañana iremos temprano a la escuela.",
            "La música nos pone alegres.",
            "Me gusta tomar tereré con mis amigos.",
        ],
        "Difícil": [
            "El sol brilla intensamente sobre las colinas por la mañana.",
            "La tecnología avanza rápidamente cambiando nuestra vida diaria.",
            "Aprender un nuevo idioma abre puertas a nuevas oportunidades.",
            "El río cruza la ciudad y refleja las luces de la noche.",
            "Cuidar el medio ambiente es responsabilidad de todos nosotros.",
            "Cuando amanece, los pájaros cantan en los árboles del jardín.",
            "Quiero ser ingeniero para crear programas que ayuden a las personas.",
            "Mañana por la tarde visitaremos el museo de historia de la ciudad.",
        ],
        "Profesional": [
            "Tres tristes tigres tragaban trigo en un trigal.",
            "El desarrollo sostenible exige equilibrar el crecimiento económico, la justicia social y la protección del medio ambiente.",
            "La inteligencia artificial transforma la medicina, la educación y la manera en que nos comunicamos.",
            "Pablito clavó un clavito. ¿Qué clavito clavó Pablito?",
            "El electrocardiograma permitió diagnosticar la arritmia cardíaca de forma rápida y precisa.",
            "Aunque la investigación científica requiere paciencia, perseverancia y rigurosidad, sus resultados benefician a toda la humanidad.",
            "El otorrinolaringólogo examinó minuciosamente al paciente antes de recomendar el tratamiento.",
            "Compré pocas copas, pocas copas compré; como compré pocas copas, pocas copas pagué.",
        ],
    },
    "Inglés": {
        "Normal": [
            "The sun shines on the hills.",
            "My grandmother cooks lunch on Sundays.",
            "The children play in the yard.",
            "Reading a good book is fun.",
            "The dog runs happily in the park.",
            "Tomorrow we will go to school early.",
            "Music makes us happy.",
            "I like to drink tea with my friends.",
        ],
        "Difícil": [
            "The quick brown fox jumps over the lazy dog.",
            "Learning a new language opens up many global opportunities.",
            "Consistency and practice are key to achieving fluency.",
            "The river crosses the city and reflects the lights at night.",
            "Taking care of the environment is everyone's responsibility.",
            "At dawn, the birds sing in the trees of the garden.",
            "I want to become an engineer and build programs that help people.",
            "Tomorrow afternoon we will visit the history museum downtown.",
        ],
        "Profesional": [
            "She sells seashells by the seashore, and the shells she sells are surely seashells.",
            "Sustainable development requires balancing economic growth, social justice, and environmental protection.",
            "Artificial intelligence is transforming medicine, education, and the way we communicate.",
            "Peter Piper picked a peck of pickled peppers.",
            "Although scientific research demands patience, perseverance, and rigor, its results benefit all of humanity.",
            "The otolaryngologist thoroughly examined the patient before recommending a treatment.",
            "Thirty-three thieves thought that they thrilled the throne throughout Thursday.",
            "The comprehensive curriculum emphasizes critical thinking, collaboration, and technological literacy.",
        ],
    },
    "Guaraní": {
        "Normal": [
            "Mba'éichapa reiko?",
            "Che réra Ana.",
            "Ahayhu che ñe'ẽ guaraní.",
            "Pe mitã ohecha peteĩ guyra.",
            "Kuarahy omimbi ko árape.",
            "Aháta eskuélape ko'ẽrõ.",
            "Ko'ágã aju eskuélagui.",
            "Ñande ñe'ẽ iporãiterei.",
        ],
        "Difícil": [
            "Che réra Ana ha aiko Paraguáipe.",
            "Ñande ñe'ẽ guaraní iporãiterei.",
            "Che ru ha che sy oñe'ẽ guaraníme.",
            "Mitãkuéra oñembosarái yvyra guýpe.",
            "Paraguay ha'e peteĩ tetã iporãva.",
            "Che aguereko peteĩ mbarakaja pyahu.",
            "Ko'ẽrõ ajapóta tembiapo ha avy'áta.",
            "Guaraní ha'e ñane ñe'ẽ teete ha jahayhu va'erã.",
        ],
        "Profesional": [
            "Che réra Ana, aiko Paraguáipe ha ahayhu che ñe'ẽ guaraní.",
            "Che ru ha che sy oñe'ẽ guaraníme, ha ko'ágã che avei añe'ẽ guaraníme.",
            "Mitãkuéra oñembosarái yvyra guýpe ha kuarahy omimbi ko árape.",
            "Aháta eskuélape ko'ẽrõ ha avy'áta che mbo'ehára ha che irũnguéra ndive.",
            "Pe mbo'ehára ombo'e mitãkuéra ohayhu haguã ñane ñe'ẽ guaraní.",
            "Ñane retã Paraguay oguereko mokõi ñe'ẽ: guaraní ha karaiñe'ẽ.",
            "Paraguay ha'e peteĩ tetã iporãva, ha ñande ñe'ẽ guaraní ha'e ñane ñe'ẽ teete.",
        ],
    },
}

# ------------------------------------------------------------------
# Estilo (minimalista, se adapta a celular, tablet y PC)
# ------------------------------------------------------------------
st.markdown("""
<style>
#MainMenu, footer { visibility: hidden; }
[data-testid="stHeader"] { background: transparent; }
.block-container { max-width: 680px; padding: 1.2rem 1rem 4rem; }
.hero { text-align: center; padding: 1.5rem 0 1rem; }
.hero h1 { font-size: clamp(2.2rem, 9vw, 3rem); margin: 0; letter-spacing: -0.03em; }
.hero p { opacity: .65; margin: .4rem 0 0; }
.tarjeta { border: 1px solid rgba(128,128,128,.25); border-radius: 18px;
           padding: 1rem 1.1rem; margin: .6rem 0; }
.chip { display: inline-block; padding: 2px 12px; border-radius: 999px; font-size: .8rem;
        background: rgba(79,70,229,.15); margin-right: 6px; }
.frase { font-size: clamp(1.3rem, 5vw, 1.9rem); line-height: 1.75; text-align: center;
         padding: .8rem .2rem; }
.w { padding: 2px 6px; border-radius: 6px; margin: 0 1px; display: inline-block; }
.w.abrev, .w.salto { background: #ffe44d; color: #222; }
.w.mal { background: #ff5c5c; color: #fff; }
.leyenda { text-align: center; font-size: .85rem; opacity: .85; }
.leyenda .w { padding: 0 9px; }
.stButton > button { width: 100%; border-radius: 14px; min-height: 3.2em; font-weight: 600; }
.stButton > button[kind="primary"],
.stButton > button[data-testid="stBaseButton-primary"] {
    background: #4f46e5; border-color: #4f46e5; color: #fff; }
</style>
""", unsafe_allow_html=True)

# Mejora la experiencia al "Agregar a pantalla de inicio" (se ejecuta una vez)
if "pwa" not in st.session_state:
    st.session_state.pwa = True
    components.html("""<script>
    const d = window.parent.document;
    const meta = (n, c) => {
      let m = d.querySelector('meta[name="' + n + '"]');
      if (!m) { m = d.createElement('meta'); m.name = n; d.head.appendChild(m); }
      m.content = c;
    };
    meta('theme-color', '#4f46e5');
    meta('mobile-web-app-capable', 'yes');
    meta('apple-mobile-web-app-capable', 'yes');
    meta('apple-mobile-web-app-title', 'Lectura');
    </script>""", height=0)

# ------------------------------------------------------------------
# Lógica de evaluación (compara lo esperado con lo dicho)
# ------------------------------------------------------------------
@dataclass
class Palabra:
    texto: str       # palabra original (para mostrar)
    estado: str      # "ok" | "abrev" | "salto" | "mal"
    dicho: str = ""  # lo que se entendió


def normalizar(p: str) -> str:
    """Minúsculas, sin tildes ni signos (tolerante con la transcripción)."""
    p = unicodedata.normalize("NFD", p.lower())
    p = "".join(c for c in p if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w]", "", p)


def _tokens(texto: str):
    out = []
    for w in texto.split():
        n = normalizar(w)
        if n:
            out.append((w, n))
    return out


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _es_abrev(orig_n: str, dicho_n: str) -> bool:
    return 2 <= len(dicho_n) < len(orig_n) and orig_n.startswith(dicho_n)


def _clasificar(orig_n: str, dicho_n: str, umbral: float) -> str:
    if _ratio(orig_n, dicho_n) >= umbral:
        return "ok"
    return "abrev" if _es_abrev(orig_n, dicho_n) else "mal"


def evaluar(original: str, dicho: str, umbral: float = 0.85):
    """Devuelve (lista de Palabra, puntaje 0-100, palabras de más)."""
    o, s = _tokens(original), _tokens(dicho)
    on, sn = [n for _, n in o], [n for _, n in s]
    res = [None] * len(o)
    extras = 0

    for tag, i1, i2, j1, j2 in SequenceMatcher(None, on, sn, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                res[i1 + k] = Palabra(o[i1 + k][0], "ok", s[j1 + k][0])
        elif tag == "delete":
            for i in range(i1, i2):
                res[i] = Palabra(o[i][0], "salto")
        elif tag == "insert":
            extras += j2 - j1
        else:  # replace
            lo, ls = i2 - i1, j2 - j1
            if lo == ls:
                for k in range(lo):
                    est = _clasificar(on[i1 + k], sn[j1 + k], umbral)
                    res[i1 + k] = Palabra(o[i1 + k][0], est, s[j1 + k][0])
            else:
                ptr = 0
                for k in range(lo):
                    i = i1 + k
                    cand = [(_ratio(on[i], sn[j1 + c]), c) for c in range(ptr, ls)]
                    mejor = max(cand) if cand else (0, -1)
                    if cand and (mejor[0] >= UMBRAL_MAL or _es_abrev(on[i], sn[j1 + mejor[1]])):
                        c = mejor[1]
                        res[i] = Palabra(o[i][0], _clasificar(on[i], sn[j1 + c], umbral), s[j1 + c][0])
                        extras += c - ptr
                        ptr = c + 1
                    elif (ls - ptr) >= (lo - k):
                        res[i] = Palabra(o[i][0], "mal", s[j1 + ptr][0])
                        ptr += 1
                    else:
                        res[i] = Palabra(o[i][0], "salto")
                extras += max(0, ls - ptr)

    total = len(res) or 1
    puntos = sum({"ok": 1, "abrev": 0.5}.get(p.estado, 0) for p in res)
    return res, round(puntos / total * 100, 1), extras

# ------------------------------------------------------------------
# Ranking persistente (SQLite)
# ------------------------------------------------------------------
def _db():
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS ranking_v2(nombre TEXT, idioma TEXT, "
                "nivel TEXT, puntaje REAL, fecha TEXT)")
    return con


def guardar_puntaje(nombre, idioma, nivel, puntaje):
    with _db() as con:
        con.execute("INSERT INTO ranking_v2 VALUES (?,?,?,?,?)",
                    (nombre, idioma, nivel, puntaje, datetime.now().isoformat()))


def top(n=8):
    with _db() as con:
        return con.execute(
            "SELECT nombre, idioma, nivel, MAX(puntaje) p FROM ranking_v2 "
            "GROUP BY nombre, idioma, nivel ORDER BY p DESC LIMIT ?", (n,)).fetchall()

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


def leer_wav(audio_bytes: bytes, sr_destino: int = 16000):
    """Lee el WAV del micrófono y lo pasa a mono 16 kHz (sin librerías extra)."""
    import wave
    import numpy as np
    with wave.open(io.BytesIO(audio_bytes), "rb") as w:
        canales, ancho, sr = w.getnchannels(), w.getsampwidth(), w.getframerate()
        crudo = w.readframes(w.getnframes())
    tipo = {1: np.uint8, 2: np.int16, 4: np.int32}[ancho]
    x = np.frombuffer(crudo, dtype=tipo).astype(np.float32)
    x = (x - 128) / 128 if ancho == 1 else x / float(2 ** (8 * ancho - 1))
    if canales > 1:
        x = x.reshape(-1, canales).mean(axis=1)
    if sr != sr_destino and len(x) > 1:
        n = int(len(x) * sr_destino / sr)
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
    return x.astype(np.float32)


def transcribir(audio_bytes: bytes, idioma: str) -> str:
    audio = leer_wav(audio_bytes)
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
S = st.session_state
S.setdefault("vista", "inicio")
S.setdefault("usuario", "")
S.setdefault("n_audio", 0)
S.setdefault("vistas", {})


def ir(vista):
    S.vista = vista
    st.rerun()


def elegir_frase(idioma, nivel):
    """Frase que todavía no salió; al agotarlas reinicia sin repetir la última."""
    vistas = S.vistas.setdefault(f"{idioma}|{nivel}", [])
    pool = TEXTOS[idioma][nivel]
    pendientes = [f for f in pool if f not in vistas]
    if not pendientes:
        ultima = vistas[-1] if vistas else None
        vistas.clear()
        pendientes = [f for f in pool if f != ultima] or pool
    f = random.choice(pendientes)
    vistas.append(f)
    return f


def pintar(palabras) -> str:
    return "".join(f'<span class="w {p.estado}">{html.escape(p.texto)}</span> '
                   for p in palabras)


def selector_idioma_nivel():
    idioma = st.segmented_control("Idioma", IDIOMAS, default="Español", key="cfg_idioma") or "Español"
    nivel = st.segmented_control("Nivel", NIVELES, default="Normal", key="cfg_nivel") or "Normal"
    st.caption(DESCRIPCION[nivel])
    return idioma, nivel


def encabezado(texto):
    st.markdown(f'<div class="hero"><h1>{texto}</h1></div>', unsafe_allow_html=True)


def mensaje(p):
    if p >= 85:
        return st.success, "¡Excelente! 🎉 Lectura casi perfecta."
    if p >= 60:
        return st.warning, "¡Buen intento! 👍 Repasa las palabras marcadas."
    return st.error, "Sigue practicando 💪 Prueba de nuevo, despacio."


def frase_actual():
    return S.frases[S.ronda] if S.modo == "local" else S.frase

# ------------------------------------------------------------------
# Vistas
# ------------------------------------------------------------------
if S.vista == "inicio":
    st.markdown('<div class="hero"><h1>🎙️ Lectura</h1>'
                '<p>Lee en voz alta y la IA te corrige</p></div>', unsafe_allow_html=True)
    if st.button("🎤 Practicar solo", type="primary"):
        ir("cfg_solo")
    if st.button("👥 Partida local"):
        ir("cfg_local")

    with st.expander("🏆 Ranking"):
        filas = top()
        if not filas:
            st.caption("Todavía no hay puntajes.")
        for i, (n, idi, niv, p) in enumerate(filas, 1):
            st.markdown(f"**#{i} {html.escape(n)}** — {p:.0f}% "
                        f'<span class="chip">{idi}</span><span class="chip">{niv}</span>',
                        unsafe_allow_html=True)
    with st.expander("📲 Instalar como app en tu celular"):
        st.markdown(
            "**Android (Chrome):** menú ⋮ → *Instalar app* o *Agregar a pantalla principal*.\n\n"
            "**iPhone (Safari):** botón Compartir → *Agregar a inicio*.\n\n"
            "Queda un ícono como cualquier app y se abre a pantalla completa.")

elif S.vista == "cfg_solo":
    encabezado("🎤 Práctica")
    S.usuario = st.text_input("Tu nombre", value=S.usuario)
    idioma, nivel = selector_idioma_nivel()
    c1, c2 = st.columns(2)
    if c1.button("Empezar", type="primary"):
        if not S.usuario.strip():
            st.error("Escribe tu nombre para comenzar.")
        else:
            S.modo, S.idioma, S.nivel = "solo", idioma, nivel
            S.jugadores, S.turno, S.ronda = [S.usuario.strip()], 0, 0
            S.frase = elegir_frase(idioma, nivel)
            S.n_audio += 1
            ir("jugar")
    if c2.button("← Volver"):
        ir("inicio")

elif S.vista == "cfg_local":
    encabezado("👥 Partida local")
    st.caption("Todos juegan en este mismo dispositivo, por turnos.")
    n = st.segmented_control("Jugadores", [2, 3, 4, 5, 6], default=2, key="cfg_n") or 2
    nombres = [st.text_input(f"Jugador {i + 1}", value=f"Jugador {i + 1}", key=f"jug_{i}")
               for i in range(n)]
    rondas = st.segmented_control("Rondas", [3, 5], default=3, key="cfg_rondas") or 3
    idioma, nivel = selector_idioma_nivel()
    c1, c2 = st.columns(2)
    if c1.button("Empezar partida", type="primary"):
        limpios, vistos = [], {}
        for i, nom in enumerate(nombres):
            nom = nom.strip() or f"Jugador {i + 1}"
            vistos[nom] = vistos.get(nom, 0) + 1
            limpios.append(nom if vistos[nom] == 1 else f"{nom} ({vistos[nom]})")
        S.modo, S.idioma, S.nivel = "local", idioma, nivel
        S.jugadores, S.turno, S.ronda, S.rondas_total = limpios, 0, 0, rondas
        S.frases = random.sample(TEXTOS[idioma][nivel], k=rondas)
        S.puntajes = {j: [] for j in limpios}
        S.n_audio += 1
        ir("jugar")
    if c2.button("← Volver"):
        ir("inicio")

elif S.vista == "jugar":
    jugador = S.jugadores[S.turno]
    chips = f'<span class="chip">{S.idioma}</span><span class="chip">{S.nivel}</span>'
    if S.modo == "local":
        chips += f'<span class="chip">Ronda {S.ronda + 1}/{S.rondas_total}</span>'
        st.markdown(f"### Turno de {html.escape(jugador)}")
    else:
        st.markdown(f"### Hola, {html.escape(jugador)}")
    st.markdown(chips, unsafe_allow_html=True)

    st.markdown(f'<div class="tarjeta"><div class="frase">{html.escape(frase_actual())}</div></div>',
                unsafe_allow_html=True)
    audio = st.audio_input("Toca el micrófono, lee la frase y toca de nuevo para parar",
                           key=f"audio_{S.n_audio}")
    with st.expander("¿No funciona el micrófono? Escribe lo que leíste"):
        manual = st.text_area("Texto", label_visibility="collapsed", key=f"manual_{S.n_audio}")

    if st.button("Evaluar", type="primary"):
        if audio is None and not manual.strip():
            st.warning("Graba tu lectura primero.")
        else:
            try:
                with st.spinner("Analizando tu lectura…"):
                    dicho = manual.strip() if audio is None else transcribir(audio.getvalue(), S.idioma)
            except ImportError as e:
                if S.idioma == "Guaraní":
                    st.error("El guaraní necesita las librerías transformers y torch "
                             "(revisa requirements.txt). Prueba con español o inglés.")
                else:
                    st.error(f"Falta instalar una librería: {e}. Revisa requirements.txt.")
                st.stop()
            except Exception as e:
                st.error(f"No se pudo analizar el audio: {e}")
                st.stop()
            palabras, puntaje, extras = evaluar(frase_actual(), dicho, UMBRALES[S.nivel])
            S.resultado = dict(palabras=palabras, puntaje=puntaje, dicho=dicho,
                               extras=extras, jugador=jugador)
            guardar_puntaje(jugador, S.idioma, S.nivel, puntaje)
            if S.modo == "local":
                S.puntajes[jugador].append(puntaje)
            ir("resultado")

    if S.modo == "solo":
        c1, c2 = st.columns(2)
        if c1.button("Otra frase"):
            S.frase = elegir_frase(S.idioma, S.nivel)
            S.n_audio += 1
            st.rerun()
        if c2.button("← Menú"):
            ir("inicio")
    elif st.button("Salir de la partida"):
        ir("inicio")

elif S.vista == "resultado":
    r = S.resultado
    st.markdown(f"### {html.escape(r['jugador'])}")
    st.metric("Acierto", f"{r['puntaje']}%")
    aviso, texto = mensaje(r["puntaje"])
    aviso(texto)

    st.markdown(f'<div class="tarjeta"><div class="frase">{pintar(r["palabras"])}</div></div>',
                unsafe_allow_html=True)
    st.markdown('<div class="leyenda"><span class="w salto">salteó / abrevió</span> '
                '<span class="w mal">dijo mal</span></div>', unsafe_allow_html=True)
    if r["extras"]:
        st.caption(f"Agregaste {r['extras']} palabra(s) que no estaban en el texto.")
    with st.expander("Lo que entendió la IA"):
        st.write(r["dicho"] or "(no se escuchó nada)")

    if S.modo == "solo":
        c1, c2 = st.columns(2)
        if c1.button("🔄 Repetir esta frase"):
            S.n_audio += 1
            ir("jugar")
        if c2.button("➡️ Siguiente frase", type="primary"):
            S.frase = elegir_frase(S.idioma, S.nivel)
            S.n_audio += 1
            ir("jugar")
        if st.button("🏠 Menú"):
            ir("inicio")
    else:
        ultimo = S.turno == len(S.jugadores) - 1 and S.ronda == S.rondas_total - 1
        if st.button("🏁 Ver resultados" if ultimo else "Continuar ➡️", type="primary"):
            S.n_audio += 1
            S.turno += 1
            if S.turno >= len(S.jugadores):
                S.turno, S.ronda = 0, S.ronda + 1
            ir("final" if S.ronda >= S.rondas_total else "jugar")

elif S.vista == "final":
    encabezado("🏁 Resultados")
    tabla = sorted(((sum(p) / len(p) if p else 0, j) for j, p in S.puntajes.items()),
                   reverse=True)
    medallas = ["🥇", "🥈", "🥉"]
    for i, (prom, j) in enumerate(tabla):
        m = medallas[i] if i < 3 else f"#{i + 1}"
        st.markdown(f'<div class="tarjeta"><b>{m} {html.escape(j)}</b> — {prom:.1f}%</div>',
                    unsafe_allow_html=True)
    if tabla:
        st.success(f"¡Ganó {tabla[0][1]}! 🎉")
    c1, c2 = st.columns(2)
    if c1.button("🔄 Jugar de nuevo", type="primary"):
        ir("cfg_local")
    if c2.button("🏠 Menú"):
        ir("inicio")

else:
    ir("inicio")
