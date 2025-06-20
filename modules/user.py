import sqlite3
from datetime import datetime, timedelta
import bcrypt

# ==============================================
# Funções de Criação de Tabelas
# ==============================================

def create_tables():
    """Cria todas as tabelas necessárias"""
    create_user_table()
    create_amigos_table()
    create_messages_table()
    create_loans_table()
    create_solicitacoes_table()
    create_user_status_table()
    atualizar_tabelas_existentes()

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

# ==============================================
# Funções de Atualização de Tabelas
# ==============================================

def atualizar_tabelas_existentes():
    """Adiciona colunas faltantes nas tabelas existentes"""
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    
    # Tabela mensagens
    verificar_e_adicionar_coluna('mensagens', 'lida', 'INTEGER DEFAULT 0')
    
    # Tabela solicitacoes
    verificar_e_adicionar_coluna('solicitacoes', 'data_criacao', 'TEXT DEFAULT CURRENT_TIMESTAMP')
    
    # Tabela usuarios
    verificar_e_adicionar_coluna('usuarios', 'cpf', 'TEXT')
    verificar_e_adicionar_coluna('usuarios', 'data_nascimento', 'TEXT')
    verificar_e_adicionar_coluna('usuarios', 'is_google', 'INTEGER DEFAULT 0')
    
    # Tabela loans
    verificar_e_adicionar_coluna('loans', 'status', "TEXT DEFAULT 'pendente'")
    verificar_e_adicionar_coluna('loans', 'cliente', 'TEXT')
    verificar_e_adicionar_coluna('loans', 'renovacoes', 'INTEGER DEFAULT 0')
    verificar_e_adicionar_coluna('loans', 'observacoes', 'TEXT')
    
    conn.commit()
    conn.close()

def verificar_e_adicionar_coluna(tabela, coluna, tipo):
    """Verifica se uma coluna existe e adiciona se não existir"""
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({tabela})")
    colunas = [col[1] for col in cursor.fetchall()]
    if coluna not in colunas:
        cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    conn.close()

# ==============================================
# Funções de Usuários
# ==============================================

def register_user(nome, email, senha, tipo, celular=None, endereco=None, cpf=None, data_nascimento=None, is_google=False):
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()

    # Verifica se o email já está cadastrado
    cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
    if cursor.fetchone():
        conn.close()
        return False, "Já existe uma conta cadastrada com este e-mail."

    senha_hashed = bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    cursor.execute("""
        INSERT INTO usuarios (nome, email, senha, tipo, celular, endereco, cpf, data_nascimento, is_google)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (nome, email, senha_hashed, tipo, celular, endereco, cpf, data_nascimento, 1 if is_google else 0))

    conn.commit()
    conn.close()
    return True, "Usuário registrado com sucesso!"

def login_user(email, senha):
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    
    # Primeiro busca o usuário pelo email
    cursor.execute("SELECT nome, tipo, senha FROM usuarios WHERE email = ?", (email,))
    user = cursor.fetchone()
    
    if user:
        nome, tipo, senha_hash = user
        # Verifica a senha com bcrypt
        if bcrypt.checkpw(senha.encode('utf-8'), senha_hash.encode('utf-8')):
            return nome, tipo
    return None

def buscar_usuario_por_email(email):
    conn = sqlite3.connect('database/finflow.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()
    return user

# ==============================================
# Funções de Empréstimos
# ==============================================

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
    conn.row_factory = sqlite3.Row
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
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM loans WHERE nome = ? AND status = 'pendente'", (nome,))
    dados = cursor.fetchall()
    conn.close()
    return dados

def listar_emprestimos_finalizados(nome=None):
    conn = sqlite3.connect('database/finflow.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if nome:
        cursor.execute("SELECT * FROM loans WHERE nome = ? AND pago = 1", (nome,))
    else:
        cursor.execute("SELECT * FROM loans WHERE pago = 1")
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

        cursor.execute('UPDATE loans SET vencimento = ?, renovacoes = renovacoes + 1 WHERE id = ?', 
                      (novo_vencimento_str, id_emprestimo))

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

def listar_todos_emprestimos(username):
    """Lista todos os empréstimos de um usuário com métricas"""
    conn = sqlite3.connect('database/finflow.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Empréstimos ativos
    cursor.execute("""
        SELECT id, cliente, valor, juros, dias, total, vencimento, status, observacoes, renovacoes
        FROM loans 
        WHERE nome = ? AND status = 'aprovado' AND pago = 0
        ORDER BY vencimento
    """, (username,))
    ativos = cursor.fetchall()
    
    # Empréstimos finalizados
    cursor.execute("""
        SELECT id, cliente, valor, juros, dias, total, vencimento, status, observacoes, renovacoes
        FROM loans 
        WHERE nome = ? AND pago = 1
        ORDER BY vencimento DESC
    """, (username,))
    finalizados = cursor.fetchall()
    
    # Empréstimos pendentes
    cursor.execute("""
        SELECT id, cliente, valor, juros, dias, total, vencimento, status, observacoes, renovacoes
        FROM loans 
        WHERE nome = ? AND status = 'pendente'
        ORDER BY vencimento
    """, (username,))
    pendentes = cursor.fetchall()
    
    # Empréstimos vencendo
    hoje = datetime.now().date()
    limite = hoje + timedelta(days=2)
    cursor.execute("""
        SELECT COUNT(*) as quantidade 
        FROM loans
        WHERE nome = ? AND pago = 0 AND status = 'aprovado'
        AND DATE(vencimento) BETWEEN ? AND ?
    """, (username, hoje.strftime('%Y-%m-%d'), limite.strftime('%Y-%m-%d')))
    vencendo_count = cursor.fetchone()['quantidade']
    
    conn.close()
    
    return {
        'ativos': ativos,
        'finalizados': finalizados,
        'pendentes': pendentes,
        'vencendo_count': vencendo_count
    }

# ==============================================
# Funções de Solicitações
# ==============================================

def listar_solicitacoes_pendentes(username):
    conn = sqlite3.connect('database/finflow.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, solicitante, valor, juros, dias, mensagem, data_criacao
        FROM solicitacoes
        WHERE emprestador = ? AND status = 'pendente'
        ORDER BY data_criacao DESC
    """, (username,))
    solicitacoes = cursor.fetchall()
    conn.close()
    return solicitacoes

# ==============================================
# Funções de Amigos
# ==============================================

def get_amigos(usuario):
    """Retorna amigos aprovados do usuário"""
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