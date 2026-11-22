LANGS = [("English", "en-US"), ("French", "fr-FR"), ("Spanish", "es-ES"), ("Portuguese", "pt-PT"), ("German", "de-DE"), ("Arabic", "ar-SA"),
         ("Hausa", "ha-NG"), ("Yoruba", "yo-NG"), ("Igbo", "ig-NG"), ("Swahili", "sw-KE"), ("Hindi", "hi-IN"), ("Chinese (Mandarin)", "zh-CN")]
def code(name): return dict(LANGS).get(name, "en-US")
