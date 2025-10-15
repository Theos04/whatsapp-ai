import json, os
from datetime import datetime

PERSONA_FILE = "data/personas.json"

def load_personas():
    return json.load(open(PERSONA_FILE)) if os.path.exists(PERSONA_FILE) else {}

def save_personas(personas):
    with open(PERSONA_FILE, "w") as f:
        json.dump(personas, f, indent=2)

def update_persona(phone, intent):
    personas = load_personas()
    persona = personas.get(phone, {"created": str(datetime.now()), "intents": []})
    persona["intents"].append(intent)
    personas[phone] = persona
    save_personas(personas)
    return persona
