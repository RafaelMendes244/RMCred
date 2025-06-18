import smtplib
from email.mime.text import MIMEText

remetente = "rmcredpb@gmail.com"
senha_app = "ocnm ahcd fnxn nyic"
destinatario = "gabriel.mito07@gmail.com"  # Use um e-mail seu

msg = MIMEText("Teste de envio de e-mail com senha de app.")
msg['Subject'] = "Teste RMCred"
msg['From'] = remetente
msg['To'] = destinatario

try:
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(remetente, senha_app)
        smtp.send_message(msg)
    print("E-mail enviado com sucesso!")
except Exception as e:
    print(f"Erro ao enviar e-mail: {e}")
