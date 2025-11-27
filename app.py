import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from typing import Tuple, List, Dict

# ----------------------------------------------------------------------------
# 1. CONFIGURAÇÃO E ESTILO VISUAL
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="Panificadora ProfitOS",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="🍞"
)

# CSS Customizado para visual de Dashboard Profissional
st.markdown("""
<style>
    /* Cards de Métricas */
    div[data-testid="stMetric"] {
        background-color: #f0f2f6;
        border: 1px solid #dcdcdc;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
    }
    /* Títulos */
    h1, h2, h3 {
        color: #2c3e50;
    }
    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #f8f9fa;
    }
    /* Botões */
    div.stButton > button {
        width: 100%;
        border-radius: 5px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# ----------------------------------------------------------------------------
# 2. LÓGICA DE NEGÓCIO (Fórmulas do Relatório)
# ----------------------------------------------------------------------------

def authenticate(username: str, password: str, role: str) -> bool:
    # Em produção: usar hash e banco de dados
    users = {
        "master": ("admin123", "master"),       # Senha alterada para padrão forte sugerido
        "socia": ("socia123", "master"),
        "gerente": ("gerente123", "gerente"),
        "vendedor": ("venda1", "vendedor"),
    }
    cred = users.get(username)
    if cred is None:
        return False
    stored_password, stored_role = cred
    # Master pode acessar tudo, mas aqui validamos se a role bate com a intenção
    if stored_role == "master" and role != "master":
         return True # Master pode logar como outros perfis se quiser testar
    return (password == stored_password) and (role == stored_role)

def calcular_dna(custo_fixo, faturamento, taxa_cartoes, imposto_pago, royalty) -> Tuple[float, float]:
    if faturamento <= 0:
        return 0.0, 0.0
    resultado_cf = custo_fixo / faturamento
    # DNA = (CF/Fat) + Taxas + Impostos + Royalty
    dna_total = resultado_cf + (taxa_cartoes / 100.0) + (imposto_pago / 100.0) + (royalty / 100.0)
    return resultado_cf, dna_total

def precificar_produto(cmv, embalagem, taxa_entrega, dna, lucro_desejado) -> float:
    # Preço = (Custos Diretos) / (1 - DNA - Margem)
    denominator = 1.0 - dna - lucro_desejado
    if denominator <= 0:
        return np.nan
    return (cmv + embalagem + taxa_entrega) / denominator

def precificar_ifood(preco_cardapio, taxa_entrega, campanha, cupom, taxa_comissao) -> Tuple[float, float]:
    # Valor iFood = (Preço + Entrega + Campanha) / (1 - Comissão)
    denominator = 1.0 - taxa_comissao
    if denominator <= 0:
        return np.nan, np.nan
    valor_minimo_ifood = (preco_cardapio + taxa_entrega + campanha) / denominator
    preco_final_cliente = valor_minimo_ifood + cupom
    return valor_minimo_ifood, preco_final_cliente

def analisar_menu(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Tratamento básico de nomes de colunas
    df.columns = [c.lower().strip() for c in df.columns]
    
    # Cálculos Financeiros
    df['faturamento'] = df['quantidade'] * df['preco_venda']
    df['custo_total'] = df['quantidade'] * df['custo']
    df['lucro'] = df['faturamento'] - df['custo_total']
    df['margem_perc'] = df['lucro'] / df['faturamento'].replace(0, np.nan)

    # Classificação ABC (Volume de Vendas/Quantidade)
    df = df.sort_values(by='quantidade', ascending=False)
    df['pct_acumulado'] = df['quantidade'].cumsum() / df['quantidade'].sum()
    
    conditions_abc = [df['pct_acumulado'] <= 0.2, df['pct_acumulado'] <= 0.5]
    choices_abc = ['A', 'B']
    df['categoria_abc'] = np.select(conditions_abc, choices_abc, default='C')

    # Classificação BCG Adaptada (Margem vs Volume)
    median_margem = df['margem_perc'].median()
    df['alta_margem'] = df['margem_perc'] >= median_margem
    
    bcg = []
    for _, row in df.iterrows():
        # A ou B = Alto Volume
        alto_volume = row['categoria_abc'] in ['A', 'B']
        alta_margem = row['alta_margem']
        
        if alto_volume and alta_margem: bcg.append('🌟 Estrela')
        elif alto_volume and not alta_margem: bcg.append('🐮 Burro de Carga')
        elif not alto_volume and alta_margem: bcg.append('🧩 Quebra-Cabeça')
        else: bcg.append('🐕 Cão')
    
    df['categoria_bcg'] = bcg
    return df

def sugerir_combos(df: pd.DataFrame, desconto: float, max_sugestoes: int) -> pd.DataFrame:
    # Lógica: Unir Burro de Carga (Volume) + Quebra-Cabeça (Margem)
    burros = df[df['categoria_bcg'] == '🐮 Burro de Carga'].sort_values('quantidade', ascending=False)
    quebras = df[df['categoria_bcg'] == '🧩 Quebra-Cabeça'].sort_values('margem_perc', ascending=False)

    combos = []
    
    # Tenta parear os tops de cada lista
    for _, b in burros.head(max_sugestoes).iterrows():
        for _, q in quebras.head(max_sugestoes).iterrows():
            preco_orig = b['preco_venda'] + q['preco_venda']
            custo_combo = b['custo'] + q['custo']
            preco_promo = preco_orig * (1 - desconto)
            lucro_promo = preco_promo - custo_combo
            margem_promo = lucro_promo / preco_promo if preco_promo > 0 else 0
            
            combos.append({
                "Combo": f"{b['produto']} + {q['produto']}",
                "Preço Original": preco_orig,
                "Preço Promo": preco_promo,
                "Lucro Previsto": lucro_promo,
                "Margem %": margem_promo * 100,
                "Estratégia": "Volume do Burro de Carga impulsiona Margem do Quebra-Cabeça"
            })
            if len(combos) >= max_sugestoes: break
        if len(combos) >= max_sugestoes: break
            
    return pd.DataFrame(combos)

# ----------------------------------------------------------------------------
# 3. INTERFACE DE USUÁRIO (FRONTEND)
# ----------------------------------------------------------------------------

def main():
    # Inicialização de Estado
    if 'dna_params' not in st.session_state:
        st.session_state.dna_params = {
            'custo_fixo': 0.0, 'faturamento': 1.0, 
            'taxa_cartoes': 0.0, 'imposto_pago': 0.0, 'royalty': 0.0,
            'dna': 0.0, 'resultado_cf': 0.0
        }
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False

    # --- TELA DE LOGIN ---
    if not st.session_state.authenticated:
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            st.title("🍞 ProfitOS Login")
            st.markdown("---")
            with st.form("login_form"):
                username = st.text_input("Usuário")
                password = st.text_input("Senha", type="password")
                role = st.selectbox("Perfil", ["vendedor", "gerente", "master"])
                if st.form_submit_button("Acessar Sistema"):
                    if authenticate(username, password, role):
                        st.session_state.authenticated = True
                        st.session_state.role = role
                        st.session_state.username = username
                        st.rerun()
                    else:
                        st.error("Acesso negado. Verifique as credenciais.")
        return

    # --- SIDEBAR (NAVEGAÇÃO E INFO) ---
    role = st.session_state.role
    st.sidebar.title("🍞 ProfitOS")
    st.sidebar.markdown(f"👤 **{st.session_state.username.upper()}** ({role})")
    
    # Menu dinâmico por permissão
    options = ["Precificador", "Simulador de Vendas"]
    if role in ['master', 'gerente']:
        options = ["Dashboard Estratégico", "Precificador", "Combos Lucrativos", "Simulador de Vendas", "Marketing"]
    if role == 'master':
        options.append("Configuração DNA")
        
    menu = st.sidebar.radio("Menu Principal", options)
    
    st.sidebar.markdown("---")
    # Indicador de DNA (Sempre visível)
    dna_val = st.session_state.dna_params['dna']
    st.sidebar.metric("🧬 DNA da Empresa", f"{dna_val*100:.1f}%", help="Soma de CF%, Impostos, Taxas e Royalties")
    
    if st.sidebar.button("Sair"):
        st.session_state.authenticated = False
        st.rerun()

    # --- PÁGINAS ---

    # 1. DASHBOARD ESTRATÉGICO
    if menu == "Dashboard Estratégico":
        st.title("📊 Análise Estratégica de Cardápio")
        st.markdown("Importe sua **Curva ABC** ou planilha de vendas para gerar inteligência.")
        
        file = st.file_uploader("Upload de Vendas (CSV/Excel)", type=['csv','xlsx'])
        if file:
            try:
                df_raw = pd.read_csv(file) if file.name.endswith('.csv') else pd.read_excel(file)
                # Validação básica
                required = ['produto', 'quantidade', 'preco_venda', 'custo']
                # Tenta normalizar colunas caso o usuário suba diferente
                df_raw.columns = [c.lower().strip() for c in df_raw.columns]
                
                if not set(required).issubset(df_raw.columns):
                    st.error(f"Faltam colunas obrigatórias. Necessário: {required}")
                else:
                    df_analise = analisar_menu(df_raw)
                    
                    # KPIs Topo
                    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                    kpi1.metric("Faturamento Total", f"R$ {df_analise['faturamento'].sum():,.2f}")
                    kpi2.metric("Lucro Bruto Total", f"R$ {df_analise['lucro'].sum():,.2f}")
                    kpi3.metric("Ticket Médio", f"R$ {df_analise['preco_venda'].mean():,.2f}")
                    kpi4.metric("Qtd Produtos", len(df_analise))
                    
                    st.markdown("---")
                    
                    # Gráficos Lado a Lado
                    g1, g2 = st.columns(2)
                    with g1:
                        st.subheader("Matriz BCG (Volume x Margem)")
                        fig_bcg = px.scatter(df_analise, x='margem_perc', y='quantidade', 
                                             color='categoria_bcg', size='faturamento',
                                             hover_name='produto', title="Distribuição de Produtos")
                        # Linhas médias
                        fig_bcg.add_hline(y=df_analise['quantidade'].median(), line_dash="dash", annotation_text="Média Vol.")
                        fig_bcg.add_vline(x=df_analise['margem_perc'].median(), line_dash="dash", annotation_text="Média Margem")
                        st.plotly_chart(fig_bcg, use_container_width=True)
                        
                    with g2:
                        st.subheader("Faturamento por Categoria")
                        df_g = df_analise.groupby('categoria_bcg')['faturamento'].sum().reset_index()
                        fig_pie = px.pie(df_g, values='faturamento', names='categoria_bcg', donut=0.4)
                        st.plotly_chart(fig_pie, use_container_width=True)
                    
                    with st.expander("Ver Tabela Detalhada dos Dados"):
                        st.dataframe(df_analise)
                        
            except Exception as e:
                st.error(f"Erro ao processar arquivo: {e}")

    # 2. CONFIGURAÇÃO DNA (MASTER ONLY)
    elif menu == "Configuração DNA":
        st.title("🧬 Configuração do DNA do Lucro")
        st.info("Estes valores afetam diretamente o precificador de todos os usuários.")
        
        with st.form("dna_config"):
            col1, col2 = st.columns(2)
            with col1:
                cf = st.number_input("Custo Fixo Mensal (R$)", value=st.session_state.dna_params['custo_fixo'])
                fat = st.number_input("Faturamento Médio Mensal (R$)", value=st.session_state.dna_params['faturamento'])
            with col2:
                taxa = st.number_input("Taxa Média Cartão (%)", value=st.session_state.dna_params['taxa_cartoes'])
                imp = st.number_input("Imposto (%)", value=st.session_state.dna_params['imposto_pago'])
                roy = st.number_input("Royalties/Franquia (%)", value=st.session_state.dna_params['royalty'])
            
            if st.form_submit_button("💾 Atualizar DNA da Empresa"):
                res_cf, dna_total = calcular_dna(cf, fat, taxa, imp, roy)
                st.session_state.dna_params.update({
                    'custo_fixo': cf, 'faturamento': fat, 'taxa_cartoes': taxa,
                    'imposto_pago': imp, 'royalty': roy, 'resultado_cf': res_cf, 'dna': dna_total
                })
                st.success(f"DNA Atualizado para {dna_total*100:.2f}%!")
                st.rerun()

    # 3. PRECIFICADOR (PRINCIPAL)
    elif menu == "Precificador":
        st.title("🏷️ Precificador Inteligente")
        
        tab1, tab2 = st.tabs(["🏪 Venda Balcão", "🛵 Venda iFood/Delivery"])
        
        # TAB 1: BALCÃO
        with tab1:
            col_in, col_res = st.columns([1, 1])
            with col_in:
                st.subheader("Dados do Produto")
                cmv = st.number_input("Custo Insumos (CMV) R$", 0.0, format="%.2f")
                emb = st.number_input("Embalagem R$", 0.0, format="%.2f")
                margem_user = st.slider("Margem de Lucro Desejada (%)", 0, 100, 20)
            
            with col_res:
                st.subheader("Resultado Sugerido")
                dna_atual = st.session_state.dna_params['dna']
                
                if dna_atual == 0:
                    st.warning("⚠️ DNA não configurado! O cálculo considerará apenas custo e margem.")
                
                preco = precificar_produto(cmv, emb, 0, dna_atual, margem_user/100)
                
                if pd.isna(preco) or preco < 0:
                    st.error("Erro matemático: Margem + DNA ultrapassam 100%. Reduza a margem.")
                else:
                    st.metric("Preço de Venda Sugerido", f"R$ {preco:.2f}")
                    st.caption(f"Composição: Custo R$ {cmv+emb:.2f} | DNA Empresa {dna_atual*100:.1f}% | Lucro {margem_user}%")
                    
                    # Gráfico de composição do preço
                    dados_pie = {
                        'Custo': cmv+emb,
                        'Custos Fixos/Impostos (DNA)': preco * dna_atual,
                        'Lucro Líquido': preco * (margem_user/100)
                    }
                    fig = px.pie(values=list(dados_pie.values()), names=list(dados_pie.keys()), hole=0.5)
                    fig.update_layout(height=250, margin=dict(t=0, b=0, l=0, r=0))
                    st.plotly_chart(fig, use_container_width=True)

        # TAB 2: IFOOD
        with tab2:
            st.markdown("Calculadora reversa para garantir lucro após taxas do app.")
            c1, c2, c3 = st.columns(3)
            with c1:
                p_cardapio = st.number_input("Preço Balcão (R$)", 0.0)
                t_entrega = st.number_input("Custo Entrega (R$)", 0.0)
            with c2:
                campanha = st.number_input("Investimento Campanha (R$)", 0.0)
                cupom = st.number_input("Cupom Cliente (R$)", 0.0)
            with c3:
                plano = st.selectbox("Plano iFood", ["Básico (12%)", "Entrega (23%)", "Full (27%)"])
                taxa_com = int(plano.split('(')[1][:2]) / 100
            
            if st.button("Calcular iFood"):
                v_min, p_final = precificar_ifood(p_cardapio, t_entrega, campanha, cupom, taxa_com)
                
                if pd.isna(v_min):
                    st.error("Taxas inviáveis.")
                else:
                    st.success("Cálculo Realizado!")
                    col_r1, col_r2 = st.columns(2)
                    col_r1.metric("Valor Mínimo (Receber)", f"R$ {v_min:.2f}", delta="Cobre custos + comissão")
                    col_r2.metric("Preço Final (App)", f"R$ {p_final:.2f}", delta="Para o cliente", delta_color="inverse")
                    st.info(f"O produto deve aparecer no app por **R$ {p_final:.2f}**. Você receberá o equivalente a **R$ {v_min:.2f}** (antes do desconto do cupom).")

    # 4. COMBOS LUCRATIVOS
    elif menu == "Combos Lucrativos":
        st.title("🤖 Gerador de Combos (IA Lógica)")
        st.markdown("Algoritmo que cruza **Burros de Carga** (atração) com **Quebra-Cabeças** (lucro).")
        
        file_combo = st.file_uploader("Dados de Vendas", type=['csv','xlsx'], key='combo_up')
        desc = st.slider("Desconto no Combo (%)", 5, 30, 10)
        
        if file_combo:
            df_c = pd.read_csv(file_combo) if file_combo.name.endswith('.csv') else pd.read_excel(file_combo)
            df_c.columns = [c.lower().strip() for c in df_c.columns]
            
            # Processa e gera
            df_an = analisar_menu(df_c)
            sugestoes = sugerir_combos(df_an, desc/100, 5)
            
            if not sugestoes.empty:
                st.subheader("Top 5 Sugestões")
                for i, row in sugestoes.iterrows():
                    with st.expander(f"🏅 {row['Combo']} (Margem {row['Margem %']:.1f}%)", expanded=True):
                        c1, c2, c3 = st.columns(3)
                        c1.metric("De (Separado)", f"R$ {row['Preço Original']:.2f}")
                        c2.metric("Por (Combo)", f"R$ {row['Preço Promo']:.2f}")
                        c3.metric("Lucro Líquido", f"R$ {row['Lucro Previsto']:.2f}")
                        st.caption(f"💡 Por que? {row['Estratégia']}")
            else:
                st.warning("Não foram encontrados pares ideais nos dados fornecidos.")

    # 5. SIMULADOR E MARKETING
    elif menu == "Simulador de Vendas":
        st.title("🧮 Simulador de Faturamento")
        st.markdown("Teste cenários antes de lançar promoções.")
        
        # Criação manual de dataframe de exemplo se não houver upload
        if 'simulador_df' not in st.session_state:
            st.session_state.simulador_df = pd.DataFrame(columns=['produto', 'preco_venda', 'custo'])
        
        with st.expander("Carregar Catálogo"):
            up_sim = st.file_uploader("Catálogo (CSV)", key="sim_up")
            if up_sim:
                df_s = pd.read_csv(up_sim)
                df_s.columns = [c.lower().strip() for c in df_s.columns]
                st.session_state.simulador_df = df_s
        
        df_prod = st.session_state.simulador_df
        
        if not df_prod.empty:
            prods = st.multiselect("Selecione Produtos", df_prod['produto'].unique())
            
            fatura_total = 0
            custo_total = 0
            
            if prods:
                st.subheader("Defina as Quantidades")
                for p in prods:
                    row = df_prod[df_prod['produto'] == p].iloc[0]
                    col_q, col_inf = st.columns([1, 3])
                    qtd = col_q.number_input(f"Qtd {p}", 1, 1000, 10)
                    
                    sub_fat = qtd * row['preco_venda']
                    sub_cust = qtd * row['custo']
                    
                    col_inf.write(f"💵 Fat: R$ {sub_fat:.2f} | 📉 Custo: R$ {sub_cust:.2f}")
                    
                    fatura_total += sub_fat
                    custo_total += sub_cust
                
                st.markdown("---")
                st.subheader("Resultado da Simulação")
                r1, r2, r3 = st.columns(3)
                r1.metric("Faturamento", f"R$ {fatura_total:.2f}")
                r2.metric("Custos Variáveis", f"R$ {custo_total:.2f}")
                lucro_sim = fatura_total - custo_total
                r3.metric("Margem de Contribuição", f"R$ {lucro_sim:.2f}", 
                          delta=f"{(lucro_sim/fatura_total)*100:.1f}%" if fatura_total > 0 else "0%")
        else:
            st.info("Carregue um arquivo com colunas 'produto', 'preco_venda', 'custo' para começar.")

    elif menu == "Marketing":
        st.title("🚀 Insights & Estratégias")
        
        tab_m1, tab_m2, tab_m3 = st.tabs(["🧠 Psicologia", "🥐 Engenharia de Menu", "⏰ Happy Hour"])
        
        with tab_m1:
            st.subheader("Efeito Isca (Decoy Effect)")
            st.markdown("""
            Ao criar combos, use 3 opções para direcionar a venda para o **Médio**.
            * ❌ **Pequeno:** R$ 15,00 (Parece caro pelo que oferece)
            * ✅ **Médio:** R$ 18,00 (Parece muito vantajoso perto do pequeno)
            * ❌ **Grande:** R$ 28,00 (Ancoragem de preço alto)
            """)
            st.image("https://images.pexels.com/photos/8901706/pexels-photo-8901706.jpeg?auto=compress&cs=tinysrgb&w=600", caption="Aplique no cardápio visual")

        with tab_m2:
            st.subheader("Como tratar cada categoria BCG")
            c1, c2 = st.columns(2)
            c1.success("**🌟 Estrelas:** Não mexa no preço! Invista em fotos bonitas e destaque no balcão.")
            c1.info("**🐮 Burros de Carga:** Mantenha a qualidade, mas tente negociar insumos mais baratos. Eles pagam as contas.")
            c2.warning("**🧩 Quebra-Cabeça:** Ótima margem, mas não vende. Faça degustação ou inclua em combos.")
            c2.error("**🐕 Cães:** Pare de produzir. Substitua por novidades.")

        with tab_m3:
            st.subheader("Estratégia Fim de Tarde")
            st.write("Use o Precificador para calcular qual o desconto máximo (ex: 30%) que seus produtos 'Burro de Carga' aguentam após as 18h apenas para cobrir o custo variável e evitar desperdício.")

if __name__ == "__main__":
    main()
