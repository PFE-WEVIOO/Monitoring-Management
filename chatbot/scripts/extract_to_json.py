import os
import json
from chatbot.utils.extract import extract_text_from_pdf

DATA_DIR = "chatbot/data"
OUTPUT_DIR = "chatbot/extracted"

os.makedirs(OUTPUT_DIR, exist_ok=True)

for filename in os.listdir(DATA_DIR):
    if filename.endswith(".pdf"):
        pdf_path = os.path.join(DATA_DIR, filename)
        text = extract_text_from_pdf(pdf_path)

        json_data = {
            "filename": filename,
            "content": text   # ✅ clé corrigée ici
        }

        output_path = os.path.join(OUTPUT_DIR, filename.replace(".pdf", ".json"))
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

        print(f"✅ {filename} extrait avec succès.")
