import re

def preprocess_text(text):
    text = text.lower()
    text = re.sub(r'[^a-zA-Z\s]', '', text)
    return text.strip()

def detect_intent(text):
    if any(greet in text for greet in ["hi", "hello", "hey"]):
        return "greeting"
    elif "order" in text:
        return "order"
    elif any(word in text for word in ["bye", "goodnight", "goodbye"]):
        return "farewell"
    else:
        return "unknown"
