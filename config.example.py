# ============================================================
# CONFIGURATION - Copie ce fichier en "config.py" et remplis tes infos
# ============================================================

MON_EMAIL = "ton_email@gmail.com"
MON_MOT_DE_PASSE = "xxxx xxxx xxxx xxxx"  # Mot de passe d'application Gmail

SMTP_SERVEUR = "smtp.gmail.com"
SMTP_PORT = 587

# ============================================================
# CONTENU DU MAIL
# Variables disponibles : {entreprise}, {poste}
# Elles seront remplacees automatiquement pour chaque envoi
# ============================================================

OBJET = "Candidature Stage Développeur Informatique - {entreprise}"

CONTENU = """Madame, Monsieur,

Je me permets de vous contacter pour vous faire part de ma recherche de stage dans le cadre de ma formation en informatique.

Vous trouverez en pièce jointe mon CV ainsi que ma lettre de motivation.

Je vous remercie par avance pour votre attention et reste à votre disposition.

Cordialement

Votre Nom
votre.email@gmail.com"""

# ============================================================
# PIECES JOINTES
# ============================================================

PIECES_JOINTES = [
    # r"C:\chemin\vers\CV.pdf",
    # r"C:\chemin\vers\LM.pdf",
]
