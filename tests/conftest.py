import pytest
from pathlib import Path
from scholarx.paper_storage import PaperStorage
from scholarx.models import Paper, PaperSource


def pytest_configure(config):
    """Register custom markers to prevent warnings."""
    config.addinivalue_line("markers", "concept(id): mark test with its associated concept ID")


@pytest.fixture
def temp_storage(tmp_path):
    """Fixture providing a transient PaperStorage instance."""
    return PaperStorage(tmp_path)


@pytest.fixture
def sample_arxiv_paper():
    """Fixture providing a sample arXiv Paper instance."""
    return Paper(
        id="arxiv:12345",
        title="Attention Is All You Need",
        authors=["Ashish Vaswani", "Noam Shazeer"],
        source=PaperSource.ARXIV,
        pdf_url="https://arxiv.org/pdf/1706.03762.pdf",
    )
