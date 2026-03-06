import requests
import csv
import os
import re
import sys
import time
from urllib.parse import urlparse, quote_plus
from bs4 import BeautifulSoup
from fishing_config import (
    FRANCE_TRAVAIL_CLIENT_ID,
    FRANCE_TRAVAIL_CLIENT_SECRET,
    HUNTER_API_KEY,
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

# ============================================================
# REFERENTIELS
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

REGIONS_INDEED = {
    "ile-de-france": "Île-de-France",
    "auvergne-rhone-alpes": "Auvergne-Rhône-Alpes",
    "bourgogne-franche-comte": "Bourgogne-Franche-Comté",
    "bretagne": "Bretagne",
    "centre-val-de-loire": "Centre-Val de Loire",
    "corse": "Corse",
    "grand-est": "Grand Est",
    "hauts-de-france": "Hauts-de-France",
    "normandie": "Normandie",
    "nouvelle-aquitaine": "Nouvelle-Aquitaine",
    "occitanie": "Occitanie",
    "pays-de-la-loire": "Pays de la Loire",
    "provence-alpes-cote-d-azur": "Provence-Alpes-Côte d'Azur",
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
        if choix.isdigit():
            idx = int(choix) - 1
            if 0 <= idx < len(noms):
                cle = noms[idx]
                return cle, REGIONS[cle], noms[idx].replace("-", " ").title()
        for nom, code in REGIONS.items():
            if choix in nom.replace("-", " "):
                return nom, code, nom.replace("-", " ").title()
        print("  [!] Region non reconnue, reessaye.")


# ============================================================
# SOURCE 1 : FRANCE TRAVAIL API
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
    try:
        resp = requests.post(url, params=params, data=data,
                             headers={"Content-Type": "application/x-www-form-urlencoded"})
        resp.raise_for_status()
        return resp.json().get("access_token")
    except Exception as e:
        print(f"  [!] Auth France Travail echouee : {e}")
        return None


def chercher_france_travail(token, mots_cles, region_code):
    if not token:
        return []

    url = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    params = {
        "motsCles": mots_cles,
        "region": region_code,
        "range": "0-149",
    }

    try:
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        resultats = resp.json().get("resultats", [])

        offres = []
        for r in resultats:
            entreprise = r.get("entreprise", {})
            contact = r.get("contact", {})
            lieu = r.get("lieuTravail", {}).get("libelle", "")

            email = ""
            if contact:
                email = contact.get("courriel", "")

            # Chercher email dans la description
            if not email:
                desc = r.get("description", "")
                found = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', desc)
                if found:
                    email = found[0]

            offres.append({
                "titre": r.get("intitule", ""),
                "entreprise": entreprise.get("nom", ""),
                "url_entreprise": entreprise.get("url", ""),
                "lieu": lieu,
                "email": email.strip().lower() if email else "",
                "source": "France Travail",
            })
        return offres
    except Exception as e:
        print(f"  [!] Erreur France Travail : {e}")
        return []


# ============================================================
# SOURCE 2 : INDEED.FR
# ============================================================
def chercher_indeed(mots_cles, region_nom_indeed):
    offres = []
    query = quote_plus(mots_cles)
    location = quote_plus(region_nom_indeed)

    for start in [0, 10]:  # 2 pages
        url = f"https://fr.indeed.com/jobs?q={query}&l={location}&start={start}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Indeed met les données dans des balises script JSON
            scripts = soup.find_all("script", {"type": "application/ld+json"})
            for script in scripts:
                try:
                    import json
                    data = json.loads(script.string)
                    if isinstance(data, list):
                        for item in data:
                            if item.get("@type") == "JobPosting":
                                org = item.get("hiringOrganization", {})
                                offres.append({
                                    "titre": item.get("title", ""),
                                    "entreprise": org.get("name", ""),
                                    "url_entreprise": org.get("sameAs", "") or org.get("url", ""),
                                    "lieu": item.get("jobLocation", {}).get("address", {}).get("addressLocality", ""),
                                    "email": "",
                                    "source": "Indeed",
                                })
                    elif isinstance(data, dict) and data.get("@type") == "JobPosting":
                        org = data.get("hiringOrganization", {})
                        offres.append({
                            "titre": data.get("title", ""),
                            "entreprise": org.get("name", ""),
                            "url_entreprise": org.get("sameAs", "") or org.get("url", ""),
                            "lieu": "",
                            "email": "",
                            "source": "Indeed",
                        })
                except Exception:
                    pass

            # Fallback: parser le HTML directement
            cards = soup.find_all("div", class_=re.compile("job_seen_beacon|cardOutline|resultContent"))
            for card in cards:
                titre_el = card.find("h2") or card.find("a", class_=re.compile("jcs-JobTitle"))
                company_el = card.find("span", {"data-testid": "company-name"}) or card.find(class_=re.compile("company"))
                location_el = card.find("div", {"data-testid": "text-location"}) or card.find(class_=re.compile("location"))

                titre = titre_el.get_text(strip=True) if titre_el else ""
                company = company_el.get_text(strip=True) if company_el else ""
                location = location_el.get_text(strip=True) if location_el else ""

                if company and company not in [o["entreprise"] for o in offres]:
                    offres.append({
                        "titre": titre,
                        "entreprise": company,
                        "url_entreprise": "",
                        "lieu": location,
                        "email": "",
                        "source": "Indeed",
                    })

            time.sleep(1)
        except Exception as e:
            print(f"  [!] Erreur Indeed page {start}: {e}")

    return offres


# ============================================================
# SOURCE 3 : HELLOWORK
# ============================================================
def chercher_hellowork(mots_cles, type_recherche):
    offres = []
    # Construire l'URL HelloWork
    mots = mots_cles.lower().replace(" ", "-")

    if type_recherche == "stage":
        url = f"https://www.hellowork.com/fr-fr/emploi/stage-{mots}.html"
    elif type_recherche == "alternance":
        url = f"https://www.hellowork.com/fr-fr/emploi/alternance-{mots}.html"
    else:
        url = f"https://www.hellowork.com/fr-fr/emploi/{mots}.html"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return offres

        soup = BeautifulSoup(resp.text, "html.parser")

        # Chercher les cartes d'offres
        cards = soup.find_all("li", class_=re.compile("hw-SearchResults"))
        if not cards:
            cards = soup.find_all("div", class_=re.compile("offer|job|card"))
        if not cards:
            cards = soup.find_all("article")

        # Aussi chercher dans les JSON-LD
        scripts = soup.find_all("script", {"type": "application/ld+json"})
        for script in scripts:
            try:
                import json
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item, dict) and item.get("@type") == "JobPosting":
                        org = item.get("hiringOrganization", {})
                        if isinstance(org, dict):
                            offres.append({
                                "titre": item.get("title", ""),
                                "entreprise": org.get("name", ""),
                                "url_entreprise": org.get("sameAs", "") or org.get("url", ""),
                                "lieu": "",
                                "email": "",
                                "source": "HelloWork",
                            })
            except Exception:
                pass

        # Fallback HTML parsing
        for card in cards:
            titre_el = card.find("h2") or card.find("h3") or card.find(class_=re.compile("title"))
            company_el = card.find(class_=re.compile("company|entreprise|employer"))

            titre = titre_el.get_text(strip=True) if titre_el else ""
            company = company_el.get_text(strip=True) if company_el else ""

            if company and company not in [o["entreprise"] for o in offres]:
                offres.append({
                    "titre": titre,
                    "entreprise": company,
                    "url_entreprise": "",
                    "lieu": "",
                    "email": "",
                    "source": "HelloWork",
                })

    except Exception as e:
        print(f"  [!] Erreur HelloWork : {e}")

    return offres


# ============================================================
# HUNTER.IO - Recherche email
# ============================================================
def chercher_email_hunter(domaine=None, company=None):
    if not HUNTER_API_KEY or HUNTER_API_KEY == "TA_CLE_HUNTER":
        return []

    url = "https://api.hunter.io/v2/domain-search"
    params = {"api_key": HUNTER_API_KEY, "limit": 5}

    if domaine:
        params["domain"] = domaine
    elif company:
        params["company"] = company
    else:
        return []

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        emails = []
        for e in data.get("emails", []):
            if e.get("confidence", 0) >= 20:
                emails.append(e.get("value", ""))
        return emails
    except Exception:
        return []


def extraire_domaine(url):
    if not url:
        return ""
    try:
        parsed = urlparse(url if url.startswith("http") else f"http://{url}")
        domaine = parsed.netloc or parsed.path
        domaine = re.sub(r"^www\.", "", domaine)
        # Ignorer les domaines de job boards
        ignore = ["indeed.com", "indeed.fr", "hellowork.com", "welcometothejungle.com",
                   "linkedin.com", "francetravail.fr", "pole-emploi.fr"]
        for ig in ignore:
            if ig in domaine:
                return ""
        return domaine
    except Exception:
        return ""


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 60)
    print("  FISHING MAIL - Trouver les emails des recruteurs")
    print("  Sources : France Travail + Indeed + HelloWork + Hunter.io")
    print("=" * 60)

    # Domaine
    print()
    mots_cles = input("  Domaine (ex: developpeur informatique) : ").strip()
    if not mots_cles:
        mots_cles = "developpeur informatique"
        print(f"  -> Par defaut : {mots_cles}")

    # Region
    region_cle, region_code, region_nom = choisir_region()
    print(f"  -> Region : {region_nom}")
    region_indeed = REGIONS_INDEED.get(region_cle, region_nom)

    # Type
    print()
    print("  Type :")
    print("    1. Stage uniquement")
    print("    2. Alternance uniquement")
    print("    3. Les deux")
    choix = input("  Choix (1/2/3) [3] : ").strip() or "3"

    types = []
    if choix == "1":
        types = ["stage"]
    elif choix == "2":
        types = ["alternance"]
    else:
        types = ["stage", "alternance"]

    # ======= COLLECTE MULTI-SOURCE =======
    print()
    print("  " + "-" * 50)
    print("  COLLECTE DES OFFRES")
    print("  " + "-" * 50)

    toutes_offres = []

    # 1. France Travail
    print("\n  [1/3] France Travail API...")
    token = get_france_travail_token()
    if token:
        for t in types:
            offres = chercher_france_travail(token, f"{t} {mots_cles}", region_code)
            print(f"    -> {len(offres)} offres ({t})")
            toutes_offres.extend(offres)
    else:
        print("    -> Connexion echouee, on continue avec les autres sources")

    # 2. Indeed
    print("\n  [2/3] Indeed.fr...")
    for t in types:
        offres = chercher_indeed(f"{t} {mots_cles}", region_indeed)
        print(f"    -> {len(offres)} offres ({t})")
        toutes_offres.extend(offres)

    # 3. HelloWork
    print("\n  [3/3] HelloWork...")
    for t in types:
        offres = chercher_hellowork(mots_cles, t)
        print(f"    -> {len(offres)} offres ({t})")
        toutes_offres.extend(offres)

    # Deduplication par nom d'entreprise
    vus = set()
    offres_uniques = []
    for o in toutes_offres:
        nom = o["entreprise"].strip().lower()
        if nom and nom != "inconnue" and nom not in vus:
            vus.add(nom)
            offres_uniques.append(o)

    print(f"\n  => {len(offres_uniques)} entreprises uniques trouvees")

    if not offres_uniques:
        print("  [!] Aucune offre trouvee. Essaye d'autres mots-cles.")
        return

    # ======= RECHERCHE D'EMAILS =======
    print()
    print("  " + "-" * 50)
    print("  RECHERCHE DES EMAILS")
    print("  " + "-" * 50)

    resultats = []
    emails_vus = set()
    hunter_calls = 0
    MAX_HUNTER = 40

    # Phase 1 : Emails deja dans les offres
    offres_sans_email = []
    for o in offres_uniques:
        if o["email"] and o["email"] not in emails_vus:
            emails_vus.add(o["email"])
            resultats.append(o)
        else:
            offres_sans_email.append(o)

    print(f"\n  Phase 1 - Emails dans les offres : {len(resultats)}")

    # Phase 2 : Hunter.io
    if HUNTER_API_KEY and HUNTER_API_KEY != "TA_CLE_HUNTER":
        print(f"  Phase 2 - Hunter.io ({min(len(offres_sans_email), MAX_HUNTER)} entreprises)...")

        for o in offres_sans_email:
            if hunter_calls >= MAX_HUNTER:
                print(f"    [!] Limite atteinte ({MAX_HUNTER} appels)")
                break

            nom = o["entreprise"]
            if not nom:
                continue

            emails_hunter = []

            # Par domaine d'abord
            domaine = extraire_domaine(o["url_entreprise"])
            if domaine:
                emails_hunter = chercher_email_hunter(domaine=domaine)
                hunter_calls += 1

            # Par nom d'entreprise sinon
            if not emails_hunter:
                emails_hunter = chercher_email_hunter(company=nom)
                hunter_calls += 1

            if emails_hunter:
                best = emails_hunter[0]
                if best not in emails_vus:
                    emails_vus.add(best)
                    o["email"] = best
                    o["source"] += " + Hunter.io"
                    resultats.append(o)
                    print(f"    [+] {nom} -> {best}")

            time.sleep(0.5)

        print(f"    {hunter_calls} appels Hunter.io effectues")
    else:
        print("  Phase 2 - Hunter.io : cle non configuree, skip")

    # ======= RESULTATS =======
    print()
    print("=" * 60)
    print(f"  RESULTATS : {len(resultats)} emails trouves !")
    print("=" * 60)

    if not resultats:
        print("  [!] Aucun email trouve.")
        print("  [*] Conseils :")
        print("      - Essaye des mots-cles plus larges (ex: 'informatique')")
        print("      - Verifie ta cle Hunter.io sur https://hunter.io/api-keys")
        return

    for i, r in enumerate(resultats, 1):
        print(f"\n  {i:3d}. {r['entreprise']}")
        print(f"       Email  : {r['email']}")
        print(f"       Poste  : {r['titre']}")
        if r["lieu"]:
            print(f"       Lieu   : {r['lieu']}")
        print(f"       Source : {r['source']}")

    # Sauvegarde CSV
    fichier_csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emails_trouves.csv")
    with open(fichier_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Email", "Entreprise", "Poste", "Lieu", "Source"])
        for r in resultats:
            writer.writerow([r["email"], r["entreprise"], r["titre"], r["lieu"], r["source"]])

    print(f"\n  [+] Sauvegarde dans emails_trouves.csv")

    # Envoyer ?
    print()
    envoyer = input("  Envoyer ton mail a tous ces contacts ? (o/N) : ").strip().lower()
    if envoyer == "o":
        from config import MON_EMAIL, OBJET
        from envoyer import envoyer_mail

        print(f"\n  [*] Envoi de {len(resultats)} mails...")
        envoyes = 0
        for i, r in enumerate(resultats, 1):
            print(f"  [{i}/{len(resultats)}] -> {r['email']} ({r['entreprise']})")
            try:
                envoyer_mail(r["email"])
                envoyes += 1
                time.sleep(2)
            except Exception as e:
                print(f"  [!] Echec : {e}")
        print(f"\n  [+] {envoyes}/{len(resultats)} mails envoyes !")


if __name__ == "__main__":
    main()
