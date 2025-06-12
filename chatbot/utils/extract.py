import fitz  # pymupdf
import re

def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    full_text = ""

    for page in doc:
        text = page.get_text()

        # Format YAML blocks
        if "apiVersion:" in text or "kind:" in text:
            text = re.sub(r"(apiVersion:[\s\S]+?)(?=\n\n|\Z)", r"```yaml\n\1\n```", text)

        # Format shell commands
        text = re.sub(r"(?m)^(sudo .*|kubectl .*|docker .*|curl .*|scp .*)", r"```bash\n\1\n```", text)

        full_text += text + "\n"

    return full_text
