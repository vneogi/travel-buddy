from services.embedding_service import EmbeddingService


def test_synthetic_deterministic_and_normalized():
    svc = EmbeddingService(use_synthetic=True)
    a, b = svc.generate_embedding("hello world"), svc.generate_embedding("hello world")
    assert a == b
    assert len(a) == svc.dimensions
    assert abs(sum(x * x for x in a) ** 0.5 - 1.0) < 1e-6


def test_cosine_self_similarity():
    svc = EmbeddingService(use_synthetic=True)
    a = svc.generate_embedding("cafe")
    assert abs(svc.cosine_similarity(a, a) - 1.0) < 1e-6
