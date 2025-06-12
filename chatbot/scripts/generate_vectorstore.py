import os
import json
from chatbot.utils.embeddings import chunk_text, create_vectorstore

chunks = []
input_dir = "chatbot/extracted"

for file in os.listdir(input_dir):
    if file.endswith(".json"):
        filepath = os.path.join(input_dir, file)
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
            if "content" in data:
                chunks += chunk_text(data["content"])
            else:
                print(f"⚠️ Le fichier {file} ne contient pas la clé 'content'.")

if chunks:
    create_vectorstore(chunks)
    print("✅ Vectorstore généré avec succès.")
else:
    print("❌ Aucun chunk à indexer. Vérifiez les fichiers extraits.")
