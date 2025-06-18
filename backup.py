from flask import Flask, render_template, request, redirect, url_for, session, make_response
from datetime import datetime, timedelta
from io import BytesIO
import sqlite3
from reportlab.pdfgen import canvas

# Módulos internos
from modules.user import (
    create_user_table, register_user, login_user, create_loans_table,
    salvar_emprestimo, listar_emprestimos_ativos, listar_emprestimos_finalizados,
    pagar_juros, quitar_emprestimo, listar_emprestimos_pendentes,
    emprestimos_vencendo, verificar_e_adicionar_coluna_status,
    verificar_e_adicionar_coluna_cliente, verificar_e_adicionar_coluna_renovacoes
)

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# Página inicial
@app.route('/')
def home():
    if 'user' in session:
        return redirect(url_for('painel'))
    return render_template('home.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

# Painel principal com gráfico
@app.route('/painel')
def painel():
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()

    # Totais de empréstimos aprovados
    cursor.execute("SELECT COUNT(*), SUM(valor), SUM(total) FROM loans WHERE nome = ? AND pago = 0 AND status = 'aprovado'", (session['user'],))
    qtd, valor_total, total_com_juros = cursor.fetchone()

    # Empréstimos por status
    cursor.execute("SELECT status, COUNT(*) FROM loans WHERE nome = ? GROUP BY status", (session['user'],))
    status_data = cursor.fetchall()
    conn.close()

    # Preparar dados para gráfico
    status_labels = [row[0].capitalize() for row in status_data]
    status_values = [row[1] for row in status_data]

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
        vencendo=vencendo
    )

# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        nome = login_user(email, password)
        if nome:
            session['user'] = nome
            return redirect(url_for('painel'))
        return render_template('login.html', erro="Login falhou.")
    return render_template('login.html')

# Registro de usuário
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nome = request.form['nome']
        email = request.form['email']
        senha = request.form['password']
        sucesso, mensagem = register_user(nome, email, senha)
        if sucesso:
            return redirect(url_for('login'))
        return render_template('register.html', erro=mensagem)
    return render_template('register.html')

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

    resultado = None
    if request.method == 'POST':
        try:
            cliente = request.form['cliente']
            valor = float(request.form['valor'])
            juros = float(request.form['juros'])
            dias = int(request.form['dias'])

            if not cliente.strip() or valor <= 0 or juros <= 0 or dias <= 0:
                raise ValueError("Preencha todos os campos corretamente.")

            total = valor + (valor * (juros / 100))
            vencimento = datetime.now() + timedelta(days=dias)

            salvar_emprestimo(cliente, valor, juros, dias, total, vencimento.strftime('%Y-%m-%d'), session['user'])

            resultado = {
                'cliente': cliente,
                'valor': valor,
                'juros': juros,
                'dias': dias,
                'total': round(total, 2),
                'vencimento': vencimento.strftime('%d/%m/%Y')
            }
        except Exception as e:
            print(f"Erro: {e}")
            resultado = 'Erro ao calcular. Verifique os dados.'

    return render_template('simulador.html', resultado=resultado, mostrar_botoes=True)

# Empréstimos ativos
@app.route('/emprestimos')
def emprestimos():
    if 'user' not in session:
        return redirect(url_for('login'))
    dados = listar_emprestimos_ativos(session['user'])
    return render_template('emprestimos.html', emprestimos=dados)

# Empréstimos finalizados
@app.route('/finalizados')
def emprestimos_finalizados():
    if 'user' not in session:
        return redirect(url_for('login'))
    dados = listar_emprestimos_finalizados(session['user'])
    return render_template('emprestimos_finalizados.html', emprestimos=dados)

# Aprovações pendentes
@app.route('/aprovacoes')
def aprovacoes():
    if 'user' not in session:
        return redirect(url_for('login'))
    pendentes = listar_emprestimos_pendentes(session['user'])
    return render_template('aprovacoes.html', emprestimos=pendentes)

# Aprovar empréstimo
@app.route('/aprovar/<int:id>')
def aprovar_emprestimo(id):
    if 'user' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE loans SET status = 'aprovado' WHERE id = ? AND nome = ?", 
    (id, session['user']))
    conn.commit()
    conn.close()
    return redirect(url_for('aprovacoes'))

# Rejeitar empréstimo
@app.route('/rejeitar/<int:id>')
def rejeitar_emprestimo(id):
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM loans WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('aprovacoes'))

# Quitar empréstimo
@app.route('/quitar/<int:id>')
def quitar(id):
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute('SELECT nome FROM loans WHERE id = ?', (id,))
    dono = cursor.fetchone()

    if not dono or dono[0] != session['user']:
        return "Acesso negado. Este empréstimo não é seu."

    cursor.execute('UPDATE loans SET pago = 1 WHERE id = ?', (id,))
    conn.commit()
    conn.close()

    return redirect(url_for('emprestimos'))

# Renovar empréstimo (pagar apenas juros)
@app.route('/pagar_juros/<int:id>')
def pagar_juros(id):
    if 'user' not in session:
        return redirect(url_for('login'))

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
@app.route('/deletar/<int:id>', methods=['POST'])
def deletar(id):
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute("SELECT nome, pago FROM loans WHERE id = ?", (id,))
    dados = cursor.fetchone()

    if not dados or dados[0] != session['user'] or dados[1] != 1:
        conn.close()
        return "Acesso negado ou empréstimo ainda não quitado."

    cursor.execute("DELETE FROM loans WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('emprestimos_finalizados'))

# Gerar relatório em PDF
@app.route('/relatorio')
def gerar_pdf():
    if 'user' not in session:
        return redirect(url_for('login'))

    try:
        buffer = BytesIO()
        p = canvas.Canvas(buffer)
        y = 800

        p.setFont("Helvetica-Bold", 16)
        p.drawString(50, y, f"Relatório - {session['user']}")
        y -= 40

        # Empréstimos Ativos
        p.setFont("Helvetica-Bold", 14)
        p.drawString(50, y, "Empréstimos Ativos:")
        y -= 30

        ativos = listar_emprestimos_ativos(session['user'])
        p.setFont("Helvetica", 12)
        for emp in ativos:
            texto = (f"Cliente: {emp[8]} | Valor: R${emp[2]:.2f} | "
                    f"Juros: {emp[3]}% | Total: R${emp[5]:.2f} | "
                    f"Vencimento: {emp[6]}")
            p.drawString(50, y, texto)
            y -= 20
            if y < 100:
                p.showPage()
                y = 800

        # Empréstimos Finalizados
        y -= 30
        p.setFont("Helvetica-Bold", 14)
        p.drawString(50, y, "Empréstimos Finalizados:")
        y -= 30

        finalizados = listar_emprestimos_finalizados(session['user'])
        p.setFont("Helvetica", 12)
        for emp in finalizados:
            texto = (f"Cliente: {emp[8]} | Valor: R${emp[2]:.2f} | "
                    f"Juros: {emp[3]}% | Total: R${emp[5]:.2f} | "
                    f"Vencimento: {emp[6]}")
            p.drawString(50, y, texto)
            y -= 20
            if y < 100:
                p.showPage()
                y = 800

        p.save()
        buffer.seek(0)

        response = make_response(buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = (
            f'attachment; filename=relatorio_{session["user"]}.pdf'
        )
        return response

    except Exception as e:
        print(f"Erro ao gerar PDF: {e}")
        flash("Erro ao gerar relatório", "error")
        return redirect(url_for('painel'))

# Inicialização
if __name__ == '__main__':
    create_user_table()
    create_loans_table()
    verificar_e_adicionar_coluna_status()
    verificar_e_adicionar_coluna_cliente()
    verificar_e_adicionar_coluna_renovacoes()
    app.run(debug=True)