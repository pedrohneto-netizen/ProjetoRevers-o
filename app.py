import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

# Configuração da página
st.set_page_config(page_title="Portal de Expedição", layout="centered")
st.title("🚚 Portal de Expedição - Motoristas")

# Conectando ao Google Sheets usando [connections.gsheets] dos Secrets
conn = st.connection("gsheets", type=GSheetsConnection)

# Nome exato da aba na planilha
aba_planilha = "Plano de expedição"

# ttl=0 garante leitura em tempo real sem cache desatualizado
df = conn.read(worksheet=aba_planilha, ttl=0)

# Garantir que a coluna ID seja tratada como string para facilitar o filtro
if 'ID' in df.columns:
    df['ID'] = df['ID'].fillna('').astype(str)
else:
    st.error("Coluna 'ID' não encontrada na planilha.")
    st.stop()

# Filtrando apenas rotas sem ID preenchido
df_disponiveis = df[df['ID'].str.strip() == '']

if df_disponiveis.empty:
    st.info("Nenhuma rota disponível no momento. Todas já foram atribuídas!")
else:
    st.subheader("Rotas Disponíveis")
    
    # Colunas visíveis para os motoristas
    colunas_visiveis = ['AT', 'GAIOLA', 'Veiculo', 'CLUSTER']
    colunas_existentes = [col for col in colunas_visiveis if col in df_disponiveis.columns]
    
    st.dataframe(df_disponiveis[colunas_existentes], use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Solicitar Rota")
    
    with st.form("form_solicitacao"):
        motorista_id = st.text_input("Digite o seu ID:")
        tipo_veiculo = st.selectbox("Qual o seu veículo?", ["PASSEIO", "FIORINO", "VAN", "CAMINHÃO"])
        
        opcoes_rotas = df_disponiveis['AT'].tolist() if 'AT' in df_disponiveis.columns else df_disponiveis.index.tolist()
        rota_escolhida = st.selectbox("Selecione a rota (AT):", opcoes_rotas)
        
        submit = st.form_submit_button("Confirmar Solicitação")
        
        if submit:
            if not motorista_id.strip():
                st.warning("Por favor, preencha o seu ID.")
            else:
                # Releitura em tempo real (ttl=0) antes de gravar para evitar conflitos
                df_atualizado = conn.read(worksheet=aba_planilha, ttl=0)
                df_atualizado['ID'] = df_atualizado['ID'].fillna('').astype(str)
                
                if 'AT' in df_atualizado.columns:
                    idx_rota = df_atualizado[df_atualizado['AT'] == rota_escolhida].index[0]
                else:
                    idx_rota = rota_escolhida
                
                id_atual = df_atualizado.at[idx_rota, 'ID'].strip()
                
                if id_atual == '' or id_atual.lower() == 'nan':
                    veiculo_rota = str(df_atualizado.at[idx_rota, 'Veiculo']).strip().upper() if 'Veiculo' in df_atualizado.columns else ''
                    
                    if veiculo_rota == 'FIORINO' and tipo_veiculo != 'FIORINO':
                        st.error(f"Esta rota tem prioridade/exigência para FIORINO. Seu veículo é {tipo_veiculo}.")
                    else:
                        df_atualizado.at[idx_rota, 'ID'] = motorista_id.strip()
                        conn.update(worksheet=aba_planilha, data=df_atualizado)
                        
                        st.success(f"Sucesso! A rota {rota_escolhida} foi atribuída ao ID {motorista_id}.")
                        st.rerun()
                else:
                    st.error("Poxa, outro motorista acabou de pegar essa rota! Tente outra.")
                    st.rerun()
