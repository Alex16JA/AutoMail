import requests
import csv
import os
import re
import sys
from urllib.parse import urlparse
from fishing_config import (
    FRANCE_TRAVAIL_CLIENT_ID,
    FRANCE_TRAVAIL_CLIENT_SECRET,
    HUNTER_API_KEY,
)

# ============================================================
# REFERENTIELS - Regions France Travail
# ============================================================
REGIONS = {
    "ile-de-france": "11",
    "auvergne-rhone-alpes": "84",
    "bourgogne-franche-comte": "27",
    "bretagne": "53",
    "centre-val-de-loire": "24",
    "corse": "94",
    "grand-est": "44",
    "hauts-de-france": "32",
    "normandie": "28",
    "nouvelle-aquitaine": "75",
    "occitanie": "76",
    "pays-de-la-loire": "52",
    "provence-alpes-cote-d-azur": "93",
}


def afficher_regions():
    print("\n  Regions disponibles :")
    for i, nom in enumerate(REGIONS.keys(), 1):
        print(f"    {i:2d}. {nom.replace('-', ' ').title()}")
    print()


def choisir_region():
    afficher_regions()
    noms = list(REGIONS.keys())
    while True:
        choix = input("  Numero de la region (ou tapez le nom) : ").strip().lower()
        # Par numero
        if choix.isdigit():
            idx = int(choix) - 1
            if 0 <= idx < len(noms):
                return REGIONS[noms[idx]], noms[idx].replace("-", " ").title()
        # Par nom partiel
        for nom, code in REGIONS.items():
            if choix in nom.replace("-", " "):
                return code, nom.replace("-", " ").title()
        print("  [!] Region non reconnue, reessaye.")


# ============================================================
# FRANCE TRAVAIL - Auth OAuth2
# ============================================================
def get_france_travail_token():
    url = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
    params = {"realm": "/partenaire"}
    data = {
        "grant_type": "client_credentials",
        "client_id": FRANCE_TRAVAIL_CLIENT_ID,
        "client_secret": FRANCE_TRAVAIL_CLIENT_SECRET,
        "scope": "api_offresdemploiv2 o2dsoffre",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        resp = requests.post(url, params=params, data=data, headers=headers)
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if not token:
            print("  [ERREUR] Pas de token dans la reponse.")
            print(f"  Reponse : {resp.text}")
            sys.exit(1)
        return token
    except requests.exceptions.HTTPError as e:
        print(f"  [ERREUR] Auth France Travail echouee : {e}")
        print(f"  Reponse : {resp.text}")
        print("  Verifie ton Client ID et Client Secret dans fishing_config.py")
        sys.exit(1)


# ============================================================
# FRANCE TRAVAIL - Recherche d'offres
# ============================================================
def chercher_offres(token, mots_cles, region_code, type_contrat="NS", max_results=50):
    """
    Cherche des offres sur France Travail.
    type_contrat: NS = stage (non salarie), CDD, CDI, MIS (interim)
    """
    url = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    params = {
        "motsCles": mots_cles,
        "region": region_code,
        "typeContrat": type_contrat,
        "range": f"0-{min(max_results, 149)}",
    }

    try:
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        resultats = data.get("resultats", [])
        total = data.get("filtresPossibles", [{}])
        print(f"  -> {len(resultats)} offres trouvees")
        return resultats
    except requests.exceptions.HTTPError as e:
        print(f"  [ERREUR] Recherche echouee : {e}")
        if resp.status_code == 401:
            print("  Token expire, relance le script.")
        return []


# ============================================================
# EXTRACTION - Emails et infos entreprise
# ============================================================
def extraire_infos_offre(offre):
    """Extrait les infos utiles d'une offre France Travail"""
    entreprise = offre.get("entreprise", {})
    contact = offre.get("contact", {})

    info = {
        "titre": offre.get("intitule", ""),
        "entreprise": entreprise.get("nom", "Inconnue"),
        "url_entreprise": entreprise.get("url", ""),
        "lieu": "",
        "email_contact": "",
        "url_offre": offre.get("origineOffre", {}).get("urlOrigine", ""),
    }

    # Lieu
    lieu_obj = offre.get("lieuTravail", {})
    info["lieu"] = lieu_obj.get("libelle", "")

    # Email de contact (directement dans l'offre)
    if contact:
        email = contact.get("courriel", "")
        if email and "@" in email:
            # Parfois il y a des formats bizarres, on nettoie
            email = email.strip().lower()
            info["email_contact"] = email

    return info


# ============================================================
# HUNTER.IO - Recherche email par domaine
# ============================================================
def chercher_email_hunter(domaine):
    """Cherche les emails d'un domaine via Hunter.io"""
    if not HUNTER_API_KEY or HUNTER_API_KEY == "TA_CLE_HUNTER":
        return []

    url = "https://api.hunter.io/v2/domain-search"
    params = {"domain": domaine, "api_key": HUNTER_API_KEY, "limit": 5}

    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        emails = []
        for e in data.get("emails", []):
            if e.get("confidence", 0) >= 30:
                emails.append(e.get("value", ""))
        return emails
    except Exception:
        return []


def extraire_domaine(url):
    """Extrait le domaine d'une URL"""
    if not url:
        return ""
    try:
        parsed = urlparse(url if url.startswith("http") else f"http://{url}")
        domaine = parsed.netloc or parsed.path
        # Enlever www.
        domaine = re.sub(r"^www\.", "", domaine)
        return domaine
    except Exception:
        return ""


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 55)
    print("  FISHING MAIL - Trouver les emails des recruteurs")
    print("=" * 55)

    # Choix du domaine
    print()
    mots_cles = input("  Domaine de recherche (ex: developpeur informatique) : ").strip()
    if not mots_cles:
        mots_cles = "developpeur informatique"
        print(f"  -> Par defaut : {mots_cles}")

    # Choix de la region
    region_code, region_nom = choisir_region()
    print(f"  -> Region : {region_nom}")

    # Choix type contrat
    print()
    print("  Type de contrat :")
    print("    1. Stage")
    print("    2. Alternance / Contrat pro")
    print("    3. Les deux")
    choix_contrat = input("  Choix (1/2/3) [3] : ").strip() or "3"

    types_contrat = []
    if choix_contrat == "1":
        types_contrat = ["NS"]
    elif choix_contrat == "2":
        types_contrat = ["CDD", "CDI"]  # L'alternance est souvent en CDD
    else:
        types_contrat = ["NS", "CDD"]

    # Auth
    print()
    print("  [*] Connexion a France Travail...")
    token = get_france_travail_token()
    print("  [+] Connecte !")

    # Recherche
    toutes_offres = []
    for tc in types_contrat:
        print(f"\n  [*] Recherche type contrat = {tc}...")
        offres = chercher_offres(token, mots_cles, region_code, tc)
        toutes_offres.extend(offres)

    if not toutes_offres:
        print("\n  [!] Aucune offre trouvee. Essaye d'autres mots-cles ou une autre region.")
        return

    # Extraction
    print(f"\n  [*] Extraction des emails de {len(toutes_offres)} offres...")
    resultats = []
    emails_vus = set()
    hunter_calls = 0
    MAX_HUNTER_CALLS = 20  # Limite pour ne pas cramer tous les credits

    for offre in toutes_offres:
        info = extraire_infos_offre(offre)

        # Si on a deja un email dans l'offre
        if info["email_contact"] and info["email_contact"] not in emails_vus:
            emails_vus.add(info["email_contact"])
            resultats.append(info)
            continue

        # Sinon, essayer Hunter.io avec le domaine de l'entreprise
        if not info["email_contact"] and info["url_entreprise"] and hunter_calls < MAX_HUNTER_CALLS:
            domaine = extraire_domaine(info["url_entreprise"])
            if domaine:
                emails_hunter = chercher_email_hunter(domaine)
                hunter_calls += 1
                if emails_hunter:
                    info["email_contact"] = emails_hunter[0]  # Premier email trouve
                    if info["email_contact"] not in emails_vus:
                        emails_vus.add(info["email_contact"])
                        resultats.append(info)

    # Resultats
    print()
    print("=" * 55)
    print(f"  RESULTATS : {len(resultats)} emails trouves")
    print("=" * 55)

    if not resultats:
        print("  [!] Aucun email trouve. Les offres n'avaient pas d'email de contact.")
        print("  [*] Conseil : essaye avec d'autres mots-cles.")
        return

    for i, r in enumerate(resultats, 1):
        print(f"\n  {i:3d}. {r['entreprise']}")
        print(f"       Email : {r['email_contact']}")
        print(f"       Poste : {r['titre']}")
        if r["lieu"]:
            print(f"       Lieu  : {r['lieu']}")

    # Sauvegarde CSV
    fichier_csv = os.path.join(os.path.dirname(__file__), "emails_trouves.csv")
    with open(fichier_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Email", "Entreprise", "Poste", "Lieu", "URL Offre"])
        for r in resultats:
            writer.writerow([
                r["email_contact"],
                r["entreprise"],
                r["titre"],
                r["lieu"],
                r["url_offre"],
            ])

    print(f"\n  [+] Sauvegarde dans {fichier_csv}")
    print(f"  [+] {len(resultats)} emails prets a utiliser avec envoyer.py !")

    # Proposer d'envoyer directement
    print()
    envoyer = input("  Veux-tu envoyer ton mail a tous ces contacts ? (o/N) : ").strip().lower()
    if envoyer == "o":
        from config import MON_EMAIL, MON_MOT_DE_PASSE, SMTP_SERVEUR, SMTP_PORT, OBJET, CONTENU, PIECES_JOINTES
        from envoyer import envoyer_mail

        print(f"\n  [*] Envoi de {len(resultats)} mails depuis {MON_EMAIL}...")
        print(f"  [*] Objet : {OBJET}")
        print()

        for i, r in enumerate(resultats, 1):
            dest = r["email_contact"]
            print(f"  [{i}/{len(resultats)}] -> {dest} ({r['entreprise']})")
            envoyer_mail(dest)

        print(f"\n  [+] Terminee ! {len(resultats)} mails envoyes.")


if __name__ == "__main__":
    main()
