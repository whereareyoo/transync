from deep_translator import GoogleTranslator

def translate(text: str, src: str = "en", tgt: str = "ru") -> str:
    text = (text or "").strip()
    if not text:
        return ""

    try:
        return GoogleTranslator(source=src, target=tgt).translate(text)
    except Exception as e:
        print("[MT ERROR]", e)
        return text