from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
import faiss
import os
import pickle

PDF_PATH = "data/nfip_policy.pdf"
VECTOR_PATH = "vectorstore/index.faiss"
META_PATH = "vectorstore/meta.pkl"

os.makedirs("vectorstore", exist_ok=True)

# Load PDF
reader = PdfReader(PDF_PATH)

texts = []
metadata = []

for i, page in enumerate(reader.pages):
    text = page.extract_text()
    if text:
        chunks = [text[j:j+1000] for j in range(0, len(text), 800)]
        for chunk in chunks:
            texts.append(chunk)
            metadata.append({"page": i + 1})

# Embeddings (LOCAL, FREE)
model = SentenceTransformer("all-MiniLM-L6-v2")
embeddings = model.encode(texts)

# FAISS
index = faiss.IndexFlatL2(embeddings.shape[1])
index.add(embeddings)

faiss.write_index(index, VECTOR_PATH)

with open(META_PATH, "wb") as f:
    pickle.dump({"texts": texts, "meta": metadata}, f)

print("✅ Vector store created successfully (FREE, LOCAL)")
