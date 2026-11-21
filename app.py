import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from streamlit_gsheets import GSheetsConnection

# Configuração da página
st.set_page_config(page_title="Portal de Expedição", layout="centered")
st.title("🚚 Portal de Expedição - Motoristas")

# Gera automaticamente o nome da aba no padrão "dia/mês - AM" (fuso horário de Brasília/SP)
fuso_sp = ZoneInfo("America/Sao_Paulo")
aba_hoje = datetime.now(fuso_sp).strftime("%d/%m - AM")

# Campo no topo já preenchido com a data de hoje, mas editável caso precise abrir outro dia
aba_planilha = st.text_input("📅 Aba da expedição (padrão dia/mês - AM):", value=aba_hoje).strip()

# Conectando ao Google Sheets usando [connections.gsheets] dos Secrets
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(nome_aba):
    df_lido = conn.read(worksheet=nome_aba, ttl=0)
    df_lido.columns = df_lido.columns.astype(str).str.strip()
    return df_lido

try:
    df = carregar_dados(aba_planilha)
except Exception as e:
    st.error(f"Não foi possível abrir a aba **'{aba_planilha}'**. Verifique se ela já foi criada na planilha.")
    st.stop()

# Verifica se a coluna 'ID' existe
if 'ID' not in df.columns:
    st.error(f"Coluna 'ID' não encontrada na aba '{aba_planilha}'.")
    st.write("Colunas encontradas:", list(df.columns))
    st.stop()

# Limpa a coluna ID (remove '.0' caso o Google Sheets envie como número decimal e trata vazios)
df['ID'] = df['ID'].fillna('').astype(str).str.replace(r'\.0$', '', regex=True).str.strip()

# Remove linhas em branco da planilha (onde AT está vazio)
df['AT'] = df['AT'].fillna('').astype(str).str.strip()
df_valido = df[df['AT'] != ''].copy()

# Filtra apenas rotas sem ID preenchido
df_disponiveis = df_valido[df_valido['ID'].isin(['', 'nan', 'None', '<NA>'])]

if df_disponiveis.empty:
    st.info(f"Nenhuma rota disponível na aba '{aba_planilha}'. Todas já foram atribuídas!")
else:
    st.subheader(f"Rotas Disponíveis ({len(df_disponiveis)})")
    
    # Colunas da sua base que serão mostradas ao motorista
    colunas_visiveis = ['AT', 'GAIOLA', 'Veiculo', 'CLUSTER', 'BAIRRO']
    colunas_existentes = [col for col in colunas_visiveis if col in df_disponiveis.columns]
    
    st.dataframe(df_disponiveis[colunas_existentes], use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Solicitar Rota")
    
    with st.form("form_solicitacao"):
        motorista_id = st.text_input("Digite o seu ID:")
        tipo_veiculo = st.selectbox("Qual o seu veículo?", ["PASSEIO", "FIORINO", "VAN", "CAMINHÃO"])
        
        opcoes_display = [
            f"{row['AT']} | Gaiola: {row.get('GAIOLA', '')} ({row.get('Veiculo', '')})"
            for _, row in df_disponiveis.iterrows()
        ]
        mapa_opcoes = dict(zip(opcoes_display, df_disponiveis['AT'].tolist()))
        
        escolha_display = st.selectbox("Selecione a rota:", opcoes_display)
        rota_escolhida = mapa_opcoes[escolha_display]
        
        submit = st.form_submit_button("Confirmar Solicitação")
        
        if submit:
            id_limpo = motorista_id.strip()
            if not id_limpo:
                st.warning("Por favor, preencha o seu ID.")
            else:
                # Releitura em tempo real (ttl=0) antes de gravar para evitar conflitos
                df_atualizado = carregar_dados(aba_planilha)
                df_atualizado['ID'] = df_atualizado['ID'].fillna('').astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                df_atualizado['AT'] = df_atualizado['AT'].fillna('').astype(str).str.strip()
                
                idx_rota = df_atualizado[df_atualizado['AT'] == rota_escolhida].index[0]
                id_atual = df_atualizado.at[idx_rota, 'ID']
                
                if id_atual in ['', 'nan', 'None', '<NA>']:
                    veiculo_rota = str(df_atualizado.at[idx_rota, 'Veiculo']).strip().upper()
                    
                    if veiculo_rota == 'FIORINO' and tipo_veiculo != 'FIORINO':
                        st.error(f"Esta rota exige veículo FIORINO. Você selecionou {tipo_veiculo}.")
                    else:
                        # Atribui o ID na linha correspondente
                        df_atualizado.at[idx_rota, 'ID'] = id_limpo
                        
                        # Salva de volta na aba do dia no Google Sheets
                        conn.update(worksheet=aba_planilha, data=df_atualizado)
                        
                        st.success(f"Sucesso! A rota {rota_escolhida} foi atribuída ao ID {id_limpo}.")
                        st.rerun()
                else:
                    st.error("Poxa, outro motorista acabou de pegar essa rota! Tente outra.")
                    st.rerun()
