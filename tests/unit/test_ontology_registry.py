from __future__ import annotations

import copy
import unittest

from pydantic import ValidationError

from src.storage.ontology.models import (
    REQUIRED_NODE_LABELS,
    REQUIRED_RELATIONSHIP_TYPES,
    OntologyRegistryDocument,
    is_legal_node_label,
    is_legal_relationship_type,
)
from src.storage.ontology.registry import load_ontology_registry


class TestOntologyRegistryContract(unittest.TestCase):
    def test_default_yaml_loads_required_nodes_and_relationships(self):
        registry = load_ontology_registry()

        self.assertEqual(registry.contract_version, "ontology-registry-v1")
        for label in REQUIRED_NODE_LABELS:
            self.assertTrue(registry.has_node(label), f"missing node: {label}")
        for rel_type in REQUIRED_RELATIONSHIP_TYPES:
            self.assertTrue(
                registry.has_relationship(rel_type),
                f"missing relationship: {rel_type}",
            )
        self.assertIn("claim_id", registry.traceability_fields())
        self.assertIn("witness_key", registry.traceability_fields())
        self.assertIn("source_ref", registry.traceability_fields())

    def test_node_and_relationship_names_are_legal(self):
        registry = load_ontology_registry()

        for label in registry.node_labels():
            self.assertTrue(is_legal_node_label(label), label)
            self.assertTrue(registry.validate_node_label(label), label)
        for rel_type in registry.relationship_types():
            self.assertTrue(is_legal_relationship_type(rel_type), rel_type)
            self.assertTrue(registry.validate_relationship_type(rel_type), rel_type)

        self.assertFalse(is_legal_node_label("Bad Label"))
        self.assertFalse(is_legal_relationship_type("treats"))

    def test_required_property_validation_reports_specific_field(self):
        registry = load_ontology_registry()
        payload = copy.deepcopy(registry.to_dict())
        payload["nodes"]["Herb"]["properties"].pop("name")

        with self.assertRaises(ValidationError) as ctx:
            OntologyRegistryDocument.model_validate(payload)

        message = str(ctx.exception)
        self.assertIn("Herb", message)
        self.assertIn("name", message)
        self.assertIn("required_properties", message)

    def test_relationship_endpoint_validation_reports_unknown_label(self):
        registry = load_ontology_registry()
        payload = copy.deepcopy(registry.to_dict())
        payload["relationships"]["TREATS"]["target_labels"] = ["UnknownNode"]

        with self.assertRaises(ValidationError) as ctx:
            OntologyRegistryDocument.model_validate(payload)

        message = str(ctx.exception)
        self.assertIn("TREATS", message)
        self.assertIn("UnknownNode", message)


if __name__ == "__main__":
    unittest.main()
