import requests
import csv
import json
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/",
    "DNT": "1",
}

# ============================================================
# TOUS LES SITES D'EMPLOI CIBLES
# ============================================================
JOB_SITES = [
    "indeed.fr",
    "hellowork.com",
    "welcometothejungle.com",
    "linkedin.com/jobs",
    "apec.fr",
    "cadremploi.fr",
    "monster.fr",
    "meteojob.com",
    "regionsjob.com",
    "keljob.com",
    "glassdoor.fr",
    "lesjeudis.com",
    "jobteaser.com",
    "stepstone.fr",
    "talent.com",
    "jooble.org",
    "optioncarriere.com",
    "emploi.lefigaro.fr",
    "letudiant.fr",
    "studyrama-emploi.com",
    "l4m.fr",
    "directemploi.com",
    "staffme.com",
    "jobijoba.com",
    "wizbii.com",
]

# ============================================================
# REFERENTIELS REGIONS
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

REGIONS_LABEL = {
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
    data = {
        "grant_type": "client_credentials",
        "client_id": FRANCE_TRAVAIL_CLIENT_ID,
        "client_secret": FRANCE_TRAVAIL_CLIENT_SECRET,
        "scope": "api_offresdemploiv2 o2dsoffre",
    }
    try:
        resp = requests.post(url, params={"realm": "/partenaire"}, data=data,
                             headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=10)
        resp.raise_for_status()
        return resp.json().get("access_token")
    except Exception as e:
        print(f"    [!] Auth echouee : {e}")
        return None


def chercher_france_travail(token, mots_cles, region_code):
    if not token:
        return []
    url = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
    params = {"motsCles": mots_cles, "region": region_code, "range": "0-149"}
    try:
        resp = requests.get(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                            params=params, timeout=10)
        resp.raise_for_status()
        resultats = resp.json().get("resultats", [])
        offres = []
        for r in resultats:
            ent = r.get("entreprise", {})
            contact = r.get("contact", {})
            email = ""
            if contact:
                email = contact.get("courriel", "")
            if not email:
                found = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', r.get("description", ""))
                if found:
                    email = found[0]
            offres.append({
                "titre": r.get("intitule", ""),
                "entreprise": ent.get("nom", ""),
                "url_entreprise": ent.get("url", ""),
                "lieu": r.get("lieuTravail", {}).get("libelle", ""),
                "email": email.strip().lower() if email else "",
                "source": "France Travail",
            })
        return offres
    except Exception as e:
        print(f"    [!] Erreur : {e}")
        return []


# ============================================================
# SOURCE 2 : GOOGLE SEARCH (cherche sur TOUS les job boards)
# ============================================================
def google_search(query, num_pages=3):
    """Scrape Google search results pour trouver des offres sur tous les sites d'emploi"""
    resultats = []

    for page in range(num_pages):
        start = page * 10
        url = f"https://www.google.com/search?q={quote_plus(query)}&start={start}&hl=fr&gl=fr"

        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Extraire les résultats de recherche
            for div in soup.find_all("div", class_="g"):
                lien = div.find("a", href=True)
                titre_el = div.find("h3")
                snippet_el = div.find("div", class_=re.compile("VwiC3b|IsZvec|s3v9rd"))

                if not lien or not titre_el:
                    continue

                href = lien["href"]
                titre = titre_el.get_text(strip=True)
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                resultats.append({
                    "url": href,
                    "titre": titre,
                    "snippet": snippet,
                })

            time.sleep(2)  # Respecter Google
        except Exception as e:
            continue

    return resultats


def extraire_entreprise_from_google(resultat):
    """Essaie d'extraire le nom de l'entreprise depuis un résultat Google"""
    titre = resultat["titre"]
    url = resultat["url"]
    snippet = resultat["snippet"]

    entreprise = ""

    # Patterns communs dans les titres d'offres
    # "Stage Développeur - NomEntreprise - Paris"
    # "NomEntreprise recrute un Stage Développeur"
    # "Offre de stage chez NomEntreprise"

    # Essayer d'extraire depuis le titre
    patterns = [
        r'(?:chez|at|@)\s+(.+?)(?:\s*[-|,]|$)',       # "chez NomEntreprise"
        r'^(.+?)\s+(?:recrute|recherche|propose)',      # "NomEntreprise recrute"
        r'[-|]\s*(.+?)\s*[-|]',                         # "Poste - Entreprise - Lieu"
        r'[-|]\s*(.+?)$',                               # "Poste - Entreprise" (fin)
    ]

    for pattern in patterns:
        match = re.search(pattern, titre, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            # Filtrer les faux positifs
            noise = ["indeed", "hellowork", "linkedin", "glassdoor", "apec",
                     "monster", "cadremploi", "welcome to the jungle", "stage",
                     "alternance", "emploi", "offre", "paris", "france",
                     "ile-de-france", "île-de-france", "h/f", "f/h", "cdi", "cdd"]
            if candidate.lower() not in noise and len(candidate) > 2 and len(candidate) < 50:
                entreprise = candidate
                break

    # Essayer aussi depuis le domaine de welcometothejungle
    if not entreprise and "welcometothejungle.com/fr/companies/" in url:
        match = re.search(r'/companies/([^/]+)', url)
        if match:
            entreprise = match.group(1).replace("-", " ").title()

    return entreprise


def chercher_google_jobs(mots_cles, region_label, types):
    """Utilise Google pour chercher des offres sur TOUS les sites d'emploi"""
    offres = []

    # Construire les requêtes Google ciblées
    sites_query = " OR ".join([f"site:{s}" for s in JOB_SITES[:10]])  # Top 10

    for t in types:
        queries = [
            f'{t} {mots_cles} {region_label} ({sites_query})',
            f'{t} {mots_cles} {region_label} recrutement email',
            f'{t} {mots_cles} {region_label} postuler',
        ]

        for query in queries:
            resultats = google_search(query, num_pages=2)

            for r in resultats:
                entreprise = extraire_entreprise_from_google(r)
                if entreprise:
                    # Extraire le domaine du site de l'entreprise (pas du job board)
                    url_ent = ""
                    parsed = urlparse(r["url"])
                    domain = parsed.netloc.replace("www.", "")
                    # Si c'est un job board, pas besoin de garder l'URL
                    if not any(jb in domain for jb in JOB_SITES):
                        url_ent = f"https://{domain}"

                    # Chercher un email dans le snippet
                    email = ""
                    found = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', r["snippet"])
                    if found:
                        email = found[0].lower()

                    offres.append({
                        "titre": r["titre"],
                        "entreprise": entreprise,
                        "url_entreprise": url_ent,
                        "lieu": region_label,
                        "email": email,
                        "source": f"Google ({domain})",
                    })

            time.sleep(1)

    return offres


# ============================================================
# SOURCE 3 : SCRAPING DIRECT des sites accessibles
# ============================================================
def scraper_site_direct(url, source_name):
    """Scrape un site directement et extrait les JSON-LD JobPosting"""
    offres = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return offres

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extraire JSON-LD (standard sur beaucoup de sites)
        scripts = soup.find_all("script", {"type": "application/ld+json"})
        for script in scripts:
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item, dict) and item.get("@type") == "JobPosting":
                        org = item.get("hiringOrganization", {})
                        if isinstance(org, dict) and org.get("name"):
                            loc = item.get("jobLocation", {})
                            address = ""
                            if isinstance(loc, dict):
                                addr = loc.get("address", {})
                                if isinstance(addr, dict):
                                    address = addr.get("addressLocality", "")
                                elif isinstance(loc, list) and loc:
                                    addr = loc[0].get("address", {})
                                    if isinstance(addr, dict):
                                        address = addr.get("addressLocality", "")

                            offres.append({
                                "titre": item.get("title", ""),
                                "entreprise": org.get("name", ""),
                                "url_entreprise": org.get("sameAs", "") or org.get("url", ""),
                                "lieu": address,
                                "email": "",
                                "source": source_name,
                            })
            except Exception:
                pass

    except Exception:
        pass
    return offres


def scraper_sites_directs(mots_cles, region_label, types):
    """Essaye de scraper directement plusieurs sites d'emploi"""
    offres = []

    for t in types:
        query = f"{t} {mots_cles}".replace(" ", "-").lower()
        query_plus = f"{t} {mots_cles}".replace(" ", "+").lower()
        query_encoded = quote_plus(f"{t} {mots_cles}")
        region_url = region_label.lower().replace(" ", "-").replace("'", "").replace("é", "e").replace("î", "i").replace("ô", "o")

        urls_to_try = [
            # Indeed
            (f"https://fr.indeed.com/jobs?q={query_encoded}&l={quote_plus(region_label)}", "Indeed"),
            # HelloWork
            (f"https://www.hellowork.com/fr-fr/emploi/recherche.html?k={query_encoded}&l={quote_plus(region_label)}", "HelloWork"),
            # Cadremploi
            (f"https://www.cadremploi.fr/emploi/liste_offres?motscles={query_encoded}&ville={quote_plus(region_label)}", "Cadremploi"),
            # Monster
            (f"https://www.monster.fr/emploi/recherche?q={query_encoded}&where={quote_plus(region_label)}", "Monster"),
            # Meteojob
            (f"https://www.meteojob.com/jobsearch/offers?what={query_encoded}&where={quote_plus(region_label)}", "Meteojob"),
            # Talent.com
            (f"https://fr.talent.com/jobs?q={query_encoded}&l={quote_plus(region_label)}", "Talent.com"),
            # Glassdoor
            (f"https://www.glassdoor.fr/Emploi/{query}-emplois-SRCH_KO0,{len(query)}.htm", "Glassdoor"),
            # Jooble
            (f"https://fr.jooble.org/emploi-{query}/{region_url}", "Jooble"),
            # OptionCarriere
            (f"https://www.optioncarriere.com/emploi?s={query_encoded}&l={quote_plus(region_label)}", "OptionCarriere"),
        ]

        for url, source in urls_to_try:
            site_offres = scraper_site_direct(url, source)
            if site_offres:
                offres.extend(site_offres)
            time.sleep(1)

    return offres


# ============================================================
# HUNTER.IO
# ============================================================
def chercher_email_hunter(domaine=None, company=None):
    if not HUNTER_API_KEY or HUNTER_API_KEY == "TA_CLE_HUNTER":
        return []
    params = {"api_key": HUNTER_API_KEY, "limit": 5}
    if domaine:
        params["domain"] = domaine
    elif company:
        params["company"] = company
    else:
        return []
    try:
        resp = requests.get("https://api.hunter.io/v2/domain-search", params=params, timeout=10)
        resp.raise_for_status()
        return [e["value"] for e in resp.json().get("data", {}).get("emails", []) if e.get("confidence", 0) >= 20]
    except Exception:
        return []


def extraire_domaine(url):
    if not url:
        return ""
    try:
        parsed = urlparse(url if url.startswith("http") else f"http://{url}")
        domaine = parsed.netloc or parsed.path
        domaine = re.sub(r"^www\.", "", domaine)
        ignore = ["indeed.com", "indeed.fr", "hellowork.com", "welcometothejungle.com",
                   "linkedin.com", "francetravail.fr", "pole-emploi.fr", "apec.fr",
                   "cadremploi.fr", "monster.fr", "glassdoor.fr", "meteojob.com",
                   "google.com", "jooble.org", "talent.com", "optioncarriere.com",
                   "keljob.com", "regionsjob.com", "jobijoba.com", "wizbii.com",
                   "directemploi.com", "staffme.com", "studyrama.com", "letudiant.fr"]
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
    print("=" * 60)
    print(f"  {len(JOB_SITES)} sites d'emploi indexes")
    print("  Sources : France Travail + Google + Scraping + Hunter.io")

    # Domaine
    print()
    mots_cles = input("  Domaine (ex: developpeur informatique) : ").strip()
    if not mots_cles:
        mots_cles = "developpeur informatique"
        print(f"  -> Par defaut : {mots_cles}")

    # Region
    region_cle, region_code, region_nom = choisir_region()
    region_label = REGIONS_LABEL.get(region_cle, region_nom)
    print(f"  -> Region : {region_label}")

    # Type
    print()
    print("  Type :")
    print("    1. Stage uniquement")
    print("    2. Alternance uniquement")
    print("    3. Les deux")
    choix = input("  Choix (1/2/3) [3] : ").strip() or "3"
    types = {"1": ["stage"], "2": ["alternance"], "3": ["stage", "alternance"]}.get(choix, ["stage", "alternance"])

    # ======= COLLECTE =======
    print()
    print("  " + "=" * 50)
    print("  COLLECTE DES OFFRES (patiente, ca cherche partout)")
    print("  " + "=" * 50)

    toutes_offres = []

    # 1. France Travail API
    print("\n  [1/3] France Travail API...")
    token = get_france_travail_token()
    if token:
        for t in types:
            offres = chercher_france_travail(token, f"{t} {mots_cles}", region_code)
            print(f"    -> {len(offres)} offres ({t})")
            toutes_offres.extend(offres)
    else:
        print("    -> Connexion echouee")

    # 2. Google Search (cherche sur TOUS les sites d'emploi)
    print(f"\n  [2/3] Google Search (sur {len(JOB_SITES)} sites d'emploi)...")
    offres_google = chercher_google_jobs(mots_cles, region_label, types)
    print(f"    -> {len(offres_google)} entreprises trouvees via Google")
    toutes_offres.extend(offres_google)

    # 3. Scraping direct des sites accessibles
    print(f"\n  [3/3] Scraping direct (9 sites)...")
    offres_scraping = scraper_sites_directs(mots_cles, region_label, types)
    print(f"    -> {len(offres_scraping)} offres via scraping direct")
    toutes_offres.extend(offres_scraping)

    # Dedup par nom d'entreprise
    vus = set()
    offres_uniques = []
    for o in toutes_offres:
        nom = o["entreprise"].strip().lower()
        if nom and nom != "inconnue" and len(nom) > 1 and nom not in vus:
            vus.add(nom)
            offres_uniques.append(o)

    print(f"\n  => {len(offres_uniques)} entreprises uniques trouvees")

    if not offres_uniques:
        print("  [!] Aucune offre trouvee.")
        return

    # ======= EMAILS =======
    print()
    print("  " + "=" * 50)
    print("  RECHERCHE DES EMAILS")
    print("  " + "=" * 50)

    resultats = []
    emails_vus = set()
    hunter_calls = 0
    MAX_HUNTER = 45

    # Phase 1 : Emails deja trouves
    offres_sans = []
    for o in offres_uniques:
        if o["email"] and o["email"] not in emails_vus:
            emails_vus.add(o["email"])
            resultats.append(o)
        else:
            offres_sans.append(o)

    print(f"\n  Phase 1 - Emails dans les offres : {len(resultats)}")

    # Phase 2 : Hunter.io
    if HUNTER_API_KEY and HUNTER_API_KEY != "TA_CLE_HUNTER":
        nb = min(len(offres_sans), MAX_HUNTER)
        print(f"  Phase 2 - Hunter.io ({nb} entreprises)...")

        for o in offres_sans:
            if hunter_calls >= MAX_HUNTER:
                print(f"    [!] Limite credtis atteinte ({MAX_HUNTER})")
                break

            nom = o["entreprise"]
            if not nom or len(nom) <= 1:
                continue

            emails = []

            # Par domaine
            dom = extraire_domaine(o["url_entreprise"])
            if dom:
                emails = chercher_email_hunter(domaine=dom)
                hunter_calls += 1

            # Par nom
            if not emails:
                emails = chercher_email_hunter(company=nom)
                hunter_calls += 1

            if emails:
                best = emails[0]
                if best not in emails_vus:
                    emails_vus.add(best)
                    o["email"] = best
                    o["source"] += " + Hunter.io"
                    resultats.append(o)
                    print(f"    [+] {nom} -> {best}")

            time.sleep(0.4)

        print(f"    {hunter_calls} appels effectues")

    # ======= RESULTATS =======
    print()
    print("=" * 60)
    print(f"  RESULTATS : {len(resultats)} emails trouves !")
    print("=" * 60)

    if not resultats:
        print("  [!] Aucun email trouve.")
        return

    for i, r in enumerate(resultats, 1):
        print(f"\n  {i:3d}. {r['entreprise']}")
        print(f"       Email  : {r['email']}")
        print(f"       Poste  : {r['titre']}")
        if r["lieu"]:
            print(f"       Lieu   : {r['lieu']}")
        print(f"       Source : {r['source']}")

    # CSV
    fichier = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emails_trouves.csv")
    with open(fichier, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Email", "Entreprise", "Poste", "Lieu", "Source"])
        for r in resultats:
            w.writerow([r["email"], r["entreprise"], r["titre"], r["lieu"], r["source"]])

    print(f"\n  [+] Sauvegarde dans emails_trouves.csv")

    # Envoyer ?
    print()
    choix = input("  Envoyer ton mail a tous ces contacts ? (o/N) : ").strip().lower()
    if choix == "o":
        from config import MON_EMAIL, OBJET
        from envoyer import envoyer_mail
        print(f"\n  [*] Envoi de {len(resultats)} mails...")
        ok = 0
        for i, r in enumerate(resultats, 1):
            print(f"  [{i}/{len(resultats)}] -> {r['email']} ({r['entreprise']})")
            try:
                envoyer_mail(r["email"])
                ok += 1
                time.sleep(2)
            except Exception as e:
                print(f"    [!] Echec : {e}")
        print(f"\n  [+] {ok}/{len(resultats)} mails envoyes !")


if __name__ == "__main__":
    main()
