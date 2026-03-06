# AutoMail

Envoi rapide de mails pré-rédigés avec pièces jointes + recherche automatique d'emails d'entreprises qui recrutent.

## Installation

```
pip install requests
```

1. Clone le repo
2. Copie `config.example.py` en `config.py` — remplis tes infos email
3. Copie `fishing_config.example.py` en `fishing_config.py` — remplis tes clés API

## Utilisation

### Envoyer un mail

```
python envoyer.py
```
Colle l'adresse email → Entrée → envoyé ✅

### Fishing Mail — Trouver des emails de recruteurs

```
python fishing.py
```
1. Choisis ton domaine (ex: développeur informatique)
2. Choisis ta région (ex: Ile-de-France)
3. Choisis le type de contrat (stage / alternance / les deux)
4. Le script cherche les offres et extrait les emails de contact
5. Résultats sauvegardés dans `emails_trouves.csv`
6. Option d'envoyer directement ton mail à tous les contacts trouvés

## APIs utilisées

- **[France Travail API](https://francetravail.io)** — Recherche d'offres de stage/alternance (gratuit)
- **[Hunter.io](https://hunter.io)** — Recherche d'emails par domaine d'entreprise (50 crédits/mois gratuits)

## Gmail — Mot de passe d'application

Pour utiliser Gmail, il faut un **mot de passe d'application** :
1. Active la vérification en 2 étapes sur ton compte Google
2. Génère un mot de passe sur [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Colle-le dans `config.py`
