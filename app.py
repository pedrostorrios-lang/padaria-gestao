import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import pdfplumber
import random

# ----------------------------------------------------------------------------
# 1. CONFIGURAÇÃO E ESTILO
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="Panificadora ProfitOS 3.0",
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
    # Inicializa banco de dados de usuários se não existir
    if 'users_db' not in st.session_state:
        st.session_state.users_db = {
            "master": {"pass": "admin123", "role": "master", "name": "Diretor"},
            "administrador": {"pass": "Pmpa2025", "role": "admin", "name": "Pacha Mama"},
            "vendedor": {"pass": "venda1", "role": "vendedor", "name": "Balconista 1"}
        }
    
    # Inicializa dados financeiros
    if 'data_base' not in st.session_state:
        st.session_state.data_base = pd.DataFrame(columns=[
            'produto', 'custo', 'preco_venda', 'quantidade', 'faturamento'
        ])
    
    # Parâmetros financeiros globais
    if 'fin_params' not in st.session_state:
        st.session_state.fin_params = {
            'custo_fixo': 5000.0, 
            'desperdicio': 200.0,
            'imposto': 6.0, # Simples
            'taxa_cartao': 3.5,
            'comissao': 0.0
        }

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
    
    # Colunas obrigatórias
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
    
    # Curva ABC
    df = df.sort_values('faturamento', ascending=False)
    df['acumulado'] = df['faturamento'].cumsum() / df['faturamento'].sum()
    df['classe_abc'] = np.where(df['acumulado'] <= 0.8, 'A', np.where(df['acumulado'] <= 0.95, 'B', 'C'))
    
    # Margem Bruta Individual
    df['lucro_bruto'] = df['faturamento'] - (df['quantidade'] * df['custo'])
    df['margem_perc'] = df['lucro_bruto'] / df['faturamento'].replace(0, np.nan)
    
    return df

def gerar_combos_ia(df, num_sugestoes=5):
    """Gera combos inteligentes baseados em regras de negócio"""
    if df.empty: return []
    
    df = analisar_dados(df)
    estrelas = df[(df['classe_abc'].isin(['A', 'B'])) & (df['margem_perc'] > 0.4)]
    burros = df[(df['classe_abc'].isin(['A', 'B'])) & (df['margem_perc'] <= 0.4)]
    quebras = df[(df['classe_abc'] == 'C') & (df['margem_perc'] > 0.5)]
    
    sugestoes = []
    
    # Estratégias
    estrategias = [
        ("Aumentar Ticket Médio", burros, quebras, 0.10),
        ("Giro de Estoque", estrelas, quebras, 0.15),
        ("Café da Manhã Completo", burros, estrelas, 0.05),
        ("Oferta Irresistível", burros, burros, 0.08),
        ("Experiência Premium", estrelas, estrelas, 0.12)
    ]
    
    # Randomiza para gerar "novas ideias"
    random.shuffle(estrategias)
    
    count = 0
    # Tenta gerar combos iterando pelas estratégias
    while count < num_sugestoes:
        for nome_estrat, df1, df2, desconto_padrao in estrategias:
            if not df1.empty and not df2.empty:
                try:
                    p1 = df1.sample(1).iloc[0]
                    df2_filt = df2[df2['produto'] != p1['produto']]
                    if not df2_filt.empty:
                        p2 = df2_filt.sample(1).iloc[0]
                        
                        custo_tot = p1['custo'] + p2['custo']
                        venda_full = p1['preco_venda'] + p2['preco_venda']
                        venda_promo = venda_full * (1 - desconto_padrao)
                        lucro = venda_promo - custo_tot
                        margem = (lucro / venda_promo) * 100 if venda_promo > 0 else 0
                        
                        sugestoes.append({
                            "titulo": f"{nome_estrat}",
                            "prod1": p1['produto'],
                            "prod2": p2['produto'],
                            "venda_full": venda_full,
                            "venda_promo": venda_promo,
                            "margem": margem,
                            "racional": f"Une '{p1['produto']}' (Volume) com '{p2['produto']}' (Margem/Giro).",
                            "desconto": desconto_padrao * 100
                        })
                        count += 1
                        if count >= num_sugestoes: break
                except:
                    continue
            if count >= num_sugestoes: break
        if count == 0: break # Evita loop infinito se não houver dados
                
    return sugestoes

# ----------------------------------------------------------------------------
# 3. INTERFACE PRINCIPAL
# ----------------------------------------------------------------------------

def main():
    init_session()
    
    # --- TELA DE LOGIN ---
    if 'logged_in' not in st.session_state or not st.session_state.logged_in:
        c1, c2, c3 = st.columns([1,1.5,1])
        with c2:
            st.title("🍞 ProfitOS Login")
            st.markdown("---")
            with st.form("login_form"):
                u = st.text_input("Usuário")
                p = st.text_input("Senha", type="password")
                # Sem seletor de perfil, define auto
                
                if st.form_submit_button("Acessar Sistema"):
                    user_data = authenticate(u, p)
                    if user_data:
                        st.session_state.logged_in = True
                        st.session_state.user_info = user_data
                        st.session_state.username = u
                        st.rerun()
                    else:
                        st.error("Usuário ou senha incorretos.")
        return

    # --- USUÁRIO LOGADO ---
    user = st.session_state.user_info
    role = user['role']
    name = user['name']
    
    # SIDEBAR
    st.sidebar.title("🍞 Menu ProfitOS")
    st.sidebar.write(f"Olá, **{name}**")
    st.sidebar.caption(f"Perfil: {role.upper()}")
    
    # Definição de Menus por Perfil
    menu_options = ["Central de Dados", "Precificador", "Dashboard Inteligente", "Combos IA"]
    if role == "vendedor":
        menu_options = ["Precificador"]
    if role == "master":
        menu_options.append("Gestão de Usuários")
        
    choice = st.sidebar.radio("Navegar", menu_options)
    
    st.sidebar.markdown("---")
    if st.sidebar.button("Sair"):
        st.session_state.logged_in = False
        st.rerun()

    # --- 1. GESTÃO DE USUÁRIOS (MASTER) ---
    if choice == "Gestão de Usuários":
        st.title("👥 Gestão de Acessos")
        
        tab_list, tab_add = st.tabs(["Lista de Usuários", "Criar Novo Usuário"])
        
        with tab_list:
            users_list = []
            for u_key, u_val in st.session_state.users_db.items():
                users_list.append({"Login": u_key, "Nome": u_val['name'], "Perfil": u_val['role']})
            st.dataframe(pd.DataFrame(users_list), use_container_width=True)
            
            st.subheader("Alterar/Remover")
            c1, c2, c3 = st.columns(3)
            user_to_edit = c1.selectbox("Selecionar Usuário", list(st.session_state.users_db.keys()))
            new_pass = c2.text_input("Nova Senha (deixe vazio para manter)", type="password")
            
            if c3.button("Atualizar Senha"):
                if new_pass:
                    st.session_state.users_db[user_to_edit]['pass'] = new_pass
                    st.success("Senha atualizada!")
            
            if st.button("🗑️ Excluir Usuário", type="primary"):
                if user_to_edit == st.session_state.username:
                    st.error("Você não pode excluir a si mesmo.")
                else:
                    del st.session_state.users_db[user_to_edit]
                    st.success(f"Usuário {user_to_edit} removido.")
                    st.rerun()

        with tab_add:
            with st.form("add_user"):
                new_login = st.text_input("Login")
                new_name = st.text_input("Nome Completo")
                new_role = st.selectbox("Perfil", ["master", "gerente", "vendedor"])
                new_p = st.text_input("Senha Inicial", type="password")
                
                if st.form_submit_button("Criar Usuário"):
                    if new_login in st.session_state.users_db:
                        st.error("Login já existe.")
                    elif new_login and new_p:
                        st.session_state.users_db[new_login] = {
                            "pass": new_p, "role": new_role, "name": new_name
                        }
                        st.success("Usuário criado com sucesso!")
                    else:
                        st.error("Preencha todos os campos.")

    # --- 2. CENTRAL DE DADOS ---
    elif choice == "Central de Dados":
        st.title("📂 Importação de Dados")
        
        uploaded = st.file_uploader("Upload (XLSX, CSV, PDF)", type=['csv','xlsx','pdf'])
        if uploaded:
            df, err = processar_upload(uploaded)
            if err:
                st.error(err)
            else:
                st.success(f"Lido com sucesso: {len(df)} itens.")
                if st.button("💾 Salvar na Base de Dados"):
                    st.session_state.data_base = df
                    st.success("Dados atualizados!")
        
        st.subheader("Base Atual")
        st.data_editor(st.session_state.data_base, num_rows="dynamic", use_container_width=True)

    # --- 3. PRECIFICADOR ---
    elif choice == "Precificador":
        st.title("🏷️ Precificador Rápido")
        
        df = st.session_state.data_base
        produtos_lista = df['produto'].unique().tolist() if not df.empty else []
        produtos_lista.insert(0, "Novo Produto (Digitar manual)")
        
        c1, c2 = st.columns(2)
        with c1:
            sel_prod = st.selectbox("Selecione um Produto", produtos_lista)
            
            custo_base = 0.0
            if sel_prod != "Novo Produto (Digitar manual)":
                if not df.empty:
                    val = df[df['produto'] == sel_prod]['custo'].iloc[0]
                    custo_base = float(val) if pd.notnull(val) else 0.0
                st.caption(f"Custo Base importado: R$ {custo_base:.2f}")
            
            custo_final = st.number_input("Custo Insumos (R$)", value=custo_base, format="%.2f")
            embalagem = st.number_input("Custo Embalagem (R$)", 0.0, format="%.2f")
            cupom = st.number_input("Cupom de Desconto (R$)", 0.0, format="%.2f")
            
        with c2:
            st.markdown("### Definição de Lucro")
            # Puxa DNA da config global
            dna_params = st.session_state.fin_params
            taxas_totais = dna_params['imposto'] + dna_params['taxa_cartao'] + dna_params['comissao']
            
            margem_target = st.slider("Margem de Lucro Líquido Desejada (%)", 0, 100, 20)
            
            # Cálculo
            custo_total = custo_final + embalagem
            divisor = 1 - (taxas_totais/100) - (margem_target/100)
            
            st.divider()
            
            if divisor <= 0:
                st.error("A soma de Taxas + Margem ultrapassa 100%. Impossível calcular.")
            else:
                preco_venda = (custo_total + cupom) / divisor
                st.metric("Preço de Venda Sugerido", f"R$ {preco_venda:.2f}")
                
                detalhe = {
                    "Custo Prod+Emb": custo_total,
                    "Cupom (Cliente ganha)": cupom,
                    f"Impostos/Taxas ({taxas_totais}%)": preco_venda * (taxas_totais/100),
                    f"Lucro Líquido ({margem_target}%)": preco_venda * (margem_target/100)
                }
                st.bar_chart(pd.Series(detalhe))

    # --- 4. DASHBOARD INTELIGENTE ---
    elif choice == "Dashboard Inteligente":
        st.title("📊 Painel Financeiro Real")
        
        # Configuração de Custos
        with st.expander("⚙️ Configurar Parâmetros de Custo do Mês", expanded=False):
            c_a, c_b, c_c = st.columns(3)
            fp = st.session_state.fin_params
            
            n_cf = c_a.number_input("Custo Fixo (Aluguel, Luz, Pessoal)", value=fp['custo_fixo'])
            n_desp = c_b.number_input("Desperdício/Perda (R$)", value=fp['desperdicio'])
            n_imp = c_c.number_input("Impostos + Taxas Totais (%)", value=fp['imposto'] + fp['taxa_cartao'])
            
            if st.button("Salvar Parâmetros"):
                st.session_state.fin_params.update({
                    'custo_fixo': n_cf, 'desperdicio': n_desp, 'imposto': n_imp, 'taxa_cartao': 0
                })
                st.success("Parâmetros atualizados!")
                st.rerun()

        df = st.session_state.data_base
        if df.empty:
            st.warning("Sem dados para analisar. Vá em 'Central de Dados' primeiro.")
        else:
            df = analisar_dados(df)
            
            # CÁLCULO DE LUCRO LÍQUIDO REAL
            faturamento_total = df['faturamento'].sum()
            custo_produtos = (df['quantidade'] * df['custo']).sum()
            lucro_bruto = faturamento_total - custo_produtos
            
            fp = st.session_state.fin_params
            # Taxa está somada no campo imposto para simplificar o cálculo
            impostos_valor = faturamento_total * (fp['imposto'] / 100) 
            despesas_operacionais = fp['custo_fixo'] + fp['desperdicio']
            
            lucro_liquido = lucro_bruto - impostos_valor - despesas_operacionais
            margem_liq_real = (lucro_liquido / faturamento_total * 100) if faturamento_total > 0 else 0
            
            # CARDS
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Faturamento", f"R$ {faturamento_total:,.2f}")
            k2.metric("CMV (Custo Mercadoria)", f"R$ {custo_produtos:,.2f}", f"-{(custo_produtos/faturamento_total)*100:.1f}% Fat")
            k3.metric("Custos Fixos + Desperdício", f"R$ {despesas_operacionais:,.2f}", help=f"CF: {fp['custo_fixo']} + Perda: {fp['desperdicio']}")
            k4.metric("Lucro Líquido Real", f"R$ {lucro_liquido:,.2f}", f"{margem_liq_real:.1f}%", delta_color="normal")
            
            st.markdown("---")
            
            # Gráficos
            g1, g2 = st.columns([2,1])
            with g1:
                st.subheader("Curva ABC de Vendas")
                fig = px.bar(df.head(15), x='produto', y='faturamento', color='classe_abc', title="Top 15 Produtos")
                st.plotly_chart(fig, use_container_width=True)
            with g2:
                st.subheader("Para onde vai o dinheiro?")
                waterfall_data = {
                    "Faturamento": faturamento_total,
                    "(-) CMV": -custo_produtos,
                    "(-) Impostos": -impostos_valor,
                    "(-) Fixos/Perdas": -despesas_operacionais,
                    "(=) Lucro Líquido": lucro_liquido
                }
                fig_w = go.Figure(go.Waterfall(
                    measure = ["absolute", "relative", "relative", "relative", "total"],
                    x = list(waterfall_data.keys()),
                    y = list(waterfall_data.values()),
                    connector = {"line":{"color":"rgb(63, 63, 63)"}},
                ))
                st.plotly_chart(fig_w, use_container_width=True)

    # --- 5. COMBOS IA ---
    elif choice == "Combos IA":
        st.title("🤖 Fábrica de Combos")
        
        tab_manual, tab_ia = st.tabs(["🛠️ Criar Manualmente", "✨ Sugestões IA"])
        
        df = st.session_state.data_base
        
        with tab_manual:
            if df.empty:
                st.warning("Carregue produtos primeiro.")
            else:
                st.markdown("Selecione os produtos para montar um kit:")
                prods = st.multiselect("Produtos do Combo", df['produto'].unique())
                
                if prods:
                    # Filtra e soma
                    selecao = df[df['produto'].isin(prods)]
                    custo_total = selecao['custo'].sum()
                    venda_soma = selecao['preco_venda'].sum()
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Preço Tabela (Soma)", f"R$ {venda_soma:.2f}")
                    # CORREÇÃO AQUI: F-string fechada corretamente
                    c2.metric("Custo Itens", f"R$ {custo_total:.2f}")
                    
                    preco_promo = c3.number_input("Preço Promocional do Combo", value=float(venda_soma)*0.9)
                    
                    if preco_promo > 0:
                        lucro = preco_promo - custo_total
                        margem = (lucro / preco_promo) * 100
                        
                        st.info(f"💰 Lucro do Combo: R$ {lucro:.2f}")
                        if margem < 20:
                            st.error(f"Margem Baixa: {margem:.1f}%")
                        elif margem > 40:
                            st.success(f"Margem Excelente: {margem:.1f}%")
                        else:
                            st.warning(f"Margem OK: {margem:.1f}%")

        with tab_ia:
            if df.empty:
                st.info("Necessário base de dados.")
            else:
                c_head, c_btn = st.columns([3,1])
                c_head.write("A IA analisa a Curva ABC e Margens para sugerir 5 combos estratégicos.")
                
                # Botão gera novas sugestões
                if 'sugestoes_ia' not in st.session_state or c_btn.button("🔄 Gerar Novas Ideias"):
                    st.session_state.sugestoes_ia = gerar_combos_ia(df, 5)
                
                sugestoes = st.session_state.sugestoes_ia
                
                if not sugestoes:
                    st.warning("Não encontrei correlações suficientes nos dados atuais (poucos produtos).")
                else:
                    for s in sugestoes:
                        with st.expander(f"💡 {s['titulo']}: {s['prod1']} + {s['prod2']}", expanded=True):
                            col_A, col_B, col_C = st.columns(3)
                            col_A.metric("De (Separados)", f"R$ {s['venda_full']:.2f}")
                            col_B.metric(f"Por (Desc {s['desconto']:.0f}%)", f"R$ {s['venda_promo']:.2f}")
                            col_C.metric("Margem Combo", f"{s['margem']:.1f}%")
                            st.caption(f"**Racional:** {s['racional']}")

if __name__ == "__main__":
    main()
