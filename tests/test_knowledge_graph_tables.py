import csv
from pathlib import Path

import pytest

from harnessing_ts.knowledge_graph import (
    add_evidence,
    add_knowledge,
    extract_reference_text,
    finalize_knowledge_base,
    read_graph_view,
    scan_references,
    search_knowledge_notes,
    upsert_class,
    upsert_relation,
    validate_knowledge_base,
)


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_csv_knowledge_base_validates_and_builds_graph_view(tmp_path):
    kb = tmp_path / "knowledge_base"
    kb.mkdir()
    (kb / "domain-brief.md").write_text("# Domain Brief\n", encoding="utf-8")
    tables = kb / "tables"
    write_csv(tables / "references.csv", ["reference_id", "path", "sha256", "title", "brief", "status", "updated_at"], [])
    write_csv(tables / "evidence.csv", ["evidence_id", "reference_file", "page", "section", "quoted_fragments", "notes"], [{
        "evidence_id": "E-00001",
        "reference_file": "paper.pdf",
        "page": "3",
        "section": "Diagnostic criteria",
        "quoted_fragments": '["A wide QRS complex supports bundle branch block."]',
        "notes": "",
    }])
    (tmp_path / "references").mkdir()
    (tmp_path / "references" / "paper.pdf").write_bytes(b"%PDF-1.4\n")
    write_csv(tables / "knowledge.csv", ["knowledge_id", "topic", "description", "summary", "evidence_ids", "class_ids", "relation_ids", "status", "notes"], [{
        "knowledge_id": "K-00001",
        "topic": "Wide QRS",
        "description": "A wide QRS complex is task-relevant evidence for conduction abnormality patterns.",
        "summary": "Wide QRS supports conduction abnormality checks.",
        "evidence_ids": '["E-00001"]',
        "class_ids": '["C-00001","C-00002"]',
        "relation_ids": '["R-00001"]',
        "status": "graph_done",
        "notes": "",
    }])
    write_csv(tables / "classes.csv", ["class_id", "label", "normalized_label", "description", "source_knowledge_ids", "evidence_ids", "aliases"], [
        {
            "class_id": "C-00001",
            "label": "QRS-COMPLEX",
            "normalized_label": "QRS-COMPLEX",
            "description": "ECG waveform component representing ventricular depolarization.",
            "source_knowledge_ids": '["K-00001"]',
            "evidence_ids": '[]',
            "aliases": '["QRS"]',
        },
        {
            "class_id": "C-00002",
            "label": "BUNDLE-BRANCH-BLOCK",
            "normalized_label": "BUNDLE-BRANCH-BLOCK",
            "description": "Conduction abnormality pattern associated with widened QRS.",
            "source_knowledge_ids": '["K-00001"]',
            "evidence_ids": '["E-00001"]',
            "aliases": '["BBB"]',
        },
    ])
    write_csv(tables / "relations.csv", ["relation_id", "source_class_id", "relation_type", "target_class_id", "description", "source_knowledge_ids", "evidence_ids"], [{
        "relation_id": "R-00001",
        "source_class_id": "C-00001",
        "relation_type": "supports",
        "target_class_id": "C-00002",
        "description": "Widened QRS supports bundle branch block pattern checks.",
        "source_knowledge_ids": '["K-00001"]',
        "evidence_ids": '["E-00001"]',
    }])

    manifest = validate_knowledge_base(tmp_path)
    graph = read_graph_view(tmp_path)
    results = search_knowledge_notes(tmp_path, "QRS conduction", top_k=3)

    assert manifest["ok"] is True
    manifest = finalize_knowledge_base(tmp_path)
    assert manifest["schemaVersion"] == 4
    assert manifest["knowledgeCount"] == 1
    assert manifest["classCount"] == 2
    assert manifest["relationCount"] == 1
    assert graph["nodes"][0]["type"] == "class"
    assert graph["nodes"][0]["evidence"][0]["evidenceId"] == "E-00001"
    assert graph["nodes"][0]["evidence"][0]["sourcePath"] == "references/paper.pdf"
    assert graph["nodes"][0]["evidence"][0]["previewUrl"] == "/api/references/preview?path=references/paper.pdf"
    assert graph["edges"][0]["sourceLabel"] == "QRS-COMPLEX"
    assert graph["edges"][0]["targetLabel"] == "BUNDLE-BRANCH-BLOCK"
    assert graph["edges"][0]["evidence"][0]["evidenceId"] == "E-00001"
    assert results[0]["note_id"] == "K-00001"


def test_deterministic_tools_add_and_upsert_knowledge_base(tmp_path):
    kb = tmp_path / "knowledge_base"
    kb.mkdir(parents=True)
    (kb / "domain-brief.md").write_text("# Domain Brief\n", encoding="utf-8")
    (tmp_path / "references").mkdir()
    (tmp_path / "references" / "paper.pdf").write_bytes(b"%PDF-1.4\n")

    refs = scan_references(tmp_path)
    assert refs["counts"]["newOrChanged"] == 1

    evidence = add_evidence(tmp_path, {
        "reference_file": "paper.pdf",
        "page": "3",
        "section": "Diagnostic criteria",
        "quoted_fragments": ["A wide QRS complex supports bundle branch block."],
    })
    knowledge = add_knowledge(tmp_path, {
        "topic": "Wide QRS",
        "description": "A wide QRS complex is task-relevant evidence for conduction abnormality patterns.",
        "summary": "Wide QRS supports conduction abnormality checks.",
        "evidence_ids": [evidence["evidence_id"]],
    })
    qrs = upsert_class(tmp_path, {
        "label": "QRS complex",
        "description_addition": "ECG waveform component representing ventricular depolarization.",
        "aliases": ["QRS"],
        "source_knowledge_ids": [knowledge["knowledge_id"]],
    })
    bbb = upsert_class(tmp_path, {
        "label": "Bundle Branch Block",
        "description_addition": "Conduction abnormality pattern associated with widened QRS.",
        "source_knowledge_ids": [knowledge["knowledge_id"]],
    })
    relation = upsert_relation(tmp_path, {
        "source_class_id": qrs["class_id"],
        "relation_type": "indicates",
        "target_class_id": bbb["class_id"],
        "description_addition": "Wide QRS supports bundle branch block checks.",
        "source_knowledge_ids": [knowledge["knowledge_id"]],
    })

    manifest = finalize_knowledge_base(tmp_path)
    graph = read_graph_view(tmp_path)

    assert manifest["knowledgeCount"] == 1
    assert qrs["class_id"] == "C-00001"
    assert relation["relation_id"] == "R-00001"
    assert graph["nodes"][0]["evidence"][0]["evidenceId"] == "E-00001"


def test_extract_reference_text_uses_pdftotext_for_pdf(tmp_path):
    kb = tmp_path / "knowledge_base"
    kb.mkdir(parents=True)
    (kb / "domain-brief.md").write_text("# Domain Brief\n", encoding="utf-8")
    pdf = tmp_path / "references" / "paper.pdf"
    pdf.parent.mkdir()
    source_pdf = Path("/Users/niuyiming/harnessts/ecg/references/ECG5000_literature_review_cn.pdf")
    if not source_pdf.exists():
        pytest.skip("workspace smoke PDF is not available")
    pdf.write_bytes(source_pdf.read_bytes())

    refs = scan_references(tmp_path)
    reference_id = refs["new_or_changed"][0]["reference_id"]
    extracted = extract_reference_text(tmp_path, {
        "reference_id": reference_id,
        "pages": "1",
        "max_chars_per_page": 800,
    })

    assert extracted["ok"] is True
    assert extracted["method"] == "pdftotext"
    assert extracted["pages"][0]["page"] == 1
    assert "ECG5000" in extracted["pages"][0]["text"]
    assert (tmp_path / extracted["cache_path"]).exists()


def test_csv_knowledge_base_rejects_unescaped_list_columns(tmp_path):
    kb = tmp_path / "knowledge_base"
    kb.mkdir()
    (kb / "domain-brief.md").write_text("# Domain Brief\n", encoding="utf-8")
    tables = kb / "tables"
    write_csv(tables / "references.csv", ["reference_id", "path", "sha256", "title", "brief", "status", "updated_at"], [])
    write_csv(tables / "evidence.csv", ["evidence_id", "reference_file", "page", "section", "quoted_fragments", "notes"], [{
        "evidence_id": "E-00001",
        "reference_file": "references/paper.pdf",
        "page": "3",
        "section": "Diagnostic criteria",
        "quoted_fragments": '["A wide QRS complex supports bundle branch block."]',
        "notes": "",
    }])
    (tables / "knowledge.csv").write_text(
        "knowledge_id,topic,description,summary,evidence_ids,class_ids,relation_ids,status,notes\n"
        "K-00001,Wide QRS,Description,Summary,E-00001,E-00002,C-00001,R-00001,pending_graph,notes\n",
        encoding="utf-8",
    )
    write_csv(tables / "classes.csv", ["class_id", "label", "normalized_label", "description", "source_knowledge_ids", "evidence_ids", "aliases"], [{
        "class_id": "C-00001",
        "label": "QRS-COMPLEX",
        "normalized_label": "QRS-COMPLEX",
        "description": "ECG waveform component.",
        "source_knowledge_ids": '["K-00001"]',
        "evidence_ids": '["E-00001"]',
        "aliases": '["QRS"]',
    }])
    write_csv(tables / "relations.csv", ["relation_id", "source_class_id", "relation_type", "target_class_id", "description", "source_knowledge_ids", "evidence_ids"], [{
        "relation_id": "R-00001",
        "source_class_id": "C-00001",
        "relation_type": "related_to",
        "target_class_id": "C-00001",
        "description": "Self relation for shape validation.",
        "source_knowledge_ids": '["K-00001"]',
        "evidence_ids": '["E-00001"]',
    }])

    with pytest.raises(RuntimeError, match="Knowledge CSV formatting failed"):
        validate_knowledge_base(tmp_path)
