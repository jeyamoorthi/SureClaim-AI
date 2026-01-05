from dotenv import load_dotenv
load_dotenv()

import os
import streamlit as st
import faiss, pickle
import numpy as np
from sentence_transformers import SentenceTransformer
from huggingface_hub import InferenceClient
import google.generativeai as genai

# ---------------- CONFIG ----------------
st.set_page_config(layout="wide")
st.title("SureClaim AI – Appian Knowledge Copilot")
st.caption("Context-aware, policy-grounded decision support for high-stakes casework")

# ---------------- GEMINI (QUESTION SUGGESTION ONLY) ----------------
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
gemini = genai.GenerativeModel("gemini-1.5-flash")

# ---------------- SIDEBAR : CASE CONTEXT ----------------
st.sidebar.header("Case Record")

CLAIM_TYPE = "Flood"
STATE = "Florida"
POLICY = "NFIP Flood Insurance"

st.sidebar.write(f"**Case Type:** {CLAIM_TYPE}")
st.sidebar.write(f"**Jurisdiction:** {STATE}")
st.sidebar.write(f"**Policy Source:** {POLICY}")

st.sidebar.divider()
st.sidebar.subheader("Context-Aware Suggestions")

case_context = f"""
Case Type: {CLAIM_TYPE}
Jurisdiction: {STATE}
Policy Source: {POLICY}
"""

suggestion_prompt = f"""
Suggest 4 policy-related questions a support agent may ask.
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
        "Is damage to a basement covered under this policy?",
        "What items are excluded under this policy?",
        "What is the maximum payout limit?",
        "Does additional compliance coverage apply?"
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
    "Ask a policy or compliance question",
    value=st.session_state.auto_query,
    placeholder="Coverage, exclusions, limits, or regulatory conditions"
)

# ---------------- RAG PIPELINE ----------------
if query:
    with st.spinner("Analyzing relevant policy knowledge…"):
        q_emb = embedder.encode([query])
        D, I = index.search(np.array(q_emb), k=8)

        context_blocks = []
        pages = set()

        for idx in I[0]:
            context_blocks.append(texts[idx])
            pages.add(meta[idx]["page"])

        context = "\n\n".join(context_blocks)

        system_message = """
You are SureClaim AI, a policy-grounded knowledge copilot for regulated casework.

STRICT RULES:
- Use ONLY the provided document context
- NEVER invent or assume information
- If policy guidance is conditional, explain conditions clearly
- If guidance is missing, say so explicitly and responsibly

RESPONSE FORMAT (MANDATORY):

Decision:
Yes / No / Conditional / Cannot Determine

Explanation:
- Bullet points
- Plain, professional language
- Explain reasoning and limits
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
        decision_text = "Cannot determine from the available policy."
        explanation_text = "The document does not provide explicit guidance for this scenario."

        if "Decision:" in answer:
            decision_text = answer.split("Decision:")[1].split("Explanation:")[0].strip()

        if "Explanation:" in answer:
            explanation_text = answer.split("Explanation:")[1].strip()

        # ---------------- OUTPUT ----------------
        st.markdown("### Decision")
        st.success(decision_text)

        st.markdown("### Explanation")
        st.markdown(explanation_text)

        if "Cannot determine" in decision_text:
            st.info(
                "This does not indicate a failure. "
                "It highlights that the policy does not explicitly cover this scenario, "
                "allowing the agent to escalate or verify with confidence."
            )

        st.markdown("### Evidence and Provenance")
        st.markdown(
            "Cited Sections: " +
            ", ".join([f"Page {p}" for p in sorted(pages)])
        )

        with st.expander("Source Verification (Audit Trail)"):
            for p in sorted(pages):
                st.write(f"Policy Document – Page {p}")

# ---------------- APPIAN ALIGNMENT ----------------
with st.expander("How this fits inside an Appian workflow"):
    st.write("""
- Case context is read automatically from the active record
- Knowledge is retrieved just-in-time, not preloaded or memorized
- AI responses are always grounded in source documents
- Decisions remain human-controlled and audit-ready
- The same architecture applies across insurance, finance, and government casework
""")
