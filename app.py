import streamlit as st
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

# Configuração da página
st.set_page_config(page_title="Monitor de Passagens", page_icon="🚌")

# Conexão com Banco
def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

st.title("🚌 Controle do Monitor de Passagens")

# Formulário
with st.form("config_form"):
    st.write("### Parâmetros da Viagem")
    
    col1, col2 = st.columns(2)
    with col1:
        data_input = st.text_input("Data (DDMMAAAA)", value="10022026")
        origem = st.text_input("ID Origem", value="14245")
    with col2:
        adultos = st.number_input("Adultos", min_value=1, value=2)
        criancas = st.number_input("Crianças (até 5 anos)", min_value=0, value=0)
        adolescentes = 0
        destino = st.text_input("ID Destino", value="14199")
    
    st.write("### Filtro de Horário")
    horas_txt = st.text_input("Horas de Partida (separar por vírgula)", value="22,23,0,1")
    st.caption("Exemplo: Digite '23,0' para monitorar qualquer ônibus saindo às 23h ou 00h.")
    
    submitted = st.form_submit_button("💾 Salvar Configuração")
    
    if submitted:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            # Atualiza sempre o registro ID=1
            query = """
                UPDATE search_config 
                SET travel_date=%s, origin_id=%s, destiny_id=%s, adults=%s, children=%s, teens=%s, target_hours=%s
                WHERE id=1;
            """
            cur.execute(query, (data_input, origem, destino, adultos, criancas, adolescentes, horas_txt))
            conn.commit()
            conn.close()
            st.success("Configuração atualizada com sucesso! O robô usará esses dados na próxima rodada.")
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")

# Mostrar dados atuais
st.divider()
st.write("🔍 **Configuração Atual no Banco:**")
try:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM search_config WHERE id=1")
    row = cur.fetchone()
    conn.close()
    
    if row:
        st.json({
            "Data": row[1],
            "Origem": row[2],
            "Destino": row[3],
            "Adultos": row[4],
            "Criancas": row[5],
            "Adolescentes": row[6],
            "Horas Alvo": row[7]
        })
except:
    st.warning("Não foi possível ler o banco.")