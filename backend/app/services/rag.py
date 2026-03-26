from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

try:
    import chromadb  # type: ignore
except Exception:  # pragma: no cover
    chromadb = None

from ..config import settings


ROOT_DIR = Path(__file__).resolve().parents[3]
PROMPTS_FILE = ROOT_DIR / "data" / "bot_prompts.json"
DEPARTMENT_FILES = {
    "sales": ROOT_DIR / "data" / "faq_sales.txt",
    "hr": ROOT_DIR / "data" / "faq_hr.txt",
    "service": ROOT_DIR / "data" / "faq_service.txt",
}
DEPARTMENT_LABELS = {
    "sales": "Продажи",
    "hr": "HR",
    "service": "Сервис",
}
DEPARTMENT_KEYWORDS = {
    "sales": [
        "кредит",
        "лизинг",
        "трейд",
        "тест-драйв",
        "купить",
        "комплектация",
        "цена",
        "скидка",
        "rav4",
        "camry",
    ],
    "hr": [
        "ваканс",
        "работ",
        "собесед",
        "резюме",
        "зарплат",
        "рекрут",
        "график",
        "обуч",
        "стажиров",
        "документ",
        "оформлен",
        "трудов",
        "снилс",
        "инн",
    ],
    "service": [
        "то",
        "сервис",
        "ремонт",
        "гарантия",
        "запчаст",
        "диагност",
        "кузов",
        "дтп",
        "чек",
        "vin",
    ],
}


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _tokenize(text: str) -> list[str]:
    return [t.strip(".,:;!?()[]{}\"'").lower() for t in text.split() if t.strip()]


def _hash_embedding(text: str, dim: int = 256) -> list[float]:
    vec = [0.0] * dim
    tokens = _tokenize(text)
    if not tokens:
        return vec

    for tok in tokens:
        h = hashlib.sha256(tok.encode("utf-8")).digest()
        idx = int.from_bytes(h[:4], "big") % dim
        sign = 1.0 if (h[4] % 2 == 0) else -1.0
        weight = 1.0 + (h[5] / 255.0) * 0.2
        vec[idx] += sign * weight

    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class FaqRagService:
    def __init__(self) -> None:
        self.prompts = _load_json(PROMPTS_FILE)
        self._docs_by_department = self._build_department_docs()
        self._use_chroma = chromadb is not None
        self.collections: dict[str, Any] = {}

        if self._use_chroma:
            chroma_abs = ROOT_DIR / settings.chroma_path
            chroma_abs.mkdir(parents=True, exist_ok=True)
            self.client = chromadb.PersistentClient(path=str(chroma_abs))
            self._ensure_seeded()

    def _parse_txt_chunks(self, path: Path, department: str) -> list[dict[str, str]]:
        text = path.read_text(encoding="utf-8")
        blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
        docs: list[dict[str, str]] = []
        idx = 1
        for block in blocks:
            if block.startswith("АССИСТЕНТ:") or block.startswith("ОТДЕЛ:"):
                continue
            # Keep only FAQ Q/A chunks for retrieval.
            # Trigger scripts are excluded to avoid procedural leakage into user answers.
            if "Вопрос:" in block:
                docs.append(
                    {
                        "id": f"{department}_{idx}",
                        "document": block,
                        "section": department,
                    }
                )
                idx += 1
        return docs

    def _build_department_docs(self) -> dict[str, list[dict[str, str]]]:
        docs: dict[str, list[dict[str, str]]] = {}
        for department, file_path in DEPARTMENT_FILES.items():
            if file_path.exists():
                docs[department] = self._parse_txt_chunks(file_path, department)
            else:
                docs[department] = []
        return docs

    def detect_department(self, query: str, preferred_department: str | None = None) -> str:
        if preferred_department in DEPARTMENT_FILES:
            return str(preferred_department)
        text = query.lower()
        scores = {"sales": 0, "hr": 0, "service": 0}
        for department, keywords in DEPARTMENT_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    scores[department] += 1
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "sales"

    def _collection_name(self, department: str) -> str:
        return f"{settings.chroma_collection_name}_{department}"

    def _rebuild_department_collection(self, department: str) -> None:
        name = self._collection_name(department)
        docs = self._docs_by_department.get(department, [])
        try:
            self.client.delete_collection(name=name)
        except Exception:
            # Collection may not exist yet; safe to ignore.
            pass

        collection = self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )
        self.collections[department] = collection

        if docs:
            collection.add(
                ids=[d["id"] for d in docs],
                documents=[d["document"] for d in docs],
                embeddings=[_hash_embedding(d["document"]) for d in docs],
                metadatas=[{"section": d["section"]} for d in docs],
            )

    def _ensure_seeded(self) -> None:
        for department, docs in self._docs_by_department.items():
            collection = self.client.get_or_create_collection(
                name=self._collection_name(department),
                metadata={"hnsw:space": "cosine"},
            )
            self.collections[department] = collection

            if collection.count() > 0:
                continue
            if not docs:
                continue
            collection.add(
                ids=[d["id"] for d in docs],
                documents=[d["document"] for d in docs],
                embeddings=[_hash_embedding(d["document"]) for d in docs],
                metadatas=[{"section": d["section"]} for d in docs],
            )

    def retrieve(self, query: str, department: str, top_k: int = 5) -> list[str]:
        if not self._use_chroma:
            return self._fallback_retrieve(query, department, top_k)
        collection = self.collections.get(department)
        if collection is None:
            return self._fallback_retrieve(query, department, top_k)

        query_vector = _hash_embedding(query)
        try:
            res = collection.query(query_embeddings=[query_vector], n_results=top_k)
            docs = res.get("documents", [[]])[0]
            return [d for d in docs if isinstance(d, str)]
        except Exception:
            # Recover from corrupted/incomplete on-disk HNSW state.
            try:
                self._rebuild_department_collection(department)
                repaired = self.collections.get(department)
                if repaired is not None:
                    res = repaired.query(query_embeddings=[query_vector], n_results=top_k)
                    docs = res.get("documents", [[]])[0]
                    return [d for d in docs if isinstance(d, str)]
            except Exception:
                pass
            return self._fallback_retrieve(query, department, top_k)

    def _fallback_retrieve(self, query: str, department: str, top_k: int) -> list[str]:
        q_tokens = set(_tokenize(query))
        scored: list[tuple[float, str]] = []
        for item in self._docs_by_department.get(department, []):
            doc = item["document"]
            d_tokens = set(_tokenize(doc))
            overlap = len(q_tokens.intersection(d_tokens))
            score = overlap / (len(q_tokens) + 1)
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:top_k]]

    def build_system_prompt(self, query: str, preferred_department: str | None = None) -> str:
        department = self.detect_department(query, preferred_department=preferred_department)
        context_chunks = self.retrieve(query=query, department=department, top_k=5)
        context = "\n\n---\n\n".join(context_chunks) if context_chunks else "Контекст не найден."

        role = self.prompts.get("system_role", "")
        style = "\n".join(f"- {x}" for x in self.prompts.get("style_rules", []))
        hard = "\n".join(f"- {x}" for x in self.prompts.get("hard_rules", []))
        goals = "\n".join(f"- {x}" for x in self.prompts.get("sales_objectives", []))
        shape = "\n".join(f"- {x}" for x in self.prompts.get("response_shape", []))
        fallback = self.prompts.get("fallback_message", "")

        return (
            f"{role}\n\n"
            "Стиль ответа:\n"
            f"{style}\n\n"
            "Жесткие ограничения:\n"
            f"{hard}\n\n"
            "Цели диалога:\n"
            f"{goals}\n\n"
            "Формат ответа:\n"
            f"{shape}\n\n"
            f"Если информации не хватает: {fallback}\n\n"
            f"Режим работы дилера: {settings.dealer_working_hours}.\n"
            f"SLA менеджера: до {settings.manager_response_sla_minutes} минут.\n\n"
            f"Текущий отдел по запросу: {DEPARTMENT_LABELS.get(department, 'Продажи')}.\n"
            "Релевантный FAQ-контекст (RAG):\n"
            f"{context}"
        )
