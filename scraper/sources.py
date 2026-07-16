"""Static country and official source configuration for the tracker."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Country:
    name: str
    iso2: str
    eu_member: bool
    region: str
    language: str
    gdelt_source_country: str


EU_EEA_COUNTRIES = [
    Country("Austria", "AT", True, "Western", "de", "austria"),
    Country("Belgium", "BE", True, "Western", "nl", "belgium"),
    Country("Bulgaria", "BG", True, "CEE", "bg", "bulgaria"),
    Country("Croatia", "HR", True, "CEE", "hr", "croatia"),
    Country("Cyprus", "CY", True, "Southern", "el", "cyprus"),
    Country("Czech Republic", "CZ", True, "CEE", "cs", "czechrepublic"),
    Country("Denmark", "DK", True, "Nordic", "da", "denmark"),
    Country("Estonia", "EE", True, "CEE", "et", "estonia"),
    Country("Finland", "FI", True, "Nordic", "fi", "finland"),
    Country("France", "FR", True, "Western", "fr", "france"),
    Country("Germany", "DE", True, "Western", "de", "germany"),
    Country("Greece", "GR", True, "Southern", "el", "greece"),
    Country("Hungary", "HU", True, "CEE", "hu", "hungary"),
    Country("Ireland", "IE", True, "Western", "en", "ireland"),
    Country("Italy", "IT", True, "Southern", "it", "italy"),
    Country("Latvia", "LV", True, "CEE", "lv", "latvia"),
    Country("Lithuania", "LT", True, "CEE", "lt", "lithuania"),
    Country("Luxembourg", "LU", True, "Western", "fr", "luxembourg"),
    Country("Malta", "MT", True, "Southern", "en", "malta"),
    Country("Netherlands", "NL", True, "Western", "nl", "netherlands"),
    Country("Poland", "PL", True, "CEE", "pl", "poland"),
    Country("Portugal", "PT", True, "Southern", "pt", "portugal"),
    Country("Romania", "RO", True, "CEE", "ro", "romania"),
    Country("Slovakia", "SK", True, "CEE", "sk", "slovakia"),
    Country("Slovenia", "SI", True, "CEE", "sl", "slovenia"),
    Country("Spain", "ES", True, "Southern", "es", "spain"),
    Country("Sweden", "SE", True, "Nordic", "sv", "sweden"),
    Country("Iceland", "IS", False, "Nordic", "is", "iceland"),
    Country("Liechtenstein", "LI", False, "Western", "de", "liechtenstein"),
    Country("Norway", "NO", False, "Nordic", "no", "norway"),
]

REGIONS = ["CEE", "Western", "Nordic", "Southern"]
COUNTRY_BY_ISO2 = {c.iso2: c for c in EU_EEA_COUNTRIES}

NAME_ALIASES = {
    "Czech Republic": ["Czechia"],
    "Denmark": ["Denmark, Greenland & Faroe Islands", "Denmark, Greenland"],
}

MASTERCARD_LISTING_URL = (
    "https://www.mastercard.com/europe/en/business/support/"
    "merchant-interchange-rates.html"
)
VISA_LISTING_URL = (
    "https://www.visa.co.uk/about-visa/visa-in-europe/fees-and-interchange.html"
)

IFR_CAP = {
    "consumer_debit": 0.20,
    "consumer_credit": 0.30,
}
