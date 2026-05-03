"""Tests for backend.documents: JSON -> LangChain Document conversion."""

from __future__ import annotations

from backend.documents import load_all_documents


def test_load_all_documents_count(tmp_data_dir):
    docs = load_all_documents(data_dir=tmp_data_dir)
    # 2 stores + 1 vendor + 1 employee + 1 department + 2 brands = 7
    assert len(docs) == 7


def test_load_all_documents_types(tmp_data_dir):
    docs  = load_all_documents(data_dir=tmp_data_dir)
    types = sorted({d.metadata["type"] for d in docs})
    assert types == ["brand", "department", "employee", "store", "vendor"]


def test_store_document_contents(tmp_data_dir):
    docs   = load_all_documents(data_dir=tmp_data_dir)
    stores = [d for d in docs if d.metadata["type"] == "store"]

    assert len(stores) == 2
    gc = next(d for d in stores if d.metadata["store_id"] == "GOLDEN_CRISP-0001")

    text = gc.page_content
    assert "Golden Crisp"        in text
    assert "Fried Chicken"       in text
    assert "Grace Hopper"        in text       # store manager
    assert "Alan Turing"         in text       # district manager
    assert "Edsger Dijkstra"     in text       # VP
    assert "Dallas"              in text


def test_store_metadata(tmp_data_dir):
    docs = load_all_documents(data_dir=tmp_data_dir)
    gc   = next(d for d in docs
                if d.metadata.get("store_id") == "GOLDEN_CRISP-0001")
    assert gc.metadata["brand_id"] == "golden_crisp"
    assert gc.metadata["state"]    == "TX"
    assert gc.metadata["city"]     == "Dallas"


def test_vendor_document_includes_credentials(tmp_data_dir):
    docs    = load_all_documents(data_dir=tmp_data_dir)
    vendors = [d for d in docs if d.metadata["type"] == "vendor"]

    assert len(vendors) == 1
    text = vendors[0].page_content
    assert "AT&T Business"     in text
    assert "tostado.gc-0001"   in text         # username
    assert "vendorPass!"       in text         # password


def test_department_document(tmp_data_dir):
    docs = load_all_documents(data_dir=tmp_data_dir)
    dept = next(d for d in docs if d.metadata["type"] == "department")
    assert dept.metadata["department"] == "IT"
    assert "Charles Babbage" in dept.page_content     # head
    assert "Ada Lovelace"    in dept.page_content     # admin
