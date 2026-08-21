// Neo4j schema for the dual digital twin.
//
// The graph plane answers traversal questions -- blast radius, delivery
// obligations, traceability. It is a projection of the metadata plane and can
// be dropped and rebuilt, so nothing here is the only copy of anything.
//
// Node identity is (entity_type, entity_id). Deliberately NOT versioned: a node
// is the thing itself, while versioned state lives in PostgreSQL.
//
// Apply with:  cat constraints.cypher | cypher-shell -u neo4j -p <password>

// --- Identity ---------------------------------------------------------------

CREATE CONSTRAINT entity_identity IF NOT EXISTS
FOR (n:Entity) REQUIRE (n.entity_type, n.entity_id) IS UNIQUE;

CREATE CONSTRAINT entity_type_exists IF NOT EXISTS
FOR (n:Entity) REQUIRE n.entity_type IS NOT NULL;

CREATE CONSTRAINT entity_id_exists IF NOT EXISTS
FOR (n:Entity) REQUIRE n.entity_id IS NOT NULL;

// --- Provenance on edges ----------------------------------------------------
// Every edge must say how it came to be believed. Without this an inferred
// DESCRIBES edge is indistinguishable from an observed one, and the platform
// would tell someone to update a document that was never about their code.

CREATE CONSTRAINT rel_provenance_exists IF NOT EXISTS
FOR ()-[r:RELATES]-() REQUIRE r.provenance IS NOT NULL;

CREATE CONSTRAINT rel_type_exists IF NOT EXISTS
FOR ()-[r:RELATES]-() REQUIRE r.rel_type IS NOT NULL;

CREATE CONSTRAINT rel_discovered_at_exists IF NOT EXISTS
FOR ()-[r:RELATES]-() REQUIRE r.discovered_at IS NOT NULL;

// --- Traversal indexes ------------------------------------------------------

CREATE INDEX entity_type_index IF NOT EXISTS
FOR (n:Entity) ON (n.entity_type);

// The twin an entity belongs to. Lets a query scope to the delivery model or
// the technical system without enumerating entity types.
CREATE INDEX entity_twin_index IF NOT EXISTS
FOR (n:Entity) ON (n.twin);

CREATE INDEX rel_type_index IF NOT EXISTS
FOR ()-[r:RELATES]-() ON (r.rel_type);

CREATE INDEX rel_confidence_index IF NOT EXISTS
FOR ()-[r:RELATES]-() ON (r.confidence);

// Cross-twin edges are queried as a set when answering "what does this change
// mean for the process?", so the dimension is indexed in its own right.
CREATE INDEX rel_dimension_index IF NOT EXISTS
FOR ()-[r:RELATES]-() ON (r.dimension);
