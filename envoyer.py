import smtplib
import os
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from config import MON_EMAIL, MON_MOT_DE_PASSE, SMTP_SERVEUR, SMTP_PORT, OBJET, CONTENU, PIECES_JOINTES


def envoyer_mail(destinataire, entreprise="", poste="", sender_email=None, sender_password=None):
    """Envoie un mail avec personnalisation optionnelle.
    
    Les variables {entreprise}, {poste} sont remplacees dans l'objet et le contenu.
    sender_email/sender_password: utiliser un autre compte que le defaut.
    """
    email_from = sender_email or MON_EMAIL
    password = sender_password or MON_MOT_DE_PASSE

    # Personnaliser le contenu
    objet = OBJET
    contenu = CONTENU

    if entreprise:
        objet = objet.replace("{entreprise}", entreprise)
        contenu = contenu.replace("{entreprise}", entreprise)
    if poste:
        objet = objet.replace("{poste}", poste)
        contenu = contenu.replace("{poste}", poste)

    msg = MIMEMultipart()
    msg["From"] = email_from
    msg["To"] = destinataire
    msg["Subject"] = objet

    # Corps du mail
    msg.attach(MIMEText(contenu, "plain"))

    # Pieces jointes
    for fichier in PIECES_JOINTES:
        if not os.path.isfile(fichier):
            print(f"  [!] Fichier introuvable, ignore : {fichier}")
            continue
        with open(fichier, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        nom_fichier = os.path.basename(fichier)
        part.add_header("Content-Disposition", f"attachment; filename={nom_fichier}")
        msg.attach(part)
        print(f"  [+] Piece jointe : {nom_fichier}")

    # Envoi
    try:
        server = smtplib.SMTP(SMTP_SERVEUR, SMTP_PORT)
        server.starttls()
        server.login(email_from, password)
        server.send_message(msg)
        server.quit()
        print(f"\n  >>> Mail envoye a {destinataire} !\n")
    except smtplib.SMTPAuthenticationError:
        print("\n  [ERREUR] Authentification echouee.")
        print("  Verifie ton email et mot de passe d'application dans config.py")
        print("  Pour Gmail, genere un mot de passe ici : https://myaccount.google.com/apppasswords\n")
        raise
    except Exception as e:
        print(f"\n  [ERREUR] {e}\n")
        raise


def main():
    print("=" * 50)
    print("  AUTOMAIL - Envoi rapide de mails")
    print(f"  De : {MON_EMAIL}")
    print(f"  Objet : {OBJET}")
    print(f"  Pieces jointes : {len(PIECES_JOINTES)}")
    print("=" * 50)
    print()

    while True:
        destinataire = input("  Email du destinataire (ou 'q' pour quitter) : ").strip()

        if destinataire.lower() == "q":
            print("  Bye !")
            break

        if not destinataire or "@" not in destinataire:
            print("  [!] Adresse mail invalide, reessaye.\n")
            continue

        envoyer_mail(destinataire)


if __name__ == "__main__":
    main()
