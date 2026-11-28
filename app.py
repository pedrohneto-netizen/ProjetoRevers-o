import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
from streamlit_gsheets import GSheetsConnection

# ==============================================================================
# CONFIGURAÇÃO DA PÁGINA E ESTILO (HTML / CSS)
# ==============================================================================
st.set_page_config(
    page_title="Portal de Expedição",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
        .block-container {
            max-width: 1080px;
            padding-top: 1.5rem;
            padding-bottom: 3rem;
        }
        .portal-header {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            color: #f8fafc;
            padding: 1.25rem 1.5rem;
            border-radius: 14px;
            border: 1px solid rgba(148, 163, 184, 0.2);
            margin-bottom: 1rem;
            box-shadow: 0 6px 18px rgba(15, 23, 42, 0.08);
        }
        .portal-header h1 {
            margin: 0;
            font-size: 1.6rem;
            font-weight: 700;
            letter-spacing: -0.02em;
        }
        .portal-header p {
            margin: 0.35rem 0 0 0;
            color: #cbd5e1;
            font-size: 0.92rem;
        }
        .rota-card {
            background-color: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 1rem 1.1rem;
            margin-bottom: 0.5rem;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
            transition: transform 0.12s ease, border-color 0.12s ease;
        }
        .rota-card:hover {
            border-color: #94a3b8;
        }
        .rota-card.incompativel {
            background-color: #f8fafc;
            opacity: 0.78;
        }
        .rota-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 0.55rem;
        }
        .gaiola-badge {
            font-weight: 700;
            font-size: 1.02rem;
            color: #0f172a;
        }
        .veic-badge {
            font-size: 0.76rem;
            font-weight: 700;
            padding: 0.22rem 0.6rem;
            border-radius: 999px;
            background-color: #e0f2fe;
            color: #0369a1;
            text-transform: uppercase;
        }
        .veic-badge.bloqueado {
            background-color: #fee2e2;
            color: #b91c1c;
        }
        .rota-meta {
            font-size: 0.88rem;
            color: #334155;
            margin: 0.2rem 0;
            line-height: 1.35;
        }
        .rota-at {
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 0.8rem;
            color: #64748b;
            margin-top: 0.45rem;
        }
        .confirm-box {
            background: #ecfdf5;
            border: 1px solid #6ee7b7;
            color: #065f46;
            padding: 1.1rem 1.25rem;
            border-radius: 12px;
            margin: 0.75rem 0 1rem 0;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

conn = st.connection("gsheets", type=GSheetsConnection)
ABA_CONFIG = "CONFIG_ADMIN"
FUSO_SP = ZoneInfo("America/Sao_Paulo")
VALORES_VAZIOS = {"", "nan", "none", "<na>", "null"}
APPS_SCRIPT_URL_PADRAO = (
    "https://script.google.com/a/macros/shopee.com/s/"
    "AKfycbzdMfDbQR1D3lGLGhz9Pb4gCJ5Ca3MGDI8cMgcTWYqzq2GbRXrhejQ6-6vL0ngJJbU39Q/exec"
)


# ==============================================================================
# FUNÇÕES UTILITÁRIAS E DE NORMALIZAÇÃO
# ==============================================================================
def agora_sp() -> datetime:
    return datetime.now(FUSO_SP)


def sugerir_aba_padrao() -> str:
    return agora_sp().strftime("%d/%m - AM")


def limpar_texto(valor) -> str:
    if valor is None or pd.isna(valor):
        return ""
    texto = str(valor).strip()
    texto = re.sub(r"\.0$", "", texto)
    return "" if texto.lower() in VALORES_VAZIOS else texto


def normalizar_veiculo(valor) -> str:
    limpo = limpar_texto(valor).upper()
    if not limpo:
        return ""
    sem_acento = "".join(
        ch for ch in unicodedata.normalize("NFD", limpo) if unicodedata.category(ch) != "Mn"
    )
    mapa = {
        "PASSEIO": "PASSEIO",
        "CARRO": "PASSEIO",
        "FIORINO": "FIORINO",
        "FURGAO": "FIORINO",
        "VAN": "VAN",
        "CAMINHAO": "CAMINHÃO",
        "CAMINHAO BAU": "CAMINHÃO",
    }
    return mapa.get(sem_acento, limpo)


def verificar_compatibilidade(veiculo_motorista: str, veiculo_rota: str) -> bool:
    mot = normalizar_veiculo(veiculo_motorista)
    rota = normalizar_veiculo(veiculo_rota)
    hierarquia = {
        "PASSEIO": {"PASSEIO", ""},
        "FIORINO": {"FIORINO", "PASSEIO", ""},
        "VAN": {"VAN", "FIORINO", "PASSEIO", ""},
        "CAMINHÃO": {"CAMINHÃO", "VAN", "FIORINO", "PASSEIO", ""},
    }
    permitidos = hierarquia.get(mot, {mot, ""})
    return rota in permitidos


def normalizar_df_rotas(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.copy()
    df.columns = df.columns.astype(str).str.strip()

    for col_obrigatoria in ["AT", "ID"]:
        if col_obrigatoria not in df.columns:
            df[col_obrigatoria] = ""

    if "Veiculo" not in df.columns and "VEICULO" in df.columns:
        df["Veiculo"] = df["VEICULO"]
    elif "Veiculo" not in df.columns:
        df["Veiculo"] = ""

    df["AT"] = df["AT"].apply(limpar_texto)
    df["ID"] = df["ID"].apply(limpar_texto)
    df["Veiculo"] = df["Veiculo"].apply(normalizar_veiculo)

    if "GAIOLA" in df.columns:
        df["GAIOLA"] = df["GAIOLA"].apply(limpar_texto)
    if "TELEFONE" in df.columns:
        df["TELEFONE"] = df["TELEFONE"].apply(limpar_texto)
    if "ATRIBUIDO_EM" in df.columns:
        df["ATRIBUIDO_EM"] = df["ATRIBUIDO_EM"].apply(limpar_texto)

    return df


def gerar_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def obter_apps_script_url() -> str:
    try:
        cfg_url = limpar_texto(st.secrets.get("apps_script_url", ""))
        return cfg_url or APPS_SCRIPT_URL_PADRAO
    except Exception:
        return APPS_SCRIPT_URL_PADRAO


# ==============================================================================
# FUNÇÕES DE LEITURA E GRAVAÇÃO (GOOGLE SHEETS + APPS SCRIPT)
# ==============================================================================
def ler_configuracao():
    aba_padrao = sugerir_aba_padrao()
    try:
        df_cfg = conn.read(worksheet=ABA_CONFIG, ttl=0)
        if df_cfg is None or df_cfg.empty:
            return aba_padrao, False, []

        df_cfg.columns = df_cfg.columns.astype(str).str.strip()
        aba_ativa = limpar_texto(df_cfg.at[0, "aba_ativa"]) if "aba_ativa" in df_cfg.columns else ""
        liberado = (
            limpar_texto(df_cfg.at[0, "portal_liberado"]).upper() == "SIM"
            if "portal_liberado" in df_cfg.columns
            else False
        )
        bloq_raw = (
            limpar_texto(df_cfg.at[0, "gaiolas_bloqueadas"])
            if "gaiolas_bloqueadas" in df_cfg.columns
            else ""
        )
        bloqueadas = sorted({g.strip() for g in bloq_raw.split(",") if limpar_texto(g)})
        return aba_ativa or aba_padrao, liberado, bloqueadas
    except Exception:
        return aba_padrao, False, []


def salvar_configuracao(aba_ativa: str, portal_liberado: bool, lista_bloqueadas: list[str]):
    aba_limpa = limpar_texto(aba_ativa) or sugerir_aba_padrao()
    bloqueadas_limpas = sorted({limpar_texto(g) for g in lista_bloqueadas if limpar_texto(g)})
    timestamp_str = agora_sp().strftime("%d/%m/%Y %H:%M:%S")

    try:
        df_atual = conn.read(worksheet=ABA_CONFIG, ttl=0)
        if df_atual is None or not isinstance(df_atual, pd.DataFrame):
            df_atual = pd.DataFrame()
    except Exception:
        df_atual = pd.DataFrame()

    if df_atual.empty:
        df_nova_cfg = pd.DataFrame(
            [
                {
                    "aba_ativa": aba_limpa,
                    "portal_liberado": "SIM" if portal_liberado else "NAO",
                    "gaiolas_bloqueadas": ",".join(bloqueadas_limpas),
                    "atualizado_em": timestamp_str,
                }
            ]
        )
    else:
        df_nova_cfg = df_atual.copy()
        df_nova_cfg.at[0, "aba_ativa"] = aba_limpa
        df_nova_cfg.at[0, "portal_liberado"] = "SIM" if portal_liberado else "NAO"
        df_nova_cfg.at[0, "gaiolas_bloqueadas"] = ",".join(bloqueadas_limpas)
        df_nova_cfg["atualizado_em"] = timestamp_str

    conn.update(worksheet=ABA_CONFIG, data=df_nova_cfg)


def carregar_dados_rotas(nome_aba: str) -> pd.DataFrame:
    df_lido = conn.read(worksheet=nome_aba, ttl=0)
    if df_lido is None or df_lido.empty:
        return pd.DataFrame(
            columns=["GAIOLA", "AT", "Veiculo", "CLUSTER", "BAIRRO", "ID", "TELEFONE", "ATRIBUIDO_EM"]
        )
    return normalizar_df_rotas(df_lido)


def liberar_rota_admin(nome_aba: str, at_alvo: str, id_esperado: str = "") -> tuple[bool, str]:
    df_atual = carregar_dados_rotas(nome_aba)
    matches = df_atual.index[df_atual["AT"] == at_alvo].tolist()
    if not matches:
        return False, f"AT '{at_alvo}' não encontrada na aba '{nome_aba}'."

    alterou = False
    for idx in matches:
        id_atual = df_atual.at[idx, "ID"]
        if id_esperado and id_atual != id_esperado:
            continue
        df_atual.at[idx, "ID"] = ""
        if "TELEFONE" in df_atual.columns:
            df_atual.at[idx, "TELEFONE"] = ""
        if "ATRIBUIDO_EM" in df_atual.columns:
            df_atual.at[idx, "ATRIBUIDO_EM"] = ""
        alterou = True

    if not alterou:
        return False, "Nenhuma linha correspondente encontrada para liberação."

    conn.update(worksheet=nome_aba, data=df_atual)
    return True, f"Rota {at_alvo} liberada e disponível novamente."


def atribuir_via_apps_script(
    url: str,
    nome_aba: str,
    rotas_preferencia: list[str],
    motorista_id: str,
    veiculo_motorista: str,
    telefone_motorista: str,
):
    payload = {
        "aba": nome_aba,
        "id": motorista_id,
        "veiculo": veiculo_motorista,
        "telefone": telefone_motorista,
        "preferencias": rotas_preferencia,
    }

    resp = requests.post(url, json=payload, timeout=20)
    resp.raise_for_status()

    try:
        data = resp.json()
    except ValueError as exc:
        raise RuntimeError(
            "O Apps Script respondeu em formato não-JSON (verifique se a implantação permite acesso sem login)."
        ) from exc

    if data.get("ok"):
        return (
            "atribuida",
            "Solicitação confirmada com sucesso!",
            {
                "gaiola": limpar_texto(data.get("gaiola")) or "Sem Gaiola",
                "at": limpar_texto(data.get("at")) or rotas_preferencia[0],
                "veiculo": limpar_texto(data.get("veiculo")) or veiculo_motorista,
            },
        )

    motivo = limpar_texto(data.get("motivo")).lower()
    if motivo == "ja_possui":
        return (
            "ja_possui",
            "Este ID já possui uma rota atribuída nesta expedição.",
            {
                "gaiola": limpar_texto(data.get("gaiola")) or "N/A",
                "at": limpar_texto(data.get("at")) or "N/A",
            },
        )

    return (
        "indisponivel",
        "As opções selecionadas já foram preenchidas ou não são compatíveis com o seu veículo. Atualize suas escolhas.",
        {},
    )


def atribuir_rota_segura(
    nome_aba: str,
    rotas_preferencia: list[str],
    motorista_id: str,
    veiculo_motorista: str,
    telefone_motorista: str,
):
    script_url = obter_apps_script_url()
    if script_url:
        return atribuir_via_apps_script(
            url=script_url,
            nome_aba=nome_aba,
            rotas_preferencia=rotas_preferencia,
            motorista_id=motorista_id,
            veiculo_motorista=veiculo_motorista,
            telefone_motorista=telefone_motorista,
        )

    df_atual = carregar_dados_rotas(nome_aba)

    existente = df_atual[df_atual["ID"] == motorista_id]
    if not existente.empty:
        row_ex = existente.iloc[0]
        return (
            "ja_possui",
            "Este ID já possui uma rota atribuída nesta expedição.",
            {
                "gaiola": row_ex.get("GAIOLA", "N/A") or "N/A",
                "at": row_ex.get("AT", "N/A") or "N/A",
            },
        )

    for at_escolhida in rotas_preferencia:
        matches = df_atual.index[df_atual["AT"] == at_escolhida].tolist()
        for idx in matches:
            id_na_planilha = df_atual.at[idx, "ID"]
            veic_na_planilha = df_atual.at[idx, "Veiculo"]
            gaiola_na_planilha = (
                df_atual.at[idx, "GAIOLA"] if "GAIOLA" in df_atual.columns else "Sem Gaiola"
            )

            if id_na_planilha == "" and verificar_compatibilidade(veiculo_motorista, veic_na_planilha):
                df_atual.at[idx, "ID"] = motorista_id
                if "TELEFONE" in df_atual.columns and limpar_texto(df_atual.at[idx, "TELEFONE"]) == "":
                    df_atual.at[idx, "TELEFONE"] = telefone_motorista
                if "ATRIBUIDO_EM" in df_atual.columns:
                    df_atual.at[idx, "ATRIBUIDO_EM"] = agora_sp().strftime("%d/%m/%Y %H:%M:%S")

                conn.update(worksheet=nome_aba, data=df_atual)
                return (
                    "atribuida",
                    "Solicitação confirmada com sucesso!",
                    {
                        "gaiola": gaiola_na_planilha or "Sem Gaiola",
                        "at": at_escolhida,
                        "veiculo": veic_na_planilha or "PADRÃO",
                    },
                )

    return (
        "indisponivel",
        "As opções selecionadas já foram preenchidas ou não são compatíveis com o seu veículo. Atualize suas escolhas.",
        {},
    )


# ==============================================================================
# ESTADO DE SESSÃO
# ==============================================================================
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False
if "mostrar_login_admin" not in st.session_state:
    st.session_state.mostrar_login_admin = False
if "motorista_cadastrado" not in st.session_state:
    st.session_state.motorista_cadastrado = False
    st.session_state.dados_motorista = {}
if "ultimo_resultado" not in st.session_state:
    st.session_state.ultimo_resultado = None


# ==============================================================================
# CABEÇALHO PRINCIPAL
# ==============================================================================
aba_planilha, portal_liberado, gaiolas_bloqueadas = ler_configuracao()

col_head, col_action = st.columns([4.5, 1.2], vertical_alignment="center")
with col_head:
    status_badge = "🟢 LIBERADO" if portal_liberado else "🔴 AGUARDANDO LIBERAÇÃO"
    st.markdown(
        f"""
        <div class="portal-header">
            <h1>🚚 Portal de Expedição</h1>
            <p>Expedição ativa: <strong>{aba_planilha}</strong> &nbsp;•&nbsp; Status: <strong>{status_badge}</strong></p>
        </div>
        """,
        unsafe_allow_html=True,
    )
with col_action:
    if not st.session_state.is_admin:
        if st.button("🔒 Admin", use_container_width=True):
            st.session_state.mostrar_login_admin = not st.session_state.mostrar_login_admin
    else:
        if st.button("🚪 Sair Admin", use_container_width=True):
            st.session_state.is_admin = False
            st.session_state.mostrar_login_admin = False
            st.rerun()


# ==============================================================================
# LOGIN DO ADMINISTRADOR
# ==============================================================================
if st.session_state.mostrar_login_admin and not st.session_state.is_admin:
    with st.container(border=True):
        st.subheader("Acesso Restrito — Administrador")
        with st.form("form_login_admin"):
            senha_digitada = st.text_input("Senha de administrador:", type="password")
            entrar_btn = st.form_submit_button("Entrar no Painel", type="primary")
            if entrar_btn:
                senha_correta = st.secrets.get("admin_password", "admin123")
                if senha_digitada and senha_digitada == senha_correta:
                    st.session_state.is_admin = True
                    st.session_state.mostrar_login_admin = False
                    st.rerun()
                else:
                    st.error("Senha incorreta.")


# ==============================================================================
# MODO ADMINISTRADOR
# ==============================================================================
if st.session_state.is_admin:
    st.success("🔓 **Modo Administrador Ativo**")

    with st.container(border=True):
        st.subheader("⚙️ Controle Geral de Liberação")
        col_a, col_b = st.columns([2.5, 1.2], vertical_alignment="center")
        with col_a:
            nova_aba = st.text_input(
                "Nome da Aba da Expedição:",
                value=aba_planilha,
                help=f"Sugestão para hoje: {sugerir_aba_padrao()}",
            )
        with col_b:
            status_toggle = st.toggle("🟢 Liberar Rotas para Motoristas", value=portal_liberado)

        df_admin = None
        gaiolas_disponiveis_aba = []
        try:
            df_admin = carregar_dados_rotas(nova_aba)
            df_admin = df_admin[df_admin["AT"] != ""].copy()
            if "GAIOLA" in df_admin.columns:
                gaiolas_disponiveis_aba = sorted({g for g in df_admin["GAIOLA"].tolist() if g})
        except Exception as exc:
            st.warning(f"⚠️ Não foi possível carregar a aba **'{nova_aba}'**: {exc}")

        default_bloqueadas = [g for g in gaiolas_bloqueadas if g in gaiolas_disponiveis_aba]
        novas_bloqueadas = st.multiselect(
            "Ocultar gaiolas específicas (opcional — deixe vazio para exibir todas):",
            options=gaiolas_disponiveis_aba,
            default=default_bloqueadas,
        )

        if st.button("💾 Salvar Configurações", type="primary", use_container_width=True):
            try:
                salvar_configuracao(nova_aba, status_toggle, novas_bloqueadas)
                st.success("✅ Configurações salvas na planilha com sucesso!")
                st.rerun()
            except Exception as exc:
                st.error(f"Erro ao salvar na aba '{ABA_CONFIG}': {exc}")

    if df_admin is not None:
        st.divider()
        col_titulo_admin, col_exp = st.columns([3.5, 1.5], vertical_alignment="center")
        with col_titulo_admin:
            st.subheader(f"📊 Acompanhamento em Tempo Real — {nova_aba}")
        with col_exp:
            nome_arquivo_csv = f"expedicao_{re.sub(r'[^a-zA-Z0-9_-]+', '_', nova_aba)}.csv"
            st.download_button(
                label="📥 Exportar CSV",
                data=gerar_csv_bytes(df_admin),
                file_name=nome_arquivo_csv,
                mime="text/csv",
                use_container_width=True,
            )

        total_rotas = len(df_admin)
        atribuidas = int((df_admin["ID"] != "").sum())
        livres = total_rotas - atribuidas
        ocupacao = int((atribuidas / total_rotas) * 100) if total_rotas > 0 else 0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total de Rotas", total_rotas)
        m2.metric("Atribuídas", atribuidas)
        m3.metric("Disponíveis", livres)
        m4.metric("Ocupação", f"{ocupacao}%")

        filtro_status = st.radio(
            "Filtrar visualização:",
            ["Todas", "Disponíveis", "Atribuídas"],
            horizontal=True,
        )

        df_view = df_admin.copy()
        if filtro_status == "Disponíveis":
            df_view = df_view[df_view["ID"] == ""]
        elif filtro_status == "Atribuídas":
            df_view = df_view[df_view["ID"] != ""]

        colunas_monitor = [
            c
            for c in [
                "GAIOLA",
                "AT",
                "Veiculo",
                "CLUSTER",
                "BAIRRO",
                "ID",
                "TELEFONE",
                "ATRIBUIDO_EM",
            ]
            if c in df_view.columns
        ]
        st.dataframe(df_view[colunas_monitor], use_container_width=True, hide_index=True)

        df_atribuidas = df_admin[df_admin["ID"] != ""].copy()
        if not df_atribuidas.empty:
            with st.container(border=True):
                st.subheader("♻️ Liberar / Reabrir Rota Atribuída")
                st.caption(
                    "Use esta função caso o motorista desista ou precise que a rota volte para disponível."
                )

                opcoes_rotas = []
                mapa_opcoes = {}
                for _, r in df_atribuidas.iterrows():
                    at_cod = r["AT"]
                    id_mot = r["ID"]
                    gai_cod = r.get("GAIOLA", "") or "Sem Gaiola"
                    label = f"{at_cod} — Gaiola {gai_cod} (ID: {id_mot})"
                    opcoes_rotas.append(label)
                    mapa_opcoes[label] = (at_cod, id_mot)

                escolha_lib = st.selectbox(
                    "Selecione a rota atribuída para liberar:",
                    options=opcoes_rotas,
                )
                confirmar_lib = st.checkbox("Confirmo que desejo devolver esta rota para disponível.")

                if st.button("🔓 Liberar Rota Selecionada", type="secondary"):
                    if not confirmar_lib:
                        st.warning("⚠️ Marque a caixa de confirmação antes de liberar a rota.")
                    else:
                        at_alvo, id_alvo = mapa_opcoes[escolha_lib]
                        with st.spinner(f"Liberando rota {at_alvo}..."):
                            try:
                                ok, msg_lib = liberar_rota_admin(nova_aba, at_alvo, id_alvo)
                                if ok:
                                    st.success(f"✅ {msg_lib}")
                                    st.rerun()
                                else:
                                    st.error(f"❌ {msg_lib}")
                            except Exception as exc:
                                st.error(f"Erro ao liberar rota: {exc}")

    st.stop()


# ==============================================================================
# MODO MOTORISTA
# ==============================================================================
if not portal_liberado:
    st.warning(
        "⏳ **As rotas ainda não foram liberadas pela expedição.**\n\n"
        "Aguarde a liberação do administrador e atualize a página."
    )
    if st.button("🔄 Atualizar Status", use_container_width=True):
        st.rerun()
    st.stop()

if st.session_state.ultimo_resultado:
    res = st.session_state.ultimo_resultado
    if res.get("status") == "atribuida":
        det = res.get("detalhes", {})
        st.markdown(
            f"""
            <div class="confirm-box">
                <strong>🎉 Rota confirmada com sucesso!</strong><br>
                Gaiola: <strong>{det.get("gaiola", "N/A")}</strong> &nbsp;|&nbsp;
                AT: <strong>{det.get("at", "N/A")}</strong> &nbsp;|&nbsp;
                Veículo da rota: <strong>{det.get("veiculo", "PADRÃO")}</strong>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ETAPA 1: IDENTIFICAÇÃO DO MOTORISTA
if not st.session_state.motorista_cadastrado:
    st.subheader("1. Identificação do Motorista")
    st.caption("Informe seus dados para consultar as rotas liberadas compatíveis com o seu veículo.")

    with st.form("form_cadastro_motorista"):
        motorista_id = st.text_input("Seu ID (apenas números):", placeholder="Ex: 10452")
        tipo_veiculo = st.selectbox(
            "Tipo de Veículo:",
            ["PASSEIO", "FIORINO", "VAN", "CAMINHÃO"],
        )
        telefone = st.text_input("Telefone para contato (com DDD):", placeholder="Ex: 11999999999")

        btn_continuar = st.form_submit_button(
            "Ver Rotas Disponíveis",
            type="primary",
            use_container_width=True,
        )

        if btn_continuar:
            id_limpo = motorista_id.strip()
            tel_limpo = re.sub(r"\D", "", telefone)

            if not id_limpo or not tel_limpo:
                st.warning("⚠️ Preencha seu ID e um telefone válido com DDD.")
            elif not id_limpo.isdigit():
                st.warning("⚠️ O ID deve conter apenas números.")
            elif len(tel_limpo) < 10:
                st.warning("⚠️ Informe o telefone completo com DDD (mínimo de 10 dígitos).")
            else:
                st.session_state.dados_motorista = {
                    "id": id_limpo,
                    "veiculo": tipo_veiculo,
                    "telefone": tel_limpo,
                }
                st.session_state.motorista_cadastrado = True
                st.session_state.ultimo_resultado = None
                st.rerun()

# ETAPA 2: CONSULTA E SOLICITAÇÃO DE ROTA
else:
    dados_mot = st.session_state.dados_motorista

    col_info, col_alterar = st.columns([4, 1], vertical_alignment="center")
    with col_info:
        st.info(
            f"👤 **ID:** `{dados_mot['id']}` &nbsp;|&nbsp; "
            f"🚐 **Veículo:** `{dados_mot['veiculo']}` &nbsp;|&nbsp; "
            f"📞 **Telefone:** `{dados_mot['telefone']}`"
        )
    with col_alterar:
        if st.button("Alterar Dados", use_container_width=True):
            st.session_state.motorista_cadastrado = False
            st.session_state.ultimo_resultado = None
            st.rerun()

    try:
        df = carregar_dados_rotas(aba_planilha)
    except Exception:
        st.error(
            f"A planilha da expedição **{aba_planilha}** ainda não está disponível. Tente novamente em instantes."
        )
        st.stop()

    rota_existente = df[df["ID"] == dados_mot["id"]]
    if not rota_existente.empty:
        row_atual = rota_existente.iloc[0]
        gaiola_atual = row_atual.get("GAIOLA", "N/A") or "N/A"
        at_atual = row_atual.get("AT", "N/A") or "N/A"
        st.success(
            f"✅ Você já possui uma rota confirmada nesta expedição!\n\n"
            f"**Gaiola:** `{gaiola_atual}` &nbsp;|&nbsp; **Rota (AT):** `{at_atual}`"
        )
        st.stop()

    df_valido = df[df["AT"] != ""].copy()
    df_disponiveis = df_valido[df_valido["ID"] == ""].copy()

    if "GAIOLA" in df_disponiveis.columns and gaiolas_bloqueadas:
        df_disponiveis = df_disponiveis[~df_disponiveis["GAIOLA"].isin(gaiolas_bloqueadas)]

    if df_disponiveis.empty:
        st.warning("Nenhuma rota disponível no momento. Todas as gaiolas liberadas já foram preenchidas.")
        if st.button("🔄 Atualizar Rotas", use_container_width=True):
            st.rerun()
        st.stop()

    st.subheader(f"2. Selecione suas opções de rota ({len(df_disponiveis)} disponíveis)")
    st.caption(
        "Você pode marcar uma ou mais opções por ordem de preferência. "
        "O sistema atribuirá **apenas 1 rota** compatível com o seu veículo."
    )

    apenas_compativeis = st.checkbox("Mostrar apenas rotas compatíveis com meu veículo", value=False)

    rotas_para_exibir = []
    for _, row in df_disponiveis.iterrows():
        veic_req = normalizar_veiculo(row.get("Veiculo", ""))
        comp = verificar_compatibilidade(dados_mot["veiculo"], veic_req)
        if apenas_compativeis and not comp:
            continue
        rotas_para_exibir.append((row, veic_req, comp))

    if not rotas_para_exibir:
        st.info("Nenhuma rota compatível encontrada com o filtro ativo. Desmarque o filtro para ver todas.")
        st.stop()

    rotas_selecionadas = []
    cols = st.columns(2)

    for idx_card, (row, veic_req, compativel) in enumerate(rotas_para_exibir):
        at_codigo = row["AT"]
        gaiola = row.get("GAIOLA", "") or "Sem Gaiola"
        cluster = limpar_texto(row.get("CLUSTER", "")) or "-"
        bairro = limpar_texto(row.get("BAIRRO", "")) or "-"
        bairro_resumo = bairro[:70] + "..." if len(bairro) > 70 else bairro
        veic_label = veic_req or "QUALQUER"
        card_class = "rota-card" if compativel else "rota-card incompativel"
        badge_class = "veic-badge" if compativel else "veic-badge bloqueado"

        with cols[idx_card % 2]:
            st.markdown(
                f"""
                <div class="{card_class}">
                    <div class="rota-top">
                        <span class="gaiola-badge">📦 Gaiola {gaiola}</span>
                        <span class="{badge_class}">{veic_label}</span>
                    </div>
                    <div class="rota-meta"><strong>Cluster:</strong> {cluster}</div>
                    <div class="rota-meta"><strong>Bairro:</strong> {bairro_resumo}</div>
                    <div class="rota-at">🔑 AT: {at_codigo}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if compativel:
                selecionado = st.checkbox(
                    f"Selecionar Gaiola {gaiola} ({at_codigo})",
                    key=f"chk_{idx_card}_{at_codigo}",
                )
                if selecionado:
                    rotas_selecionadas.append(at_codigo)
            else:
                st.button(
                    f"Exige {veic_label}",
                    key=f"dis_{idx_card}_{at_codigo}",
                    disabled=True,
                    use_container_width=True,
                )

    st.divider()

    if rotas_selecionadas:
        st.caption(f"Opções marcadas: **{len(rotas_selecionadas)}** ({', '.join(rotas_selecionadas)})")

    if st.button("🚀 Enviar Solicitação", type="primary", use_container_width=True):
        if not rotas_selecionadas:
            st.warning("⚠️ Selecione pelo menos uma rota compatível antes de enviar.")
        else:
            with st.spinner("Verificando disponibilidade em tempo real e reservando rota..."):
                try:
                    status_res, msg_res, detalhes_res = atribuir_rota_segura(
                        nome_aba=aba_planilha,
                        rotas_preferencia=rotas_selecionadas,
                        motorista_id=dados_mot["id"],
                        veiculo_motorista=dados_mot["veiculo"],
                        telefone_motorista=dados_mot["telefone"],
                    )

                    if status_res == "atribuida":
                        st.session_state.ultimo_resultado = {
                            "status": "atribuida",
                            "detalhes": detalhes_res,
                        }
                        st.balloons()
                        st.rerun()
                    elif status_res == "ja_possui":
                        st.info(
                            f"ℹ️ {msg_res} "
                            f"(Gaiola: **{detalhes_res.get('gaiola')}** | AT: **{detalhes_res.get('at')}**)"
                        )
                    else:
                        st.error(f"😕 {msg_res}")
                        st.rerun()
                except Exception as exc:
                    st.error(f"Ocorreu um erro ao comunicar com a planilha: {exc}")
