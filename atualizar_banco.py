import sqlite3

conn = sqlite3.connect('database/finflow.db')
cursor = conn.cursor()

# Tabela de mensagens
cursor.execute('''
CREATE TABLE IF NOT EXISTS mensagens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    remetente TEXT NOT NULL,
    destinatario TEXT NOT NULL,
    mensagem TEXT NOT NULL,
    data_envio DATETIME DEFAULT CURRENT_TIMESTAMP
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
    renovacoes INTEGER DEFAULT 0
)
''')

# Adiciona coluna observacoes se não existir
try:
    cursor.execute("ALTER TABLE loans ADD COLUMN observacoes TEXT")
except sqlite3.OperationalError:
    pass

# Tabela de solicitações
# Tabela de solicitações
cursor.execute('''
CREATE TABLE IF NOT EXISTS solicitacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    solicitante TEXT NOT NULL,
    emprestador TEXT NOT NULL,
    valor REAL NOT NULL,
    juros REAL NOT NULL,
    dias INTEGER NOT NULL,
    observacoes TEXT,
    status TEXT DEFAULT 'pendente',
    data_criacao TEXT DEFAULT CURRENT_TIMESTAMP
)
''')

conn.commit()
conn.close()

print("✅ Banco atualizado com sucesso!")