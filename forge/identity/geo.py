"""forge.identity.geo - Geographic database and regional national ID shapes.

Provides coherent locale datasets:
- Cities, ZIP/postal codes, area codes, streets
- Culture-matched first & last name pools
- Algorithmic national ID generators (US SSN, ID NIK, JP My Number, BR CPF, DE Personalausweis)
"""
from __future__ import annotations

import random
from typing import Dict, Tuple

COUNTRIES = ["US", "GB", "JP", "ID", "DE", "BR", "CA", "FR", "IT", "ES", "AU", "SG", "NL", "SE"]

COUNTRY_LABEL = {
    "US": "United States",
    "GB": "United Kingdom",
    "JP": "Japan",
    "ID": "Indonesia",
    "DE": "Germany",
    "BR": "Brazil",
    "CA": "Canada",
    "FR": "France",
    "IT": "Italy",
    "ES": "Spain",
    "AU": "Australia",
    "SG": "Singapore",
    "NL": "Netherlands",
    "SE": "Sweden",
}

GEO: dict[str, dict] = {
    "US": {
        "phone_fmt": "(aaa) nnn-nnnn",
        "id_name": "ssn",
        "cities": {
            "10001": {"city": "New York", "state": "NY", "area": "212",
                      "streets": ["W 23rd St", "Broadway", "8th Ave", "7th Ave"]},
            "90210": {"city": "Beverly Hills", "state": "CA", "area": "310",
                      "streets": ["Rodeo Dr", "Wilshire Blvd", "Canon Dr", "Crescent Dr"]},
            "60601": {"city": "Chicago", "state": "IL", "area": "312",
                      "streets": ["N Michigan Ave", "E Wacker Dr", "N State St"]},
            "33101": {"city": "Miami", "state": "FL", "area": "305",
                      "streets": ["Biscayne Blvd", "Ocean Dr", "Collins Ave", "Washington Ave"]},
            "98101": {"city": "Seattle", "state": "WA", "area": "206",
                      "streets": ["Pine St", "Pike St", "4th Ave", "Union St"]},
            "78701": {"city": "Austin", "state": "TX", "area": "512",
                      "streets": ["Congress Ave", "E 6th St", "W 5th St", "Lavaca St"]},
        },
        "ssn_state_block": {"NY": 50, "CA": 550, "IL": 320, "FL": 260, "WA": 530, "TX": 460},
    },
    "GB": {
        "phone_fmt": "+44 7nnn nnnnnn",
        "id_name": "nino",
        "cities": {
            "EC1A 1BB": {"city": "London", "state": "Greater London", "area": "20",
                         "streets": ["Baker St", "Oxford St", "Piccadilly", "Fleet St"]},
            "M1 1AD": {"city": "Manchester", "state": "Greater Manchester", "area": "161",
                       "streets": ["Deansgate", "Market St", "King St", "Portland St"]},
            "EH1 1YZ": {"city": "Edinburgh", "state": "Midlothian", "area": "131",
                        "streets": ["Princes St", "George St", "Royal Mile", "Rose St"]},
        },
    },
    "JP": {
        "phone_fmt": "090-nnnn-nnnn",
        "id_name": "my_number",
        "cities": {
            "160-0022": {"city": "Shinjuku, Tokyo", "state": "Tokyo", "area": "03",
                         "streets": ["Shinjuku", "Nishi-Shinjuku", "Yotsuya"]},
            "530-0001": {"city": "Kita, Osaka", "state": "Osaka", "area": "06",
                         "streets": ["Umeda", "Dojima", "Tenma"]},
            "460-0008": {"city": "Naka, Nagoya", "state": "Aichi", "area": "052",
                         "streets": ["Nishiki", "Sakae", "Marunouchi"]},
        },
    },
    "ID": {
        "phone_fmt": "0812-nnnn-nnn",
        "id_name": "nik",
        "cities": {
            "10110": {"city": "Jakarta Pusat", "state": "DKI Jakarta", "area": "021",
                      "nik_regency": "71", "nik_districts": list(range(1, 9)),  # 31.71.01-08 (8 kecamatan)
                      "streets": ["Jl. Thamrin", "Jl. Sudirman", "Jl. Kebon Sirih"]},
            "40111": {"city": "Bandung", "state": "Jawa Barat", "area": "022",
                      "nik_regency": "73", "nik_districts": list(range(1, 31)),  # 32.73.01-30 (30 kecamatan)
                      "streets": ["Jl. Asia Afrika", "Jl. Braga", "Jl. Merdeka"]},
            "80111": {"city": "Denpasar", "state": "Bali", "area": "0361",
                      "nik_regency": "71", "nik_districts": list(range(1, 5)),  # 51.71.01-04 (4 kecamatan)
                      "streets": ["Jl. Sunset Road", "Jl. Teuku Umar", "Jl. Raya Kuta"]},
        },
    },
    "DE": {
        "phone_fmt": "+49 a nnnnnnn",
        "id_name": "personalausweis",
        "cities": {
            "10115": {"city": "Berlin", "state": "Berlin", "area": "30",
                      "streets": ["Torstrasse", "Invalidenstrasse", "Chausseestrasse"]},
            "80331": {"city": "Munchen", "state": "Bayern", "area": "89",
                      "streets": ["Kaufingerstrasse", "Sendlinger Strasse", "Prannerstrasse"]},
            "60311": {"city": "Frankfurt", "state": "Hessen", "area": "69",
                      "streets": ["Kaiserstrasse", "Zeil", "Rossmarkt"]},
        },
    },
    "BR": {
        "phone_fmt": "+55 a nnnnn-nnnn",
        "id_name": "cpf",
        "cities": {
            "01310-100": {"city": "Sao Paulo", "state": "SP", "area": "11",
                          "streets": ["Av. Paulista", "Rua Augusta", "Rua Bela Cintra"]},
            "20040-020": {"city": "Rio de Janeiro", "state": "RJ", "area": "21",
                          "streets": ["Av. Rio Branco", "Rua Primeiro de Marco", "Rua Uruguaiana"]},
        },
    },
    "CA": {
        "phone_fmt": "+1 (aaa) nnn-nnnn",
        "id_name": "sin",
        "cities": {
            "M5V 2T6": {"city": "Toronto", "state": "ON", "area": "416",
                        "streets": ["King St W", "Queen St W", "Yonge St", "Bay St"]},
            "V6B 1A1": {"city": "Vancouver", "state": "BC", "area": "604",
                        "streets": ["Granville St", "Robson St", "Main St", "W Georgia St"]},
            "H3A 1B1": {"city": "Montreal", "state": "QC", "area": "514",
                        "streets": ["Rue Sainte-Catherine", "Rue Sherbrooke", "Rue St-Denis", "Ave McGill College"]},
            "K1A 0A9": {"city": "Ottawa", "state": "ON", "area": "613",
                        "streets": ["Elgin St", "Rideau St", "Bank St", "Wellington St"]},
        },
    },
    "FR": {
        "phone_fmt": "+33 a nn nn nn nn",
        "id_name": "nir",
        "cities": {
            "75001": {"city": "Paris", "state": "Ile-de-France", "area": "1",
                      "streets": ["Rue de Rivoli", "Avenue des Champs-Elysees", "Rue Saint-Honore", "Boulevard Haussmann"]},
            "13001": {"city": "Marseille", "state": "Provence-Alpes-Cote d'Azur", "area": "4",
                      "streets": ["Rue Paradis", "La Canebiere", "Rue Saint-Ferreol", "Quai du Port"]},
            "69001": {"city": "Lyon", "state": "Auvergne-Rhone-Alpes", "area": "4",
                      "streets": ["Rue de la Republique", "Place Bellecour", "Rue Victor Hugo", "Rue des Marronniers"]},
            "33000": {"city": "Bordeaux", "state": "Nouvelle-Aquitaine", "area": "5",
                      "streets": ["Rue Sainte-Catherine", "Cours de l'Intendance", "Rue Port Dijeaux"]},
        },
    },
    "IT": {
        "phone_fmt": "+39 a nnn nnnn",
        "id_name": "codice_fiscale",
        "cities": {
            "00187": {"city": "Roma", "state": "Lazio", "area": "06", "cf_code": "H501",
                      "streets": ["Via del Corso", "Via Veneto", "Piazza di Spagna", "Via Nazionale"]},
            "20121": {"city": "Milano", "state": "Lombardia", "area": "02", "cf_code": "F205",
                      "streets": ["Via Montenapoleone", "Corso Buenos Aires", "Via della Moscova", "Corso Vittorio Emanuele II"]},
            "10121": {"city": "Torino", "state": "Piemonte", "area": "011", "cf_code": "L219",
                      "streets": ["Via Po", "Via Roma", "Via Garibaldi", "Via Pietro Micca"]},
            "50123": {"city": "Firenze", "state": "Toscana", "area": "055", "cf_code": "D612",
                      "streets": ["Via de' Tornabuoni", "Via Calzaiuoli", "Borgo Ognissanti"]},
        },
    },
    "ES": {
        "phone_fmt": "+34 6nn nnn nnn",
        "id_name": "nie",
        "cities": {
            "28013": {"city": "Madrid", "state": "Comunidad de Madrid", "area": "91",
                      "streets": ["Calle de Alcala", "Gran Via", "Calle de la Montera", "Calle Fuencarral"]},
            "08001": {"city": "Barcelona", "state": "Cataluna", "area": "93",
                      "streets": ["La Rambla", "Passeig de Gracia", "Carrer de Balmes"]},
            "46001": {"city": "Valencia", "state": "Comunidad Valenciana", "area": "96",
                      "streets": ["Calle Colon", "Calle de la Paz", "Calle San Vicente"]},
            "41001": {"city": "Sevilla", "state": "Andalucia", "area": "95",
                      "streets": ["Calle Sierpes", "Avenida de la Constitucion", "Calle Tetuan"]},
        },
    },
    "AU": {
        "phone_fmt": "+61 4nn nnn nnn",
        "id_name": "tfn",
        "cities": {
            "2000": {"city": "Sydney", "state": "NSW", "area": "2",
                     "streets": ["George St", "Pitt St", "Oxford St", "Castlereagh St"]},
            "3000": {"city": "Melbourne", "state": "VIC", "area": "3",
                     "streets": ["Collins St", "Swanston St", "Bourke St", "Flinders Ln"]},
            "4000": {"city": "Brisbane", "state": "QLD", "area": "7",
                     "streets": ["Queen St", "Albert St", "Adelaide St", "Edward St"]},
            "6000": {"city": "Perth", "state": "WA", "area": "8",
                     "streets": ["St Georges Terrace", "Hay St", "William St", "Murray St"]},
        },
    },
    "SG": {
        "phone_fmt": "+65 nnnn nnnn",
        "id_name": "nric",
        "cities": {
            "018956": {"city": "Singapore", "state": "Singapore", "area": "",
                       "streets": ["Raffles Place", "Robinson Rd", "Marina Blvd", "Cecil St"]},
            "238859": {"city": "Singapore", "state": "Singapore", "area": "",
                       "streets": ["Orchard Rd", "Scotts Rd", "Cairnhill Rd", "Cuppage Rd"]},
        },
    },
    "NL": {
        "phone_fmt": "+31 6 nn nn nn nn",
        "id_name": "bsn",
        "cities": {
            "1012": {"city": "Amsterdam", "state": "Noord-Holland", "area": "20",
                     "streets": ["Damrak", "Kalverstraat", "Nieuwendijk", "Rokin"]},
            "3011": {"city": "Rotterdam", "state": "Zuid-Holland", "area": "10",
                     "streets": ["Coolsingel", "Meent", "Hoogstraat", "Mariniersweg"]},
            "2511": {"city": "Den Haag", "state": "Zuid-Holland", "area": "70",
                     "streets": ["Spuistraat", "Grote Marktstraat", "Kneuterdijk"]},
        },
    },
    "SE": {
        "phone_fmt": "+46 7n nnn nnn",
        "id_name": "personnummer",
        "cities": {
            "111 57": {"city": "Stockholm", "state": "Stockholms lan", "area": "08",
                       "streets": ["Drottninggatan", "Sveavagen", "Gotgatan", "Kungsgatan"]},
            "411 03": {"city": "Goteborg", "state": "Vastra Gotaland", "area": "031",
                       "streets": ["Avenyn", "Drottninggatan", "Kungsgatan"]},
            "211 22": {"city": "Malmo", "state": "Skane", "area": "040",
                       "streets": ["Sodra Forstadsgatan", "Ostra Ronneholmsvagen"]},
        },
    },
}

NAMES: dict[str, dict[str, tuple[str, ...]]] = {
    "US": {
        "first": ("James", "Mary", "Robert", "Patricia", "John", "Jennifer",
                  "Michael", "Linda", "David", "Elizabeth", "William", "Jessica"),
        "last": ("Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia",
                 "Miller", "Davis", "Rodriguez", "Wilson", "Anderson", "Taylor"),
    },
    "JP": {
        "first": ("Hiroshi", "Yuki", "Takashi", "Sakura", "Kenji", "Aoi",
                  "Daiki", "Hana", "Ryo", "Mei", "Sora", "Yui"),
        "last": ("Sato", "Suzuki", "Takahashi", "Tanaka", "Watanabe", "Ito",
                 "Yamamoto", "Nakamura", "Kobayashi", "Kato", "Yoshida", "Sasaki"),
    },
    "ID": {
        "first": ("Rizky", "Dimas", "Bayu", "Arif", "Fajar", "Putra", "Siti",
                  "Dewi", "Ayu", "Putri", "Wulan", "Budi"),
        "last": ("Pratama", "Saputra", "Wijaya", "Hidayat", "Nugroho", "Setiawan",
                 "Kusuma", "Permana", "Gunawan", "Santoso", "Wibowo", "Lestari"),
    },
    "GB": {
        "first": ("Oliver", "George", "Arthur", "Noah", "Olivia", "Amelia",
                  "Isla", "Ava", "Harry", "Jack", "Emily", "Charlotte"),
        "last": ("Smith", "Jones", "Taylor", "Brown", "Williams", "Wilson",
                 "Johnson", "Davies", "Robinson", "Wright", "Thompson", "Evans"),
    },
    "DE": {
        "first": ("Lukas", "Felix", "Jonas", "Leon", "Anna", "Lena", "Julia",
                  "Sophie", "Maximilian", "Niklas", "Elena", "Laura"),
        "last": ("Muller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer",
                 "Wagner", "Becker", "Hoffmann", "Schulz", "Koch", "Bauer"),
    },
    "BR": {
        "first": ("Miguel", "Arthur", "Gabriel", "Rafael", "Sofia", "Helena",
                  "Alice", "Laura", "Thiago", "Bruno", "Lucas", "Pedro"),
        "last": ("Silva", "Santos", "Oliveira", "Souza", "Lima", "Pereira",
                 "Costa", "Almeida", "Nascimento", "Araujo", "Ribeiro", "Carvalho"),
    },
    "CA": {
        "first": ("Liam", "Emma", "Noah", "Olivia", "William", "Charlotte",
                  "Lucas", "Sophie", "Ethan", "Mia", "Benjamin", "Chloe"),
        "last": ("Smith", "Tremblay", "Gagnon", "Roy", "Cote", "Wilson",
                 "Taylor", "Campbell", "Martin", "Brown", "Lee", "MacLeod"),
    },
    "FR": {
        "first": ("Lucas", "Emma", "Louis", "Lea", "Marc", "Julie",
                  "Thomas", "Camille", "Nicolas", "Sarah", "Antoine", "Marine"),
        "last": ("Martin", "Bernard", "Dubois", "Thomas", "Robert", "Richard",
                 "Petit", "Durand", "Leroy", "Moreau", "Simon", "Laurent"),
    },
    "IT": {
        "first": ("Francesco", "Chiara", "Alessandro", "Giulia", "Luca", "Martina",
                  "Matteo", "Federica", "Giovanni", "Silvia", "Marco", "Elena"),
        "last": ("Rossi", "Russo", "Ferrari", "Esposito", "Bianchi", "Romano",
                 "Colombo", "Ricci", "Marino", "Greco", "Bruno", "Gallo"),
    },
    "ES": {
        "first": ("Alejandro", "Lucia", "Javier", "Carmen", "Miguel", "Maria",
                  "David", "Paula", "Jorge", "Alba", "Sergio", "Marta"),
        "last": ("Garcia", "Fernandez", "Lopez", "Martinez", "Sanchez", "Perez",
                 "Gomez", "Martin", "Jimenez", "Ruiz", "Hernandez", "Diaz"),
    },
    "AU": {
        "first": ("Jack", "Olivia", "Lachlan", "Charlotte", "Cooper", "Amelia",
                  "Noah", "Mia", "Harry", "Emily", "Oscar", "Sophie"),
        "last": ("Smith", "Jones", "Williams", "Brown", "Wilson", "Taylor",
                 "Lee", "Nguyen", "Martin", "Thompson", "Harris", "Walker"),
    },
    "SG": {
        "first": ("Wei", "Li", "Jun", "Mei", "Kai", "Xin",
                  "Yong", "Ling", "Jian", "Hui", "Sheng", "Ying"),
        "last": ("Tan", "Lim", "Lee", "Ng", "Chua", "Ong",
                 "Goh", "Tay", "Yap", "Wong", "Koh", "Teo"),
    },
    "NL": {
        "first": ("Daan", "Emma", "Sem", "Sophie", "Bram", "Fleur",
                  "Lars", "Anouk", "Thijs", "Sanne", "Joris", "Iris"),
        "last": ("de Vries", "Jansen", "van den Berg", "Bakker", "Visser", "Smit",
                 "Meijer", "Mulder", "de Boer", "Koning", "Vos", "Peters"),
    },
    "SE": {
        "first": ("Erik", "Anna", "Lars", "Maria", "Karl", "Elin",
                  "Magnus", "Sara", "Anders", "Emma", "Johan", "Karin"),
        "last": ("Andersson", "Johansson", "Karlsson", "Nilsson", "Eriksson",
                 "Larsson", "Olsson", "Persson", "Svensson", "Gustafsson",
                 "Lindberg", "Lindqvist"),
    },
}


def us_ssn(state: str, rnd: Any = random) -> str:
    """SSN-shaped ID. Respects SSA allocation blocks."""
    block = (GEO["US"].get("ssn_state_block") or {}).get(state)
    if block:
        area = block * 10 + rnd.randint(1, 9)
        area = min(area, 899)
    else:
        area = rnd.randint(1, 899)
    if area == 666:
        area = 665
    return f"{area:03d}-{rnd.randint(1, 99):02d}-{rnd.randint(1, 9999):04d}"


def id_nik(zip_code: str, rnd: Any = random, dob: Optional[str] = None, female: bool = False) -> str:
    """Indonesian NIK (16 digit): PP KK CC DDMMYY SSSS using Kemendagri codes.

    PP=province, KK=regency, CC=district from the ZIP's city record;
    DDMMYY=birthdate (female: day+40); SSSS=registration serial (>=1).
    """
    geo = GEO["ID"]["cities"].get(zip_code)
    prov = {"10110": "31", "40111": "32", "80111": "51"}.get(zip_code, "31")
    reg = (geo or {}).get("nik_regency") or f"{rnd.randint(1, 75):02d}"
    dist = f"{rnd.choice((geo or {}).get('nik_districts') or range(1, 58)):02d}"
    if dob:
        mm, dd, yy = dob.split("/")
        yy = yy[2:]
        day = int(dd) + (40 if female else 0)
    else:
        # Plausible adult birth year (never a future birthdate), matching
        # generate_dob()'s 18-65 window.
        year = rnd.randint(1961, 2008)
        day = rnd.randint(1, 28) + (40 if female else 0)
        mm, yy = f"{rnd.randint(1, 12):02d}", f"{year % 100:02d}"
    serial = f"{rnd.randint(1, 9999):04d}"
    return f"{prov}{reg}{dist}{day:02d}{mm}{yy}{serial}"


def jp_my_number(rnd: Any = random) -> str:
    """Japanese My Number (12 digits with weighted check digit)."""
    digits = [rnd.randint(0, 9) for _ in range(11)]
    weights = list(range(6, 1, -1)) + list(range(9, 0, -1)) + list(range(8, 0, -1))
    s = sum(d * w for d, w in zip(digits, weights))
    check = (s % 11)
    check = 0 if check <= 1 else 11 - check
    digits.append(check)
    return "".join(map(str, digits))
def uk_nino(rnd: Any = random) -> str:
    """UK National Insurance Number (NINO) format: e.g. QQ 12 34 56 A."""
    letters = "ABCDEFGHJKLMNPRSTWXYZ"
    prefix = rnd.choice("ABCEGHJKLMNOPRSTWXYZ") + rnd.choice(letters)
    digits = f"{rnd.randint(100000, 999999):06d}"
    suffix = rnd.choice("ABCD")
    return f"{prefix} {digits[:2]} {digits[2:4]} {digits[4:6]} {suffix}"


def br_cpf(rnd: Any = random) -> str:
    """Brazilian CPF (11 digits with dual modulo-11 check digits)."""
    def calc(nums: list[int], weights: list[int]) -> int:
        s = sum(n * w for n, w in zip(nums, weights))
        r = (s * 10) % 11
        return 0 if r == 10 else r

    nums = [rnd.randint(0, 9) for _ in range(9)]
    d1 = calc(nums, list(range(10, 1, -1)))
    d2 = calc(nums + [d1], list(range(11, 1, -1)))
    return "".join(map(str, nums)) + f"{d1}{d2}"


def de_steuer(rnd: Any = random) -> str:
    """German Tax ID / Personalausweis shape."""
    return f"{rnd.randint(10, 99)}{rnd.randint(100000, 999999)}"[:11]


def _luhn_check_digit(digits: str) -> str:
    """Luhn check digit (ISO/IEC 7812) for a partial numeric string."""
    total = 0
    for i, d in enumerate([int(c) for c in digits][::-1]):
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - (total % 10)) % 10)


def ca_sin(rnd: Any = random) -> str:
    """Canadian Social Insurance Number: 9 digits, Luhn-valid, first digit 1-8.

    Digits 9 excludes temporary-status SINs; 0 is not issued.
    """
    while True:
        partial = f"{rnd.randint(1, 8)}{rnd.randint(0, 9999999):07d}"
        out = partial + _luhn_check_digit(partial)
        if int(out) % 100 > 0:  # avoid the all-zeros-looking reserved pattern
            return out


def fr_nir(zip_code: str, dob: Optional[str] = None, female: bool = False,
           rnd: Any = random) -> str:
    """French INSEE/NIR: sex(1) YY MM dep(2) com(3) ord(3) + mod-97 key(2).

    15 digits; key = 97 - (first 13 digits mod 97). Department comes from the
    address's postal code so the ID matches the identity that owns it.
    """
    if dob:
        mm, dd, yy = dob.split("/")
    else:
        yy = str(rnd.randint(1961, 2008))
        mm = f"{rnd.randint(1, 12):02d}"
        dd = f"{rnd.randint(1, 28):02d}"
    sex = "2" if female else "1"
    dep = str(zip_code)[:2]
    com = f"{rnd.randint(0, 999):03d}"
    ord_ = f"{rnd.randint(1, 999):03d}"
    num = f"{sex}{yy[2:]}{mm}{dep}{com}{ord_}"
    key = 97 - (int(num) % 97)
    return f"{num}{key:02d}"


def it_cf(last: str, first: str, dob: Optional[str] = None, female: bool = False,
          cf_code: str = "H501", rnd: Any = random) -> str:
    """Italian Codice Fiscale: 16 char (surname/given/year/month/day/place)+EIGEN.

    Uses the official einfachen tables: consonants first (given name takes the
    1st, 3rd and 4th when there are four or more), vowel padding to X, real
    check digit over the 15-char body.
    """
    _VOWELS = "AEIOU"

    def block(word: str, surname: bool) -> str:
        word = (word or "").upper()
        cons = [c for c in word if c.isalpha() and c not in _VOWELS]
        vows = [c for c in word if c in _VOWELS]
        if surname:
            letters = (cons + vows)[:3]
        elif len(cons) >= 4:
            letters = [cons[0], cons[2], cons[3]]
        else:
            letters = (cons + vows)[:3]
        return "".join(letters).ljust(3, "X")

    if dob:
        mm, dd, yy = dob.split("/")
    else:
        yy = str(rnd.randint(1961, 2008))
        mm = f"{rnd.randint(1, 12):02d}"
        dd = f"{rnd.randint(1, 28):02d}"
    day = str(int(dd) + (40 if female else 0)).rjust(2, "0")
    body = f"{block(last, True)}{block(first, False)}{yy[2:]}{'ABCDEHLMPRST'[int(mm)-1]}{day}{cf_code}"

    odd = {"0": 1, "1": 0, "2": 5, "3": 7, "4": 9, "5": 13, "6": 15, "7": 17, "8": 19, "9": 21,
           "A": 1, "B": 0, "C": 5, "D": 7, "E": 9, "F": 13, "G": 15, "H": 17, "I": 19,
           "J": 21, "K": 2, "L": 4, "M": 18, "N": 20, "O": 11, "P": 3, "Q": 6, "R": 8,
           "S": 12, "T": 14, "U": 16, "V": 10, "W": 22, "X": 25, "Y": 24, "Z": 23}
    even = {"0": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
            "A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5, "G": 6, "H": 7, "I": 8, "J": 9,
            "K": 10, "L": 11, "M": 12, "N": 13, "O": 14, "P": 15, "Q": 16, "R": 17, "S": 18,
            "T": 19, "U": 20, "V": 21, "W": 22, "X": 23, "Y": 24, "Z": 25}
    total = 0
    for i, ch in enumerate(body):
        total += (odd if i % 2 == 0 else even)[ch]
    return body + chr(65 + (total % 26))


def es_nie(rnd: Any = random) -> str:
    """Spanish DNI/NIE: 8 digits + control letter (num % 23 table)."""
    table = "TRWAGMYFPDXBNJZSQVHLCKE"
    num = rnd.randint(1000000, 99999999)
    return f"{num:08d}{table[num % 23]}"


def au_tfn(rnd: Any = random) -> str:
    """Australian Tax File Number: 9 digits whose weighted sum is 0 mod 11.

    Weights (1,4,3,7,5,8,6,9,10) run from the least significant digit.
    """
    while True:
        digits = [rnd.randint(0, 9) for _ in range(8)]
        digits[0] = rnd.randint(1, 9)
        # weights increase right-to-left: d9 gets 10, d1 gets 1
        s8 = sum(d * w for d, w in zip(digits, (1, 4, 3, 7, 5, 8, 6, 9)))
        d9 = (10 * ((11 - s8 % 11) % 11)) % 11
        if 0 <= d9 <= 9:
            return "".join(map(str, digits)) + str(d9)


def sg_nric(rnd: Any = random) -> str:
    """Singapore NRIC (S series): S + 7 digits + check letter (sum % 11 table)."""
    weights = (2, 7, 6, 5, 4, 3, 2)
    digits = [str(rnd.randint(0, 9)) for _ in range(7)]
    rem = sum(int(d) * w for d, w in zip(digits, weights)) % 11
    nric_type = rnd.choice(("S", "T"))
    if nric_type == "S":
        return "S" + "".join(digits) + "JZIHGFEDCBA"[rem]
    return "T" + "".join(digits) + "XWUTRQPNMLK"[rem]


def nl_bsn(rnd: Any = random) -> str:
    """Dutch BSN: 9 digits with (9..2 * first eight) - ninth == 0 mod 11."""
    while True:
        digits = [rnd.randint(0, 9) for _ in range(8)]
        digits[0] = rnd.randint(1, 9)
        s8 = sum(d * w for d, w in zip(digits, (9, 8, 7, 6, 5, 4, 3, 2)))
        d9 = s8 % 11
        if d9 != 10:
            return "".join(map(str, digits)) + str(d9)


def se_personnummer(dob: Optional[str] = None, rnd: Any = random) -> str:
    """Swedish personnummer: YYYYMMDDNNNC where C is a Luhn check digit.

    12-digit identity card format; the checksum is computed over the 9-digit
    string YYMMDD + serial, the documented form.
    """
    if dob:
        mm, dd, yy = dob.split("/")
    else:
        yy = str(rnd.randint(1961, 2008))
        mm = f"{rnd.randint(1, 12):02d}"
        dd = f"{rnd.randint(1, 28):02d}"
    serial = f"{rnd.randint(0, 999):03d}"
    check = _luhn_check_digit(f"{yy[2:]}{mm}{dd}{serial}")
    return f"{yy}{mm}{dd}{serial}{check}"


def format_phone(fmt: str, area: str, rnd: Any = random) -> str:
    """Render the country phone template: 'a' -> area code, 'n' -> random digit."""
    out = []
    area_used = False
    for ch in fmt:
        if ch == "a":
            if not area_used:
                out.append(area)
                area_used = True
        elif ch == "n":
            out.append(str(rnd.randint(0, 9)))
        else:
            out.append(ch)
    return "".join(out)
