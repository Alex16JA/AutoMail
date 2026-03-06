# AutoMail

Envoi rapide de mails pré-rédigés avec pièces jointes. Tu colles l'adresse, tu appuies sur Entrée, c'est envoyé.

## Installation

1. Clone le repo
2. Copie `config.example.py` en `config.py`
3. Remplis tes infos dans `config.py` (email, mot de passe d'application, contenu, pièces jointes)
4. Lance `python envoyer.py`

## Utilisation

```
python envoyer.py
```

- Colle l'adresse email du destinataire → Entrée → envoyé ✅
- Tape `q` pour quitter

## Gmail - Mot de passe d'application

Pour utiliser Gmail, il faut un **mot de passe d'application** :
1. Active la vérification en 2 étapes sur ton compte Google
2. Génère un mot de passe sur [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Colle-le dans `config.py`
