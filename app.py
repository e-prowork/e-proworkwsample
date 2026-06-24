
import streamlit as st
import sqlite3
from pathlib import Path
from datetime import datetime, date, time
import pandas as pd
import plotly.express as px
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

DB_PATH = Path("worksample.db")

st.set_page_config(
    page_title="E-Prowork | Work Sample MVP",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = """
<style>
:root {
    --azul-forte:#003B73;
    --azul-medio:#0074B7;
    --azul-claro:#BFD7ED;
    --branco:#FFFFFF;
    --preto:#111111;
}
.stApp { background: #f7fbff; }
.block-container { padding-top: 1.5rem; }
h1, h2, h3 { color: var(--azul-forte); }
[data-testid="stSidebar"] { background: linear-gradient(180deg, #003B73, #0074B7); }
[data-testid="stSidebar"] * { color: white !important; }
div.stButton > button {
    background-color: #0074B7;
    color: white;
    border-radius: 8px;
    border: 0;
    padding: .5rem 1rem;
    font-weight: 600;
}
div.stButton > button:hover {
    background-color: #003B73;
    color: white;
}
.metric-card {
    background: white;
    border: 1px solid #BFD7ED;
    border-radius: 12px;
    padding: 1rem;
    box-shadow: 0 1px 4px rgba(0,0,0,.06);
}
.header-box {
    background: linear-gradient(90deg, #003B73, #0074B7);
    color: white;
    padding: 1.2rem;
    border-radius: 14px;
    margin-bottom: 1rem;
}
.header-box h1, .header-box p { color:white; margin:0; }
.small-muted { color:#555; font-size:.9rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

DEFAULT_ACTIVITIES = [
    ("Produtiva", "Trabalhando"),
    ("Produtiva", "Planejando / lendo desenho ou procedimento"),
    ("Suplementar", "Recebendo instruções"),
    ("Suplementar", "Preparando para executar atividade"),
    ("Suplementar", "Aguardando ferramenta / material / informação"),
    ("Suplementar", "Trânsito"),
    ("Suplementar", "Assistindo atividade"),
    ("Não Produtiva", "Ociosidade forçada"),
    ("Não Produtiva", "Inativo / café / lanche"),
    ("Não Produtiva", "Ausente da área"),
]

def connect():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = connect()
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        cnpj TEXT,
        economic_activity TEXT,
        employee_count INTEGER,
        revenue_range TEXT,
        contact TEXT,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS sectors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        employee_count INTEGER,
        shift_count INTEGER,
        start_time TEXT,
        end_time TEXT,
        responsible TEXT,
        layout_notes TEXT,
        weekly_hours REAL DEFAULT 44,
        FOREIGN KEY(company_id) REFERENCES companies(id)
    );
    CREATE TABLE IF NOT EXISTS studies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sector_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        responsible_user TEXT,
        description TEXT,
        absolute_error REAL DEFAULT 0.02,
        correction_factor REAL DEFAULT 1.0,
        vacation_pct REAL DEFAULT 8.33,
        absence_pct REAL DEFAULT 3.0,
        status TEXT DEFAULT 'Aberto',
        created_at TEXT,
        FOREIGN KEY(sector_id) REFERENCES sectors(id)
    );
    CREATE TABLE IF NOT EXISTS activities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        study_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        name TEXT NOT NULL,
        FOREIGN KEY(study_id) REFERENCES studies(id)
    );
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        study_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        function TEXT,
        photo_path TEXT,
        active INTEGER DEFAULT 1,
        FOREIGN KEY(study_id) REFERENCES studies(id)
    );
    CREATE TABLE IF NOT EXISTS rounds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        study_id INTEGER NOT NULL,
        round_number INTEGER,
        start_at TEXT,
        end_at TEXT,
        notes TEXT,
        FOREIGN KEY(study_id) REFERENCES studies(id)
    );
    CREATE TABLE IF NOT EXISTS observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        round_id INTEGER NOT NULL,
        study_id INTEGER NOT NULL,
        employee_id INTEGER NOT NULL,
        activity_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        observed_at TEXT,
        comment TEXT,
        FOREIGN KEY(round_id) REFERENCES rounds(id),
        FOREIGN KEY(study_id) REFERENCES studies(id),
        FOREIGN KEY(employee_id) REFERENCES employees(id),
        FOREIGN KEY(activity_id) REFERENCES activities(id)
    );
    """)
    conn.commit()
    conn.close()

def q(sql, params=()):
    conn = connect()
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    return df

def exec_sql(sql, params=()):
    conn = connect()
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    last_id = cur.lastrowid
    conn.close()
    return last_id

def fx_by_people(n):
    if n <= 10: return 0.16
    if n <= 19: return 0.28
    if n <= 31: return 0.40
    if n <= 53: return 0.52
    if n <= 89: return 0.72
    if n <= 149: return 0.88
    return 1.00

def ensure_default_activities(study_id):
    existing = q("SELECT COUNT(*) as n FROM activities WHERE study_id=?", (study_id,)).iloc[0]["n"]
    if existing == 0:
        for cat, name in DEFAULT_ACTIVITIES:
            exec_sql("INSERT INTO activities(study_id, category, name) VALUES (?, ?, ?)", (study_id, cat, name))

def counts_by_category(study_id):
    df = q("""
        SELECT category, COUNT(*) as total
        FROM observations
        WHERE study_id=?
        GROUP BY category
    """, (study_id,))
    cats = {"Produtiva":0, "Suplementar":0, "Não Produtiva":0}
    for _, r in df.iterrows():
        cats[r["category"]] = int(r["total"])
    total = sum(cats.values())
    return cats, total

def study_selectbox(label="Selecione o estudo"):
    studies = q("""
        SELECT s.id, s.name as estudo, sec.name as setor, c.name as empresa
        FROM studies s
        JOIN sectors sec ON sec.id=s.sector_id
        JOIN companies c ON c.id=sec.company_id
        ORDER BY s.id DESC
    """)
    if studies.empty:
        st.warning("Cadastre uma empresa, setor e estudo primeiro.")
        return None
    studies["label"] = studies["empresa"] + " > " + studies["setor"] + " > " + studies["estudo"]
    label_to_id = dict(zip(studies["label"], studies["id"]))
    selected = st.selectbox(label, studies["label"].tolist())
    return int(label_to_id[selected])

def calc_required_observations(p, e, fx):
    if e <= 0:
        return 0
    return int(round((4 * p * (1 - p) / (e ** 2)) * fx))

def calc_final_error(p, n, fx):
    if n <= 0:
        return 0
    return ((4 * p * (1 - p) * fx) / n) ** 0.5

def export_excel(study_id):
    obs = q("""
        SELECT o.id, r.round_number as ronda, o.observed_at, e.name as funcionario,
               e.function as funcao, o.category as categoria, a.name as atividade, o.comment as comentario
        FROM observations o
        JOIN rounds r ON r.id=o.round_id
        JOIN employees e ON e.id=o.employee_id
        JOIN activities a ON a.id=o.activity_id
        WHERE o.study_id=?
        ORDER BY o.id
    """, (study_id,))
    cat = q("""
        SELECT category as categoria, COUNT(*) as observacoes
        FROM observations
        WHERE study_id=?
        GROUP BY category
    """, (study_id,))
    act = q("""
        SELECT o.category as categoria, a.name as atividade, COUNT(*) as observacoes
        FROM observations o
        JOIN activities a ON a.id=o.activity_id
        WHERE o.study_id=?
        GROUP BY o.category, a.name
        ORDER BY o.category, observacoes DESC
    """, (study_id,))
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        obs.to_excel(writer, index=False, sheet_name="Observacoes")
        cat.to_excel(writer, index=False, sheet_name="Resumo Categoria")
        act.to_excel(writer, index=False, sheet_name="Resumo Atividade")
    return output.getvalue()

def export_pdf(study_id):
    study = q("""
        SELECT s.*, sec.name as setor, sec.employee_count as funcionarios_setor, sec.weekly_hours, c.name as empresa
        FROM studies s
        JOIN sectors sec ON sec.id=s.sector_id
        JOIN companies c ON c.id=sec.company_id
        WHERE s.id=?
    """, (study_id,)).iloc[0]
    cats, total = counts_by_category(study_id)
    p_prod = cats["Produtiva"] / total if total else 0
    required = calc_required_observations(p_prod if total else 0.5, study["absolute_error"], study["correction_factor"])
    err = calc_final_error(p_prod, total, study["correction_factor"]) if total else 0

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setFillColorRGB(0, 0.23, 0.45)
    c.rect(0, h-3*cm, w, 3*cm, fill=True, stroke=False)
    c.setFillColorRGB(1,1,1)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(1.5*cm, h-1.3*cm, "E-Prowork | Relatório Work Sample")
    c.setFont("Helvetica", 10)
    c.drawString(1.5*cm, h-2.0*cm, f"Empresa: {study['empresa']} | Setor: {study['setor']} | Estudo: {study['name']}")
    y = h-4*cm
    c.setFillColorRGB(0,0,0)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1.5*cm, y, "Resumo Geral")
    y -= .8*cm
    c.setFont("Helvetica", 10)
    linhas = [
        f"Total de observações: {total}",
        f"Produtiva: {cats['Produtiva']} ({cats['Produtiva']/total*100 if total else 0:.1f}%)",
        f"Suplementar: {cats['Suplementar']} ({cats['Suplementar']/total*100 if total else 0:.1f}%)",
        f"Não Produtiva: {cats['Não Produtiva']} ({cats['Não Produtiva']/total*100 if total else 0:.1f}%)",
        f"Utilização: {(cats['Produtiva']+cats['Suplementar'])/total*100 if total else 0:.1f}%",
        f"Observações necessárias estimadas: {required}",
        f"Erro final estimado: {err*100:.2f}%",
    ]
    for linha in linhas:
        c.drawString(1.5*cm, y, linha)
        y -= .55*cm
    c.showPage()
    c.save()
    return buf.getvalue()

init_db()

st.sidebar.title("E-Prowork")
st.sidebar.caption("Work Sample MVP")
menu = st.sidebar.radio(
    "Menu",
    [
        "Início",
        "1. Empresa e Setor",
        "2. Estudo WS",
        "3. Funcionários",
        "4. Execução da Ronda",
        "5. Cálculo de Observações",
        "6. Dashboard e Relatórios",
    ],
)

st.markdown("""
<div class="header-box">
<h1>Work Sample MVP</h1>
<p>Demo funcional para cadastro, rondas, observações, cálculo de amostras e análise gerencial.</p>
</div>
""", unsafe_allow_html=True)

if menu == "Início":
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Empresas", len(q("SELECT id FROM companies")))
    c2.metric("Setores", len(q("SELECT id FROM sectors")))
    c3.metric("Estudos", len(q("SELECT id FROM studies")))
    c4.metric("Observações", len(q("SELECT id FROM observations")))
    st.subheader("Fluxo do MVP")
    st.write("1. Cadastre empresa e setor → 2. Abra o estudo Work Sample → 3. Cadastre funcionários → 4. Execute rondas → 5. Analise gráficos e exporte relatórios.")
    st.info("Usuário demo: não há controle de login nesta versão. O login deve ser incluído na versão comercial.")

elif menu == "1. Empresa e Setor":
    st.subheader("Cadastro de Empresa")
    with st.form("empresa"):
        col1, col2 = st.columns(2)
        name = col1.text_input("Nome da Empresa", "Empresa Demonstração")
        cnpj = col2.text_input("CNPJ", "")
        econ = col1.text_input("Atividade Econômica", "Indústria / Serviços")
        emp_count = col2.number_input("Número de Funcionários", min_value=1, value=50)
        revenue = col1.text_input("Faixa de Faturamento", "")
        contact = col2.text_area("Contato", "")
        if st.form_submit_button("Salvar Empresa"):
            exec_sql("""INSERT INTO companies(name, cnpj, economic_activity, employee_count, revenue_range, contact, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                     (name, cnpj, econ, emp_count, revenue, contact, datetime.now().isoformat()))
            st.success("Empresa salva.")

    companies = q("SELECT id, name FROM companies ORDER BY id DESC")
    if not companies.empty:
        st.subheader("Cadastro de Setor")
        comp_label = st.selectbox("Empresa", companies["name"].tolist())
        comp_id = int(companies.loc[companies["name"] == comp_label, "id"].iloc[0])
        with st.form("setor"):
            col1, col2, col3 = st.columns(3)
            sname = col1.text_input("Nome do Setor", "Manutenção")
            semployees = col2.number_input("Nº de Funcionários no Setor", min_value=1, value=15)
            shifts = col3.number_input("Nº de Turnos", min_value=1, value=1)
            stime = col1.time_input("Horário de Início", value=time(7,0))
            etime = col2.time_input("Horário de Término", value=time(17,0))
            whours = col3.number_input("Carga semanal por funcionário", min_value=1.0, value=44.0)
            resp = st.text_input("Responsável", "")
            notes = st.text_area("Arquivos/Layout/Observações do Setor", "")
            if st.form_submit_button("Salvar Setor"):
                exec_sql("""INSERT INTO sectors(company_id, name, employee_count, shift_count, start_time, end_time, responsible, layout_notes, weekly_hours)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                         (comp_id, sname, semployees, shifts, str(stime), str(etime), resp, notes, whours))
                st.success("Setor salvo.")

    st.subheader("Empresas e Setores Cadastrados")
    st.dataframe(q("""
        SELECT c.name as empresa, s.name as setor, s.employee_count as funcionarios, s.shift_count as turnos, s.responsible as responsavel
        FROM sectors s JOIN companies c ON c.id=s.company_id
        ORDER BY c.name, s.name
    """), use_container_width=True)

elif menu == "2. Estudo WS":
    sectors = q("""
        SELECT s.id, c.name || ' > ' || s.name as label, s.employee_count
        FROM sectors s JOIN companies c ON c.id=s.company_id
        ORDER BY s.id DESC
    """)
    if sectors.empty:
        st.warning("Cadastre uma empresa e um setor antes de abrir o estudo.")
    else:
        st.subheader("Abertura de Estudo Work Sample")
        selected = st.selectbox("Empresa > Setor", sectors["label"].tolist())
        sector_id = int(sectors.loc[sectors["label"] == selected, "id"].iloc[0])
        employee_count = int(sectors.loc[sectors["label"] == selected, "employee_count"].iloc[0])
        suggested_fx = fx_by_people(employee_count)
        with st.form("study"):
            name = st.text_input("Nome do Estudo", f"WS {date.today().strftime('%d/%m/%Y')}")
            resp = st.text_input("Usuário Responsável", "Administrador")
            desc = st.text_area("Descrição", "Estudo Work Sample conforme metodologia E-Prowork.")
            col1, col2 = st.columns(2)
            e = col1.number_input("Erro Absoluto", min_value=0.005, max_value=0.20, value=0.02, step=0.005, format="%.3f")
            fx = col2.number_input("Fator de Correção", min_value=0.01, max_value=1.0, value=float(suggested_fx), step=0.01, format="%.2f")
            if st.form_submit_button("Criar Estudo"):
                sid = exec_sql("""INSERT INTO studies(sector_id, name, responsible_user, description, absolute_error, correction_factor, created_at)
                                  VALUES (?, ?, ?, ?, ?, ?, ?)""",
                               (sector_id, name, resp, desc, e, fx, datetime.now().isoformat()))
                ensure_default_activities(sid)
                st.success("Estudo criado com lista padrão de atividades.")

        sid = study_selectbox("Editar atividades do estudo")
        if sid:
            ensure_default_activities(sid)
            st.markdown("### Atividades")
            acts = q("SELECT id, category as categoria, name as atividade FROM activities WHERE study_id=? ORDER BY category, name", (sid,))
            st.dataframe(acts, use_container_width=True, hide_index=True)
            with st.form("atividade"):
                col1, col2 = st.columns([1,2])
                cat = col1.selectbox("Categoria", ["Produtiva", "Suplementar", "Não Produtiva"])
                aname = col2.text_input("Nova Atividade")
                if st.form_submit_button("Adicionar Atividade") and aname:
                    exec_sql("INSERT INTO activities(study_id, category, name) VALUES (?, ?, ?)", (sid, cat, aname))
                    st.success("Atividade adicionada.")

elif menu == "3. Funcionários":
    sid = study_selectbox()
    if sid:
        st.subheader("Cadastro de Funcionários do Estudo")
        with st.form("employee"):
            col1, col2 = st.columns(2)
            name = col1.text_input("Nome do Funcionário")
            function = col2.text_input("Função")
            if st.form_submit_button("Salvar Funcionário") and name:
                exec_sql("INSERT INTO employees(study_id, name, function) VALUES (?, ?, ?)", (sid, name, function))
                st.success("Funcionário salvo.")
        st.dataframe(q("SELECT name as nome, function as funcao, active as ativo FROM employees WHERE study_id=? ORDER BY name", (sid,)), use_container_width=True)

elif menu == "4. Execução da Ronda":
    sid = study_selectbox()
    if sid:
        employees = q("SELECT id, name, function FROM employees WHERE study_id=? AND active=1 ORDER BY name", (sid,))
        activities = q("SELECT id, category, name FROM activities WHERE study_id=? ORDER BY category, name", (sid,))
        if employees.empty:
            st.warning("Cadastre funcionários antes de iniciar a ronda.")
        elif activities.empty:
            st.warning("Cadastre atividades antes de iniciar a ronda.")
        else:
            st.subheader("Nova Ronda")
            last_round = q("SELECT COALESCE(MAX(round_number),0) as n FROM rounds WHERE study_id=?", (sid,)).iloc[0]["n"]
            st.write(f"Próxima ronda: **{int(last_round)+1}**")
            with st.form("round_form"):
                st.caption("Selecione a atividade observada no instante da ronda para cada funcionário.")
                selections = {}
                comments = {}
                for _, emp in employees.iterrows():
                    st.markdown(f"**{emp['name']}** — {emp['function'] or ''}")
                    opts = [f"{r['category']} | {r['name']} | {r['id']}" for _, r in activities.iterrows()]
                    selections[int(emp["id"])] = st.selectbox("Atividade observada", opts, key=f"act_{emp['id']}")
                    comments[int(emp["id"])] = st.text_input("Comentário opcional", key=f"comm_{emp['id']}")
                    st.divider()
                notes = st.text_area("Observações gerais da ronda")
                submitted = st.form_submit_button("Salvar Ronda")
                if submitted:
                    start = datetime.now().isoformat(timespec="seconds")
                    rid = exec_sql("INSERT INTO rounds(study_id, round_number, start_at, end_at, notes) VALUES (?, ?, ?, ?, ?)",
                                   (sid, int(last_round)+1, start, start, notes))
                    for emp_id, sel in selections.items():
                        parts = sel.split(" | ")
                        cat, aname, aid = parts[0], parts[1], int(parts[2])
                        exec_sql("""INSERT INTO observations(round_id, study_id, employee_id, activity_id, category, observed_at, comment)
                                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                                 (rid, sid, emp_id, aid, cat, start, comments[emp_id]))
                    st.success("Ronda salva com sucesso.")
            cats, total = counts_by_category(sid)
            if total:
                st.markdown("### Status atual do estudo")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Observações", total)
                c2.metric("Produtiva", f"{cats['Produtiva']/total*100:.1f}%")
                c3.metric("Suplementar", f"{cats['Suplementar']/total*100:.1f}%")
                c4.metric("Não Produtiva", f"{cats['Não Produtiva']/total*100:.1f}%")

elif menu == "5. Cálculo de Observações":
    sid = study_selectbox()
    if sid:
        study = q("""
            SELECT s.*, sec.employee_count
            FROM studies s JOIN sectors sec ON sec.id=s.sector_id
            WHERE s.id=?
        """, (sid,)).iloc[0]
        cats, total = counts_by_category(sid)
        p_observed = cats["Produtiva"] / total if total else 0.5
        st.subheader("Cálculo de Observações Necessárias")
        col1, col2, col3 = st.columns(3)
        p = col1.number_input("P - % produtivo observado", min_value=0.01, max_value=0.99, value=float(p_observed), step=0.01, format="%.2f")
        e = col2.number_input("E - erro absoluto", min_value=0.005, max_value=0.20, value=float(study["absolute_error"]), step=0.005, format="%.3f")
        fx = col3.number_input("fx - fator de correção", min_value=0.01, max_value=1.00, value=float(study["correction_factor"]), step=0.01, format="%.2f")
        required = calc_required_observations(p, e, fx)
        err_final = calc_final_error(p, total, fx) if total else 0
        st.metric("Nº de observações necessárias", required)
        st.metric("Observações realizadas", total)
        st.metric("Erro final estimado", f"{err_final*100:.2f}%")
        if total:
            st.progress(min(total / required, 1.0) if required else 0)
        st.info("Fórmula: N = [4 × P × (1 - P) / E²] × fx. O fator fx pode ser sugerido conforme número de funcionários alocados.")

elif menu == "6. Dashboard e Relatórios":
    sid = study_selectbox()
    if sid:
        cats, total = counts_by_category(sid)
        st.subheader("Dashboard Work Sample")
        if total == 0:
            st.warning("Ainda não há observações para este estudo.")
        else:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Observações", total)
            col2.metric("Produtiva", f"{cats['Produtiva']/total*100:.1f}%")
            col3.metric("Suplementar", f"{cats['Suplementar']/total*100:.1f}%")
            col4.metric("Utilização", f"{(cats['Produtiva']+cats['Suplementar'])/total*100:.1f}%")

            df_cat = pd.DataFrame({"Categoria": list(cats.keys()), "Observações": list(cats.values())})
            fig = px.pie(df_cat, names="Categoria", values="Observações", title="Incidência por Categoria")
            st.plotly_chart(fig, use_container_width=True)

            df_act = q("""
                SELECT o.category as categoria, a.name as atividade, COUNT(*) as observacoes
                FROM observations o
                JOIN activities a ON a.id=o.activity_id
                WHERE o.study_id=?
                GROUP BY o.category, a.name
                ORDER BY observacoes DESC
            """, (sid,))
            fig2 = px.bar(df_act, x="atividade", y="observacoes", color="categoria", title="Observações por Atividade")
            st.plotly_chart(fig2, use_container_width=True)

            df_round = q("""
                SELECT r.round_number as ronda, o.category as categoria, COUNT(*) as observacoes
                FROM observations o
                JOIN rounds r ON r.id=o.round_id
                WHERE o.study_id=?
                GROUP BY r.round_number, o.category
                ORDER BY r.round_number
            """, (sid,))
            if not df_round.empty:
                fig3 = px.line(df_round, x="ronda", y="observacoes", color="categoria", markers=True, title="Resumo por Ronda")
                st.plotly_chart(fig3, use_container_width=True)

            df_hist = q("""
                SELECT strftime('%H:00', observed_at) as hora, category as categoria, COUNT(*) as observacoes
                FROM observations
                WHERE study_id=?
                GROUP BY hora, category
                ORDER BY hora
            """, (sid,))
            if not df_hist.empty:
                fig4 = px.bar(df_hist, x="hora", y="observacoes", color="categoria", title="Histograma por Hora")
                st.plotly_chart(fig4, use_container_width=True)

            st.markdown("### Exportações")
            st.download_button("Baixar Excel", data=export_excel(sid), file_name="work_sample_relatorio.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.download_button("Baixar PDF", data=export_pdf(sid), file_name="work_sample_relatorio.pdf", mime="application/pdf")
