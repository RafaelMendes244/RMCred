import sqlite3

def criar_banco_completo():
    conn = sqlite3.connect('database/finflow.db')
    cursor = conn.cursor()
    
    # Tabela de usuários
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        senha TEXT NOT NULL,
        tipo TEXT,
        celular TEXT,
        endereco TEXT,
        cpf TEXT,
        data_nascimento TEXT,
        data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Tabela de amigos (como na sua imagem)
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
    
    # Tabela de mensagens
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS mensagens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        remetente TEXT NOT NULL,
        destinatario TEXT NOT NULL,
        mensagem TEXT NOT NULL,
        data_envio DATETIME DEFAULT CURRENT_TIMESTAMP,
        lida INTEGER DEFAULT 0
    )
    ''')
    
    # Tabela de empréstimos (loans)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS loans (
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
    )
    ''')
    
    # Tabela de solicitações
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS solicitacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        solicitante TEXT NOT NULL,
        emprestador TEXT NOT NULL,
        valor REAL NOT NULL,
        juros REAL NOT NULL,
        dias INTEGER NOT NULL,
        mensagem TEXT,
        status TEXT DEFAULT 'pendente',
        data_criacao TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (solicitante) REFERENCES usuarios(nome),
        FOREIGN KEY (emprestador) REFERENCES usuarios(nome)
    )
    ''')
    
    # Tabela de status do usuário
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_status (
        usuario TEXT PRIMARY KEY,
        online INTEGER DEFAULT 0,
        ultima_vez TEXT
    )
    ''')
    
    # Adicionar colunas que podem não existir em tabelas já criadas
    colunas_para_verificar = [
        ("loans", "observacoes", "TEXT"),
        ("mensagens", "lida", "INTEGER DEFAULT 0"),
        ("amigos", "data_criacao", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    ]
    
    for tabela, coluna, tipo in colunas_para_verificar:
        try:
            cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
        except sqlite3.OperationalError:
            pass  # Coluna já existe
    
    conn.commit()
    conn.close()
    print("✅ Banco de dados criado/atualizado com sucesso!")

if __name__ == '__main__':
    criar_banco_completo()