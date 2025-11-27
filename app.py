import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Panificadora ProfitOS", layout="wide")

# --- SISTEMA DE LOGIN SIMPLIFICADO ---
# Em produção real, usaríamos um banco de dados hash ou st-authenticator
USERS = {
    "admin": {"pass": "admin123", "role": "Master"},  # Você
    "socia": {"pass": "socia123", "role": "Master"},  # Sócia
    "func":  {"pass": "vendas1",  "role": "Staff"}    # Funcionários
}

def check_password():
    """Retorna True se o usuário estiver logado corretamente."""
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    
    if not st.session_state.logged_in:
        st.sidebar.title("🔐 Acesso Restrito")
        username = st.sidebar.text_input("Usuário")
        password = st.sidebar.text_input("Senha", type="password")
        if st.sidebar.button("Entrar"):
            if username in USERS and USERS[username]["pass"] == password:
                st.session_state.logged_in = True
                st.session_state.user_role = USERS[username]["role"]
                st.session_state.username = username
                st.rerun()
            else:
                st.sidebar.error("Senha incorreta")
        return False
    return True

if not check_password():
    st.stop()

# --- LÓGICA DE NEGÓCIO ---

def classificar_abc(df):
    """Gera classificação ABC baseada no Faturamento"""
    df = df.sort_values(by='Faturamento', ascending=False)
    df['Faturamento_Acumulado'] = df['Faturamento'].cumsum()
    df['Percentual_Acumulado'] = 100 * df['Faturamento_Acumulado'] / df['Faturamento'].sum()
    
    def get_class(x):
        if x <= 80: return 'A'
        elif x <= 95: return 'B'
        else: return 'C'
    
    df['Curva_ABC'] = df['Percentual_Acumulado'].apply(get_class)
    return df

def sugerir_combos(df):
    """
    IA Lógica: Cruza produtos de alta atratividade (Volumosos) 
    com produtos de alta margem (Lucrativos).
    """
    # Define "Alto Volume" como top 25% vendas
    limite_vendas = df['Qtd_Vendas'].quantile(0.75)
    # Define "Alta Margem" como top 25% margem
    limite_margem = df['Margem_R$'].quantile(0.75)

    iscas = df[df['Qtd_Vendas'] >= limite_vendas] # Produtos que trazem gente (Pão francês)
    lucrativos = df[(df['Margem_R$'] >= limite_margem) & (df['Qtd_Vendas'] < limite_vendas)] # Produtos para empurrar (Doces finos)
    
    sugestoes = []
    if not iscas.empty and not lucrativos.empty:
        # Pega a melhor isca e o melhor lucrativo
        isca = iscas.iloc[0]
        lucro = lucrativos.iloc[0]
        
        preco_original = isca['Preco_Venda'] + lucro['Preco_Venda']
        preco_combo = preco_original * 0.90 # 10% de desconto
        
        sugestoes.append({
            "Nome do Combo": f"Combo {isca['Produto']} + {lucro['Produto']}",
            "Isca (Chamariz)": isca['Produto'],
            "Lucrativo (Impulso)": lucro['Produto'],
            "Preço Original": f"R$ {preco_original:.2f}",
            "Preço Sugerido (Combo)": f"R$ {preco_combo:.2f}",
            "Motivo da IA": "Une alta rotatividade com alta margem."
        })
    return pd.DataFrame(sugestoes)

# --- INTERFACE DO USUÁRIO ---

st.sidebar.markdown(f"👤 Logado como: **{st.session_state.username.upper()}** ({st.session_state.user_role})")
if st.sidebar.button("Sair"):
    st.session_state.logged_in = False
    st.rerun()

st.title("🍞 Panificadora ProfitOS")
st.markdown("---")

# MENU DE NAVEGAÇÃO
menu = ["Precificador Rápido"]
if st.session_state.user_role == "Master":
    menu = ["Dashboard Estratégico", "Análise de Cardápio", "Gerador de Combos", "Precificador Rápido"]

choice = st.sidebar.radio("Navegação", menu)

# --- MÓDULO 1: DASHBOARD ESTRATÉGICO (MASTER) ---
if choice == "Dashboard Estratégico":
    st.header("📊 Inteligência de Dados")
    
    uploaded_file = st.file_uploader("Importar Relatório de Vendas (CSV/Excel)", type=['csv', 'xlsx'])
    
    if uploaded_file:
        try:
            # Simulação de leitura de dados. O arquivo precisa ter colunas: Produto, Custo, Preco_Venda, Qtd_Vendas
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            # Cálculos automáticos
            df['Faturamento'] = df['Preco_Venda'] * df['Qtd_Vendas']
            df['Lucro_Bruto'] = (df['Preco_Venda'] - df['Custo']) * df['Qtd_Vendas']
            df['Margem_R$'] = df['Preco_Venda'] - df['Custo']
            df['Margem_%'] = ((df['Preco_Venda'] - df['Custo']) / df['Preco_Venda']) * 100
            
            df = classificar_abc(df)
            
            # KPIs
            col1, col2, col3 = st.columns(3)
            col1.metric("Faturamento Total", f"R$ {df['Faturamento'].sum():,.2f}")
            col2.metric("Lucro Bruto Total", f"R$ {df['Lucro_Bruto'].sum():,.2f}")
            col3.metric("Ticket Médio (Produto)", f"R$ {df['Preco_Venda'].mean():,.2f}")
            
            # Gráfico ABC
            st.subheader("Curva ABC de Produtos")
            fig = px.bar(df, x='Produto', y='Faturamento', color='Curva_ABC', title="Faturamento por Classificação ABC")
            st.plotly_chart(fig, use_container_width=True)
            
            # Salvar no session state para usar em outras abas
            st.session_state.df_vendas = df
            st.success("Dados processados com sucesso!")
            
        except Exception as e:
            st.error(f"Erro ao ler arquivo. Verifique as colunas: Produto, Custo, Preco_Venda, Qtd_Vendas. Erro: {e}")

# --- MÓDULO 2: GERADOR DE COMBOS (MASTER) ---
elif choice == "Gerador de Combos":
    st.header("🤖 IA de Criação de Ofertas")
    
    if 'df_vendas' in st.session_state:
        df = st.session_state.df_vendas
        
        st.info("A IA analisa seus produtos 'Estrela' e 'Burros de Carga' para sugerir pares ideais.")
        
        if st.button("Gerar Sugestões de Combos"):
            sugestoes = sugerir_combos(df)
            if not sugestoes.empty:
                st.table(sugestoes)
                st.markdown("**Dica de Marketing:** Coloque este combo no balcão principal e treine os funcionários para oferecê-lo no checkout.")
            else:
                st.warning("Dados insuficientes para sugerir combos confiáveis.")
    else:
        st.warning("Por favor, carregue os dados na aba 'Dashboard Estratégico' primeiro.")

# --- MÓDULO 3: PRECIFICADOR RÁPIDO (TODOS) ---
elif choice == "Precificador Rápido":
    st.header("🏷️ Calculadora de Preço de Venda")
    
    # Configurações do Master (Default values)
    margem_meta = 50.0 # %
    imposto = 6.0 # % Simples Nacional
    taxa_cartao = 3.0 # %
    
    st.sidebar.markdown("---")
    st.sidebar.caption("Parâmetros do Sistema (Fixo pelo Master)")
    st.sidebar.text(f"Meta Margem: {margem_meta}%")
    
    col1, col2 = st.columns(2)
    
    with col1:
        nome_prod = st.text_input("Nome do Produto")
        custo_insumos = st.number_input("Custo dos Insumos (R$)", min_value=0.0, format="%.2f")
        tempo_preparo = st.number_input("Tempo de Mão de Obra (Minutos)", min_value=0, value=10)
    
    with col2:
        # Cálculo reverso (Markup divisor)
        # PV = Custo / (1 - (Impostos + Taxas + MargemLiq))
        
        fator_divisao = (100 - (imposto + taxa_cartao + margem_meta)) / 100
        
        # Adicional de mão de obra simplificado (R$ 15/hora base)
        custo_mo = (15 / 60) * tempo_preparo
        custo_total = custo_insumos + custo_mo
        
        if fator_divisao > 0:
            preco_sugerido = custo_total / fator_divisao
        else:
            preco_sugerido = 0
            
        st.metric("Custo Total (Insumo + MO)", f"R$ {custo_total:.2f}")
        st.metric("Preço de Venda Sugerido", f"R$ {preco_sugerido:.2f}")
        
        st.markdown(f"**Margem aplicada:** {margem_meta}% | **Impostos:** {imposto}%")

    if st.button("Salvar Cálculo"):
        # Aqui conectaria com Google Sheets para salvar o registro
        st.success(f"Produto '{nome_prod}' precificado e salvo no histórico!")

# --- MÓDULO 4: ANÁLISE (MASTER) ---
elif choice == "Análise de Cardápio":
    st.header("📈 Matriz de Engenharia de Menu")
    if 'df_vendas' in st.session_state:
        df = st.session_state.df_vendas
        
        # Scatter plot: Eixo X = Margem, Eixo Y = Volume
        fig = px.scatter(df, x="Margem_R$", y="Qtd_Vendas", color="Curva_ABC", hover_data=['Produto'],
                         title="Matriz de Lucratividade (Engenharia de Menu)")
        
        # Adicionar linhas médias
        fig.add_hline(y=df['Qtd_Vendas'].mean(), line_dash="dash", annotation_text="Média Vendas")
        fig.add_vline(x=df['Margem_R$'].mean(), line_dash="dash", annotation_text="Média Margem")
        
        st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("""
        * **Quadrante Superior Direito:** 🌟 Estrelas (Mantenha qualidade).
        * **Quadrante Superior Esquerdo:** 🐮 Burros de Carga (Tente reduzir custo).
        * **Quadrante Inferior Direito:** 🧩 Quebra-Cabeças (Faça combos/marketing).
        * **Quadrante Inferior Esquerdo:** 🐕 Cães (Remova do cardápio).
        """)
    else:
        st.warning("Carregue os dados no Dashboard primeiro.")
