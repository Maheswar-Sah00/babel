"""The 14 translation targets Babel plans for, and how Qloo's countries map onto them.

Copied from backtest/evaluate.py (the validated method); tests/test_plan.py checks they still match.
"""
# Steam language code -> the Steam review languages it covers (Spanish = Spain + Latin America)
TARGETS = {"schinese": ["schinese"], "japanese": ["japanese"], "koreana": ["koreana"], "brazilian": ["brazilian"],
           "russian": ["russian"], "spanish": ["spanish", "latam"], "turkish": ["turkish"], "german": ["german"],
           "french": ["french"], "tchinese": ["tchinese"], "polish": ["polish"], "italian": ["italian"],
           "ukrainian": ["ukrainian"], "thai": ["thai"]}
LABEL = {"schinese": "Simplified Chinese", "japanese": "Japanese", "koreana": "Korean", "brazilian": "Portuguese-BR",
         "russian": "Russian", "spanish": "Spanish", "turkish": "Turkish", "german": "German", "french": "French",
         "tchinese": "Traditional Chinese", "polish": "Polish", "italian": "Italian", "ukrainian": "Ukrainian",
         "thai": "Thai"}
# The copy-pasted tier list; also the tie-break order when two languages score the same
GENERIC = ["schinese", "japanese", "koreana", "brazilian", "russian", "spanish", "turkish", "german", "french",
           "tchinese", "polish", "thai", "ukrainian", "italian"]
COUNTRIES = {"schinese": ["CN"], "tchinese": ["TW", "HK", "MO"], "japanese": ["JP"], "koreana": ["KR"],
             "brazilian": ["BR"], "russian": ["RU", "BY", "KZ"], "spanish": ["ES", "MX", "AR", "CO", "CL", "PE"],
             "turkish": ["TR"], "german": ["DE", "AT", "CH"], "french": ["FR", "BE"], "polish": ["PL"],
             "italian": ["IT"], "ukrainian": ["UA"], "thai": ["TH"]}
POP = {"CN": 1410, "TW": 23, "HK": 7.5, "MO": 0.7, "JP": 124, "KR": 52, "BR": 216, "PT": 10, "RU": 144, "BY": 9,
       "KZ": 20, "ES": 48, "MX": 129, "AR": 46, "CO": 52, "CL": 19, "PE": 34, "TR": 85, "DE": 84, "AT": 9, "CH": 9,
       "FR": 68, "BE": 12, "PL": 37, "IT": 59, "UA": 37, "TH": 72}  # millions
COUNTRY_NAME = {"CN": "China", "TW": "Taiwan", "HK": "Hong Kong", "MO": "Macau", "JP": "Japan", "KR": "South Korea",
                "BR": "Brazil", "PT": "Portugal", "RU": "Russia", "BY": "Belarus", "KZ": "Kazakhstan", "ES": "Spain",
                "MX": "Mexico", "AR": "Argentina", "CO": "Colombia", "CL": "Chile", "PE": "Peru", "TR": "Turkey",
                "DE": "Germany", "AT": "Austria", "CH": "Switzerland", "FR": "France", "BE": "Belgium", "PL": "Poland",
                "IT": "Italy", "UA": "Ukraine", "TH": "Thailand"}
STEAM_SHARE = {"schinese": 31.39, "russian": 9.05, "spanish": 4.83, "brazilian": 3.70, "german": 2.48, "japanese": 2.41,
               "french": 2.08, "polish": 1.49, "koreana": 1.37, "tchinese": 1.27, "turkish": 1.09, "thai": 0.82,
               "ukrainian": 0.66, "italian": 0.56}  # Steam survey, Sep 2026, % of users
# Display only, never in a score: countries where a target language has official or national status (public
# reference data, e.g. the CIA World Factbook's language lists). COUNTRIES above is the model's own mapping; this lets
# the map say "French is also official in Canada, but Canada is not counted" instead of implying one language per
# country. Portuguese-BR is Brazil's variant: Portugal and other Portuguese-speaking countries are not listed for it.
OFFICIAL_IN = {
    "schinese": ["CN", "SG"], "tchinese": ["TW", "HK", "MO"], "japanese": ["JP"], "koreana": ["KR", "KP"],
    "brazilian": ["BR"], "russian": ["RU", "BY", "KZ", "KG"],
    "spanish": ["ES", "MX", "AR", "CO", "CL", "PE", "VE", "EC", "GT", "CU", "BO", "DO", "HN", "PY", "SV", "NI", "CR",
                "PA", "UY", "PR", "GQ"],
    "turkish": ["TR", "CY"], "german": ["DE", "AT", "CH", "LI", "LU", "BE"],
    "french": ["FR", "BE", "CH", "CA", "LU", "MC", "HT", "SN", "CI", "CM", "CD", "CG", "GA", "GN", "MG", "BJ", "TG",
               "CF", "TD", "DJ", "KM", "RW", "BI", "SC", "VU", "GQ"],
    "polish": ["PL"], "italian": ["IT", "CH", "SM"], "ukrainian": ["UA"], "thai": ["TH"],
}
# Steam store language names (appdetails "supported_languages") -> target code
STORE_NAME = {"Simplified Chinese": "schinese", "Traditional Chinese": "tchinese", "Japanese": "japanese",
              "Korean": "koreana", "Portuguese - Brazil": "brazilian", "Russian": "russian",
              "Spanish - Spain": "spanish", "Spanish - Latin America": "spanish", "Turkish": "turkish",
              "German": "german", "French": "french", "Polish": "polish", "Italian": "italian",
              "Ukrainian": "ukrainian", "Thai": "thai"}
