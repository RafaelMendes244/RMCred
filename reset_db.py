import sqlite3

def reset_db(db_path):
    # Conectar ao banco de dados SQLite
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Definir as tabelas do banco
    tabelas = [
        'amigos', 'loans', 'mensagens', 'solicitacoes', 
        'user_status', 'usuarios'
    ]

    try:
        # Apagar os dados de todas as tabelas
        for tabela in tabelas:
            print(f"Zerando dados da tabela: {tabela}")
            cursor.execute(f"DELETE FROM {tabela};")
            cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{tabela}';")
        
        # Commit para salvar as mudanças
        conn.commit()
        print("Dados zerados com sucesso!")

    except sqlite3.Error as e:
        print(f"Erro ao zerar os dados: {e}")

    finally:
        # Fechar a conexão com o banco
        conn.close()

if __name__ == "__main__":
    # Caminho para o banco de dados SQLite
    db_path = "database/finflow.db"  # Altere para o caminho correto do seu banco de dados 
    reset_db(db_path)