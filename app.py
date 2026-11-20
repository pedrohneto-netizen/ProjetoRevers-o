import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

# Configuração da página
st.set_page_config(page_title="Portal de Expedição", layout="centered")
st.title("🚚 Portal de Expedição - Motoristas")

# Conectando ao Google Sheets
# Lembre-se de configurar os secrets no Streamlit (.streamlit/secrets.toml)
conn = st.connection("gsheets", type=GSheetsConnection)

# Lendo os dados da aba específica
aba_planilha = "Plano de expedição"
df = conn.read(worksheet=aba_planilha)

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
    
    # Exibir tabela para os motoristas (Ajuste as colunas conforme sua necessidade)
    # Pela sua planilha, algumas colunas interessantes são: AT, GAIOLA, Zipcode, CEP, Veiculo, CLUSTER
    colunas_visiveis = ['AT', 'GAIOLA', 'Veiculo', 'CLUSTER']
    colunas_existentes = [col for col in colunas_visiveis if col in df_disponiveis.columns]
    
    st.dataframe(df_disponiveis[colunas_existentes], use_container_width=True)

    st.divider()
    st.subheader("Solicitar Rota")
    
    # Formulário para o motorista preencher
    with st.form("form_solicitacao"):
        motorista_id = st.text_input("Digite o seu ID:")
        tipo_veiculo = st.selectbox("Qual o seu veículo?", ["PASSEIO", "FIORINO", "VAN", "CAMINHÃO"])
        
        # Opções de rotas baseadas na disponibilidade
        opcoes_rotas = df_disponiveis['AT'].tolist() if 'AT' in df_disponiveis.columns else df_disponiveis.index.tolist()
        rota_escolhida = st.selectbox("Selecione a rota (AT):", opcoes_rotas)
        
        submit = st.form_submit_button("Confirmar Solicitação")
        
        if submit:
            if not motorista_id:
                st.warning("Por favor, preencha o seu ID.")
            else:
                # Localizar o índice da rota selecionada
                if 'AT' in df.columns:
                    idx_rota = df[df['AT'] == rota_escolhida].index[0]
                else:
                    idx_rota = rota_escolhida
                
                # Validação de concorrência: verifica se a rota AINDA está vazia direto no df lido agora
                # Em um ambiente com muitos acessos simultâneos, o ideal é reler a base antes de gravar
                df_atualizado = conn.read(worksheet=aba_planilha)
                id_atual = str(df_atualizado.at[idx_rota, 'ID']).strip()
                
                if id_atual == '' or id_atual == 'nan':
                    # Lógica de priorização simples: se a rota pede Fiorino e o motorista tem Passeio, podemos alertar
                    veiculo_rota = str(df_atualizado.at[idx_rota, 'Veiculo']).strip().upper()
                    
                    if veiculo_rota == 'FIORINO' and tipo_veiculo != 'FIORINO':
                        st.error(f"Esta rota tem prioridade/exigência para FIORINO. Seu veículo é {tipo_veiculo}.")
                    else:
                        # Preenche o ID do motorista na linha correspondente
                        df_atualizado.at[idx_rota, 'ID'] = motorista_id
                        
                        # Atualiza a planilha do Google
                        conn.update(worksheet=aba_planilha, data=df_atualizado)
                        
                        st.success(f"Sucesso! A rota {rota_escolhida} foi atribuída ao ID {motorista_id}.")
                        st.rerun() # Recarrega a página para atualizar a tabela
                else:
                    st.error("Poxa, outro motorista acabou de pegar essa rota! Tente outra.")
                    st.rerun()
