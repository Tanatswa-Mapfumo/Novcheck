from novelty_harness.evidence.provenance.independence import (
    independent_root_map,
    independent_roots_for_sources,
)
from novelty_harness.evidence.provenance.models import EvidenceLineageCluster


def test_nonroot_member_of_multiroot_cluster_is_ambiguous_and_limited() -> None:
    cluster = EvidenceLineageCluster(
        cluster_id="lin_multi_root",
        source_ids=("src_root_a", "src_root_b", "src_joined"),
        root_source_ids=("src_root_a", "src_root_b"),
        independent_roots=2,
        rationale=("Two independent origins remain in the cluster.",),
    )

    roots, limitations = independent_roots_for_sources(("src_joined",), (cluster,))

    assert roots == ()
    assert len(limitations) == 1
    assert "unambiguous" in limitations[0]


def test_multiroot_cluster_root_maps_only_to_itself() -> None:
    cluster = EvidenceLineageCluster(
        cluster_id="lin_multi_root",
        source_ids=("src_root_a", "src_root_b", "src_joined"),
        root_source_ids=("src_root_a", "src_root_b"),
        independent_roots=2,
        rationale=("Two independent origins remain in the cluster.",),
    )

    roots, limitations = independent_roots_for_sources(("src_root_b",), (cluster,))

    assert roots == ("src_root_b",)
    assert limitations == ()
    assert independent_root_map((cluster,))["src_root_b"] == "src_root_b"
