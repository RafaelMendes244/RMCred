import sqlite3
import hashlib
from datetime import datetime, timedelta

def create_amigos_table():
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS amigos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        solicitante TEXT NOT NULL,
        amigo TEXT NOT NULL,
        status TEXT DEFAULT 'pendente',
        FOREIGN KEY (solicitante) REFERENCES usuarios(nome),
        FOREIGN KEY (amigo) REFERENCES usuarios(nome)
    )
    ''')
    conn.commit()
    conn.close()

def create_messages_table():
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS mensagens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        remetente TEXT NOT NULL,
        destinatario TEXT NOT NULL,
        mensagem TEXT NOT NULL,
        data_envio DATETIME DEFAULT CURRENT_TIMESTAMP,
        lida INTEGER DEFAULT 0,
        FOREIGN KEY (remetente) REFERENCES usuarios(nome),
        FOREIGN KEY (destinatario) REFERENCES usuarios(nome)
    )
    ''')
    conn.commit()
    conn.close()

def create_user_table():
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        senha TEXT NOT NULL,
        tipo TEXT,
        celular TEXT,
        endereco TEXT,
        cpf TEXT,
        data_nascimento TEXT,
        is_google INTEGER DEFAULT 0,
        data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        renovacoes INTEGER DEFAULT 0,
        observacoes TEXT
    )''')
    conn.commit()
    conn.close()

def create_solicitacoes_table():
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS solicitacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        solicitante TEXT NOT NULL,
        emprestador TEXT NOT NULL,
        valor REAL NOT NULL,
        juros REAL NOT NULL,
        dias INTEGER NOT NULL,
        status TEXT DEFAULT 'pendente',
        mensagem TEXT,
        data_criacao TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (solicitante) REFERENCES usuarios(nome),
        FOREIGN KEY (emprestador) REFERENCES usuarios(nome)
    )''')
    conn.commit()
    conn.close()

def create_user_table():
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        senha TEXT NOT NULL,
        tipo TEXT,
        celular TEXT,
        endereco TEXT,
        cpf TEXT,
        data_nascimento TEXT,
        data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_google INTEGER DEFAULT 0
    )''')
    conn.commit()
    conn.close()

def atualizar_tabelas_existentes():
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    
    # Adicionar coluna 'lida' na tabela mensagens se não existir
    cursor.execute("PRAGMA table_info(mensagens)")
    colunas = [col[1] for col in cursor.fetchall()]
    if 'lida' not in colunas:
        cursor.execute("ALTER TABLE mensagens ADD COLUMN lida INTEGER DEFAULT 0")
    
    # Adicionar coluna 'data_criacao' na tabela solicitacoes se não existir
    cursor.execute("PRAGMA table_info(solicitacoes)")
    colunas = [col[1] for col in cursor.fetchall()]
    if 'data_criacao' not in colunas:
        cursor.execute("ALTER TABLE solicitacoes ADD COLUMN data_criacao TEXT DEFAULT CURRENT_TIMESTAMP")
    
    # Adicionar colunas faltantes na tabela usuarios
    cursor.execute("PRAGMA table_info(usuarios)")
    colunas = [col[1] for col in cursor.fetchall()]
    if 'cpf' not in colunas:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN cpf TEXT")
    if 'data_nascimento' not in colunas:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN data_nascimento TEXT")
    if 'is_google' not in colunas:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN is_google INTEGER DEFAULT 0")
    
    conn.commit()
    conn.close()

def register_user(nome, email, senha, tipo, celular=None, endereco=None, cpf=None, data_nascimento=None, is_google=False):
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()

    # Verifica se o email já está cadastrado
    cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
    if cursor.fetchone():
        conn.close()
        return False, "Já existe uma conta cadastrada com este e-mail."

    senha_hashed = hashlib.sha256(senha.encode()).hexdigest()

    cursor.execute("""
        INSERT INTO usuarios (nome, email, senha, tipo, celular, endereco, cpf, data_nascimento, is_google)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (nome, email, senha_hashed, tipo, celular, endereco, cpf, data_nascimento, 1 if is_google else 0))

    conn.commit()
    conn.close()
    return True, "Usuário registrado com sucesso!"

def login_user(email, senha):
    senha_hashed = hashlib.sha256(senha.encode()).hexdigest()
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute("SELECT nome, tipo FROM usuarios WHERE email = ? AND senha = ?", (email, senha_hashed))
    user = cursor.fetchone()
    if user:
        return user  # retorna (nome, tipo)
    return None

def salvar_emprestimo(cliente, valor, juros, dias, total, vencimento, observacoes, nome_admin):
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO loans (cliente, valor, juros, dias, total, vencimento, observacoes, nome, status, pago)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pendente', 0)
    """, (cliente, valor, juros, dias, total, vencimento, observacoes, nome_admin))
    conn.commit()
    conn.close()

def listar_emprestimos_ativos(nome):
    conn = sqlite3.connect('database/finflow.db')
    conn.row_factory = sqlite3.Row  # Permite acesso tipo emp['cliente']
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, nome, valor, juros, dias, total, vencimento, status, cliente, renovacoes, observacoes
        FROM loans
        WHERE nome = ? AND pago = 0 AND status = 'aprovado'
    """, (nome,))
    dados = cursor.fetchall()
    conn.close()
    return dados

def listar_emprestimos_pendentes(nome):
    conn = sqlite3.connect('database/finflow.db')
    conn.row_factory = sqlite3.Row  # 👈 Importante!
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

def listar_emprestimos_finalizados(nome=None):
    conn = sqlite3.connect('database/finflow.db')
    conn.row_factory = sqlite3.Row  # isso permite acessar dados como dicionário
    cursor = conn.cursor()
    if nome:
        cursor.execute("SELECT * FROM loans WHERE nome = ? AND pago = 1", (nome,))
    else:
        cursor.execute("SELECT * FROM loans WHERE pago = 1")
    dados = cursor.fetchall()
    conn.close()
    return dados

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

def verificar_e_adicionar_coluna_observacoes():
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(loans)")
    colunas = [col[1] for col in cursor.fetchall()]
    if 'observacoes' not in colunas:
        cursor.execute("ALTER TABLE loans ADD COLUMN observacoes TEXT")
    conn.commit()
    conn.close()

def verificar_e_adicionar_coluna_data_criacao():
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(solicitacoes)")
    colunas = [col[1] for col in cursor.fetchall()]
    if 'data_criacao' not in colunas:
        cursor.execute("ALTER TABLE solicitacoes ADD COLUMN data_criacao TEXT DEFAULT CURRENT_TIMESTAMP")
    conn.commit()
    conn.close()

def buscar_usuario_por_email(email):
    conn = sqlite3.connect('database/finflow.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()
    return user

def create_user_status_table():
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_status (
            usuario TEXT PRIMARY KEY,
            online INTEGER DEFAULT 0,
            ultima_vez TEXT
        )
    """)
    conn.commit()
    conn.close()

def verificar_e_adicionar_colunas_usuario():
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(usuarios)")
    colunas = [col[1] for col in cursor.fetchall()]
    
    if 'data_nascimento' not in colunas:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN data_nascimento TEXT")
    
    if 'cpf' not in colunas:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN cpf TEXT")
    
    if 'is_google' not in colunas:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN is_google INTEGER DEFAULT 0")
    
    conn.commit()
    conn.close()