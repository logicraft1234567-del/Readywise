import io
def extract_text(f):
    name = f.name.lower(); data = f.read()
    if name.endswith(".pdf"):
        import fitz
        with fitz.open(stream=data, filetype="pdf") as d: return "\n".join(p.get_text() for p in d)
    if name.endswith(".docx"):
        import docx
        return "\n".join(p.text for p in docx.Document(io.BytesIO(data)).paragraphs)
    return data.decode("utf-8", "ignore")
