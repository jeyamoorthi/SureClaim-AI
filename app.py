from dotenv import load_dotenv
load_dotenv()

import os
import streamlit as st
import faiss, pickle
import numpy as np
from sentence_transformers import SentenceTransformer
from huggingface_hub import InferenceClient
import google.generativeai as genai
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# ---------------- CONFIG ----------------
st.set_page_config(layout="wide")
st.title("SureClaim AI – Appian Knowledge Copilot")

# ---------------- GEMINI (QUESTION SUGGESTION ONLY) ----------------
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
gemini = genai.GenerativeModel("gemini-1.5-flash")

# ---------------- SIDEBAR : CASE CONTEXT ----------------
st.sidebar.header("Case Record")

CLAIM_TYPE = "Flood"
STATE = "Florida"
POLICY = "NFIP Flood Insurance"

st.sidebar.write(f"Claim Type: {CLAIM_TYPE}")
st.sidebar.write(f"State: {STATE}")
st.sidebar.write(f"Policy: {POLICY}")

st.sidebar.divider()
st.sidebar.subheader("Context-Aware Suggestions")

case_context = f"""
Claim Type: {CLAIM_TYPE}
State: {STATE}
Policy: {POLICY}
"""

suggestion_prompt = f"""
Suggest 4 policy-related questions an insurance agent may ask.
Rules:
- ONLY questions
- NO answers
- NO explanations

Context:
{case_context}
"""

try:
    g_resp = gemini.generate_content(suggestion_prompt)
    suggestions = [
        q.strip("-• ").strip()
        for q in g_resp.text.split("\n")
        if q.strip()
    ][:4]
except Exception:
    suggestions = [
        "Is damage to a basement covered under this flood insurance policy?",
        "What items are excluded from basement coverage?",
        "What is the maximum payout limit under this policy?",
        "Does Coverage D apply to this claim?"
    ]

if "auto_query" not in st.session_state:
    st.session_state.auto_query = ""

for q in suggestions:
    if st.sidebar.button(q):
        st.session_state.auto_query = q

# ---------------- LOAD VECTOR STORE ----------------
index = faiss.read_index("vectorstore/index.faiss")

with open("vectorstore/meta.pkl", "rb") as f:
    store = pickle.load(f)

texts = store["texts"]
meta = store["meta"]

# ---------------- MODELS ----------------
embedder = SentenceTransformer("all-MiniLM-L6-v2")

llm = InferenceClient(
    model="HuggingFaceH4/zephyr-7b-beta",
    token=os.environ.get("HF_TOKEN")
)

# ---------------- MAIN INPUT ----------------
query = st.text_input(
    "Ask a policy question",
    value=st.session_state.auto_query,
    placeholder="Ask about coverage, exclusions, limits, or compliance"
)

# ---------------- RAG PIPELINE ----------------
if query:
    with st.spinner("Analyzing policy…"):
        q_emb = embedder.encode([query])
        D, I = index.search(np.array(q_emb), k=8)  # 🔑 IMPORTANT

        context_blocks = []
        pages = set()

        for idx in I[0]:
            context_blocks.append(texts[idx])
            pages.add(meta[idx]["page"])

        context = "\n\n".join(context_blocks)

        system_message = """
You are SureClaim AI, an enterprise insurance policy copilot.

STRICT RULES:
- Use ONLY the provided policy context.
- DO NOT invent facts.
- DO NOT ask new questions.
- If coverage depends on conditions, EXPLAIN the conditions.
- Only say "Cannot determine" if the policy text truly provides no guidance.

RESPONSE FORMAT (MANDATORY):

Decision:
One clear sentence (Yes / No / Conditional)

Explanation:
- Bullet points in plain English
- Summarize rules and conditions
- NO citations inside text

"""

        user_message = f"""
Policy Context:
{context}

Question:
{query}
"""

        response = llm.chat.completions.create(
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            max_tokens=300,
            temperature=0.2
        )

        answer = response.choices[0].message.content.strip()

        # ---------------- SAFE PARSING ----------------
        if "Decision:" in answer:
            decision_text = answer.split("Decision:")[1].split("Explanation:")[0].strip()
        else:
            decision_text = "Cannot determine from the available policy."

        if "Explanation:" in answer:
            explanation_text = answer.split("Explanation:")[1].strip()
        else:
            explanation_text = "The policy text does not clearly define this scenario."

        # ---------------- OUTPUT ----------------
        st.markdown("### Decision")
        st.success(decision_text)

        st.markdown("### Explanation")
        st.markdown(explanation_text)

        st.markdown("### Evidence and Provenance")
        st.markdown(
            "Cited Pages: " +
            ", ".join([f"Page {p}" for p in sorted(pages)])
        )

        with st.expander("Source Verification (Audit Trail)"):
            for p in sorted(pages):
                st.write(f"Policy Document – Page {p}")

# ---------------- APPIAN ALIGNMENT ----------------
with st.expander("How this aligns with Appian"):
    st.write("""
- Gemini is used only for workflow question suggestions
- Policy decisions are grounded in indexed documents
- AI operates inside case context
- All answers are explainable and auditable
- Human review remains the final authority
""")
