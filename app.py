import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import pdfplumber
import io
from typing import Tuple, List, Dict

# ----------------------------------------------------------------------------
# 1. CONFIGURAÇÃO E ESTILO
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="Panificadora ProfitOS 2.0",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="🍞"
)

st.markdown("""
<style>
    div[data-testid="stMetric"] {
        background-color: #f0f2f6;
        border: 1px solid #dcdcdc;
        padding: 10px;
        border-radius: 8px;
    }
    [data-testid="stSidebar"] { background-color: #f8f9fa; }
    h1, h2 { color: #2c3e50; }
    .stDataFrame { border: 1px solid #ddd; border-radius: 5px; }
</style>
""", unsafe_allow_html=True)

# ----------------------------------------------------------------------------
# 2. INTEELIGÊNCIA DE DADOS & FUNÇÕES
# ----------------------------------------------------------------------------

def authenticate(username, password, role):
    # Em produção, usar hash seguro
    users = {
        "master": ("admin123", "master"),
        "socia": ("socia123", "master"),
        "gerente": ("gerente123", "gerente"),
        "vendedor": ("venda1", "vendedor"),
    }
    cred = users.get(username)
    if cred and cred[0] == password:
        # Permite acesso se a role for compativel ou se for master acessando outros
        if cred[1] == "master" or cred[1] == role:
            return True
    return False

def normalizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    """
    IA Lógica: Mapeia nomes variados de colunas para o padrão do sistema.
    """
    # Remove espaços e joga pra minusculo
    df.columns = [str(c).strip().lower() for c in df.columns]
    
    # Dicionário de Sinônimos (O sistema entende essas variações)
    mapa = {
        'produto': ['nome', 'descrição', 'item', 'mercadoria', 'produto'],
        'quantidade': ['qtd', 'quant', 'quantidade', 'volume', 'unidades'],
        'custo': ['custo', 'custo unit', 'vl custo', 'preço de custo', 'custo_unitario'],
        'preco_venda': ['venda', 'preço venda', 'vl venda', 'preço de venda', 'preco medio', 'preço médio r$'],
        'faturamento': ['total', 'faturamento', 'total r$', 'valor total'],
        'percentual': ['%', 'perc', 'part', 'participacao'],
        'acumulado': ['acum', 'acumulado', '% acum']
    }
    
    rename_dict = {}
    for padrao, variacoes in mapa.items():
        for col in df.columns:
            # Verifica correspondência exata ou parcial
            if col in variacoes or any(v in col for v in variacoes if len(v) > 3):
                rename_dict[col] = padrao
                break # Para ao encontrar a primeira correspondencia para evitar duplicidade
    
    df = df.rename(columns=rename_dict)
    
    # Garante colunas mínimas se não existirem
    required = ['produto', 'quantidade', 'custo', 'preco_venda']
    for req in required:
        if req not in df.columns:
            if req == 'custo': df[req] = 0.0
            elif req == 'quantidade': df[req] = 0.0
            elif req == 'preco_venda': df[req] = 0.0
            else: df[req] = "Produto Desconhecido"
            
    return df

def extrair_pdf(file) -> pd.DataFrame:
    """
    Tenta extrair tabelas de um PDF usando pdfplumber.
    """
    all_data = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            # Tenta extrair tabela
            table = page.extract_table()
            if table:
                df_page = pd.DataFrame(table[1:], columns=table[0])
                all_data.append(df_page)
    
    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return pd.DataFrame()

def processar_upload(file):
    try:
        if file.name.endswith('.csv'):
            df = pd.read_csv(file, encoding='latin1', sep=None, engine='python')
        elif file.name.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(file)
        elif file.name.endswith('.pdf'):
            df = extrair_pdf(file)
        else:
            return None, "Formato não suportado."
        
        # Limpeza Numérica (Converter '1.200,50' para float)
        df = normalizar_colunas(df)
        cols_num = ['custo', 'preco_venda', 'quantidade', 'faturamento']
        for col in cols_num:
            if col in df.columns:
                if df[col].dtype == 'object':
                    df[col] = df[col].astype(str).str.replace('R$', '').str.replace('.', '').str.replace(',', '.')
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                
        return df, None
    except Exception as e:
        return None, str(e)

def analisar_menu(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Recalcula campos calculados se faltarem
    if 'faturamento' not in df.columns or df['faturamento'].sum() == 0:
        df['faturamento'] = df['quantidade'] * df['preco_venda']
        
    df['lucro'] = df['faturamento'] - (df['quantidade'] * df['custo'])
    df['margem_perc'] = df['lucro'] / df['faturamento'].replace(0, np.nan)

    # Curva ABC
    df = df.sort_values(by='faturamento', ascending=False)
    df['acumulado_calc'] = df['faturamento'].cumsum() / df['faturamento'].sum()
    
    # Classificação ABC
    conditions = [df['acumulado_calc'] <= 0.80, df['acumulado_calc'] <= 0.95]
    choices = ['A', 'B']
    df['classe_abc'] = np.select(conditions, choices, default='C')
    
    # Classificação BCG (Margem vs Volume)
    mediana_margem = df['margem_perc'].median()
    df['alta_margem'] = df['margem_perc'] >= mediana_margem
    
    bcg = []
    for _, row in df.iterrows():
        eh_popular = row['classe_abc'] in ['A', 'B'] # Alto Volume/Fat
        tem_margem = row['alta_margem']
        
        if eh_popular and tem_margem: bcg.append('🌟 Estrela')
        elif eh_popular and not tem_margem: bcg.append('🐮 Burro de Carga')
        elif not eh_popular and tem_margem: bcg.append('🧩 Quebra-Cabeça')
        else: bcg.append('🐕 Cão')
    df['categoria_bcg'] = bcg
    
    return df

# ----------------------------------------------------------------------------
# 3. INTERFACE
# ----------------------------------------------------------------------------

def main():
    # Inicializa sessão
    if 'data_base' not in st.session_state:
        # Estrutura base vazia
        st.session_state.data_base = pd.DataFrame(columns=[
            'produto', 'custo', 'preco_venda', 'quantidade', 'faturamento', 'classe_abc'
        ])
    if 'dna_params' not in st.session_state:
        st.session_state.dna_params = {'dna': 0.0, 'custo_fixo': 0.0, 'faturamento': 1.0}
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    # --- LOGIN ---
    if not st.session_state.logged_in:
        c1, c2, c3 = st.columns([1,2,1])
        with c2:
            st.title("🍞 ProfitOS 2.0")
            with st.form("login"):
                u = st.text_input("Usuário")
                p = st.text_input("Senha", type="password")
                r = st.selectbox("Perfil", ["master", "gerente", "vendedor"])
                if st.form_submit_button("Entrar"):
                    if authenticate(u, p, r):
                        st.session_state.logged_in = True
                        st.session_state.user = u
                        st.session_state.role = r
                        st.rerun()
                    else:
                        st.error("Dados inválidos")
        return

    # --- SIDEBAR ---
    role = st.session_state.role
    st.sidebar.title("🍞 Menu")
    st.sidebar.caption(f"Logado: {st.session_state.user} ({role})")
    
    opts = ["Central de Dados", "Dashboard Inteligente", "Precificador", "Combos IA"]
    if role == "vendedor": opts = ["Precificador"]
    
    nav = st.sidebar.radio("Navegação", opts)
    
    if st.sidebar.button("Sair"):
        st.session_state.logged_in = False
        st.rerun()

    # --- PÁGINA 1: CENTRAL DE DADOS (IMPORTAÇÃO + MANUAL) ---
    if nav == "Central de Dados":
        st.title("📂 Central de Dados & Produtos")
        st.markdown("Aqui você alimenta a Inteligência do sistema. Importe arquivos ou cadastre manualmente.")
        
        with st.expander("ℹ️ Ver Modelo de Importação Ideal (Margem de Flexibilidade)", expanded=False):
            st.info("""
            **O sistema usa IA para tentar ler qualquer formato**, mas este é o ideal para garantir 100% de precisão:
            
            | Produto | Quantidade | Custo Unit | Preço Venda | Faturamento | % | Acumulado |
            | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
            | Pão Francês | 1000 | 0.30 | 0.90 | 900.00 | 5% | 5% |
            
            *Formatos aceitos:* .xlsx (Excel), .csv (Texto), .pdf (Relatórios do Sistema)
            """)

        tab_imp, tab_man = st.tabs(["📤 Importar Arquivo", "📝 Cadastro Manual / Edição"])
        
        with tab_imp:
            file = st.file_uploader("Arraste seu relatório (ABC, Vendas, Custos)", type=['csv', 'xlsx', 'pdf'])
            if file:
                df_new, err = processar_upload(file)
                if err:
                    st.error(f"Erro na leitura: {err}")
                else:
                    st.success(f"Arquivo lido com sucesso! {len(df_new)} linhas identificadas.")
                    st.dataframe(df_new.head())
                    
                    if st.button("Confirmar e Carregar para Análise"):
                        st.session_state.data_base = df_new
                        st.success("Dados carregados para o sistema! Vá para o Dashboard.")

        with tab_man:
            st.markdown("Use a tabela abaixo para **cadastrar produtos novos** ou **corrigir** dados importados.")
            
            # Editor de Dados
            edited_df = st.data_editor(
                st.session_state.data_base,
                num_rows="dynamic",
                column_config={
                    "custo": st.column_config.NumberColumn("Custo (R$)", format="%.2f"),
                    "preco_venda": st.column_config.NumberColumn("Venda (R$)", format="%.2f"),
                    "faturamento": st.column_config.NumberColumn("Faturamento (R$)", format="%.2f"),
                },
                use_container_width=True
            )
            
            if st.button("Salvar Alterações Manuais"):
                st.session_state.data_base = edited_df
                st.success("Base de dados atualizada!")

    # --- PÁGINA 2: DASHBOARD ---
    elif nav == "Dashboard Inteligente":
        st.title("📊 Análise 360º")
        
        df = st.session_state.data_base
        
        if df.empty or 'produto' not in df.columns:
            st.warning("⚠️ Nenhum dado carregado. Vá em 'Central de Dados' e importe um arquivo ou cadastre produtos.")
        else:
            # Processa Análise
            df_analise = analisar_menu(df)
            
            # KPI
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Faturamento Analisado", f"R$ {df_analise['faturamento'].sum():,.2f}")
            k2.metric("Lucro Estimado", f"R$ {df_analise['lucro'].sum():,.2f}")
            k3.metric("Margem Média", f"{df_analise['margem_perc'].mean()*100:.1f}%")
            k4.metric("Total Produtos", len(df_analise))
            
            # Gráficos
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Curva ABC (Pareto)")
                fig_abc = px.bar(df_analise.head(20), x='produto', y='faturamento', color='classe_abc', title="Top 20 Produtos")
                st.plotly_chart(fig_abc, use_container_width=True)
            
            with c2:
                st.subheader("Matriz de Lucratividade")
                fig_bcg = px.scatter(df_analise, x='margem_perc', y='faturamento', color='categoria_bcg',
                                     hover_name='produto', size='quantidade', title="Volume vs Margem")
                # Adiciona linhas de corte
                fig_bcg.add_hline(y=df_analise['faturamento'].mean(), line_dash="dash", annotation_text="Média Fat.")
                fig_bcg.add_vline(x=df_analise['margem_perc'].median(), line_dash="dash", annotation_text="Mediana Margem")
                st.plotly_chart(fig_bcg, use_container_width=True)
            
            st.dataframe(df_analise)

    # --- PÁGINA 3: PRECIFICADOR ---
    elif nav == "Precificador":
        st.title("🏷️ Precificador Mestre")
        
        # Area de configuração rapida de DNA
        if role == 'master':
            with st.expander("⚙️ Configurar DNA (Custos da Empresa)"):
                cf = st.number_input("Custo Fixo", value=st.session_state.dna_params.get('custo_fixo', 0.0))
                fat = st.number_input("Faturamento Médio", value=st.session_state.dna_params.get('faturamento', 1.0))
                taxas = st.number_input("Taxas + Impostos (%)", value=10.0)
                
                if st.button("Atualizar DNA"):
                    dna = (cf/fat) + (taxas/100)
                    st.session_state.dna_params = {'dna': dna, 'custo_fixo': cf, 'faturamento': fat}
                    st.success(f"DNA: {dna*100:.2f}%")
        
        dna = st.session_state.dna_params.get('dna', 0.0)
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Composição")
            custo = st.number_input("Custo Insumos (R$)", 0.0)
            margem = st.slider("Margem Desejada (%)", 0, 100, 25) / 100
        
        with col2:
            st.subheader("Resultado")
            divisor = 1 - dna - margem
            if divisor <= 0:
                st.error("Margem + Custos estouram 100%. Impossível precificar.")
            else:
                preco = custo / divisor
                st.metric("Preço Sugerido", f"R$ {preco:.2f}")
                st.write(f"Custo: {custo} | DNA: {dna*100:.1f}% | Lucro: {margem*100:.0f}%")

    # --- PÁGINA 4: COMBOS IA ---
    elif nav == "Combos IA":
        st.title("🤖 Sugestão de Combos")
        df = st.session_state.data_base
        
        if df.empty:
            st.warning("Carregue dados na Central de Dados primeiro.")
        else:
            df = analisar_menu(df)
            burros = df[df['categoria_bcg'] == '🐮 Burro de Carga']
            quebras = df[df['categoria_bcg'] == '🧩 Quebra-Cabeça']
            
            if not burros.empty and not quebras.empty:
                st.success("IA encontrou oportunidades de combinação!")
                
                b_prod = burros.iloc[0]
                q_prod = quebras.iloc[0]
                
                total = b_prod['preco_venda'] + q_prod['preco_venda']
                desc = total * 0.90
                
                st.metric("Combo Sugerido", f"{b_prod['produto']} + {q_prod['produto']}")
                c1, c2 = st.columns(2)
                c1.metric("Preço Original", f"R$ {total:.2f}")
                c2.metric("Preço Combo (10% off)", f"R$ {desc:.2f}")
                
                st.info(f"Estratégia: Usar o alto volume de vendas do '{b_prod['produto']}' para impulsionar a venda do '{q_prod['produto']}' que tem alta margem.")
            else:
                st.info("Ainda não há dados suficientes classificados como Burro de Carga e Quebra-Cabeça para sugerir combos.")

if __name__ == "__main__":
    main()
