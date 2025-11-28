import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import pdfplumber
import random
from io import BytesIO

# ----------------------------------------------------------------------------
# 1. CONFIGURAÇÃO E ESTILO
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="Panificadora ProfitOS 4.0",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="🍞"
)

st.markdown("""
<style>
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    [data-testid="stSidebar"] { background-color: #f8f9fa; }
    h1, h2, h3 { color: #2c3e50; }
    .stButton>button { width: 100%; border-radius: 6px; }
    .stDataFrame { border: 1px solid #ddd; border-radius: 5px; }
</style>
""", unsafe_allow_html=True)

# ----------------------------------------------------------------------------
# 2. FUNÇÕES DE LÓGICA E DADOS
# ----------------------------------------------------------------------------

def init_session():
    # Inicializa banco de dados de usuários
    if 'users_db' not in st.session_state:
        st.session_state.users_db = {
            "master": {"pass": "admin123", "role": "master", "name": "Diretor"},
            "gerente": {"pass": "gerente123", "role": "gerente", "name": "Gerente Loja"},
            "vendedor": {"pass": "venda1", "role": "vendedor", "name": "Balconista 1"}
        }
    
    # Inicializa base de dados principal
    if 'data_base' not in st.session_state:
        st.session_state.data_base = pd.DataFrame(columns=[
            'produto', 'custo', 'preco_venda', 'quantidade', 'faturamento'
        ])
    
    # Parâmetros financeiros globais
    if 'fin_params' not in st.session_state:
        st.session_state.fin_params = {
            'custo_fixo_valor': 5000.0, 
            'faturamento_esperado': 20000.0, # Para calcular % do custo fixo
            'desperdicio': 200.0,
            'imposto': 6.0, # Simples Nacional
            'taxa_cartao': 3.0,
            'comissao': 0.0
        }

def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8')

def authenticate(username, password):
    users = st.session_state.users_db
    if username in users:
        if users[username]['pass'] == password:
            return users[username]
    return None

def normalizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip().lower() for c in df.columns]
    mapa = {
        'produto': ['nome', 'descrição', 'item', 'mercadoria', 'produto'],
        'quantidade': ['qtd', 'quant', 'quantidade', 'volume', 'unidades'],
        'custo': ['custo', 'custo unit', 'vl custo', 'preço de custo', 'custo_unitario'],
        'preco_venda': ['venda', 'preço venda', 'vl venda', 'preço de venda', 'preco medio'],
        'faturamento': ['total', 'faturamento', 'total r$', 'valor total']
    }
    rename_dict = {}
    for padrao, variacoes in mapa.items():
        for col in df.columns:
            if col in variacoes or any(v in col for v in variacoes if len(v) > 3):
                rename_dict[col] = padrao
                break
    df = df.rename(columns=rename_dict)
    
    req = ['produto', 'quantidade', 'custo', 'preco_venda']
    for r in req:
        if r not in df.columns: df[r] = 0.0 if r != 'produto' else 'Item Desconhecido'
            
    return df

def processar_upload(file):
    try:
        if file.name.endswith('.csv'):
            df = pd.read_csv(file, encoding='latin1', sep=None, engine='python')
        elif file.name.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(file)
        elif file.name.endswith('.pdf'):
            with pdfplumber.open(file) as pdf:
                data = []
                for page in pdf.pages:
                    tbl = page.extract_table()
                    if tbl: data.extend(tbl[1:])
                df = pd.DataFrame(data)
        else:
            return None, "Formato inválido"
            
        df = normalizar_colunas(df)
        cols_num = ['custo', 'preco_venda', 'quantidade', 'faturamento']
        for c in cols_num:
            if c in df.columns:
                if df[c].dtype == 'object':
                    df[c] = df[c].astype(str).str.replace('R$', '').str.replace('.', '').str.replace(',', '.')
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        return df, None
    except Exception as e:
        return None, str(e)

def analisar_dados(df):
    df = df.copy()
    if 'faturamento' not in df.columns or df['faturamento'].sum() == 0:
        df['faturamento'] = df['quantidade'] * df['preco_venda']
    
    df = df.sort_values('faturamento', ascending=False)
    df['acumulado'] = df['faturamento'].cumsum() / df['faturamento'].sum()
    df['classe_abc'] = np.where(df['acumulado'] <= 0.8, 'A', np.where(df['acumulado'] <= 0.95, 'B', 'C'))
    
    df['lucro_bruto'] = df['faturamento'] - (df['quantidade'] * df['custo'])
    df['margem_perc'] = df['lucro_bruto'] / df['faturamento'].replace(0, np.nan)
    
    return df

def calcular_dna_empresa():
    # Calcula o peso percentual do Custo Fixo sobre o Faturamento Esperado
    fp = st.session_state.fin_params
    perc_custo_fixo = (fp['custo_fixo_valor'] / fp['faturamento_esperado']) * 100 if fp['faturamento_esperado'] > 0 else 0
    
    # Soma todas as deduções (Imposto + Cartão + Custo Fixo %)
    deducoes_totais = fp['imposto'] + fp['taxa_cartao'] + fp['comissao'] + perc_custo_fixo
    return deducoes_totais, perc_custo_fixo

def gerar_combos_ia(df, num_sugestoes=5):
    if df.empty: return []
    
    df = analisar_dados(df)
    estrelas = df[(df['classe_abc'].isin(['A', 'B'])) & (df['margem_perc'] > 0.4)]
    burros = df[(df['classe_abc'].isin(['A', 'B'])) & (df['margem_perc'] <= 0.4)]
    quebras = df[(df['classe_abc'] == 'C') & (df['margem_perc'] > 0.5)]
    
    sugestoes = []
    deducoes, perc_cf = calcular_dna_empresa()
    
    estrategias = [
        ("Aumentar Ticket Médio", burros, quebras, 0.10),
        ("Giro de Estoque", estrelas, quebras, 0.15),
        ("Café da Manhã Completo", burros, estrelas, 0.05),
        ("Oferta Irresistível", burros, burros, 0.08),
        ("Experiência Premium", estrelas, estrelas, 0.12)
    ]
    random.shuffle(estrategias)
    
    count = 0
    while count < num_sugestoes:
        for nome_estrat, df1, df2, desconto_padrao in estrategias:
            if not df1.empty and not df2.empty:
                try:
                    p1 = df1.sample(1).iloc[0]
                    df2_filt = df2[df2['produto'] != p1['produto']]
                    if not df2_filt.empty:
                        p2 = df2_filt.sample(1).iloc[0]
                        
                        # Precificação Real do Combo
                        custo_insumos = p1['custo'] + p2['custo']
                        venda_full = p1['preco_venda'] + p2['preco_venda']
                        venda_promo = venda_full * (1 - desconto_padrao)
                        
                        # Cálculo de Custos Operacionais do Combo
                        custo_operacional = venda_promo * (deducoes / 100)
                        lucro_liq = venda_promo - custo_insumos - custo_operacional
                        margem_liq = (lucro_liq / venda_promo) * 100 if venda_promo > 0 else 0
                        
                        sugestoes.append({
                            "titulo": f"{nome_estrat}",
                            "prod1": p1['produto'],
                            "prod2": p2['produto'],
                            "venda_full": venda_full,
                            "venda_promo": venda_promo,
                            "margem_liq": margem_liq,
                            "lucro_liq": lucro_liq,
                            "racional": f"Une '{p1['produto']}' (Volume) com '{p2['produto']}' (Giro).",
                            "desconto": desconto_padrao * 100
                        })
                        count += 1
                        if count >= num_sugestoes: break
                except:
                    continue
            if count >= num_sugestoes: break
        if count == 0: break
                
    return sugestoes

# ----------------------------------------------------------------------------
# 3. INTERFACE PRINCIPAL
# ----------------------------------------------------------------------------

def main():
    init_session()
    
    # --- LOGIN ---
    if 'logged_in' not in st.session_state or not st.session_state.logged_in:
        c1, c2, c3 = st.columns([1,1.5,1])
        with c2:
            st.title("🍞 ProfitOS 4.0")
            st.markdown("---")
            with st.form("login_form"):
                u = st.text_input("Usuário")
                p = st.text_input("Senha", type="password")
                if st.form_submit_button("Acessar Sistema"):
                    user_data = authenticate(u, p)
                    if user_data:
                        st.session_state.logged_in = True
                        st.session_state.user_info = user_data
                        st.session_state.username = u
                        st.rerun()
                    else:
                        st.error("Usuário incorreto.")
        return

    # --- SIDEBAR E PERSISTÊNCIA ---
    user = st.session_state.user_info
    role = user['role']
    
    st.sidebar.title("🍞 Menu ProfitOS")
    st.sidebar.write(f"Olá, **{user['name']}**")
    
    menu_options = ["Central de Dados", "Precificador", "Painel Financeiro", "Combos IA"]
    if role == "vendedor": menu_options = ["Precificador"]
    if role == "master": menu_options.append("Gestão de Usuários")
    
    choice = st.sidebar.radio("Navegar", menu_options)
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("💾 Backup de Dados")
    st.sidebar.info("Para usar em outro computador, baixe o backup aqui e restaure no destino.")
    
    # Botão de Download
    csv = convert_df_to_csv(st.session_state.data_base)
    st.sidebar.download_button(
        label="📥 Baixar Dados Atuais",
        data=csv,
        file_name='backup_profitos.csv',
        mime='text/csv',
    )
    
    # Botão de Restaurar
    uploaded_backup = st.sidebar.file_uploader("📤 Restaurar Backup", type=['csv'])
    if uploaded_backup is not None:
        try:
            df_restore = pd.read_csv(uploaded_backup)
            st.session_state.data_base = df_restore
            st.sidebar.success("Dados restaurados! Atualize a página.")
        except:
            st.sidebar.error("Erro ao ler backup.")

    if st.sidebar.button("Sair"):
        st.session_state.logged_in = False
        st.rerun()

    # --- FUNCIONALIDADES ---
    
    # 1. GESTÃO DE USUÁRIOS
    if choice == "Gestão de Usuários":
        st.title("👥 Gestão de Acessos")
        users_list = [{"Login": k, "Nome": v['name'], "Perfil": v['role']} for k, v in st.session_state.users_db.items()]
        st.dataframe(pd.DataFrame(users_list), use_container_width=True)
        
        with st.expander("➕ Adicionar Novo Usuário"):
            with st.form("new_user"):
                nl = st.text_input("Login")
                nn = st.text_input("Nome")
                np = st.text_input("Senha", type="password")
                nr = st.selectbox("Perfil", ["master", "gerente", "vendedor"])
                if st.form_submit_button("Criar"):
                    st.session_state.users_db[nl] = {"pass": np, "role": nr, "name": nn}
                    st.success("Criado!")
                    st.rerun()

    # 2. CENTRAL DE DADOS
    elif choice == "Central de Dados":
        st.title("📂 Central de Dados")
        st.info("Importe seus relatórios ou edite manualmente abaixo.")
        
        uploaded = st.file_uploader("Importar Planilha/PDF", type=['csv','xlsx','pdf'])
        if uploaded:
            df, err = processar_upload(uploaded)
            if not err:
                st.session_state.data_base = df
                st.success(f"{len(df)} itens importados.")
            else:
                st.error(err)
        
        st.subheader("Editor de Produtos")
        st.data_editor(st.session_state.data_base, num_rows="dynamic", use_container_width=True, key="data_editor")

    # 3. PRECIFICADOR
    elif choice == "Precificador":
        st.title("🏷️ Precificador Inteligente")
        
        # Pega parâmetros globais
        fp = st.session_state.fin_params
        
        # Area de Configuração dos Custos Operacionais
        with st.expander("⚙️ Configurar Taxas e Custos da Empresa (DNA)", expanded=True):
            c1, c2, c3 = st.columns(3)
            fp['faturamento_esperado'] = c1.number_input("Faturamento Mensal Médio (R$)", value=fp['faturamento_esperado'])
            fp['custo_fixo_valor'] = c2.number_input("Total Custos Fixos (Aluguel/Luz/Folha)", value=fp['custo_fixo_valor'])
            fp['imposto'] = c3.number_input("Imposto (%)", value=fp['imposto'])
            fp['taxa_cartao'] = c1.number_input("Taxa Máquina Cartão (%)", value=fp['taxa_cartao'])
        
        # Cálculos do DNA
        deducoes_totais, perc_cf = calcular_dna_empresa()
        st.info(f"🧬 **Custo Operacional Total:** {deducoes_totais:.2f}% do preço de venda (sendo {perc_cf:.1f}% de custo fixo)")

        st.divider()

        # Seleção de Produto
        df = st.session_state.data_base
        prods = ["Novo Produto"] + df['produto'].unique().tolist() if not df.empty else ["Novo Produto"]
        sel = st.selectbox("Selecione Produto", prods)
        
        custo_ini = 0.0
        if sel != "Novo Produto":
            custo_ini = float(df[df['produto']==sel]['custo'].iloc[0])
        
        col_in, col_res = st.columns(2)
        with col_in:
            custo_insumo = st.number_input("Custo Insumos (R$)", value=custo_ini, format="%.2f")
            custo_emb = st.number_input("Embalagem (R$)", 0.0)
            margem_desejada = st.slider("Margem Líquida Desejada (%)", 0, 50, 20)
        
        with col_res:
            # FÓRMULA CORRETA DE PRECIFICAÇÃO (MARKUP DIVISOR)
            # Preço = Custo / (1 - (Taxas + CustoFixo% + MargemLiq))
            custo_total = custo_insumo + custo_emb
            divisor = 1 - (deducoes_totais/100) - (margem_desejada/100)
            
            if divisor <= 0:
                st.error("❌ Impossível atingir essa margem com os custos atuais!")
                st.write("A soma de (Custos Fixos + Impostos + Margem) ultrapassa 100%.")
            else:
                preco_sugerido = custo_total / divisor
                st.metric("Preço de Venda Sugerido", f"R$ {preco_sugerido:.2f}")
                
                # Prova real
                imposto_r = preco_sugerido * (fp['imposto']/100)
                taxa_r = preco_sugerido * (fp['taxa_cartao']/100)
                cf_r = preco_sugerido * (perc_cf/100)
                lucro_r = preco_sugerido - custo_total - imposto_r - taxa_r - cf_r
                
                detalhe = {
                    "Custo Mercadoria": custo_total,
                    "Impostos/Taxas": imposto_r + taxa_r,
                    "Custo Fixo (Rateio)": cf_r,
                    "Lucro Líquido Real": lucro_r
                }
                st.write(f"Lucro Líquido Real: **R$ {lucro_r:.2f} ({margem_desejada}%)**")
                st.bar_chart(pd.Series(detalhe))

    # 4. PAINEL FINANCEIRO
    elif choice == "Painel Financeiro":
        st.title("📊 Painel Financeiro")
        
        df = st.session_state.data_base
        if df.empty:
            st.warning("Sem dados.")
        else:
            df = analisar_dados(df)
            
            # Cálculo Automático
            fat_auto = df['faturamento'].sum()
            custo_auto = (df['quantidade'] * df['custo']).sum()
            
            # --- AJUSTE MANUAL DE FATURAMENTO ---
            st.subheader("Resumo do Mês")
            col_fat1, col_fat2 = st.columns([1, 2])
            
            with col_fat1:
                st.caption("Faturamento Importado (Automático)")
                st.write(f"R$ {fat_auto:,.2f}")
            
            with col_fat2:
                # Campo editável que inicia com o valor automático
                fat_real = st.number_input("Faturamento Real Ajustado (Digite aqui se houver vendas extras)", 
                                           value=float(fat_auto), format="%.2f")
            
            # Recalcula proporcionalmente o CMV se o faturamento mudou (estimativa)
            fator_ajuste = fat_real / fat_auto if fat_auto > 0 else 1
            cmv_real = custo_auto * fator_ajuste
            
            deducoes, perc_cf = calcular_dna_empresa()
            
            # DRE Gerencial
            impostos_v = fat_real * ((st.session_state.fin_params['imposto'] + st.session_state.fin_params['taxa_cartao']) / 100)
            custos_fixos_v = st.session_state.fin_params['custo_fixo_valor']
            desperdicio_v = st.session_state.fin_params['desperdicio']
            
            lucro_op = fat_real - cmv_real - impostos_v - custos_fixos_v - desperdicio_v
            margem_op = (lucro_op / fat_real * 100) if fat_real > 0 else 0
            
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Faturamento Real", f"R$ {fat_real:,.2f}")
            k2.metric("CMV Estimado", f"R$ {cmv_real:,.2f}")
            k3.metric("Custos Operacionais", f"R$ {custos_fixos_v + impostos_v + desperdicio_v:,.2f}", help="Fixos + Impostos + Perda")
            k4.metric("Lucro Líquido", f"R$ {lucro_op:,.2f}", f"{margem_op:.1f}%", delta_color="normal")

            # Gráficos
            g1, g2 = st.columns(2)
            g1.plotly_chart(px.bar(df.head(10), x='produto', y='faturamento', title="Top 10 Vendas"), use_container_width=True)
            
            fig_pie = px.pie(names=["CMV", "Custos Fixos", "Impostos", "Desperdício", "Lucro"], 
                             values=[cmv_real, custos_fixos_v, impostos_v, desperdicio_v, max(0, lucro_op)], 
                             title="Distribuição da Receita")
            g2.plotly_chart(fig_pie, use_container_width=True)

    # 5. COMBOS IA
    elif choice == "Combos IA":
        st.title("🤖 Combos com Análise de Lucro Real")
        
        tab_man, tab_ia = st.tabs(["Manual", "IA"])
        df = st.session_state.data_base
        deducoes, perc_cf = calcular_dna_empresa()
        
        with tab_man:
            if not df.empty:
                prods = st.multiselect("Produtos", df['produto'].unique())
                if prods:
                    sel = df[df['produto'].isin(prods)]
                    custo_i = sel['custo'].sum()
                    venda_i = sel['preco_venda'].sum()
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Preço Tabela", f"R$ {venda_i:.2f}")
                    c2.metric("Custo Insumos", f"R$ {custo_i:.2f}")
                    
                    promo = c3.number_input("Preço Combo", value=venda_i*0.9)
                    
                    # Lucro Líquido Real
                    custo_op_combo = promo * (deducoes / 100)
                    lucro_liq = promo - custo_i - custo_op_combo
                    margem_liq = (lucro_liq / promo * 100) if promo > 0 else 0
                    
                    st.write(f"Custo Operacional do Combo (Taxas + Rateio Fixo): R$ {custo_op_combo:.2f}")
                    
                    if lucro_liq > 0:
                        st.success(f"✅ Lucro Líquido: R$ {lucro_liq:.2f} ({margem_liq:.1f}%)")
                    else:
                        st.error(f"❌ Prejuízo: R$ {lucro_liq:.2f}")
        
        with tab_ia:
            if not df.empty:
                if st.button("Gerar Sugestões"):
                    sugestoes = gerar_combos_ia(df)
                    for s in sugestoes:
                        with st.expander(f"{s['titulo']}: {s['prod1']} + {s['prod2']}", expanded=True):
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Preço Promo", f"R$ {s['venda_promo']:.2f}")
                            c2.metric("Lucro Líquido", f"R$ {s['lucro_liq']:.2f}")
                            c3.metric("Margem Líq", f"{s['margem_liq']:.1f}%")
                            st.caption(s['racional'])

if __name__ == "__main__":
    main()
