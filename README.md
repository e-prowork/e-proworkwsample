
# E-Prowork Work Sample MVP

Demo funcional do módulo Work Sample com:
- Cadastro de empresa e setor
- Abertura de estudo WS
- Cadastro de atividades produtivas, suplementares e não produtivas
- Cadastro de funcionários
- Execução de rondas
- Cálculo de observações necessárias
- Dashboard com gráficos
- Exportação Excel e PDF

## Como rodar localmente

1. Instale Python 3.10 ou superior.
2. Abra o terminal nesta pasta.
3. Crie o ambiente virtual:

```bash
python -m venv .venv
```

4. Ative o ambiente:

Windows:
```bash
.venv\Scripts\activate
```

Mac/Linux:
```bash
source .venv/bin/activate
```

5. Instale as dependências:

```bash
pip install -r requirements.txt
```

6. Rode o aplicativo:

```bash
streamlit run app.py
```

## Como postar no GitHub

```bash
git init
git add .
git commit -m "MVP Work Sample E-Prowork"
git branch -M main
git remote add origin https://github.com/SEU-USUARIO/eprowork-worksample-mvp.git
git push -u origin main
```

## Como publicar no Streamlit Cloud

1. Suba este projeto para o GitHub.
2. Acesse https://share.streamlit.io
3. Conecte seu GitHub.
4. Selecione o repositório.
5. Main file path: `app.py`
6. Clique em Deploy.

## Observação

Esta é uma versão MVP/demo. Para versão comercial, recomenda-se:
- Login por usuário
- Banco PostgreSQL
- Controle por empresa/cliente
- Upload real de fotos e áudios
- Permissões de acesso
- API backend
- Backup e LGPD
