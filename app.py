from flask import Flask, render_template, request, redirect, url_for, session, make_response, jsonify, flash
from datetime import datetime, timedelta
from io import BytesIO
from flask_dance.contrib.google import make_google_blueprint, google
from dotenv import load_dotenv
import os
import sqlite3
import secrets
from reportlab.pdfgen import canvas
from flask_socketio import SocketIO, emit, join_room
import bcrypt
import re
import random
import smtplib
from email.mime.text import MIMEText
import hashlib

os.makedirs('database', exist_ok=True)

# Módulos internos
from modules.user import (
    create_user_table, create_solicitacoes_table, register_user, login_user, create_loans_table,
    salvar_emprestimo, listar_emprestimos_ativos, listar_emprestimos_finalizados,
    pagar_juros, quitar_emprestimo, listar_emprestimos_pendentes,
    emprestimos_vencendo, verificar_e_adicionar_coluna_status,
    verificar_e_adicionar_coluna_cliente, verificar_e_adicionar_coluna_renovacoes,
    create_user_status_table
)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
socketio = SocketIO(app, cors_allowed_origins="*")

@app.route('/mensagens/nao-lidas')
def contar_mensagens_nao_lidas():
    if 'user' not in session:
        return jsonify({'count': 0})
    
    user = session['user']
    try:
        conn = sqlite3.connect('database/finflow.db')
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) FROM mensagens 
            WHERE destinatario = ? AND lida = 0
        """, (user,))
        
        count = cursor.fetchone()[0]
        return jsonify({'count': count})
        
    except Exception as e:
        print(f"Erro ao contar mensagens não lidas: {e}")
        return jsonify({'count': 0})
        
    finally:
        conn.close()

# Página inicial
@app.route('/')
def home():
    if 'user' in session:
        return redirect(url_for('painel'))
    return render_template('home.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', user=session['user'])

# Painel principal com gráfico
@app.route('/painel')
def painel():
    if session.get('tipo') == 'solicitante':
        return render_template('painel_solicitante.html', usuario=session['user'])

    if 'user' not in session or session.get('tipo') != 'emprestador':
        return redirect(url_for('login', mensagem="Acesso negado. Faça login como Emprestador."))

    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()

    # Consultar solicitações de amizade pendentes
    cursor.execute("""
        SELECT COUNT(*) FROM amigos
        WHERE amigo = ? AND status = 'pendente'
    """, (session['user'],))
    solicitacoes_amizade = cursor.fetchone()[0]

    # Totais de empréstimos aprovados
    cursor.execute("SELECT COUNT(*), SUM(valor), SUM(total) FROM loans WHERE nome = ? AND pago = 0 AND status = 'aprovado'", (session['user'],))
    qtd, valor_total, total_com_juros = cursor.fetchone()

    # Empréstimos por status
    cursor.execute("SELECT status, COUNT(*) FROM loans WHERE nome = ? GROUP BY status", (session['user'],))
    status_data = cursor.fetchall()
    conn.close()

    # Preparar dados para gráfico
    todos_status = ['pendente', 'aprovado', 'quitado']
    status_dict = {row[0]: row[1] for row in status_data}

    status_labels = []
    status_values = []
    status_colors = []

    cores = {
        'pendente': '#f1c40f',  # amarelo
        'aprovado': '#3498db',  # azul
        'quitado': '#e67e22'    # laranja
    }

    for status in todos_status:
        count = status_dict.get(status, 0)
        status_labels.append(status.capitalize())
        status_values.append(count)
        status_colors.append(cores.get(status.lower(), '#95a5a6'))  # cinza padrão

    # ✅ Adicionando vencimento próximo
    from modules.user import emprestimos_vencendo
    vencendo = emprestimos_vencendo(session['user'])

    return render_template('index.html',
        usuario=session['user'],
        qtd=qtd or 0,
        valor_total=valor_total or 0,
        total_com_juros=total_com_juros or 0,
        status_labels=status_labels,
        status_values=status_values,
        status_colors=status_colors,
        vencendo=vencendo,
        solicitacoes_amizade=solicitacoes_amizade  # 👈 isso aqui!
    )

# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    mensagem = request.args.get('mensagem')
    erro = ""

    if request.method == 'POST':
        email = request.form['email']
        senha = request.form.get('password')

        conn = sqlite3.connect('database/finflow.db')
        cursor = conn.cursor()
        cursor.execute("SELECT nome, tipo, senha FROM usuarios WHERE email = ?", (email,))
        resultado = cursor.fetchone()
        conn.close()

        if resultado:
            nome_db, tipo_db, senha_db = resultado
            # Hash da senha com bcrypt
            if bcrypt.checkpw(senha.encode('utf-8'), senha_db.encode('utf-8')):
                session.permanent = True
                session['user'] = nome_db
                session['tipo'] = tipo_db  # Armazena o tipo

                # Redireciona para o painel correto
                if tipo_db == 'solicitante':
                    return redirect(url_for('painel_solicitante'))
                else:
                    return redirect(url_for('painel'))

        erro = "E-mail ou senha inválidos. Verifique seus dados."

    return render_template('login.html', erro=erro, mensagem=mensagem)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Coleta de dados do formulário
        nome = request.form.get('nome')
        email = request.form.get('email')
        senha = request.form.get('password')
        tipo = request.form.get('tipo')
        cpf = request.form.get('cpf')
        data_nascimento = request.form.get('data_nascimento')
        
        # Validações básicas
        if not all([nome, email, senha, tipo]):
            return render_template('register.html', erro="Todos os campos obrigatórios devem ser preenchidos.")
        
        # Validação de e-mail
        if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
            return render_template('register.html', erro="Por favor, insira um e-mail válido.")
        
        # Verifica se e-mail já existe
        conn = sqlite3.connect('database/finflow.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
        if cursor.fetchone():
            conn.close()
            return render_template('register.html', erro="Este e-mail já está cadastrado.")
        
        # Verificação de força da senha
        if len(senha) < 8 or not re.search(r'[A-Z]', senha) or not re.search(r'[0-9]', senha):
            conn.close()
            return render_template('register.html', erro="A senha deve ter pelo menos 8 caracteres, incluindo uma letra maiúscula e um número.")
        
        # Coleta dados adicionais para solicitantes
        celular = request.form.get('celular')
        endereco = request.form.get('endereco') if tipo == 'solicitante' else None
        
        # Gera código de verificação
        codigo = str(random.randint(100000, 999999))
        
        # Hash da senha com bcrypt
        senha_hash = bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt())
        
        # Salva dados na sessão
        session['cadastro'] = {
        'nome': nome,
        'email': email,
        'senha_hash': senha_hash.decode('utf-8'),
        'tipo': tipo,
        'celular': celular,
        'endereco': endereco,
        'cpf': cpf,
        'data_nascimento': data_nascimento,
        'codigo': codigo,
        'expira': datetime.now().timestamp() + 300
        }

        
        # Envia e-mail de verificação
        try:
            enviar_email_verificacao(email, codigo)
            return redirect(url_for('verificar_cadastro'))
        except Exception as e:
            print(f"Erro ao enviar e-mail: {e}")
            return render_template('register.html', erro="Erro ao enviar e-mail de verificação. Por favor, tente novamente.")
        
    return render_template('register.html')

def enviar_email_verificacao(destinatario, codigo):
    """Função para enviar e-mail de verificação"""
    remetente = os.getenv("EMAIL_REMETENTE")
    senha_app = os.getenv("EMAIL_SENHA")
    
    mensagem_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Código de Verificação - RMCred</title>
        <style>
            body {{
                font-family: 'Segoe UI', Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                text-align: center;
                padding-bottom: 20px;
                border-bottom: 1px solid #eaeaea;
            }}
            .logo {{
                color: #2a7de1;
                font-size: 24px;
                font-weight: bold;
                margin-bottom: 10px;
            }}
            .code-container {{
                background: #f8f9fa;
                border-radius: 8px;
                padding: 20px;
                text-align: center;
                margin: 25px 0;
                border: 1px dashed #2a7de1;
            }}
            .verification-code {{
                font-size: 28px;
                font-weight: bold;
                letter-spacing: 2px;
                color: #343a40;
                margin: 15px 0;
            }}
            .footer {{
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #eaeaea;
                font-size: 12px;
                color: #6c757d;
            }}
            .warning {{
                background-color: #fff3cd;
                padding: 10px;
                border-radius: 5px;
                margin: 15px 0;
                font-size: 14px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo">RMCred</div>
            <h2 style="color: #2a7de1; margin-bottom: 5px;">Código de Verificação</h2>
            <p style="color: #6c757d;">Confirmação de cadastro</p>
        </div>
        
        <p>Olá,</p>
        <p>Recebemos uma solicitação para cadastro no sistema RMCred. Utilize o seguinte código para confirmar seu e-mail:</p>
        
        <div class="code-container">
            <p style="margin-bottom: 5px;">Seu código de verificação é:</p>
            <div class="verification-code">{codigo}</div>
            <p style="font-size: 14px; color: #dc3545;">Válido por 5 minutos</p>
        </div>
        
        <div class="warning">
            <strong>Importante:</strong> Nunca compartilhe este código com terceiros, mesmo que afirmem ser da equipe RMCred.
        </div>
        
        <p>Se você não solicitou este código, por favor ignore este e-mail.</p>
        
        <div class="footer">
            <p>© {datetime.now().year} RMCred - Todos os direitos reservados</p>
            <p>Este é um e-mail automático, por favor não responda.</p>
        </div>
    </body>
    </html>
    """
    
    msg = MIMEText(mensagem_html, 'html')
    msg['Subject'] = "🔒 Código de Verificação RMCred"
    msg['From'] = remetente
    msg['To'] = destinatario
    
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(remetente, senha_app)
        smtp.send_message(msg)

# Logout
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))

# Simulador
@app.route('/simular', methods=['GET', 'POST'])
def simular():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        cliente = request.form['cliente']
        valor = float(request.form['valor'])
        juros = float(request.form['juros'])
        dias = int(request.form['dias'])
        observacoes = request.form.get('observacoes')

        meses = dias / 30
        total = valor + (valor * (juros / 100))
        vencimento = datetime.now() + timedelta(days=dias)

        dados = {
            'cliente': cliente,
            'valor': valor,
            'juros': juros,
            'dias': dias,
            'total': round(total, 2),
            'vencimento': vencimento.strftime('%Y-%m-%d'),
            'observacoes': observacoes
        }
        return render_template('simulador.html', dados=dados)

    return render_template('simulador.html')


@app.route('/salvar_simulacao', methods=['POST'])
def salvar_simulacao():
    if 'user' not in session:
        return redirect(url_for('login'))

    nome = session['user']
    cliente = request.form['cliente']
    valor = float(request.form['valor'])
    juros = float(request.form['juros'])
    dias = int(request.form['dias'])
    total = float(request.form['total'])
    vencimento = request.form['vencimento']
    observacoes = request.form.get('observacoes')

    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO loans (nome, cliente, valor, juros, dias, total, vencimento, status, observacoes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (nome, cliente, valor, juros, dias, total, vencimento, 'pendente', observacoes))
    conn.commit()
    conn.close()

    return redirect(url_for('aprovacoes'))

# Empréstimos ativos
@app.route('/emprestimos')
def emprestimos():
    if 'user' not in session or session.get('tipo') != 'emprestador':
        return redirect(url_for('login', mensagem="Acesso negado. Faça login como Emprestador."))

    dados_raw = listar_emprestimos_ativos(session['user'])

    dados = []
    hoje = datetime.now().date()
    vencendo = 0

    for emp_row in dados_raw:
        emp = dict(emp_row)  # transforma o Row em dict editável

        if 'vencimento' in emp and emp['vencimento']:
            data_venc = datetime.strptime(emp['vencimento'][:10], '%Y-%m-%d').date()
            dias_para_vencer = (data_venc - hoje).days
            emp['dias_para_vencer'] = dias_para_vencer

            if 0 <= dias_para_vencer <= 2:
                vencendo += 1
        else:
            emp['dias_para_vencer'] = 999  # sem data de vencimento, joga pro final

        dados.append(emp)

    dados.sort(key=lambda x: x['dias_para_vencer'])

    return render_template('emprestimos.html', emprestimos=dados, vencendo=vencendo)

# Empréstimos finalizados
@app.route('/emprestimos_finalizados')
def emprestimos_finalizados():
    if 'user' not in session or session.get('tipo') != 'emprestador':
        return redirect(url_for('login', mensagem="Acesso negado. Faça login como Emprestador."))

    dados = listar_emprestimos_finalizados(session['user'])
    return render_template('emprestimos_finalizados.html', emprestimos=dados)

# Aprovações pendentes
@app.route('/aprovacoes')
def aprovacoes():
    if 'user' not in session or session.get('tipo') != 'emprestador':
        return redirect(url_for('login', mensagem="Acesso negado. Faça login como Emprestador."))
    pendentes = listar_emprestimos_pendentes(session['user'])
    return render_template('aprovacoes.html', emprestimos=pendentes)

# Aprovar empréstimo
@app.route('/aprovar/<int:id>')
def aprovar_emprestimo(id):
    if 'user' not in session or session.get('tipo') != 'emprestador':
        return redirect(url_for('login', mensagem="Acesso negado."))

    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()

    # Verifica se o empréstimo é do usuário
    cursor.execute("SELECT nome FROM loans WHERE id = ?", (id,))
    resultado = cursor.fetchone()

    if not resultado or resultado[0] != session['user']:
        conn.close()
        return "Acesso negado. Empréstimo não encontrado ou não é seu."

    cursor.execute("UPDATE loans SET status = 'aprovado' WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('aprovacoes'))

# Rejeitar empréstimo
@app.route('/rejeitar/<int:id>')
def rejeitar_emprestimo(id):
    if 'user' not in session or session.get('tipo') != 'emprestador':
        return redirect(url_for('login', mensagem="Acesso negado."))

    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()

    # Verifica se o empréstimo é do usuário logado
    cursor.execute("SELECT nome FROM loans WHERE id = ?", (id,))
    resultado = cursor.fetchone()

    if not resultado or resultado[0] != session['user']:
        conn.close()
        return "Acesso negado. Empréstimo não encontrado ou não é seu."

    cursor.execute("DELETE FROM loans WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for('aprovacoes'))

# Quitar empréstimo
@app.route('/quitar/<int:id>')
def quitar(id):
    if 'user' not in session or session.get('tipo') != 'emprestador':
        return redirect(url_for('login', mensagem="Acesso negado. Faça login como Emprestador."))

    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute('SELECT nome FROM loans WHERE id = ?', (id,))
    dono = cursor.fetchone()

    if not dono or dono[0] != session['user']:
        return "Acesso negado. Este empréstimo não é seu."

    cursor.execute('UPDATE loans SET pago = 1, status = "quitado" WHERE id = ?', (id,))
    conn.commit()
    conn.close()

    return redirect(url_for('emprestimos'))

# Renovar empréstimo (pagar apenas juros)
@app.route('/pagar_juros/<int:id>')
def pagar_juros(id):
    if 'user' not in session or session.get('tipo') != 'emprestador':
        return redirect(url_for('login', mensagem="Acesso negado. Faça login como Emprestador."))

    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()

    cursor.execute('SELECT nome, vencimento, dias FROM loans WHERE id = ?', (id,))
    dados = cursor.fetchone()

    if not dados:
        return "Empréstimo não encontrado."

    nome, vencimento_str, dias = dados

    if nome != session['user']:
        return "Acesso negado. Este empréstimo não é seu."

    vencimento_atual = datetime.strptime(vencimento_str, '%Y-%m-%d')
    novo_vencimento = vencimento_atual + timedelta(days=dias)
    novo_vencimento_str = novo_vencimento.strftime('%Y-%m-%d')

    cursor.execute('''
    UPDATE loans
    SET vencimento = ?, renovacoes = renovacoes + 1
    WHERE id = ?
''', (novo_vencimento_str, id))
    conn.commit()
    conn.close()

    return redirect(url_for('emprestimos'))

# Deletar empréstimo finalizado
@app.route('/deletar/<int:id>')
def deletar_emprestimo(id):
    if 'user' not in session or session.get('tipo') != 'emprestador':
        return redirect(url_for('login', mensagem="Acesso negado. Faça login como Emprestador."))

    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()

    # Verifica se o empréstimo pertence ao usuário logado
    cursor.execute("SELECT nome FROM loans WHERE id = ?", (id,))
    resultado = cursor.fetchone()

    if not resultado or resultado[0] != session['user']:
        conn.close()
        return "Acesso negado. Empréstimo não encontrado ou não é seu."

    cursor.execute("DELETE FROM loans WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for('emprestimos_finalizados'))

# Gerar relatório em PDF
from flask import make_response
from io import BytesIO
from reportlab.pdfgen import canvas

@app.route('/relatorio')
def gerar_pdf():
    if 'user' not in session or session.get('tipo') != 'emprestador':
        return redirect(url_for('login', mensagem="Acesso negado. Faça login como Emprestador."))

    
    buffer = BytesIO()
    p = canvas.Canvas(buffer)
    y = 800

    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, y, "Relatório de Empréstimos - RMCred")
    y -= 30

    p.setFont("Helvetica", 12)
    p.drawString(50, y, "Empréstimos Ativos:")
    y -= 20

    # Ativos
    ativos = listar_emprestimos_ativos(session['user'])
    for emp in ativos:
        texto = (
            f"Cliente: {emp['cliente']} | Valor: R${emp['valor']} | "
            f"Juros: {emp['juros']}% | Total: R${emp['total']} | "
            f"Vencimento: {emp['vencimento']}"
        )
        p.drawString(50, y, texto)
        y -= 20
        if y < 100:
            p.showPage()
            y = 800

    y -= 20
    p.drawString(50, y, "Empréstimos Finalizados:")
    y -= 20

    # Finalizados
    finalizados = listar_emprestimos_finalizados(session['user'])
    for emp in finalizados:
        texto = (
            f"Cliente: {emp['cliente']} | Valor: R${emp['valor']} | "
            f"Juros: {emp['juros']}% | Total: R${emp['total']} | "
            f"Vencimento: {emp['vencimento']}"
        )
        p.drawString(50, y, texto)
        y -= 20
        if y < 100:
            p.showPage()
            y = 800

    p.save()
    buffer.seek(0)

    return make_response(buffer.read(), {
        'Content-Type': 'application/pdf',
        'Content-Disposition': 'attachment; filename="relatorio_rmc.pdf"'
    })

# Página de recuperação de senha
@app.route('/recuperar', methods=['GET', 'POST'])
def recuperar():
    if request.method == 'POST':
        email = request.form['email']
        codigo = str(random.randint(100000, 999999))

        conn = sqlite3.connect('database/finflow.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()

        if user:
            # Salva e expira o código em 5 minutos
            session['recupera_email'] = email
            session['codigo_verificacao'] = codigo
            session['codigo_expira'] = datetime.now().timestamp() + 300  # 5 minutos

            # Envia e-mail
            remetente = os.getenv("EMAIL_REMETENTE")
            senha_app = os.getenv("EMAIL_SENHA")
            mensagem_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Recuperação de Senha - RMCred</title>
                <style>
                    body {{
                        font-family: 'Segoe UI', Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 20px;
                    }}
                    .header {{
                        text-align: center;
                        padding-bottom: 20px;
                        border-bottom: 1px solid #eaeaea;
                    }}
                    .logo {{
                        color: #3498db;
                        font-size: 24px;
                        font-weight: bold;
                        margin-bottom: 10px;
                    }}
                    .code-container {{
                        background: #f8f9fa;
                        border-radius: 8px;
                        padding: 20px;
                        text-align: center;
                        margin: 25px 0;
                        border: 1px dashed #3498db;
                    }}
                    .verification-code {{
                        font-size: 28px;
                        font-weight: bold;
                        letter-spacing: 2px;
                        color: #2c3e50;
                        margin: 15px 0;
                    }}
                    .footer {{
                        margin-top: 30px;
                        padding-top: 20px;
                        border-top: 1px solid #eaeaea;
                        font-size: 12px;
                        color: #7f8c8d;
                    }}
                    .warning {{
                        background-color: #fff3cd;
                        padding: 10px;
                        border-radius: 5px;
                        margin: 15px 0;
                        font-size: 14px;
                    }}
                    .instructions {{
                        background-color: #e8f4fd;
                        padding: 15px;
                        border-radius: 5px;
                        margin: 15px 0;
                        font-size: 14px;
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <div class="logo">RMCred</div>
                    <h2 style="color: #3498db; margin-bottom: 5px;">Recuperação de Senha</h2>
                    <p style="color: #7f8c8d;">Redefinição de acesso à sua conta</p>
                </div>
                
                <p>Olá,</p>
                <p>Recebemos uma solicitação para redefinir a senha da sua conta RMCred. Utilize o seguinte código de verificação para prosseguir:</p>
                
                <div class="code-container">
                    <p style="margin-bottom: 5px;">Seu código de segurança é:</p>
                    <div class="verification-code">{codigo}</div>
                    <p style="font-size: 14px; color: #e74c3c;">Válido por apenas 5 minutos</p>
                </div>
                
                <div class="instructions">
                    <strong><i class="fas fa-info-circle"></i> Como usar este código:</strong>
                    <ol style="margin: 10px 0 0 20px; padding-left: 15px;">
                        <li>Volte à página de recuperação de senha</li>
                        <li>Insira o código acima no campo indicado</li>
                        <li>Siga as instruções para criar uma nova senha</li>
                    </ol>
                </div>
                
                <div class="warning">
                    <strong><i class="fas fa-exclamation-triangle"></i> Segurança:</strong> 
                    <ul style="margin: 10px 0 0 20px; padding-left: 15px;">
                        <li>Nunca compartilhe este código</li>
                        <li>A equipe RMCred nunca pedirá seu código por telefone ou e-mail</li>
                        <li>Se não solicitou esta redefinição, proteja sua conta alterando sua senha</li>
                    </ul>
                </div>
                
                <div class="footer">
                    <p>© {datetime.now().year} RMCred - Todos os direitos reservados</p>
                    <p>Este é um e-mail automático, por favor não responda.</p>
                    <p style="margin-top: 5px;"><small>ID da solicitação: {secrets.token_hex(8)}</small></p>
                </div>
            </body>
            </html>
            """

            msg = MIMEText(mensagem_html, 'html')
            msg['Subject'] = "🔑 Redefinição de Senha RMCred - Código de Segurança"
            msg['From'] = remetente
            msg['To'] = email

            try:
                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                    smtp.login(remetente, senha_app)
                    smtp.send_message(msg)
                return redirect('/verificar')
            except Exception as e:
                return f"Erro ao enviar e-mail: {e}"
        else:
            return render_template('recuperar.html', erro="E-mail não encontrado.")

    return render_template('recuperar.html')

@app.route('/reenviar_codigo')
def reenviar_codigo():
    if 'cadastro' not in session:
        return redirect(url_for('register'))
    
    try:
        # Gera novo código
        novo_codigo = str(random.randint(100000, 999999))
        session['cadastro']['codigo'] = novo_codigo
        session['cadastro']['expira'] = datetime.now().timestamp() + 300  # 5 minutos
        
        # Reenvia e-mail
        enviar_email_verificacao(session['cadastro']['email'], novo_codigo)
        return redirect(url_for('verificar_cadastro'))
    except Exception as e:
        print(f"Erro ao reenviar código: {e}")
        return redirect(url_for('verificar_cadastro', erro="Erro ao reenviar código. Tente novamente."))

@app.route('/verificar', methods=['GET', 'POST'])
def verificar_codigo():
    if request.method == 'POST':
        codigo = request.form['codigo']
        nova_senha = request.form['nova_senha']

        # Verifica se o código existe e não expirou
        codigo_salvo = session.get('codigo_verificacao')
        expira = session.get('codigo_expira')

        if not codigo_salvo or not expira:
            return render_template('verificar.html', erro="Código não encontrado. Solicite outro.")

        if datetime.now().timestamp() > expira:
            return render_template('verificar.html', erro="⏰ Código expirado. Solicite outro.")

        if codigo != codigo_salvo:
            return render_template('verificar.html', erro="❌ Código incorreto. Tente novamente.")

        # Atualiza a senha
        email = session.get('recupera_email')
        senha_hash = bcrypt.hashpw(nova_senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        conn = sqlite3.connect('database/finflow.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE usuarios SET senha = ? WHERE email = ?", (senha_hash, email))
        conn.commit()
        conn.close()

        session.pop('codigo_verificacao', None)
        session.pop('codigo_expira', None)
        session.pop('recupera_email', None)

        return redirect(url_for('login', mensagem='Senha alterada com sucesso!'))

    return render_template('verificar.html')

@app.route('/verificar_cadastro', methods=['GET', 'POST'])
def verificar_cadastro():
    if 'cadastro' not in session:
        return redirect(url_for('register'))

    if request.method == 'POST':
        # Combina os dígitos individuais em um código completo
        codigo_digitado = ''.join([
            request.form.get('digit1', ''),
            request.form.get('digit2', ''),
            request.form.get('digit3', ''),
            request.form.get('digit4', ''),
            request.form.get('digit5', ''),
            request.form.get('digit6', '')
        ])

        cadastro = session['cadastro']

        if datetime.now().timestamp() > cadastro['expira']:
            return render_template('verificar_cadastro.html', erro="⏰ Código expirado. Refaça o cadastro.")

        if not codigo_digitado.isdigit() or len(codigo_digitado) != 6:
            return render_template('verificar_cadastro.html', erro="O código deve conter 6 dígitos numéricos.")
        # Verifica se o código digitado corresponde ao código salvo na sessão
        if codigo_digitado != str(cadastro['codigo']):
            return render_template('verificar_cadastro.html', erro="❌ Código incorreto. Tente novamente.")

        # Código correto, salva o usuário
        conn = sqlite3.connect('database/finflow.db')
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
            INSERT INTO usuarios (nome, email, senha, tipo, celular, endereco, cpf, data_nascimento)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cadastro['nome'], cadastro['email'], cadastro['senha_hash'], cadastro['tipo'],
            cadastro.get('celular'), cadastro.get('endereco'),
            cadastro.get('cpf'), cadastro.get('data_nascimento')
        ))
            conn.commit()
            
            # Limpa sessão
            session.pop('cadastro', None)
            
            return redirect(url_for('login', mensagem='Cadastro realizado com sucesso!'))
        except Exception as e:
            print(f"Erro ao cadastrar usuário: {e}")
            return render_template('verificar_cadastro.html', erro="Erro ao cadastrar. Tente novamente.")
        finally:
            conn.close()

    return render_template('verificar_cadastro.html')

@app.route('/check_email', methods=['POST'])
def check_email():
    if not request.is_json:
        return jsonify({'error': 'Content-Type must be application/json'}), 415
    
    data = request.get_json()
    email = data.get('email')
    
    if not email:
        return jsonify({'error': 'Email não fornecido'}), 400
    
    try:
        conn = sqlite3.connect('database/finflow.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
        exists = cursor.fetchone() is not None
        return jsonify({'exists': exists})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

def verificar_e_adicionar_coluna_observacoes():
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN is_google_auth BOOLEAN DEFAULT 0")
        conn.commit()
        print("✅ Coluna 'is_google_auth' adicionada com sucesso.")
    except:
        print("ℹ️ Coluna 'is_google_auth' já existe.")
    conn.close()

import sqlite3

def adicionar_coluna_lida():
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN data_nascimento TEXT;")
        conn.commit()
        print("✅ Coluna 'data nascimento' adicionada com sucesso")
    except sqlite3.OperationalError:
        print("ℹ️ Coluna 'data nascimento' já existe")
    conn.close()

@app.route('/solicitar', methods=['GET', 'POST'])
def solicitar():
    if 'user' not in session or session.get('tipo') != 'solicitante':
        return redirect(url_for('login', mensagem="Acesso negado. Faça login como Solicitante."))

    if request.method == 'POST':
        try:
            emprestador = request.form['emprestador']
            valor = float(request.form['valor'])
            juros = float(request.form['juros'])
            dias = int(request.form['dias'])
            mensagem = request.form.get('mensagem', '')

            # Verifica se o emprestador é realmente amigo
            conn = sqlite3.connect('database/finflow.db')
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM amigos 
                WHERE ((solicitante = ? AND amigo = ?) OR (solicitante = ? AND amigo = ?))
                AND status = 'aprovado'
            """, (session['user'], emprestador, emprestador, session['user']))
            
            if not cursor.fetchone():
                conn.close()
                return render_template('solicitar.html', 
                                    emprestadores=get_amigos(session['user']),
                                    erro="Você só pode solicitar empréstimos a amigos aprovados.")

            # Continua com a solicitação
            cursor.execute("""
                INSERT INTO solicitacoes (solicitante, emprestador, valor, juros, dias, mensagem)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (session['user'], emprestador, valor, juros, dias, mensagem))
            conn.commit()
            conn.close()
            
            dados = {
                'valor': valor,
                'juros': juros,
                'dias': dias,
                'emprestador': emprestador
            }
            return render_template("solicitacao_sucesso.html", dados_solicitacao=dados)
            
        except Exception as e:
            print(f"Erro ao processar solicitação: {e}")
            return render_template('solicitar.html', 
                                emprestadores=get_amigos(session['user']),
                                erro="Erro ao processar solicitação. Verifique os dados.")

    return render_template('solicitar.html', emprestadores=get_amigos(session['user']))

def get_amigos(usuario):
    """Retorna apenas amigos aprovados do usuário"""
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            CASE WHEN solicitante = ? THEN amigo ELSE solicitante END
        FROM amigos
        WHERE (solicitante = ? OR amigo = ?) AND status = 'aprovado'
    """, (usuario, usuario, usuario))
    amigos = [row[0] for row in cursor.fetchall()]
    conn.close()
    return amigos

@app.route('/solicitacoes')
def ver_solicitacoes():
    if 'user' not in session:
        return redirect(url_for('login'))
    if 'user' not in session or session.get('tipo') != 'emprestador':
        return redirect(url_for('login', mensagem="Acesso negado. Faça login como Emprestador."))

    conn = sqlite3.connect('database/finflow.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM solicitacoes WHERE emprestador = ?", (session['user'],))
    dados = cursor.fetchall()
    conn.close()

    return render_template('painel_solicitacoes.html', solicitacoes=dados)

@app.route('/aprovar_solicitacao/<int:id>')
def aprovar_solicitacao(id):
    if 'user' not in session or session.get('tipo') != 'emprestador':
        return redirect(url_for('login', mensagem="Acesso negado. Faça login como Emprestador."))

    conn = sqlite3.connect('database/finflow.db')
    conn.row_factory = sqlite3.Row  # 👈 Importante!
    cursor = conn.cursor()

    # Verifica se o usuário é o dono da solicitação
    cursor.execute("SELECT * FROM solicitacoes WHERE id = ? AND emprestador = ?", (id, session['user']))
    solicitacao = cursor.fetchone()

    if not solicitacao:
        return "Solicitação não encontrada ou acesso negado."

    # Adiciona aos empréstimos
    solicitante, valor, juros, dias, observacao = solicitacao[1], solicitacao[3], solicitacao[4], solicitacao[5], solicitacao[7]
    total = round(valor + (valor * (juros / 100)), 2)
    vencimento = (datetime.now() + timedelta(days=dias)).strftime('%Y-%m-%d')

    cursor.execute("""
        INSERT INTO loans (nome, valor, juros, dias, total, vencimento, status, cliente, pago, renovacoes, observacoes)
        VALUES (?, ?, ?, ?, ?, ?, 'aprovado', ?, 0, 0, ?)
        """, (session['user'], valor, juros, dias, total, vencimento, solicitante, observacao))

    # Atualiza o status da solicitação
    cursor.execute("UPDATE solicitacoes SET status = 'aprovado' WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for('ver_solicitacoes'))

@app.route('/recusar_solicitacao/<int:id>')
def recusar_solicitacao(id):
    if 'user' not in session or session.get('tipo') != 'emprestador':
        return redirect(url_for('login', mensagem="Acesso negado. Faça login como Emprestador."))

    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE solicitacoes SET status = 'recusado' WHERE id = ? AND emprestador = ?", (id, session['user']))
    conn.commit()
    conn.close()
    return redirect(url_for('ver_solicitacoes'))

@app.route('/editar_solicitacao/<int:id>', methods=['GET', 'POST'])
def editar_solicitacao(id):
    if 'user' not in session or session.get('tipo') != 'emprestador':
        return redirect(url_for('login', mensagem="Acesso negado."))

    origem = request.args.get('origem')  # 👈 Corrigido: pegar origem da URL no GET

    conn = sqlite3.connect('database/finflow.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == 'POST':
        valor = float(request.form['valor'])
        juros = float(request.form['juros'])
        dias = int(request.form['dias'])
        origem = request.form.get('origem')

        if origem not in ['loans', 'solicitacoes']:
            conn.close()
            return "Origem inválida.", 400

        if origem == 'loans':
            observacoes = request.form.get('observacoes', '')
            meses = dias / 30
            total = valor + (valor * (juros / 100))

            cursor.execute("""
                UPDATE loans SET valor = ?, juros = ?, dias = ?, total = ?, observacoes = ?
                WHERE id = ?
            """, (valor, juros, dias, round(total, 2), observacoes, id))
            conn.commit()
            conn.close()
            return redirect(url_for('aprovacoes'))
        else:
            mensagem = request.form.get('mensagem', '')
            cursor.execute("""
                UPDATE solicitacoes SET valor = ?, juros = ?, dias = ?, mensagem = ?
                WHERE id = ?
            """, (valor, juros, dias, mensagem, id))
            conn.commit()
            conn.close()
            return redirect(url_for('ver_solicitacoes'))

    # --- GET ---
    if origem == 'loans':
        cursor.execute("SELECT * FROM loans WHERE id = ?", (id,))
        emprestimo = cursor.fetchone()
    else:
        cursor.execute("SELECT * FROM solicitacoes WHERE id = ?", (id,))
        emprestimo = cursor.fetchone()

    if not emprestimo:
        conn.close()
        return "Solicitação não encontrada", 404

    conn.close()
    return render_template('editar_solicitacao.html', emprestimo=emprestimo, origem=origem)

@app.route('/painel_solicitante')
def painel_solicitante():
    if 'user' not in session or session.get('tipo') != 'solicitante':
        return redirect(url_for('login', mensagem="Acesso negado. Faça login como Solicitante."))
    
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()

    # Consultar solicitações de amizade pendentes
    cursor.execute("""
        SELECT COUNT(*) FROM amigos
        WHERE amigo = ? AND status = 'pendente'
    """, (session['user'],))
    solicitacoes_amizade = cursor.fetchone()[0]
    
    return render_template(
        'painel_solicitante.html',
        usuario=session['user'],
        solicitacoes_amizade=solicitacoes_amizade
    )

@app.route('/minhas_solicitacoes')
def minhas_solicitacoes():
    if 'user' not in session or session.get('tipo') != 'solicitante':
        return redirect(url_for('login'))

    pagina = int(request.args.get('pagina', 1))
    por_pagina = 10
    inicio = (pagina - 1) * por_pagina

    conn = sqlite3.connect('database/finflow.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM solicitacoes WHERE solicitante = ?", (session['user'],))
    total = cursor.fetchone()[0]

    cursor.execute("""
        SELECT * FROM solicitacoes
        WHERE solicitante = ?
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """, (session['user'], por_pagina, inicio))
    dados = cursor.fetchall()
    conn.close()

    total_paginas = (total + por_pagina - 1) // por_pagina

    return render_template(
        'minhas_solicitacoes.html',
        solicitacoes=dados,
        pagina=pagina,
        total_paginas=total_paginas
    )

@app.route('/excluir_solicitacao/<int:id>', methods=['POST'])
def excluir_solicitacao(id):
    if 'user' not in session or session.get('tipo') != 'solicitante':
        return redirect(url_for('login', mensagem="Acesso negado. Faça login como Solicitante."))

    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    
    # Verifica se a solicitação é do usuário e está pendente
    cursor.execute("SELECT status FROM solicitacoes WHERE id = ? AND solicitante = ?", 
    (id, session['user']))
    resultado = cursor.fetchone()
    
    if not resultado or resultado[0] != 'pendente':
        conn.close()
        return redirect(url_for('minhas_solicitacoes'))
    
    cursor.execute("DELETE FROM solicitacoes WHERE id = ? AND solicitante = ?", (id, session['user']))
    conn.commit()
    conn.close()

    return redirect(url_for('minhas_solicitacoes'))

@app.route('/emprestimos_aprovados')
def emprestimos_aprovados():
    if 'user' not in session or session.get('tipo') != 'solicitante':
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('database/finflow.db')
    conn.row_factory = sqlite3.Row  # Isso permite acesso como dicionário
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, cliente, valor, juros, dias, total, 
        vencimento, status, observacoes
        FROM loans 
        WHERE cliente = ? AND status = 'aprovado'
        ORDER BY vencimento DESC
    """, (session['user'],))
    
    emprestimos = []
    hoje = datetime.now().date()
    
    for row in cursor.fetchall():
        emp = {
            'id': row['id'],
            'valor': row['valor'],
            'juros': row['juros'],
            'dias': row['dias'],
            'total': row['total'],
            'vencimento': datetime.strptime(row['vencimento'], '%Y-%m-%d').date(),
            'status': row['status']
        }
        
        dias_restantes = (emp['vencimento'] - hoje).days
        dias_restantes = max(0, dias_restantes)
        
        emp['percentual_pago'] = min(100, int((emp['dias'] - dias_restantes) / emp['dias'] * 100))
        emp['dias_restantes'] = dias_restantes
        emprestimos.append(emp)
    
    return render_template('emprestimos_aprovados.html', emprestimos=emprestimos)

@socketio.on('join_chat')
def handle_join_chat(data):
    user = data['user']
    destinatario = data['destinatario']
    
    # Entra nas salas de chat (bidirecional)
    join_room(f"{user}_{destinatario}")
    join_room(f"{destinatario}_{user}")
    
    print(f"Usuário {user} entrou na conversa com {destinatario}")

@socketio.on('digitando')
def handle_digitando(data):
    # Envia apenas para o destinatário
    emit('usuario_digitando', data, room=f"{data['destinatario']}_{data['remetente']}")

@socketio.on('parou_digitando')
def handle_parou_digitando(data):
    # Notifica que o usuário parou de digitar
    emit('usuario_parou_digitando', data, room=f"{data['destinatario']}_{data['remetente']}")

@socketio.on('enviar_mensagem')
def handle_enviar_mensagem(data):
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    
    hora_brasil = datetime.utcnow() - timedelta(hours=3)
    data_formatada = hora_brasil.strftime('%d/%m/%Y %H:%M')
    
    cursor.execute("""
        INSERT INTO mensagens (remetente, destinatario, mensagem, data_envio, lida) 
        VALUES (?, ?, ?, ?, ?)
    """, (data['remetente'], data['destinatario'], data['conteudo'], data_formatada, 0))
    conn.commit()
    
    # Obter contagem atualizada de mensagens não lidas
    cursor.execute("""
        SELECT COUNT(*) FROM mensagens 
        WHERE destinatario = ? AND lida = 0
    """, (data['destinatario'],))
    unread_count = cursor.fetchone()[0]
    conn.close()
    
    # Envia a mensagem e a atualização da contagem
    emit('nova_mensagem', {
        'remetente': data['remetente'],
        'destinatario': data['destinatario'],
        'conteudo': data['conteudo'],
        'horario': data_formatada
    }, room=f"{data['remetente']}_{data['destinatario']}")
    
    emit('nova_mensagem', {
        'remetente': data['remetente'],
        'destinatario': data['destinatario'],
        'conteudo': data['conteudo'],
        'horario': data_formatada
    }, room=f"{data['destinatario']}_{data['remetente']}")
    
    # Atualiza a contagem para o destinatário
    emit('atualizar_contagem', {
        'count': unread_count
    }, room=data['destinatario'])

@app.route('/mensagens')
def mensagens():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute("""
        SELECT amigo FROM amigos 
        WHERE solicitante = ? AND status = 'aprovado'
        UNION
        SELECT solicitante FROM amigos 
        WHERE amigo = ? AND status = 'aprovado'
    """, (user, user))
    usuarios = [r[0] for r in cursor.fetchall()]
    conn.close()

    return render_template('mensagens.html', usuarios=usuarios)

@app.route('/mensagem/<destinatario>', methods=['GET', 'POST'])
def conversa(destinatario):
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']

    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()

    if request.method == 'POST':
        mensagem = request.form['mensagem']
        hora_brasil = datetime.utcnow() - timedelta(hours=3)
        data_formatada = hora_brasil.strftime('%d/%m/%Y %H:%M')
        
        cursor.execute("""
            INSERT INTO mensagens (remetente, destinatario, mensagem, data_envio, lida) 
            VALUES (?, ?, ?, ?, ?)
        """, (user, destinatario, mensagem, data_formatada, 0))
        conn.commit()
        
        # Emitir a mensagem via Socket.IO
        socketio.emit('nova_mensagem', {
            'remetente': user,
            'destinatario': destinatario,
            'conteudo': mensagem,
            'horario': data_formatada
        }, room=f"{user}_{destinatario}")
        socketio.emit('nova_mensagem', {
            'remetente': user,
            'destinatario': destinatario,
            'conteudo': mensagem,
            'horario': data_formatada
        }, room=f"{destinatario}_{user}")

    cursor.execute("""
        SELECT remetente, mensagem, data_envio FROM mensagens
        WHERE (remetente = ? AND destinatario = ?) OR (remetente = ? AND destinatario = ?)
        ORDER BY data_envio ASC
    """, (user, destinatario, destinatario, user))
    mensagens = cursor.fetchall()
    conn.close()

    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE mensagens SET lida = 1 
        WHERE destinatario = ? AND remetente = ? AND lida = 0
    """, (session['user'], destinatario))
    conn.commit()
    conn.close()
    
    # Emitir atualização de contagem
    socketio.emit('atualizar_contagem', {'count': 0}, room=session['user'])

    return render_template('conversa.html', mensagens=mensagens, destinatario=destinatario)

@app.route('/usuarios')
def lista_usuarios_para_conversar():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']

    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    
    # Agora busca apenas AMIGOS com status aprovado
    cursor.execute("""
        SELECT 
            CASE WHEN solicitante = ? THEN amigo ELSE solicitante END
        FROM amigos
        WHERE (solicitante = ? OR amigo = ?) AND status = 'aprovado'
    """, (user, user, user))

    usuarios = cursor.fetchall()
    conn.close()

    return render_template('lista_usuarios.html', usuarios=usuarios)

@app.route('/buscar', methods=['GET', 'POST'])
def buscar_usuario():
    if 'user' not in session:
        return redirect(url_for('login'))

    resultados = []
    if request.method == 'POST':
        termo = request.form['termo']
        conn = sqlite3.connect('database/finflow.db')
        cursor = conn.cursor()
        cursor.execute("""
            SELECT nome FROM usuarios 
            WHERE nome LIKE ? AND nome != ?
        """, (f'%{termo}%', session['user']))
        resultados = [r[0] for r in cursor.fetchall()]
        conn.close()

    return render_template('buscar.html', resultados=resultados)

@app.route('/adicionar_amigo/<nome>')
def adicionar_amigo(nome):
    if 'user' not in session:
        return redirect(url_for('login'))

    solicitante = session['user']
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    
    try:
        # Verifica se já existe solicitação entre esses usuários
        cursor.execute("""
            SELECT id FROM amigos 
            WHERE (solicitante = ? AND amigo = ?)
            OR (solicitante = ? AND amigo = ?)
        """, (solicitante, nome, nome, solicitante))
        
        if cursor.fetchone():
            flash(f'Você e {nome} já têm uma conexão pendente ou confirmada! 🌟', 'info')

            conn.close()  # Fecha a conexão ANTES do redirect
            return redirect(url_for('buscar_usuario'))
        
        # Cria nova solicitação
        cursor.execute("""
            INSERT INTO amigos (solicitante, amigo, status) 
            VALUES (?, ?, 'pendente')
        """, (solicitante, nome))
        
        conn.commit()
        flash(f'Solicitação de amizade enviada com para  {nome}!', 'success')
    
    except sqlite3.IntegrityError as e:
        print(f"Erro de banco de dados: {e}")
        flash('Erro ao enviar solicitação de amizade', 'danger')
    
    finally:
        conn.close()
    
    return redirect(url_for('buscar_usuario'))

@app.route('/solicitacoes_amizade')
def solicitacoes_amizade():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    
    # Busca solicitações pendentes para o usuário atual
    cursor.execute("""
        SELECT a.id, a.solicitante 
        FROM amigos a
        WHERE a.amigo = ? AND a.status = 'pendente'
    """, (user,))
    
    solicitacoes = cursor.fetchall()
    conn.close()

    return render_template('solicitacoes_amizade.html', solicitacoes=solicitacoes)

@app.route('/aprovar_amizade/<int:id>')
def aprovar_amizade(id):
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    
    try:
        # Verifica se a solicitação é para o usuário atual
        cursor.execute("""
            SELECT amigo FROM amigos 
            WHERE id = ? AND status = 'pendente'
        """, (id,))
        
        resultado = cursor.fetchone()
        
        if not resultado or resultado[0] != session['user']:
            flash('Solicitação não encontrada', 'danger')
            return redirect(url_for('solicitacoes_amizade'))
        
        # Aprova a solicitação
        cursor.execute("""
            UPDATE amigos 
            SET status = 'aprovado' 
            WHERE id = ?
        """, (id,))
        
        conn.commit()
        flash('Amizade aprovada com sucesso!', 'success')
    
    except sqlite3.Error as e:
        print(f"Erro ao aprovar amizade: {e}")
        flash('Erro ao aprovar amizade', 'danger')
    
    finally:
        conn.close()
    
    return redirect(url_for('solicitacoes_amizade'))

@app.route('/recusar_amizade/<int:id>')
def recusar_amizade(id):
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    
    try:
        # Verifica se a solicitação é para o usuário atual
        cursor.execute("""
            SELECT amigo FROM amigos 
            WHERE id = ? AND status = 'pendente'
        """, (id,))
        
        resultado = cursor.fetchone()
        
        if not resultado or resultado[0] != session['user']:
            flash('Solicitação não encontrada', 'danger')
            return redirect(url_for('solicitacoes_amizade'))
        
        # Remove a solicitação
        cursor.execute("DELETE FROM amigos WHERE id = ?", (id,))
        
        conn.commit()
        flash('Solicitação recusada', 'info')
    
    except sqlite3.Error as e:
        print(f"Erro ao recusar amizade: {e}")
        flash('Erro ao recusar amizade', 'danger')
    
    finally:
        conn.close()
    
    return redirect(url_for('solicitacoes_amizade'))

@app.route('/editar_perfil', methods=['GET', 'POST'])
def editar_perfil():
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    
    # Verifica se o usuário tem empréstimos pendentes ou aprovados em qualquer uma das tabelas
    cursor.execute("""
        SELECT COUNT(*) FROM loans 
        WHERE cliente = ?
        AND status IN ('pendente', 'aprovado')
    """, (session['user'],))
    loans_count = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM solicitacoes 
        WHERE solicitante = ?
        AND status IN ('pendente')
    """, (session['user'],))
    solicitacoes_count = cursor.fetchone()[0]

    tem_emprestimos_pendentes = (loans_count + solicitacoes_count) > 0

    if request.method == 'POST':
        # Obter dados atuais primeiro
        cursor.execute("SELECT nome, celular, endereco FROM usuarios WHERE nome = ?", (session['user'],))
        dados_atuais = cursor.fetchone()
        
        # Se não encontrar usuário, redireciona com mensagem de erro
        if not dados_atuais:
            flash('Usuário não encontrado', 'error')
            conn.close()
            return redirect(url_for('editar_perfil'))
        
        novo_nome = request.form.get('nome')
        novo_celular = request.form.get('celular') or dados_atuais[1] or ''
        novo_endereco = request.form.get('endereco') or dados_atuais[2] or ''

        # Se tentar mudar nome com empréstimos pendentes
        if tem_emprestimos_pendentes and novo_nome != session['user']:
            flash('Você não pode alterar seu nome enquanto tiver empréstimos pendentes', 'error')
            conn.close()
            # Mantém os valores submetidos exceto o nome
            return render_template('editar_perfil.html',
                dados=(session['user'], '', novo_celular, novo_endereco),
                tem_emprestimos_pendentes=tem_emprestimos_pendentes)

        try:
            cursor.execute("""
                UPDATE usuarios 
                SET nome = ?, celular = ?, endereco = ? 
                WHERE nome = ?
            """, (novo_nome, novo_celular, novo_endereco, session['user']))
            conn.commit()
            
            # Atualiza sessão apenas se o nome mudou
            if novo_nome != session['user']:
                session['user'] = novo_nome
            
            flash('Perfil atualizado com sucesso!', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Erro ao atualizar perfil: {str(e)}', 'error')
        finally:
            conn.close()
        
        return redirect(url_for('editar_perfil'))

    # GET request
    cursor.execute("SELECT nome, email, celular, endereco FROM usuarios WHERE nome = ?", (session['user'],))
    dados = cursor.fetchone()
    
    # Se não encontrar usuário, redireciona para login
    if not dados:
        conn.close()
        return redirect(url_for('login'))
    
    conn.close()

    return render_template('editar_perfil.html', 
        dados=dados,
        tem_emprestimos_pendentes=tem_emprestimos_pendentes)

@app.route('/configuracoes_conta')
def configuracoes_conta():
    if 'user' not in session:
        return redirect(url_for('login'))

    return render_template('configuracoes_conta.html')

@app.route('/ver_amigos')
def ver_amigos():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']
    conn = sqlite3.connect('database/finflow.db')
    conn.row_factory = sqlite3.Row  # 👈 importante!
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            CASE
                WHEN a.solicitante = ? THEN a.amigo
                ELSE a.solicitante
            END AS nome_amigo,
            a.status
        FROM amigos a
        WHERE (a.solicitante = ? OR a.amigo = ?)
        AND a.status = 'aprovado'
    """, (user, user, user))
    
    amigos = cursor.fetchall()
    conn.close()

    return render_template('ver_amigos.html', amigos=amigos)

@app.route('/remover_amigo/<nome>')
def remover_amigo(nome):
    if 'user' not in session:
        return redirect(url_for('login'))

    user = session['user']
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()

    try:
        # Verifica se há empréstimos PENDENTES ou ATIVOS entre os dois (ambas direções)
        cursor.execute("""
            SELECT COUNT(*) FROM loans
            WHERE (
                (cliente = ? AND nome = ?) OR 
                (cliente = ? AND nome = ?)
            ) AND status IN ('pendente', 'aprovado')
        """, (user, nome, nome, user))
        loans_count = cursor.fetchone()[0]

        # Verifica se há solicitações ainda PENDENTES entre os dois (ambas direções)
        cursor.execute("""
            SELECT COUNT(*) FROM solicitacoes
            WHERE (
                (solicitante = ? AND emprestador = ?) OR 
                (solicitante = ? AND emprestador = ?)
            ) AND status = 'pendente'
        """, (user, nome, nome, user))
        solicitacoes_count = cursor.fetchone()[0]

        if loans_count + solicitacoes_count > 0:
            flash("❌ Você não pode desfazer a amizade enquanto houver empréstimos pendentes ou ativos entre vocês.", "error")
            return redirect(url_for('ver_amigos'))

        # Remove amizade
        cursor.execute("""
            DELETE FROM amigos 
            WHERE (solicitante = ? AND amigo = ?) OR (solicitante = ? AND amigo = ?)
        """, (user, nome, nome, user))
        conn.commit()

        flash(f"✅ Amizade com {nome} foi removida com sucesso.", "info")
    
    except Exception as e:
        print(f"Erro ao remover amigo: {e}")
        flash("Erro ao remover amigo.", "error")
    
    finally:
        conn.close()

    return redirect(url_for('ver_amigos'))

def criar_banco_e_tabelas():
    create_user_table()
    create_loans_table()
    create_solicitacoes_table()
    verificar_e_adicionar_coluna_status()
    verificar_e_adicionar_coluna_cliente()
    verificar_e_adicionar_coluna_renovacoes()
    verificar_e_adicionar_coluna_observacoes()
    create_user_status_table()
    adicionar_coluna_lida()

# Chama a função sempre que o app iniciar
criar_banco_e_tabelas()

if __name__ == '__main__':
    import eventlet
    eventlet.monkey_patch()
    socketio.run(app, host='0.0.0.0', port=5000)