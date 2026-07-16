"""Multilingual search and classification vocabulary.

The list is intentionally conservative. English terms are always used because
GDELT searches machine-translated article text; local-language phrases improve
Brave Search coverage in national media and public price lists.
"""

from __future__ import annotations

COMMON_TERMS = {
    "interchange": [
        "interchange fee", "interchange fees", "interchange rate",
        "multilateral interchange fee", "MIF",
    ],
    "scheme_fee": [
        "scheme fee", "scheme fees", "card scheme fee", "card network fee",
        "network fee", "assessment fee", "brand fee",
    ],
    "processing_fee": [
        "processing fee", "card processing fee", "authorisation fee",
        "authorization fee", "clearing fee", "settlement fee",
    ],
    "merchant_service_charge": [
        "merchant service charge", "merchant discount rate", "merchant fee",
        "card acceptance fee", "acquiring fee", "card acquiring fee",
    ],
}

LOCAL_TERMS = {
    "bg": {
        "interchange": ["междубанкова такса", "такса обмен"],
        "scheme_fee": ["такса на картова схема", "мрежова такса"],
        "processing_fee": ["такса за обработка на карта"],
        "merchant_service_charge": ["такса за приемане на карти", "такса за търговец"],
    },
    "cs": {
        "interchange": ["mezibankovní poplatek", "interchange poplatek"],
        "scheme_fee": ["poplatek karetního schématu", "síťový poplatek", "poplatek karetní asociaci"],
        "processing_fee": ["poplatek za zpracování karetní transakce", "autorizační poplatek"],
        "merchant_service_charge": ["poplatek za přijímání karet", "akceptační poplatek", "poplatek obchodníka za karty"],
    },
    "da": {
        "interchange": ["interbankgebyr", "interchangegebyr"],
        "scheme_fee": ["kortsystemgebyr", "netværksgebyr"],
        "processing_fee": ["kortbehandlingsgebyr"],
        "merchant_service_charge": ["indløsningsgebyr", "gebyr for kortaccept"],
    },
    "de": {
        "interchange": ["Interbankenentgelt", "Interchange-Gebühr"],
        "scheme_fee": ["Kartensystemgebühr", "Scheme Fee", "Netzwerkgebühr"],
        "processing_fee": ["Kartenverarbeitungsgebühr", "Autorisierungsgebühr"],
        "merchant_service_charge": ["Händlerentgelt", "Kartenakzeptanzgebühr", "Acquiring-Gebühr"],
    },
    "el": {
        "interchange": ["διατραπεζική προμήθεια"],
        "scheme_fee": ["τέλος συστήματος καρτών", "τέλος δικτύου"],
        "processing_fee": ["τέλος επεξεργασίας κάρτας"],
        "merchant_service_charge": ["προμήθεια αποδοχής καρτών", "χρέωση εμπόρου"],
    },
    "en": COMMON_TERMS,
    "es": {
        "interchange": ["tasa de intercambio", "comisión de intercambio"],
        "scheme_fee": ["tarifa del esquema de tarjetas", "tarifa de red"],
        "processing_fee": ["tarifa de procesamiento de tarjetas", "tasa de autorización"],
        "merchant_service_charge": ["tasa de descuento del comercio", "comisión por aceptación de tarjetas", "comisión de adquirencia"],
    },
    "et": {
        "interchange": ["vahendustasu", "kaardimakse vahendustasu"],
        "scheme_fee": ["kaardiskeemi tasu", "võrgutasu"],
        "processing_fee": ["kaarditöötlustasu"],
        "merchant_service_charge": ["kaardi vastuvõtmise tasu", "kaupmehetasu"],
    },
    "fi": {
        "interchange": ["siirtohinta", "interchange-maksu"],
        "scheme_fee": ["korttijärjestelmämaksu", "verkkomaksu"],
        "processing_fee": ["kortinkäsittelymaksu"],
        "merchant_service_charge": ["korttimaksujen vastaanottomaksu", "kauppiasmaksu"],
    },
    "fr": {
        "interchange": ["commission d'interchange", "taux d'interchange"],
        "scheme_fee": ["frais de réseau de cartes", "frais de schéma", "frais de réseau"],
        "processing_fee": ["frais de traitement des cartes", "frais d'autorisation"],
        "merchant_service_charge": ["commission commerçant", "frais d'acceptation des cartes", "commission d'acquisition"],
    },
    "hr": {
        "interchange": ["međubankovna naknada", "interchange naknada"],
        "scheme_fee": ["naknada kartične sheme", "mrežna naknada"],
        "processing_fee": ["naknada za obradu kartice"],
        "merchant_service_charge": ["naknada za prihvat kartica", "trgovačka naknada"],
    },
    "hu": {
        "interchange": ["bankközi jutalék", "interchange díj"],
        "scheme_fee": ["kártyatársasági díj", "hálózati díj"],
        "processing_fee": ["kártyafeldolgozási díj"],
        "merchant_service_charge": ["kártyaelfogadási díj", "kereskedői díj"],
    },
    "is": {
        "interchange": ["millibankagjald", "interchange gjald"],
        "scheme_fee": ["kortakerfisgjald", "netgjald"],
        "processing_fee": ["kortavinnslugjald"],
        "merchant_service_charge": ["kortamóttökugjald", "kaupmannagjald"],
    },
    "it": {
        "interchange": ["commissione interbancaria", "commissione di interscambio"],
        "scheme_fee": ["commissione del circuito", "commissione di rete"],
        "processing_fee": ["commissione di elaborazione carta", "commissione di autorizzazione"],
        "merchant_service_charge": ["commissione esercente", "commissione di accettazione carte", "commissione di acquiring"],
    },
    "lt": {
        "interchange": ["tarpbankinis mokestis", "interchange mokestis"],
        "scheme_fee": ["kortelių schemos mokestis", "tinklo mokestis"],
        "processing_fee": ["kortelės apdorojimo mokestis"],
        "merchant_service_charge": ["kortelių priėmimo mokestis", "prekybininko mokestis"],
    },
    "lv": {
        "interchange": ["starpbanku komisija", "interchange maksa"],
        "scheme_fee": ["karšu shēmas maksa", "tīkla maksa"],
        "processing_fee": ["karšu apstrādes maksa"],
        "merchant_service_charge": ["karšu pieņemšanas maksa", "tirgotāja komisija"],
    },
    "nl": {
        "interchange": ["interchangevergoeding", "interbancaire vergoeding"],
        "scheme_fee": ["kaartschemavergoeding", "netwerkvergoeding"],
        "processing_fee": ["kaartverwerkingskosten", "autorisatiekosten"],
        "merchant_service_charge": ["merchant service charge", "kaartacceptatiekosten", "acquiringkosten"],
    },
    "no": {
        "interchange": ["formidlingsgebyr", "interchangegebyr"],
        "scheme_fee": ["kortsystemgebyr", "nettverksgebyr"],
        "processing_fee": ["kortbehandlingsgebyr"],
        "merchant_service_charge": ["innløsningsgebyr", "gebyr for kortaksept"],
    },
    "pl": {
        "interchange": ["opłata interchange", "opłata międzybankowa"],
        "scheme_fee": ["opłata organizacji kartowej", "opłata schematowa", "opłata sieciowa"],
        "processing_fee": ["opłata za przetwarzanie kart", "opłata autoryzacyjna"],
        "merchant_service_charge": ["opłata akceptanta", "opłata za akceptację kart", "prowizja acquiringowa"],
    },
    "pt": {
        "interchange": ["taxa de intercâmbio", "comissão de intercâmbio"],
        "scheme_fee": ["taxa do esquema de cartões", "taxa de rede"],
        "processing_fee": ["taxa de processamento de cartões", "taxa de autorização"],
        "merchant_service_charge": ["taxa de serviço ao comerciante", "taxa de aceitação de cartões", "taxa de adquirência"],
    },
    "ro": {
        "interchange": ["comision interbancar", "taxă de interchange"],
        "scheme_fee": ["taxă de schemă de card", "taxă de rețea"],
        "processing_fee": ["taxă de procesare a cardului", "taxă de autorizare"],
        "merchant_service_charge": ["comision de acceptare a cardurilor", "comision comerciant", "comision de acquiring"],
    },
    "sk": {
        "interchange": ["medzibankový poplatok", "interchange poplatok"],
        "scheme_fee": ["poplatok kartovej schémy", "sieťový poplatok"],
        "processing_fee": ["poplatok za spracovanie kartovej transakcie"],
        "merchant_service_charge": ["poplatok za prijímanie kariet", "akceptačný poplatok", "poplatok obchodníka"],
    },
    "sl": {
        "interchange": ["medbančna provizija", "interchange provizija"],
        "scheme_fee": ["provizija kartične sheme", "omrežnina"],
        "processing_fee": ["provizija za obdelavo kartice"],
        "merchant_service_charge": ["provizija za sprejem kartic", "trgovska provizija"],
    },
    "sv": {
        "interchange": ["mellanbanksavgift", "interchangeavgift"],
        "scheme_fee": ["kortsystemavgift", "nätverksavgift"],
        "processing_fee": ["kortbehandlingsavgift"],
        "merchant_service_charge": ["inlösenavgift", "avgift för kortacceptans"],
    },
}

CARD_SEGMENT_TERMS = {
    "consumer": [
        "consumer", "personal", "retail card", "debit card", "credit card",
        "spotřebitelsk", "osobní kart", "privatkort", "Verbraucherkarte",
        "particulier", "consommateur", "konsumenck", "konsument",
    ],
    "commercial": [
        "commercial", "business card", "corporate card", "company card",
        "firemní", "podnikatelsk", "obchodní kart", "Firmenkarte",
        "carte commerciale", "carte professionnelle", "karta biznesowa",
        "kort firmowy", "tarjeta comercial", "carta aziendale",
    ],
}

NETWORK_TERMS = {
    "visa": ["visa"],
    "mastercard": ["mastercard", "master card"],
}

SOURCE_TYPE_DOMAINS = {
    "official_network": ["visa.com", "visa.co.uk", "mastercard.com"],
    "regulator": [
        "europa.eu", "ecb.europa.eu", "eba.europa.eu", "bis.org",
        "psr.org.uk", "kansascityfed.org", "riksbank.se", "bundesbank.de",
        "banque-france.fr", "bancaditalia.it", "bde.es", "nbp.pl",
        "cnb.cz", "mnb.hu", "bnr.ro", "nbs.sk", "bankofgreece.gr",
    ],
    "acquirer_or_psp": [
        "adyen.com", "stripe.com", "worldline.com", "nexi.com", "sumup.com",
        "checkout.com", "globalpayments.com", "fiserv.com", "elavon.com",
    ],
}


def terms_for(language: str, fee_type: str) -> list[str]:
    terms = list(COMMON_TERMS[fee_type])
    local = LOCAL_TERMS.get(language, {})
    terms.extend(local.get(fee_type, []))
    # stable dedup preserving order
    return list(dict.fromkeys(t for t in terms if t))
