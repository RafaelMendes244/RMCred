import sqlite3
import hashlib
from datetime import datetime, timedelta

def create_user_table():
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        senha TEXT NOT NULL
    )''')
    conn.commit()
    conn.close()

def create_loans_table():
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS loans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        valor REAL NOT NULL,
        juros REAL NOT NULL,
        dias INTEGER NOT NULL,
        total REAL NOT NULL,
        vencimento TEXT NOT NULL,
        status TEXT DEFAULT 'pendente',
        cliente TEXT,
        pago INTEGER DEFAULT 0,
        renovacoes INTEGER DEFAULT 0
    )''')
    conn.commit()
    conn.close()

def register_user(nome, email, senha):
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
    if cursor.fetchone():
        conn.close()
        return False, "Já existe uma conta cadastrada com este e-mail."

    senha_hashed = hashlib.sha256(senha.encode()).hexdigest()
    cursor.execute("INSERT INTO usuarios (nome, email, senha) VALUES (?, ?, ?)", (nome, email, senha_hashed))
    conn.commit()
    conn.close()
    return True, "Usuário registrado com sucesso!"

def login_user(email, senha):
    senha_hashed = hashlib.sha256(senha.encode()).hexdigest()
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute("SELECT nome FROM usuarios WHERE email = ? AND senha = ?", (email, senha_hashed))
    user = cursor.fetchone()
    conn.close()
    if user:
        return user[0]
    return None

def salvar_emprestimo(cliente, valor, juros, dias, total, vencimento, admin):
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO loans (nome, valor, juros, dias, total, vencimento, status, cliente, renovacoes)
        VALUES (?, ?, ?, ?, ?, ?, 'pendente', ?, 0)
    ''', (admin, valor, juros, dias, total, vencimento, cliente))
    conn.commit()
    conn.close()

def listar_emprestimos_ativos(nome):
    try:
        conn = sqlite3.connect('database/finflow.db')
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, nome, valor, juros, dias, total, vencimento, status, cliente, renovacoes
            FROM loans
            WHERE nome = ? AND pago = 0 AND status = 'aprovado'
            ORDER BY vencimento
        """, (nome,))
        return cursor.fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()

def listar_emprestimos_finalizados(nome):
    try:
        conn = sqlite3.connect('database/finflow.db')
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, nome, valor, juros, dias, total, vencimento, status, cliente, renovacoes
            FROM loans
            WHERE nome = ? AND pago = 1
            ORDER BY vencimento DESC
        """, (nome,))
        return cursor.fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()

def listar_emprestimos_pendentes(nome):
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM loans WHERE nome = ? AND status = 'pendente'", (nome,))
    dados = cursor.fetchall()
    conn.close()
    return dados

def aprovar_emprestimo(id_emprestimo):
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE loans SET status = 'aprovado' WHERE id = ?", (id_emprestimo,))
    conn.commit()
    conn.close()

def rejeitar_emprestimo(id_emprestimo):
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM loans WHERE id = ?", (id_emprestimo,))
    conn.commit()
    conn.close()

def pagar_juros(id_emprestimo):
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()

    cursor.execute('SELECT vencimento, dias FROM loans WHERE id = ?', (id_emprestimo,))
    dados = cursor.fetchone()
    if dados:
        vencimento_str, dias = dados
        vencimento_atual = datetime.strptime(vencimento_str, '%Y-%m-%d')
        novo_vencimento = vencimento_atual + timedelta(days=dias)
        novo_vencimento_str = novo_vencimento.strftime('%Y-%m-%d')

        cursor.execute('UPDATE loans SET vencimento = ? WHERE id = ?', (novo_vencimento_str, id_emprestimo))

    conn.commit()
    conn.close()

def quitar_emprestimo(id_emprestimo):
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE loans SET pago = 1, status = 'quitado' WHERE id = ?", (id_emprestimo,))
    conn.commit()
    conn.close()

def deletar_emprestimo(id_emprestimo):
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM loans WHERE id = ?", (id_emprestimo,))
    conn.commit()
    conn.close()

def emprestimos_vencendo(nome, dias_antes=2):
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()

    hoje = datetime.now().date()
    limite = hoje + timedelta(days=dias_antes)

    cursor.execute('''
        SELECT COUNT(*) FROM loans
        WHERE nome = ? AND pago = 0 AND status = 'aprovado'
        AND DATE(vencimento) BETWEEN ? AND ?
    ''', (nome, hoje.strftime('%Y-%m-%d'), limite.strftime('%Y-%m-%d')))

    qtd = cursor.fetchone()[0]
    conn.close()
    return qtd

def verificar_e_adicionar_coluna_status():
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(loans)")
    colunas = [col[1] for col in cursor.fetchall()]
    if 'status' not in colunas:
        cursor.execute("ALTER TABLE loans ADD COLUMN status TEXT DEFAULT 'pendente'")
    conn.commit()
    conn.close()

def verificar_e_adicionar_coluna_cliente():
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(loans)")
    colunas = [col[1] for col in cursor.fetchall()]
    if 'cliente' not in colunas:
        cursor.execute("ALTER TABLE loans ADD COLUMN cliente TEXT")
    conn.commit()
    conn.close()

def verificar_e_adicionar_coluna_renovacoes():
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(loans)")
    colunas = [col[1] for col in cursor.fetchall()]
    if 'renovacoes' not in colunas:
        cursor.execute("ALTER TABLE loans ADD COLUMN renovacoes INTEGER DEFAULT 0")
        conn.commit()
    conn.close()