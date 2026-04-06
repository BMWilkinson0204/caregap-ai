import json
import os
import re
from io import BytesIO
from typing import Any
from textwrap import dedent

import streamlit as st
from openai import OpenAI, RateLimitError
from PyPDF2 import PdfReader


st.set_page_config(
    page_title="CareGap AI",
    page_icon=":hospital:",
    layout="wide",
    initial_sidebar_state="collapsed",
)


DEMO_PATIENT_RECORD = """
Patient: Maria Johnson
DOB: 06/12/1962

Problem List:
- Type 2 diabetes mellitus with poor control
- Hypertension
- Hyperlipidemia
- Peripheral neuropathy
- Chronic kidney disease stage 3

Medication History:
- Metformin 1000 mg twice daily
- Insulin glargine 18 units nightly, prescribed 03/2023
- Lisinopril 20 mg daily
- Atorvastatin 40 mg nightly
- Pharmacy refill history in 2024 suggests intermittent insulin and lisinopril gaps

01/12/2023 - Primary care follow-up for diabetes and hypertension. HbA1c 9.2%, BP 162/94. Patient reports numbness in both feet and difficulty checking glucose regularly.
02/02/2023 - Referred to endocrinology and podiatry for uncontrolled diabetes and neuropathy.
03/01/2023 - Insulin glargine started due to persistent hyperglycemia. Recommended repeat HbA1c and basic metabolic panel in 3 months.
05/18/2023 - Missed endocrinology new patient appointment. No rescheduled visit documented.
06/22/2023 - Lab review overdue. Ordered HbA1c, CMP, urine microalbumin, and lipid panel not completed.
08/09/2023 - Urgent care visit for increasing redness and drainage from left plantar foot wound. Advised to go to emergency department if symptoms worsen and to follow with podiatry within 1 week.
08/14/2023 - Missed podiatry follow-up appointment.
10/03/2023 - Primary care note documents patient ran out of insulin for approximately 3 weeks and had inconsistent lisinopril use due to cost.
10/03/2023 - HbA1c 10.1%, creatinine 1.5 mg/dL, eGFR 42 mL/min/1.73m2, urine microalbumin elevated. No nephrology referral documented.
12/11/2023 - Emergency department visit for dizziness, weakness, and glucose >350 mg/dL. Treated with IV fluids and insulin. Discharged same day with recommendation for close PCP follow-up within 72 hours.
12/21/2023 - No completed primary care follow-up documented after ER visit.
01/26/2024 - Ophthalmology exam shows moderate nonproliferative diabetic retinopathy. Follow-up recommended in 4 months.
03/07/2024 - Care management outreach attempted regarding overdue labs and diabetes follow-up; unable to reach patient.
04/16/2024 - PCP visit for worsening fatigue and bilateral leg swelling. BP 168/96. Repeat labs ordered, including CMP, A1c, CBC, and lipid panel.
05/02/2024 - Missed lab appointment and missed PCP follow-up visit.
07/19/2024 - Emergency department visit for infected diabetic foot ulcer with surrounding cellulitis. Started on oral antibiotics and advised urgent wound care and podiatry follow-up.
07/29/2024 - No wound care visit completed within recommended timeframe.
09/05/2024 - Follow-up note states patient still has poor glucose monitoring adherence, has not seen endocrinology, and remains overdue for repeat kidney function testing and retinal follow-up.
""".strip()


LOW_RISK_DEMO_PATIENT_RECORD = """
Patient: Daniel Brooks
DOB: 03/28/1978

Problem List:
- Mild persistent asthma
- Hyperlipidemia
- Prediabetes

Medication History:
- Albuterol inhaler as needed
- Fluticasone inhaler twice daily
- Rosuvastatin 10 mg nightly

02/14/2024 - Annual primary care visit. Patient reports good exercise tolerance and no recent asthma exacerbations. HbA1c 5.9%, LDL 118 mg/dL.
02/14/2024 - Clinician recommended repeat lipid panel in 6 months and routine pulmonary follow-up as needed.
04/08/2024 - Telehealth follow-up for seasonal allergy symptoms with mild wheezing. Controller inhaler adherence reviewed and reinforced.
06/19/2024 - Screening colonoscopy referral placed.
07/11/2024 - Missed initial colonoscopy scheduling call; patient later returned call.
08/22/2024 - Repeat lipid panel completed. LDL improved to 92 mg/dL on rosuvastatin.
09/17/2024 - Preventive follow-up visit. No ER visits, hospitalizations, or urgent care needs in prior year. Asthma symptoms well controlled.
10/03/2024 - Colonoscopy completed with no major findings. Recommended routine interval follow-up.
11/21/2024 - Patient message requesting refill of fluticasone inhaler; refill sent without lapse in therapy documented.
01/16/2025 - Primary care follow-up confirms continued medication adherence, stable asthma control, and plan for repeat HbA1c in 6 months.
""".strip()


HIGH_RISK_DEMO_ANALYSIS = {
    "patient_summary": (
        "Patient has poorly controlled diabetes with chronic kidney disease, neuropathy, repeated missed "
        "specialty follow-ups, medication adherence gaps, overdue labs, and recurrent acute care use for "
        "hyperglycemia and diabetic foot complications."
    ),
    "risk_level": "High",
    "risk_score": 86,
    "timeline": [
        {
            "date": "01/12/2023",
            "event": "PCP follow-up showed uncontrolled chronic disease",
            "details": "HbA1c 9.2% and blood pressure 162/94 with neuropathy symptoms reported.",
        },
        {
            "date": "03/01/2023",
            "event": "Insulin initiated",
            "details": "Insulin glargine was started and repeat diabetes and kidney labs were recommended.",
        },
        {
            "date": "05/18/2023 to 08/14/2023",
            "event": "Specialty care delays",
            "details": "Endocrinology and podiatry follow-ups were missed without timely documented rescheduling.",
        },
        {
            "date": "10/03/2023",
            "event": "Medication and lab gaps documented",
            "details": "Patient ran out of insulin for about 3 weeks, used lisinopril inconsistently, and had worsening A1c and kidney markers.",
        },
        {
            "date": "12/11/2023",
            "event": "Emergency department visit for severe hyperglycemia",
            "details": "Treated with IV fluids and insulin, then discharged with recommendation for close PCP follow-up.",
        },
        {
            "date": "07/19/2024",
            "event": "Emergency department visit for infected diabetic foot ulcer",
            "details": "Started on antibiotics with urgent wound care and podiatry follow-up advised, but follow-up remained delayed.",
        },
    ],
    "risks_detected": [
        "Poorly controlled diabetes with evidence of progression to retinopathy, neuropathy, and chronic kidney disease.",
        "Recurrent diabetic foot complications with infection risk and risk of limb-threatening progression.",
        "Persistent hypertension increasing cardiovascular and renal risk.",
        "Medication nonadherence and access barriers affecting glycemic and blood pressure control.",
    ],
    "missed_care_or_delays": [
        "Missed endocrinology and podiatry follow-ups after referral.",
        "Overdue HbA1c, metabolic, lipid, and kidney monitoring labs.",
        "No timely documented primary care follow-up after ER visit for hyperglycemia.",
        "Delayed wound care follow-up after diabetic foot infection.",
    ],
    "recommended_actions": [
        "Arrange urgent primary care and endocrinology follow-up to address uncontrolled diabetes and insulin adherence barriers.",
        "Schedule immediate podiatry or wound care evaluation for ongoing diabetic foot risk.",
        "Repeat HbA1c, CMP, urine microalbumin, and renal function testing as soon as possible.",
        "Assess medication affordability, refill access, and home glucose monitoring adherence.",
        "Consider nephrology follow-up given CKD progression markers and persistent albuminuria.",
    ],
}


LOW_RISK_DEMO_ANALYSIS = {
    "patient_summary": (
        "Patient has generally stable chronic disease control with good medication adherence, completed preventive "
        "care, and only minor scheduling delays without evidence of acute deterioration."
    ),
    "risk_level": "Low",
    "risk_score": 24,
    "timeline": [
        {
            "date": "02/14/2024",
            "event": "Annual preventive visit",
            "details": "Asthma was stable, HbA1c was 5.9%, and LDL was mildly elevated.",
        },
        {
            "date": "04/08/2024",
            "event": "Telehealth respiratory follow-up",
            "details": "Seasonal symptoms were reviewed and inhaler adherence was reinforced.",
        },
        {
            "date": "08/22/2024",
            "event": "Repeat lipid monitoring completed",
            "details": "LDL improved on statin therapy, suggesting treatment adherence.",
        },
        {
            "date": "10/03/2024",
            "event": "Screening colonoscopy completed",
            "details": "Preventive follow-up was completed without major findings.",
        },
        {
            "date": "01/16/2025",
            "event": "Routine primary care follow-up",
            "details": "Chronic conditions remained stable and repeat HbA1c was planned.",
        },
    ],
    "risks_detected": [
        "Prediabetes requires ongoing surveillance to reduce progression risk.",
        "Asthma may worsen seasonally if controller adherence declines.",
    ],
    "missed_care_or_delays": [
        "Minor delay in colonoscopy scheduling, later completed without documented harm.",
    ],
    "recommended_actions": [
        "Continue current controller inhaler and statin adherence.",
        "Repeat HbA1c and lipid monitoring on schedule.",
        "Maintain preventive primary care follow-up and asthma symptom monitoring.",
    ],
}


ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "patient_summary": {"type": "string"},
        "risk_level": {"type": "string", "enum": ["Low", "Medium", "High"]},
        "risk_score": {"type": "integer", "minimum": 1, "maximum": 100},
        "timeline": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "event": {"type": "string"},
                    "details": {"type": "string"},
                },
                "required": ["date", "event", "details"],
                "additionalProperties": False,
            },
        },
        "risks_detected": {
            "type": "array",
            "items": {"type": "string"},
        },
        "missed_care_or_delays": {
            "type": "array",
            "items": {"type": "string"},
        },
        "recommended_actions": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "patient_summary",
        "risk_level",
        "risk_score",
        "timeline",
        "risks_detected",
        "missed_care_or_delays",
        "recommended_actions",
    ],
    "additionalProperties": False,
}

MAX_CHUNK_CHARS = 12000
CHUNK_OVERLAP_CHARS = 800


def inject_styles() -> None:
    st.markdown(
        """
        <style>
            .stApp {
                background:
                    radial-gradient(circle at top right, rgba(8, 145, 178, 0.12), transparent 28%),
                    linear-gradient(180deg, #f4f8fb 0%, #eef4f8 100%);
                color: #0f172a;
            }
            .hero {
                background: linear-gradient(135deg, #0f766e 0%, #164e63 100%);
                color: white;
                padding: 2.2rem 2.4rem;
                border-radius: 22px;
                margin-bottom: 1.5rem;
                box-shadow: 0 18px 45px rgba(15, 23, 42, 0.12);
            }
            .hero h1 {
                margin: 0;
                font-size: 2.5rem;
                font-weight: 700;
                letter-spacing: -0.03em;
            }
            .hero p {
                margin: 0.5rem 0 0;
                font-size: 1.05rem;
                opacity: 0.92;
            }
            .toolbar-card {
                background: rgba(255, 255, 255, 0.92);
                border: 1px solid rgba(148, 163, 184, 0.18);
                border-radius: 18px;
                padding: 1.1rem 1.2rem 0.2rem;
                box-shadow: 0 10px 28px rgba(15, 23, 42, 0.05);
                margin-bottom: 1.1rem;
            }
            .about-card {
                background: rgba(255, 255, 255, 0.9);
                border: 1px solid rgba(148, 163, 184, 0.18);
                border-radius: 18px;
                padding: 1.15rem 1.25rem;
                box-shadow: 0 10px 28px rgba(15, 23, 42, 0.05);
                margin-bottom: 1.1rem;
            }
            .use-case-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                gap: 0.8rem;
                margin-top: 1rem;
            }
            .use-case-item {
                background: rgba(15, 118, 110, 0.06);
                border: 1px solid rgba(15, 118, 110, 0.12);
                border-radius: 14px;
                padding: 0.85rem 0.95rem;
            }
            .use-case-title {
                color: #0f172a;
                font-size: 0.95rem;
                font-weight: 700;
                margin-bottom: 0.2rem;
            }
            .use-case-copy {
                color: #475569;
                font-size: 0.88rem;
                line-height: 1.45;
            }
            .section-card {
                background: rgba(255, 255, 255, 0.88);
                border: 1px solid rgba(148, 163, 184, 0.18);
                border-radius: 20px;
                padding: 1.2rem 1.25rem;
                box-shadow: 0 14px 32px rgba(15, 23, 42, 0.06);
                margin-bottom: 1.15rem;
                backdrop-filter: blur(8px);
            }
            .section-header {
                display: flex;
                align-items: center;
                gap: 0.55rem;
                margin-bottom: 0.85rem;
            }
            .section-icon {
                width: 2rem;
                height: 2rem;
                border-radius: 12px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: rgba(15, 118, 110, 0.12);
                color: #0f766e;
                font-size: 1rem;
                font-weight: 700;
            }
            .section-title {
                margin: 0;
                font-size: 1.08rem;
                font-weight: 700;
                color: #0f172a;
            }
            .risk-badge {
                display: inline-block;
                padding: 0.8rem 1.2rem;
                border-radius: 999px;
                font-weight: 700;
                font-size: 1rem;
                letter-spacing: 0.01em;
                color: white;
                box-shadow: 0 12px 24px rgba(15, 23, 42, 0.14);
            }
            .risk-score {
                margin-top: 1rem;
                margin-bottom: 0.35rem;
                color: #0f172a;
                font-size: 1.6rem;
                font-weight: 800;
            }
            .risk-score-label {
                color: #64748b;
                font-size: 0.88rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                margin-bottom: 0.45rem;
            }
            .risk-low {
                background: linear-gradient(135deg, #15803d 0%, #16a34a 100%);
            }
            .risk-medium {
                background: linear-gradient(135deg, #b45309 0%, #f59e0b 100%);
            }
            .risk-high {
                background: linear-gradient(135deg, #b91c1c 0%, #ef4444 100%);
            }
            .timeline-item {
                border-left: 3px solid #0f766e;
                padding: 0.1rem 0 0.9rem 0.9rem;
                margin-left: 0.25rem;
            }
            .timeline-date {
                color: #0f766e;
                font-weight: 700;
                font-size: 0.92rem;
                margin-bottom: 0.15rem;
            }
            .timeline-event {
                font-weight: 700;
                color: #0f172a;
                margin-bottom: 0.1rem;
            }
            .timeline-details {
                color: #334155;
                font-size: 0.95rem;
            }
            .muted {
                color: #475569;
                font-size: 0.95rem;
                line-height: 1.55;
            }
            ul.clean-list {
                margin: 0;
                padding-left: 1.2rem;
            }
            ul.clean-list li {
                margin-bottom: 0.45rem;
                color: #1e293b;
                line-height: 1.5;
            }
            .kpi-card {
                background: rgba(255, 255, 255, 0.94);
                border: 1px solid rgba(148, 163, 184, 0.18);
                border-radius: 18px;
                padding: 1rem 1.1rem;
                box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
                margin-bottom: 1rem;
            }
            .kpi-label {
                color: #64748b;
                font-size: 0.84rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                margin-bottom: 0.35rem;
            }
            .kpi-value {
                color: #0f172a;
                font-size: 1.9rem;
                font-weight: 800;
                line-height: 1;
                margin-bottom: 0.2rem;
            }
            .kpi-note {
                color: #475569;
                font-size: 0.9rem;
            }
            .footer {
                text-align: center;
                color: #64748b;
                font-size: 0.92rem;
                padding: 1.2rem 0 0.4rem;
            }
            .footer strong {
                color: #0f172a;
            }
            .risk-meter {
                margin-top: 0.65rem;
                margin-bottom: 0.5rem;
                width: 100%;
                height: 12px;
                background: #e2e8f0;
                border-radius: 999px;
                overflow: hidden;
            }
            .risk-meter-fill {
                height: 100%;
                border-radius: 999px;
            }
            div[data-testid="stButton"] > button {
                border-radius: 12px;
                min-height: 2.8rem;
                font-weight: 600;
            }
            div[data-testid="stFileUploader"] {
                margin-bottom: 0.85rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def extract_text_from_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(file_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(page.strip() for page in pages if page.strip())


def load_uploaded_text(uploaded_file: Any) -> str:
    if uploaded_file is None:
        return ""

    suffix = os.path.splitext(uploaded_file.name)[1].lower()
    file_bytes = uploaded_file.read()

    if suffix == ".pdf":
        return extract_text_from_pdf(file_bytes)

    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1", errors="ignore")


@st.cache_data(show_spinner=False)
def preprocess_record_text(record_text: str) -> str:
    cleaned_lines: list[str] = []
    seen_recent: list[str] = []

    for raw_line in record_text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        if re.fullmatch(r"(page|pg)\s*\d+(\s*of\s*\d+)?", line.lower()):
            continue
        if re.fullmatch(r"\d+\s*of\s*\d+", line.lower()):
            continue
        if line.lower().startswith(("confidential", "fax cover", "printed on", "scanned by")):
            continue
        if seen_recent and line == seen_recent[-1]:
            continue
        cleaned_lines.append(line)
        seen_recent.append(line)
        if len(seen_recent) > 25:
            seen_recent.pop(0)

    normalized_text = "\n".join(cleaned_lines)
    normalized_text = re.sub(r"\n{3,}", "\n\n", normalized_text)
    return normalized_text.strip()


@st.cache_data(show_spinner=False)
def split_record_into_chunks(record_text: str, max_chars: int = MAX_CHUNK_CHARS, overlap_chars: int = CHUNK_OVERLAP_CHARS) -> list[str]:
    if len(record_text) <= max_chars:
        return [record_text]

    paragraphs = [paragraph.strip() for paragraph in record_text.split("\n\n") if paragraph.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)
            overlap = current[-overlap_chars:].strip()
            current = f"{overlap}\n\n{paragraph}".strip() if overlap else paragraph
        else:
            chunks.append(paragraph[:max_chars])
            current = paragraph[max_chars - overlap_chars :].strip()

    if current:
        chunks.append(current)

    return chunks


def get_risk_badge(level: str) -> str:
    normalized = level.strip().lower()
    css_class = {
        "low": "risk-low",
        "medium": "risk-medium",
        "high": "risk-high",
    }.get(normalized, "risk-medium")
    return f'<span class="risk-badge {css_class}">{level}</span>'


def risk_level_from_score(score: int) -> str:
    safe_score = max(1, min(100, int(score)))
    if safe_score >= 67:
        return "High"
    if safe_score >= 34:
        return "Medium"
    return "Low"


def section_header(icon: str, title: str) -> str:
    return (
        "<div class='section-header'>"
        f"<span class='section-icon'>{icon}</span>"
        f"<div class='section-title'>{title}</div>"
        "</div>"
    )


def render_kpi_card(label: str, value: str, note: str) -> None:
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def risk_meter(score: int) -> str:
    safe_score = max(1, min(100, int(score)))
    if safe_score >= 67:
        color = "linear-gradient(135deg, #b91c1c 0%, #ef4444 100%)"
    elif safe_score >= 34:
        color = "linear-gradient(135deg, #b45309 0%, #f59e0b 100%)"
    else:
        color = "linear-gradient(135deg, #15803d 0%, #16a34a 100%)"

    return (
        "<div class='risk-meter'>"
        f"<div class='risk-meter-fill' style='width: {safe_score}%; background: {color};'></div>"
        "</div>"
    )


def final_analysis_instructions() -> str:
    return (
        "You are a healthcare risk review assistant for CareGap AI. Analyze only the information "
        "contained in the provided patient record summaries and return JSON only.\n\n"
        "Your output must map cleanly to these four sections:\n"
        "Timeline: a chronological list of the most important medical events.\n"
        "Risks: clinically meaningful risks, missed care, or delays in care.\n"
        "Risk Score: one integer from 1 to 100 based on overall severity and urgency.\n"
        "Risk Level: one value only, chosen from Low, Medium, or High, and it must match the score bands.\n"
        "Recommendations: 3 to 5 concise, actionable next steps.\n\n"
        "Writing requirements:\n"
        "- Be concise, professional, and healthcare-relevant.\n"
        "- Avoid repetition, filler, disclaimers, and unnecessary commentary.\n"
        "- Use short, specific statements grounded in the record.\n"
        "- Do not invent diagnoses, dates, or events not supported by the text.\n"
        "- Summarize missed care or delays separately from general risks when applicable.\n"
        "- Keep recommendations practical and appropriate for follow-up care review.\n"
        "- Set risk_score to reflect severity of risks, care delays, and likelihood of harm progression.\n"
        "- Use these exact score bands: 1 to 33 = Low, 34 to 66 = Medium, 67 to 100 = High."
    )


def analyze_chunk(client: OpenAI, chunk_text: str, chunk_index: int, total_chunks: int) -> dict[str, Any]:
    instructions = (
        "You are a healthcare risk review assistant for CareGap AI. Analyze only the information "
        "contained in this chunk of a patient record and return JSON only.\n\n"
        "This is part of a larger chart. Focus on extracting the most clinically meaningful events, risks, "
        "care delays, and recommendations visible in this chunk. Be concise, professional, healthcare-relevant, "
        "and avoid repetition."
    )

    response = client.responses.create(
        model="gpt-5.2",
        reasoning={"effort": "medium"},
        instructions=instructions,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            f"Record chunk {chunk_index} of {total_chunks}.\n"
                            "Return structured JSON with concise content for Timeline, Risks, Risk Level, "
                            "Risk Score, and Recommendations.\n\n"
                            f"{chunk_text}"
                        ),
                    }
                ],
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "caregap_chunk_analysis",
                "strict": True,
                "schema": ANALYSIS_SCHEMA,
            }
        },
    )

    return json.loads(response.output_text)


def analyze_structured_record(client: OpenAI, record_text: str) -> dict[str, Any]:
    response = client.responses.create(
        model="gpt-5.2",
        reasoning={"effort": "medium"},
        instructions=final_analysis_instructions(),
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Analyze this patient record for a healthcare dashboard.\n"
                            "Return structured JSON with concise content for Timeline, Risks, Risk Level, "
                            "Risk Score, and Recommendations.\n\n"
                            f"{record_text}"
                        ),
                    }
                ],
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "caregap_analysis",
                "strict": True,
                "schema": ANALYSIS_SCHEMA,
            }
        },
    )

    return json.loads(response.output_text)


def synthesize_chunk_analyses(client: OpenAI, chunk_analyses: list[dict[str, Any]]) -> dict[str, Any]:
    return analyze_structured_record(
        client,
        "Synthesize these chunk-level patient record analyses into one final healthcare dashboard output.\n\n"
        + json.dumps(chunk_analyses),
    )


def analyze_medical_record(record_text: str) -> dict[str, Any]:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Missing OPENAI_API_KEY environment variable.")

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    cleaned_text = preprocess_record_text(record_text)
    chunks = split_record_into_chunks(cleaned_text)

    if len(chunks) == 1:
        return analyze_structured_record(client, chunks[0])

    chunk_analyses = [
        analyze_chunk(client, chunk_text, index, len(chunks))
        for index, chunk_text in enumerate(chunks, start=1)
    ]
    return synthesize_chunk_analyses(client, chunk_analyses)


def load_demo_case(record_text: str) -> dict[str, Any] | None:
    if record_text.strip() == DEMO_PATIENT_RECORD:
        return HIGH_RISK_DEMO_ANALYSIS
    if record_text.strip() == LOW_RISK_DEMO_PATIENT_RECORD:
        return LOW_RISK_DEMO_ANALYSIS
    return None


def school_project_notice() -> None:
    st.warning(
        "School project demo mode: the built-in demo patients show the full CareGap AI experience without "
        "using the OpenAI API. Live analysis for pasted or uploaded records requires a funded OpenAI API key."
    )


def render_timeline(items: list[dict[str, str]]) -> None:
    if not items:
        st.info("No timeline events were returned.")
        return

    for item in items:
        st.markdown(
            f"""
            <div class="timeline-item">
                <div class="timeline-date">{item.get("date", "Unknown date")}</div>
                <div class="timeline-event">{item.get("event", "Event")}</div>
                <div class="timeline-details">{item.get("details", "")}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_list(items: list[str], empty_message: str) -> None:
    if not items:
        st.write(empty_message)
        return

    st.markdown(
        "<ul class='clean-list'>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>",
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def build_export_summary(result_json: str) -> str:
    result = json.loads(result_json)
    timeline_lines = [
        f"- {item.get('date', 'Unknown date')}: {item.get('event', 'Event')} - {item.get('details', '')}"
        for item in result.get("timeline", [])
    ]
    risk_lines = [f"- {item}" for item in result.get("risks_detected", [])]
    delay_lines = [f"- {item}" for item in result.get("missed_care_or_delays", [])]
    recommendation_lines = [f"- {item}" for item in result.get("recommended_actions", [])]

    return dedent(
        f"""
        CareGap AI Analysis

        Patient Summary:
        {result.get("patient_summary", "")}

        Risk Level:
        {result.get("risk_level", "Medium")}

        Risk Score:
        {result.get("risk_score", 50)}/100

        Timeline:
        {chr(10).join(timeline_lines) if timeline_lines else "- No timeline events returned."}

        Risks:
        {chr(10).join(risk_lines) if risk_lines else "- No risks returned."}

        Missed Care or Delays:
        {chr(10).join(delay_lines) if delay_lines else "- No delays returned."}

        Recommendations:
        {chr(10).join(recommendation_lines) if recommendation_lines else "- No recommendations returned."}
        """
    ).strip()


@st.cache_data(show_spinner=False)
def build_timeline_csv(result_json: str) -> str:
    result = json.loads(result_json)
    rows = ["date,event,details"]
    for item in result.get("timeline", []):
        date = str(item.get("date", "")).replace('"', '""')
        event = str(item.get("event", "")).replace('"', '""')
        details = str(item.get("details", "")).replace('"', '""')
        rows.append(f'"{date}","{event}","{details}"')
    return "\n".join(rows)


def initialize_state() -> None:
    if "record_text" not in st.session_state:
        st.session_state.record_text = ""
    if "analysis_result" not in st.session_state:
        st.session_state.analysis_result = None


def main() -> None:
    initialize_state()
    inject_styles()

    st.markdown(
        """
        <div class="hero">
            <h1>CareGap AI</h1>
            <p>AI-powered medical record review for timeline reconstruction, risk detection, and next-step care guidance.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="about-card">
            """
        + section_header("H", "Why CareGap AI Matters")
        + """
            <p class="muted">
                CareGap AI helps turn long, fragmented medical records into a clear, chronological view of what happened,
                where follow-up may have been missed, and which patients may need more urgent attention. In healthcare,
                delays in labs, referrals, medications, or specialist follow-up can contribute to preventable complications,
                higher costs, and poorer outcomes.
            </p>
            <p class="muted" style="margin-bottom: 0;">
                By surfacing likely care gaps quickly, this tool can support care management teams, quality improvement work,
                utilization review, and clinical operations that need faster chart review and better prioritization.
            </p>
            <div class="use-case-grid">
                <div class="use-case-item">
                    <div class="use-case-title">Care Management</div>
                    <div class="use-case-copy">Highlight missed follow-ups, overdue labs, and patients who may need outreach.</div>
                </div>
                <div class="use-case-item">
                    <div class="use-case-title">Discharge Review</div>
                    <div class="use-case-copy">Track whether recommended post-discharge visits, medications, and specialty referrals happened.</div>
                </div>
                <div class="use-case-item">
                    <div class="use-case-title">Risk Stratification</div>
                    <div class="use-case-copy">Support prioritization by combining chart events, care delays, and severity into a clear risk view.</div>
                </div>
                <div class="use-case-item">
                    <div class="use-case-title">Quality Improvement</div>
                    <div class="use-case-copy">Surface recurring documentation and follow-up patterns that may point to workflow gaps.</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div class='toolbar-card'>", unsafe_allow_html=True)
    demo_col_1, demo_col_2 = st.columns(2)
    with demo_col_1:
        if st.button("Try High-Risk Demo", use_container_width=True):
            st.session_state.record_text = DEMO_PATIENT_RECORD
            st.session_state.analysis_result = HIGH_RISK_DEMO_ANALYSIS
    with demo_col_2:
        if st.button("Try Lower-Risk Demo", use_container_width=True):
            st.session_state.record_text = LOW_RISK_DEMO_PATIENT_RECORD
            st.session_state.analysis_result = LOW_RISK_DEMO_ANALYSIS
    st.caption("Demo patients use built-in sample analysis and do not consume OpenAI API quota.")
    school_project_notice()

    uploaded_file = st.file_uploader(
        "Upload patient medical record",
        type=["pdf", "txt"],
        help="Upload a PDF or plain text medical record.",
    )

    pasted_text = st.text_area(
        "Or paste patient medical record text",
        value=st.session_state.record_text,
        height=240,
        placeholder="Paste clinical notes, discharge summaries, referral records, or other patient history here...",
    )
    st.session_state.record_text = pasted_text

    analyze_clicked = st.button("Analyze Record", type="primary", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)
    st.info(
        "CareGap AI is an AI-assisted review tool for care-gap screening and workflow support. "
        "It does not replace clinician judgment or provide medical advice."
    )

    if analyze_clicked:
        uploaded_text = load_uploaded_text(uploaded_file)
        combined_text = "\n\n".join(part.strip() for part in [uploaded_text, pasted_text] if part and part.strip())

        if not combined_text:
            st.error("Please paste a medical record or upload a PDF/text file before running the analysis.")
        else:
            try:
                with st.spinner("Analyzing medical record with OpenAI..."):
                    demo_result = load_demo_case(combined_text)
                    st.session_state.analysis_result = demo_result or analyze_medical_record(combined_text)
                st.success("Analysis completed successfully.")
            except RateLimitError:
                st.session_state.analysis_result = None
                st.error(
                    "Live record analysis is unavailable in this deployment because the OpenAI API key does "
                    "not currently have available quota. For your school presentation, use the demo patients "
                    "above to show the full experience."
                )
            except Exception as exc:
                st.session_state.analysis_result = None
                st.error(f"Unable to complete the analysis: {exc}")

    result = st.session_state.analysis_result
    if not result:
        st.markdown(
            """
            <div class="section-card">
                """
            + section_header("i", "How It Works")
            + """
                <p class="muted">
                    Upload or paste a patient record, then run the analysis to generate a structured timeline,
                    identify potential care gaps, assign a risk level, and surface practical follow-up actions.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<div class='footer'><strong>CareGap AI</strong> | Intelligent care gap review dashboard</div>", unsafe_allow_html=True)
        return

    risk_items = result.get("risks_detected", [])
    delay_items = result.get("missed_care_or_delays", [])
    recommendation_items = result.get("recommended_actions", [])
    timeline_items = result.get("timeline", [])
    normalized_score = int(result.get("risk_score", 50))
    normalized_level = risk_level_from_score(normalized_score)

    kpi_col_1, kpi_col_2, kpi_col_3 = st.columns(3, gap="large")
    with kpi_col_1:
        render_kpi_card("Risk Level", normalized_level, "Overall patient review severity")
    with kpi_col_2:
        render_kpi_card("Risk Score", str(normalized_score), "Severity score from 1 to 100")
    with kpi_col_3:
        render_kpi_card("Action Items", str(len(recommendation_items)), "Recommended next steps surfaced by AI")

    export_col_1, export_col_2 = st.columns(2)
    export_payload = json.dumps(result, sort_keys=True)
    with export_col_1:
        st.download_button(
            "Download Summary (.txt)",
            data=build_export_summary(export_payload),
            file_name="caregap_ai_summary.txt",
            mime="text/plain",
            use_container_width=True,
        )
    with export_col_2:
        st.download_button(
            "Download Timeline (.csv)",
            data=build_timeline_csv(export_payload),
            file_name="caregap_ai_timeline.csv",
            mime="text/csv",
            use_container_width=True,
        )

    left_col, right_col = st.columns(2, gap="large")

    with left_col:
        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.markdown(section_header("T", "Timeline"), unsafe_allow_html=True)
        render_timeline(timeline_items)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.markdown(section_header("A", "Recommendations"), unsafe_allow_html=True)
        render_list(
            recommendation_items,
            "No recommendations were generated.",
        )
        st.markdown("</div>", unsafe_allow_html=True)

    with right_col:
        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.markdown(section_header("R", "Risk Level"), unsafe_allow_html=True)
        risk_score = normalized_score
        risk_level = normalized_level
        st.markdown(get_risk_badge(risk_level), unsafe_allow_html=True)
        st.markdown("<div class='risk-score-label'>Numerical Risk Score</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='risk-score'>{risk_score}/100</div>", unsafe_allow_html=True)
        st.markdown(risk_meter(risk_score), unsafe_allow_html=True)
        summary = result.get("patient_summary", "")
        if summary:
            st.markdown(f"<p class='muted' style='margin-top: 0.85rem;'>{summary}</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.markdown(section_header("!", "Risks"), unsafe_allow_html=True)
        render_list(
            risk_items + delay_items,
            "No specific risks or care gaps were identified.",
        )
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='footer'><strong>CareGap AI</strong> | Intelligent care gap review dashboard</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
